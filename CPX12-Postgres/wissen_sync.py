#!/usr/bin/env python3
"""
wissen_sync.py – Abgleich des Obsidian-Vaults DK-Wissen (Nextcloud) mit der
Volltextsuche im CRM (Migration 005, 2026-10-19)
==========================================================================

Laeuft stuendlich als systemd-Timer (crm-wissen.timer) und auf Knopfdruck aus
dem CRM ("Jetzt abgleichen"). Ablauf:

  1. Per WebDAV die Ordner aus der Konfiguration durchgehen (Standard:
     Fachwissen und Vorlagen).
  2. Neue oder geaenderte Dateien (ETag) herunterladen und Text gewinnen:
     Markdown/Text direkt, Word aus dem docx-Archiv, PDF per pdftotext,
     gescannte PDFs und Bilder per Texterkennung (tesseract, deutsch+englisch).
  3. Text in wissen_dokumente speichern. Die Datei selbst bleibt in Nextcloud.
  4. In Nextcloud geloeschte Dateien aus der Suche nehmen.
  5. Namenspruefung: Kommen Firmen- oder Personennamen aus dem CRM im Text vor,
     wird das Dokument markiert (Warnung, keine Sperre).
  6. Kundenwissen (Migration 012): in den Kundenordnern je Firma die
     Unterordner ACOS/ und Besprechungen/ in die Tabelle kundenwissen.
     Getrennt von der Recherche, nur in der Akte der Firma durchsuchbar.

Zugangsdaten: secrets/wissen.env (chmod 600), nie im Repository:
    WEBDAV_URL=https://.../remote.php/dav/files/wissen-sync/DK-Wissen/
    WEBDAV_USER=wissen-sync
    WEBDAV_PASSWORD=<App-Passwort>
    NEXTCLOUD_WEB=https://.../apps/files/files?dir=/DK-Wissen   (optional, fuer Links)

Aufruf von Hand (auf dem Server):
    sudo -u crmapp python3 /opt/crm/wissen_sync.py
"""

import base64
import fcntl
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crm_core as core  # noqa: E402

SECRETS_FILE = core.BASE_DIR / "secrets" / "wissen.env"
LOCK_FILE = core.BASE_DIR / "secrets" / "wissen_sync.lock"

STANDARD = {
    "ordner": ["Fachwissen", "Vorlagen"],
    "max_mb": 25,              # groessere Dateien nur mit Namen, ohne Inhalt
    "max_dateien_je_lauf": 200,
    "max_ocr_je_lauf": 40,     # Texterkennung ist auf dem kleinen Server teuer
    "max_ocr_seiten": 30,
    "namen_ignorieren": ["Intern", "Privat", "Diverse", "Sonstige", "Test"],
}
MAX_ZEICHEN = 200_000          # tsvector-Grenze von Postgres (1 MB) sicher einhalten

TEXT_ENDUNGEN = {".md", ".txt", ".csv", ".markdown"}
BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".bmp"}
UEBERSPRINGEN = {".obsidian", ".trash", ".git"}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%dT%H:%M:%S}] {msg}", flush=True)


def lade_konfig():
    cfg = dict(STANDARD)
    cfg.update((core.load_config().get("wissen") or {}))
    return cfg


def lade_zugang():
    if not SECRETS_FILE.exists():
        return {}
    werte = {}
    for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        werte[k.strip()] = v.strip()
    return werte


# ── WebDAV ───────────────────────────────────────────────────────────────────

class Dav:
    def __init__(self, url, user, passwort):
        self.basis = url.rstrip("/") + "/"
        self.basis_pfad = urllib.parse.unquote(urllib.parse.urlparse(self.basis).path)
        token = base64.b64encode(f"{user}:{passwort}".encode("utf-8")).decode("ascii")
        self.auth = f"Basic {token}"

    def _url(self, rel):
        teile = [urllib.parse.quote(t) for t in rel.strip("/").split("/") if t]
        return self.basis + "/".join(teile) + ("/" if rel.endswith("/") and teile else "")

    def _req(self, methode, rel, headers=None, daten=None, timeout=60):
        h = {"Authorization": self.auth}
        h.update(headers or {})
        req = urllib.request.Request(self._url(rel), data=daten, method=methode, headers=h)
        return urllib.request.urlopen(req, timeout=timeout)

    def liste(self, rel):
        body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                b'<d:resourcetype/><d:getetag/><d:getcontentlength/><d:getlastmodified/>'
                b'</d:prop></d:propfind>')
        with self._req("PROPFIND", rel.rstrip("/") + "/", {"Depth": "1", "Content-Type": "application/xml"}, body) as r:
            xml = r.read()
        ns = {"d": "DAV:"}
        eintraege = []
        for resp in ET.fromstring(xml).findall("d:response", ns):
            href = urllib.parse.unquote(resp.findtext("d:href", "", ns))
            pfad = urllib.parse.unquote(urllib.parse.urlparse(href).path)
            if not pfad.startswith(self.basis_pfad):
                continue
            relpfad = pfad[len(self.basis_pfad):].strip("/")
            if relpfad == rel.strip("/"):
                continue  # der Ordner selbst
            prop = resp.find("d:propstat/d:prop", ns)
            if prop is None:
                continue
            ist_ordner = prop.find("d:resourcetype/d:collection", ns) is not None
            mtime = None
            lm = prop.findtext("d:getlastmodified", "", ns)
            if lm:
                try:
                    mtime = parsedate_to_datetime(lm)
                except (TypeError, ValueError):
                    pass
            groesse = prop.findtext("d:getcontentlength", "", ns)
            eintraege.append({
                "pfad": relpfad, "ordner": ist_ordner,
                "etag": (prop.findtext("d:getetag", "", ns) or "").strip('"'),
                "groesse": int(groesse) if groesse.isdigit() else None,
                "geaendert_am": mtime,
            })
        return eintraege

    def alle_dateien(self, rel):
        for e in self.liste(rel):
            name = e["pfad"].rsplit("/", 1)[-1]
            if name.startswith(".") or name in UEBERSPRINGEN:
                continue
            if e["ordner"]:
                yield from self.alle_dateien(e["pfad"])
            else:
                yield e

    def hole(self, rel, ziel):
        with self._req("GET", rel, timeout=180) as r, open(ziel, "wb") as f:
            shutil.copyfileobj(r, f)

    def hole_bytes(self, rel, max_bytes=60 * 1024 * 1024):
        with self._req("GET", rel, timeout=180) as r:
            ctype = r.headers.get("Content-Type", "application/octet-stream")
            return r.read(max_bytes + 1), ctype


def verbindung():
    z = lade_zugang()
    if not (z.get("WEBDAV_URL") and z.get("WEBDAV_USER") and z.get("WEBDAV_PASSWORD")):
        return None
    return Dav(z["WEBDAV_URL"], z["WEBDAV_USER"], z["WEBDAV_PASSWORD"])


# ── Text gewinnen ────────────────────────────────────────────────────────────

def typ_von(name):
    endung = Path(name).suffix.lower()
    if endung in (".md", ".markdown"):
        return "md"
    if endung in TEXT_ENDUNGEN:
        return "text"
    if endung == ".pdf":
        return "pdf"
    if endung in BILD_ENDUNGEN:
        return "bild"
    if endung == ".docx":
        return "docx"
    return "sonst"


def _lauf(cmd, timeout=180):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.stdout.decode("utf-8", "replace")


def _ocr_bild(pfad):
    return _lauf(["tesseract", str(pfad), "stdout", "-l", "deu+eng"], timeout=180)


def _docx_text(pfad):
    with zipfile.ZipFile(pfad) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    import html as _html
    return _html.unescape(text)


def text_gewinnen(pfad, typ, cfg, ocr_frei):
    """Liefert (text, ocr_benutzt). ocr_frei: ob in diesem Lauf noch OCR erlaubt ist."""
    if typ in ("md", "text"):
        return Path(pfad).read_text(encoding="utf-8", errors="replace"), False
    if typ == "docx":
        return _docx_text(pfad), False
    if typ == "pdf":
        text = _lauf(["pdftotext", "-q", str(pfad), "-"])
        seiten = max(1, text.count("\f") or 1)
        if len(text.strip()) >= 80 * seiten or not ocr_frei:
            return text, False
        # Kaum Text: vermutlich ein Scan -> Seiten als Bilder rendern und erkennen
        tmp = tempfile.mkdtemp(prefix="wissen_ocr_")
        try:
            _lauf(["pdftoppm", "-r", "200", "-gray", "-png", "-l", str(cfg["max_ocr_seiten"]),
                   str(pfad), os.path.join(tmp, "s")], timeout=300)
            teile = [_ocr_bild(os.path.join(tmp, f)) for f in sorted(os.listdir(tmp)) if f.endswith(".png")]
            return "\n\f".join(teile), True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if typ == "bild":
        if not ocr_frei:
            return None, False  # spaeter erneut versuchen
        return _ocr_bild(pfad), True
    return "", False


# ── Namenspruefung ───────────────────────────────────────────────────────────

_RECHTSFORMEN = r"\s+(GmbH\s*&\s*Co\.?\s*KG|GmbH|UG(\s*\(haftungsbeschränkt\))?|AG|KG|OHG|e\.\s?K\.|e\.V\.|PartG(mbB)?|mbH|SE|Ltd\.?|Inc\.?)\.?$"


def namensmuster(cfg):
    ignorieren = {n.lower() for n in cfg.get("namen_ignorieren", [])}
    muster = []
    for r in core._q("SELECT name FROM firmen"):
        name = (r["name"] or "").strip()
        varianten = {name}
        kurz = re.sub(_RECHTSFORMEN, "", name, flags=re.I).strip(" ,&")
        if kurz and kurz != name:
            varianten.add(kurz)
        for v in varianten:
            if len(v) < 5 or v.lower() in ignorieren:
                continue
            muster.append(("Firma", name, re.compile(r"(?<!\w)" + re.escape(v) + r"(?!\w)", re.I)))
    for r in core._q("SELECT name FROM personen"):
        name = (r["name"] or "").strip()
        # Nur volle Namen (Vor- und Nachname), sonst trifft jeder Vorname
        if len(name.split()) < 2 or len(name) < 6 or name.lower() in ignorieren:
            continue
        muster.append(("Person", name, re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I)))
    return muster


def treffer_fuer(text, muster):
    gefunden = {}
    for art, name, rx in muster:
        if (art, name) not in gefunden and rx.search(text or ""):
            gefunden[(art, name)] = {"art": art, "name": name}
    return list(gefunden.values())


# ── Kundenwissen (Migration 012, 2026-10-30) ─────────────────────────────────
# Je Firma im CRM der gleichnamige Kundenordner, darin nur ACOS/ und
# Besprechungen/. Ordnername = Firmenname im CRM (Leerzeichen, Punkte und
# Gross/Klein egal). Nichts davon landet in der allgemeinen Recherche.

KUNDEN_UNTERORDNER = {"ACOS": "acos", "Besprechungen": "besprechung"}
_DATUM_VORNE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[\s_-]*")


def kunden_verbindung():
    z = lade_zugang()
    url = z.get("WEBDAV_URL") or ""
    if not (url and z.get("WEBDAV_USER") and z.get("WEBDAV_PASSWORD")):
        return None
    m = re.match(r"^(https?://.+?/remote\.php/dav/files/[^/]+/)", url)
    basis = m.group(1) if m else url.rstrip("/").rsplit("/", 1)[0] + "/"
    basis += urllib.parse.quote(core.kunden_ablage_basis(), safe="/") + "/"
    return Dav(basis, z["WEBDAV_USER"], z["WEBDAV_PASSWORD"])


def _schluessel(name):
    return re.sub(r"[^a-z0-9äöüß]", "", (name or "").lower())


def titel_und_datum(name, geaendert_am):
    stamm = Path(name).stem
    m = _DATUM_VORNE.match(stamm)
    if m:
        try:
            return stamm[m.end():].strip() or stamm, date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return stamm, (geaendert_am.date() if geaendert_am else None)


def kundenwissen_abgleich(cfg):
    """Gleicht die Unterordner ACOS/ und Besprechungen/ aller Kundenordner ab,
    die einer Firma im CRM zugeordnet werden koennen. Rueckgabe: Kennzahlen."""
    dav = kunden_verbindung()
    zahl = {"ordner": 0, "neu": 0, "geaendert": 0, "geloescht": 0, "fehler": 0, "offen": 0, "ohne_firma": 0}
    if dav is None:
        return zahl
    firmen = {_schluessel(r["name"]): r["id"] for r in core._q("SELECT id, name FROM firmen WHERE archiviert_am IS NULL")}
    bekannt = {r["pfad"]: r["etag"] for r in core._q("SELECT pfad, etag FROM kundenwissen")}
    gesehen, geprueft = set(), set()
    bearbeitet = ocr_benutzt = 0
    tmpdir = tempfile.mkdtemp(prefix="kundenwissen_")
    try:
        for ordner in dav.liste(""):
            if not ordner["ordner"] or ordner["pfad"].startswith("."):
                continue
            firma_id = firmen.get(_schluessel(ordner["pfad"]))
            if not firma_id:
                zahl["ohne_firma"] += 1
                continue
            zahl["ordner"] += 1
            for unter, quelle in KUNDEN_UNTERORDNER.items():
                wurzel = f"{ordner['pfad']}/{unter}"
                try:
                    dateien = list(dav.alle_dateien(wurzel))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        continue
                    raise
                geprueft.add(wurzel)
                for d in dateien:
                    pfad = d["pfad"]
                    gesehen.add(pfad)
                    if pfad in bekannt and bekannt[pfad] == d["etag"] and d["etag"]:
                        continue
                    if bearbeitet >= cfg["max_dateien_je_lauf"]:
                        zahl["offen"] += 1
                        continue
                    name = pfad.rsplit("/", 1)[-1]
                    typ = typ_von(name)
                    titel, datum = titel_und_datum(name, d["geaendert_am"])
                    status, fehler, text, ocr = "ok", None, "", False
                    try:
                        if d["groesse"] and d["groesse"] > cfg["max_mb"] * 1024 * 1024:
                            status = "zu_gross"
                        elif typ != "sonst":
                            lokal = os.path.join(tmpdir, "datei" + Path(name).suffix.lower())
                            dav.hole(pfad, lokal)
                            ergebnis, ocr = text_gewinnen(lokal, typ, cfg, ocr_benutzt < cfg["max_ocr_je_lauf"])
                            os.remove(lokal)
                            if ergebnis is None:
                                zahl["offen"] += 1
                                continue
                            text = ergebnis
                            if ocr:
                                ocr_benutzt += 1
                    except Exception as e:
                        status, fehler = "fehler", f"{e.__class__.__name__}: {e}"[:500]
                        zahl["fehler"] += 1
                        log(f"Kundenwissen: Fehler bei einer Datei ({e.__class__.__name__})")
                    text = re.sub(r"\x00", "", text or "")[:MAX_ZEICHEN]
                    core._x("""
                        INSERT INTO kundenwissen (firma_id, pfad, quelle, name, titel, datum, typ, groesse, etag,
                                                  geaendert_am, inhalt, ocr, status, fehler, abgeglichen_am)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                        ON CONFLICT (pfad) DO UPDATE SET firma_id=EXCLUDED.firma_id, quelle=EXCLUDED.quelle,
                            name=EXCLUDED.name, titel=EXCLUDED.titel, datum=EXCLUDED.datum, typ=EXCLUDED.typ,
                            groesse=EXCLUDED.groesse, etag=EXCLUDED.etag, geaendert_am=EXCLUDED.geaendert_am,
                            inhalt=EXCLUDED.inhalt, ocr=EXCLUDED.ocr, status=EXCLUDED.status,
                            fehler=EXCLUDED.fehler, abgeglichen_am=now()""",
                        (firma_id, pfad, quelle, name, titel, datum, typ, d["groesse"],
                         d["etag"] if status != "fehler" else None, d["geaendert_am"], text, ocr, status, fehler))
                    zahl["geaendert" if pfad in bekannt else "neu"] += 1
                    bearbeitet += 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    # Entfernt: nur loeschen, was in einem tatsaechlich gelesenen Ordner fehlt,
    # oder dessen Firma/Ordner es nicht mehr gibt (Ordner umbenannt oder Firma archiviert)
    lebende_ordner = {w.split("/", 1)[0] for w in geprueft}
    for pfad in bekannt:
        if pfad in gesehen:
            continue
        oben = pfad.split("/", 1)[0]
        in_geprueftem = any(pfad.startswith(w + "/") for w in geprueft)
        if in_geprueftem or oben not in lebende_ordner:
            core._x("DELETE FROM kundenwissen WHERE pfad=%s", (pfad,))
            zahl["geloescht"] += 1
    return zahl


# ── Neue Dateien im Kundenordner -> Journal "Dokument" (Umbau Schritt 12, Migration 023) ──
ABLAGE_AUSNAHMEN = {"acos", "mail-eingang"}
MAX_NAMEN_IM_EINTRAG = 8


def _liste_mit_id(dav, rel):
    """Wie Dav.liste, zusaetzlich mit der stabilen Nextcloud-Datei-ID (oc:fileid)."""
    body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop>'
            b'<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><oc:fileid/>'
            b'</d:prop></d:propfind>')
    with dav._req("PROPFIND", rel.rstrip("/") + "/", {"Depth": "1", "Content-Type": "application/xml"}, body) as r:
        xml = r.read()
    ns = {"d": "DAV:", "oc": "http://owncloud.org/ns"}
    out = []
    for resp in ET.fromstring(xml).findall("d:response", ns):
        pfad = urllib.parse.unquote(urllib.parse.urlparse(urllib.parse.unquote(resp.findtext("d:href", "", ns))).path)
        if not pfad.startswith(dav.basis_pfad):
            continue
        relpfad = pfad[len(dav.basis_pfad):].strip("/")
        if relpfad == rel.strip("/"):
            continue
        prop = resp.find("d:propstat/d:prop", ns)
        if prop is None:
            continue
        mtime = None
        lm = prop.findtext("d:getlastmodified", "", ns)
        if lm:
            try:
                mtime = parsedate_to_datetime(lm)
            except (TypeError, ValueError):
                pass
        groesse = prop.findtext("d:getcontentlength", "", ns)
        out.append({"pfad": relpfad, "ordner": prop.find("d:resourcetype/d:collection", ns) is not None,
                    "id": (prop.findtext("oc:fileid", "", ns) or "").strip(),
                    "groesse": int(groesse) if groesse.isdigit() else None, "geaendert_am": mtime})
    return out


def _ablage_dateien(dav, rel, ausgeblendet, tiefe=0):
    for e in _liste_mit_id(dav, rel):
        name = e["pfad"].rsplit("/", 1)[-1]
        if name.startswith(".") or name in UEBERSPRINGEN:
            continue
        if e["ordner"]:
            if name.lower() in ABLAGE_AUSNAHMEN or name.lower() in ausgeblendet or tiefe > 8:
                continue
            yield from _ablage_dateien(dav, e["pfad"], ausgeblendet, tiefe + 1)
        elif e["id"]:
            yield e


def dokumente_ins_journal():
    """Neue Dateien in den Kundenordnern erfassen und je Unternehmen einen Journal-Eintrag
    "Dokument" anlegen. Erster Lauf: nur Bestand erfassen. Rueckgabe: Kennzahlen."""
    zahl = {"dateien": 0, "neu": 0, "eintraege": 0, "bestand_erfasst": False, "ohne_firma": 0}
    if not core._tabelle_da("ablage_datei"):
        return zahl
    dav = kunden_verbindung()
    if dav is None:
        return zahl
    erstlauf = core._q1("SELECT 1 AS x FROM ablage_datei LIMIT 1") is None
    zahl["bestand_erfasst"] = erstlauf
    firmen = {_schluessel(r["name"]): (r["id"], r["name"])
              for r in core._q("SELECT id, name FROM firmen WHERE archiviert_am IS NULL")}
    bekannt = {r["datei_id"]: r for r in core._q("SELECT datei_id, pfad, firma_id FROM ablage_datei")}
    ausgeblendet = {w.lower() for w in (core._system_raw().get("acos_ordner_ausblenden") or []) if isinstance(w, str)}
    neu_je_firma, gesehen = {}, set()
    for ordner in dav.liste(""):
        if not ordner["ordner"] or ordner["pfad"].startswith("."):
            continue
        treffer = firmen.get(_schluessel(ordner["pfad"]))
        if not treffer:
            zahl["ohne_firma"] += 1
            continue
        firma_id, firma = treffer
        for d in _ablage_dateien(dav, ordner["pfad"], ausgeblendet):
            zahl["dateien"] += 1
            gesehen.add(d["id"])
            alt = bekannt.get(d["id"])
            if alt:
                if alt["pfad"] != d["pfad"] or alt["firma_id"] != firma_id:
                    core._x("UPDATE ablage_datei SET pfad=%s, firma_id=%s, entfernt=false, zuletzt_am=now() WHERE datei_id=%s",
                            (d["pfad"], firma_id, d["id"]))
                continue
            core._x("""INSERT INTO ablage_datei (datei_id, pfad, firma_id, groesse, geaendert_am)
                       VALUES (%s,%s,%s,%s,%s) ON CONFLICT (datei_id) DO NOTHING""",
                    (d["id"], d["pfad"], firma_id, d["groesse"], d["geaendert_am"]))
            if not erstlauf:
                neu_je_firma.setdefault((firma_id, firma), []).append(d)
                zahl["neu"] += 1
    weg = [i for i in bekannt if i not in gesehen]
    if weg:
        core._x("UPDATE ablage_datei SET entfernt=true WHERE datei_id = ANY(%s) AND NOT entfernt", (weg,))
    for (firma_id, firma), dateien in neu_je_firma.items():
        dateien.sort(key=lambda d: d["pfad"].lower())
        namen = [d["pfad"].rsplit("/", 1)[-1] for d in dateien]
        if len(namen) == 1:
            text = f"Neu im Kundenordner: {namen[0]}"
        else:
            text = f"{len(namen)} neue Dateien im Kundenordner: " + ", ".join(namen[:MAX_NAMEN_IM_EINTRAG]) + \
                   (f" und {len(namen) - MAX_NAMEN_IM_EINTRAG} weitere" if len(namen) > MAX_NAMEN_IM_EINTRAG else "")
        ordner_set = {d["pfad"].rsplit("/", 1)[0] for d in dateien}
        gemeinsam = ordner_set.pop() if len(ordner_set) == 1 else firma
        rel_ordner = f"{core.kunden_ablage_basis()}/{gemeinsam}"
        payload = {"anhaenge": [{"name": d["pfad"][len(firma) + 1:] if d["pfad"].startswith(firma + "/") else d["pfad"],
                                 "pfad": f"{core.kunden_ablage_basis()}/{d['pfad']}"} for d in dateien[:50]],
                   "anhang_ordner": rel_ordner, "anhang_link": core._nextcloud_ordner_link(rel_ordner),
                   "quelle": "nextcloud"}
        r = core._x("""INSERT INTO aktivitaeten (firma_id, art, datum, quelle, notiz, payload)
                       VALUES (%s,'dokument',%s,'nextcloud',%s,%s::jsonb) RETURNING id""",
                    (firma_id, core.heute_lokal(), text, core.json.dumps(payload, ensure_ascii=False)))[0]
        core._x("UPDATE ablage_datei SET aktivitaet_id=%s WHERE datei_id = ANY(%s)", (r["id"], [d["id"] for d in dateien]))
        zahl["eintraege"] += 1
    return zahl


# ── Lauf ─────────────────────────────────────────────────────────────────────

def abgleich(ausgeloest_von="timer"):
    cfg = lade_konfig()
    dav = verbindung()
    lauf = core._x("INSERT INTO wissen_laeufe (ausgeloest_von) VALUES (%s) RETURNING id", (ausgeloest_von,))[0]["id"]
    zahl = {"neu": 0, "geaendert": 0, "geloescht": 0, "fehler": 0, "offen": 0}
    meldung = ""
    try:
        if dav is None:
            raise RuntimeError("Zugang fehlt: secrets/wissen.env mit WEBDAV_URL, WEBDAV_USER, WEBDAV_PASSWORD anlegen")
        bekannt = {r["pfad"]: r["etag"] for r in core._q("SELECT pfad, etag FROM wissen_dokumente")}
        gesehen = set()
        bearbeitet = ocr_benutzt = 0
        tmpdir = tempfile.mkdtemp(prefix="wissen_")
        try:
            for wurzel in cfg["ordner"]:
                try:
                    dateien = list(dav.alle_dateien(wurzel))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        log(f"Ordner {wurzel} nicht gefunden - uebersprungen")
                        continue
                    raise
                for d in dateien:
                    pfad = d["pfad"]
                    gesehen.add(pfad)
                    if pfad in bekannt and bekannt[pfad] == d["etag"] and d["etag"]:
                        continue
                    if bearbeitet >= cfg["max_dateien_je_lauf"]:
                        zahl["offen"] += 1
                        continue
                    name = pfad.rsplit("/", 1)[-1]
                    ordner = pfad.rsplit("/", 1)[0] if "/" in pfad else ""
                    typ = typ_von(name)
                    status, fehler, text, ocr = "ok", None, "", False
                    try:
                        if d["groesse"] and d["groesse"] > cfg["max_mb"] * 1024 * 1024:
                            status = "zu_gross"
                        elif typ != "sonst":
                            lokal = os.path.join(tmpdir, "datei" + Path(name).suffix.lower())
                            dav.hole(pfad, lokal)
                            ergebnis, ocr = text_gewinnen(lokal, typ, cfg, ocr_benutzt < cfg["max_ocr_je_lauf"])
                            os.remove(lokal)
                            if ergebnis is None:          # OCR-Kontingent erschoepft
                                zahl["offen"] += 1
                                continue
                            text = ergebnis
                            if ocr:
                                ocr_benutzt += 1
                    except Exception as e:  # einzelne Datei darf den Lauf nicht abbrechen
                        status, fehler = "fehler", f"{e.__class__.__name__}: {e}"[:500]
                        zahl["fehler"] += 1
                        log(f"Fehler bei {pfad}: {fehler}")
                    text = re.sub(r"\x00", "", text or "")[:MAX_ZEICHEN]
                    core._x("""
                        INSERT INTO wissen_dokumente (pfad, name, ordner, typ, groesse, etag, geaendert_am,
                                                      inhalt, ocr, status, fehler, abgeglichen_am)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                        ON CONFLICT (pfad) DO UPDATE SET name=EXCLUDED.name, ordner=EXCLUDED.ordner,
                            typ=EXCLUDED.typ, groesse=EXCLUDED.groesse, etag=EXCLUDED.etag,
                            geaendert_am=EXCLUDED.geaendert_am, inhalt=EXCLUDED.inhalt, ocr=EXCLUDED.ocr,
                            status=EXCLUDED.status, fehler=EXCLUDED.fehler, abgeglichen_am=now()
                        RETURNING id""",
                        (pfad, name, ordner, typ, d["groesse"], d["etag"] if status != "fehler" else None,
                         d["geaendert_am"], text, ocr, status, fehler))
                    zahl["geaendert" if pfad in bekannt else "neu"] += 1
                    bearbeitet += 1
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        # In Nextcloud geloescht (nur innerhalb der abgeglichenen Ordner)
        for pfad in bekannt:
            if pfad not in gesehen and any(pfad == w or pfad.startswith(w + "/") for w in cfg["ordner"]):
                core._x("DELETE FROM wissen_dokumente WHERE pfad=%s", (pfad,))
                zahl["geloescht"] += 1
        # Dokumente aus Ordnern, die nicht mehr abgeglichen werden, ebenfalls entfernen
        for pfad in bekannt:
            if pfad not in gesehen and not any(pfad == w or pfad.startswith(w + "/") for w in cfg["ordner"]):
                core._x("DELETE FROM wissen_dokumente WHERE pfad=%s", (pfad,))
                zahl["geloescht"] += 1

        # Namenspruefung ueber alle Dokumente (CRM-Namen koennen sich geaendert haben)
        muster = namensmuster(cfg)
        for r in core._q("SELECT id, inhalt, name, namens_treffer FROM wissen_dokumente"):
            neu = treffer_fuer((r["name"] or "") + "\n" + (r["inhalt"] or ""), muster)
            if neu != (r["namens_treffer"] or []):
                core._x("UPDATE wissen_dokumente SET namens_treffer=%s::jsonb WHERE id=%s",
                        (core.json.dumps(neu, ensure_ascii=False), r["id"]))
        meldung = "ok"
        # Kundenwissen: eigener Fehlerbereich, darf den Wissens-Abgleich nicht kippen
        try:
            kunden = kundenwissen_abgleich(cfg)
        except Exception as e:
            kunden = {"meldung": f"{e.__class__.__name__}: {e}"[:300]}
            log("Kundenwissen fehlgeschlagen:\n" + traceback.format_exc())
        try:
            kunden["dokumente"] = dokumente_ins_journal()
        except Exception as e:
            kunden["dokumente"] = {"meldung": f"{e.__class__.__name__}: {e}"[:300]}
            log("Dokumente ins Journal fehlgeschlagen:\n" + traceback.format_exc())
        core._x("UPDATE wissen_laeufe SET kunden=%s::jsonb WHERE id=%s",
                (core.json.dumps(kunden, ensure_ascii=False, default=str), lauf))
        log(f"Kundenwissen: {kunden}")
    except urllib.error.HTTPError as e:
        texte = {401: "Anmeldung bei Nextcloud fehlgeschlagen: Benutzer oder App-Passwort falsch",
                 403: "Nextcloud verweigert den Zugriff: Ordner nicht freigegeben",
                 404: "Vault-Ordner in Nextcloud nicht gefunden: WEBDAV_URL prüfen"}
        meldung = texte.get(e.code, f"Nextcloud antwortet mit Fehler {e.code}")
        log("Abgleich fehlgeschlagen: " + meldung)
    except urllib.error.URLError as e:
        meldung = f"Nextcloud nicht erreichbar ({e.reason})"[:500]
        log("Abgleich fehlgeschlagen: " + meldung)
    except Exception as e:
        meldung = f"{e.__class__.__name__}: {e}"[:500]
        log("Abgleich fehlgeschlagen:\n" + traceback.format_exc())
    core._x("""UPDATE wissen_laeufe SET ende=now(), neu=%s, geaendert=%s, geloescht=%s, fehler=%s, offen=%s,
               meldung=%s WHERE id=%s""",
            (zahl["neu"], zahl["geaendert"], zahl["geloescht"], zahl["fehler"], zahl["offen"], meldung, lauf))
    log(f"Abgleich beendet: {zahl} {meldung}")
    return zahl, meldung


def main():
    ausgeloest = sys.argv[1] if len(sys.argv) > 1 else "timer"
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Abgleich laeuft bereits - beende.")
            return 0
        t0 = time.time()
        _, meldung = abgleich(ausgeloest)
        log(f"Dauer: {time.time() - t0:.1f} s")
        return 0 if meldung == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
