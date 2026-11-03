#!/usr/bin/env python3
"""
Abgleich CRM -> ACOS (Konzept "Abgleich CRM-ACOS", Stand 20.10.2026).

Je Lauf:
  1. Mandantenliste aus ACOS holen (MCP, am_acos_clients_list).
  2. Unternehmen mit "In ACOS fuehren", die noch nicht zugeordnet sind:
     Treffer nach Namen suchen und als Vorschlag ins CRM schreiben. Verknuepft
     oder angelegt wird erst, wenn du im CRM bestaetigt hast.
  3. Bestaetigte Unternehmen: Name, Status und Stammdaten nach ACOS senden,
     wenn sie sich seit dem letzten Senden geaendert haben.
  4. Ausgeschaltete oder archivierte Unternehmen: Mandant in ACOS archivieren.
     Geloescht wird in ACOS nie etwas.
  5. Wissensobjekte je Mandant holen (additiv: nur neue IDs) und neue Inhalte
     in den Kundenordner der Nextcloud legen (nur anlegen, nie ueberschreiben).

Modus (Einstellungen > System > ACOS-Abgleich):
  trocken  - Standard. Schreibt nichts nach ACOS und nichts in die Nextcloud,
             sondern in den Bericht, was es tun wuerde. Vorschlaege und die
             Liste der Wissensobjekte landen trotzdem im CRM.
  scharf   - fuehrt die Schritte wirklich aus.

Zugang: secrets/acos.env (chmod 600), nie im Repository:
    ACOS_TOKEN=<Zugriffstoken aus dem ACOS-Portal>
    ACOS_MCP_URL=https://acos.alchimedus.pro/mcp/v2
Nextcloud: derselbe Benutzer wie die Wissens-DB (secrets/wissen.env).

Aufruf:
    sudo -u crmapp python3 /opt/crm/acos_sync.py            # wie der Timer
    sudo -u crmapp python3 /opt/crm/acos_sync.py --struktur # nur Feldnamen der
        ACOS-Antworten anzeigen (keine Inhalte) - zur Pruefung nach Updates
"""

import fcntl
import hashlib
import json
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crm_core as core  # noqa: E402
import wissen_sync as ws  # noqa: E402

ACOS_ENV = core.BASE_DIR / "secrets" / "acos.env"
LOCK_FILE = core.BASE_DIR / "secrets" / "acos_sync.lock"
MAX_ABLAGE_JE_LAUF = 50
PROTOKOLL_VERSION = "2025-06-18"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%dT%H:%M:%S}] {msg}", flush=True)


class AcosFehler(Exception):
    pass


def lade_acos_zugang():
    if not ACOS_ENV.exists():
        return {}
    werte = {}
    for line in ACOS_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            werte[k.strip()] = v.strip()
    return werte


# ── MCP-Verbindung ───────────────────────────────────────────────────────────

class Mcp:
    """Schlanker MCP-Client (Streamable HTTP, JSON oder SSE als Antwort)."""

    def __init__(self, url, token):
        self.url, self.token = url, token
        self.sitzung, self.nr, self.werkzeuge = None, 0, set()

    def _post(self, body):
        kopf = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": PROTOKOLL_VERSION}
        if self.sitzung:
            kopf["Mcp-Session-Id"] = self.sitzung
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=kopf, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                if r.headers.get("Mcp-Session-Id"):
                    self.sitzung = r.headers["Mcp-Session-Id"]
                text = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AcosFehler(f"ACOS lehnt den Zugang ab ({e.code}). Token in secrets/acos.env prüfen.")
            if e.code == 404:
                raise AcosFehler("ACOS-Adresse nicht gefunden (404). ACOS_MCP_URL in secrets/acos.env prüfen.")
            raise AcosFehler(f"ACOS antwortet mit Fehler {e.code}.")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise AcosFehler(f"ACOS nicht erreichbar ({e.__class__.__name__}).")
        if "id" not in body:
            return None
        kandidaten = [z[5:].strip() for z in text.splitlines() if z.startswith("data:")] or [text]
        for k in reversed(kandidaten):
            try:
                obj = json.loads(k)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("id") == body["id"]:
                if obj.get("error"):
                    raise AcosFehler("ACOS meldet: " + str(obj["error"].get("message") or obj["error"])[:300])
                return obj.get("result") or {}
        raise AcosFehler("Unerwartete Antwort von ACOS.")

    def _rpc(self, methode, params):
        self.nr += 1
        return self._post({"jsonrpc": "2.0", "id": self.nr, "method": methode, "params": params})

    def start(self):
        self._rpc("initialize", {"protocolVersion": PROTOKOLL_VERSION, "capabilities": {},
                                 "clientInfo": {"name": "crm-acos-abgleich", "version": "1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        res = self._rpc("tools/list", {})
        self.werkzeuge = {t.get("name") for t in res.get("tools", [])}

    def _aufruf(self, name, args):
        res = self._rpc("tools/call", {"name": name, "arguments": args})
        inhalt = res.get("structuredContent")
        if inhalt is None:
            texte = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
            roh = "\n".join(texte).strip()
            try:
                inhalt = json.loads(roh) if roh else {}
            except ValueError:
                inhalt = {"text": roh}
        if res.get("isError") or (isinstance(inhalt, dict) and inhalt.get("error") and len(inhalt) <= 4):
            msg = inhalt.get("message") or inhalt.get("error") or inhalt.get("text") if isinstance(inhalt, dict) else inhalt
            raise AcosFehler(f"{name}: {str(msg)[:300]}")
        return inhalt

    def lesen(self, name, args=None):
        if name in self.werkzeuge:
            return self._aufruf(name, args or {})
        return self._aufruf("am_acos_call_tool", {"name": name, "arguments": args or {}})

    def aendern(self, name, args):
        if name in self.werkzeuge:
            return self._aufruf(name, args)
        return self._aufruf("am_acos_call_action", {"name": name, "arguments": args})


def _liste(obj, schluessel=("clients", "items", "knowledge", "objects", "results", "data", "entries")):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in schluessel:
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                inner = _liste(v, schluessel)
                if inner:
                    return inner
        for v in obj.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
    return []


def _feld(d, *namen):
    for n in namen:
        teile = n.split(".")
        v = d
        for t in teile:
            v = v.get(t) if isinstance(v, dict) else None
        if v not in (None, ""):
            return v
    return None


def _zeit(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def mandant(c):
    return {"id": str(_feld(c, "id", "client_id", "uuid") or ""), "name": str(_feld(c, "name", "title") or ""),
            "status": str(_feld(c, "status") or "")}


def wissensobjekt(k):
    return {
        "id": str(_feld(k, "id", "knowledge_id", "uuid") or ""),
        "titel": str(_feld(k, "title", "titel", "name", "label") or "")[:300],
        "art": _feld(k, "kind", "type", "artifact_type", "skill"),
        "erstellt": _zeit(_feld(k, "created_at", "createdAt", "created")),
        "geaendert": _zeit(_feld(k, "updated_at", "updatedAt", "modified_at", "updated")),
        "projekt": _feld(k, "project.name", "project_name", "projectName"),
        "link": _feld(k, "url", "link", "web_url", "portal_url"),
    }


# ── Namensvergleich ──────────────────────────────────────────────────────────

RECHTSFORM = {"gmbh", "mbh", "ug", "haftungsbeschraenkt", "ag", "kg", "co", "ohg", "gbr", "ek", "ekfm",
              "ev", "partg", "partgmbb", "se", "kgaa", "inh", "gmbhcokg", "ltd", "inc", "e", "k", "v"}


def norm(name):
    n = (name or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        n = n.replace(a, b)
    n = re.sub(r"&\s*co\b", " co ", n)
    n = n.replace("&", " und ").replace("+", " und ")
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return " ".join(t for t in n.split() if t not in RECHTSFORM)


def vorschlaege_fuer(name, mandanten, belegt):
    ziel = norm(name)
    treffer = []
    for m in mandanten:
        if not m["id"] or m["id"] in belegt:
            continue
        mn = norm(m["name"])
        if not mn or not ziel:
            continue
        if mn == ziel:
            wert, art = 1.0, "gleich"
        else:
            wert = SequenceMatcher(None, ziel, mn).ratio()
            if (len(ziel) >= 4 and len(mn) >= 4) and (mn.startswith(ziel + " ") or ziel.startswith(mn + " ")):
                wert = max(wert, 0.85)
            if wert < 0.82:
                continue
            art = "ähnlich"
        treffer.append({"id": m["id"], "name": m["name"], "status": m["status"], "art": art, "wert": round(wert, 2)})
    treffer.sort(key=lambda t: -t["wert"])
    return treffer[:5]


# ── Daten fuer ACOS ──────────────────────────────────────────────────────────

def acos_status(crm_status):
    s = (crm_status or "").lower()
    if "kunde" in s or re.search(r"\baktiv\b", s):
        return "active"
    if "lead" in s or "interessent" in s:
        return "lead"
    return None


def nutzdaten(f, client_id=None):
    """Nur Felder, die das CRM selbst fuehrt und die gefuellt sind."""
    d = {"name": f["name"]}
    if client_id:
        d["client_id"] = client_id
    st = acos_status(f["status"])
    if st:
        d["status"] = st
    company = {}
    if (f.get("branch") or "").strip():
        company["industry"] = f["branch"].strip()
    m = re.search(r"\b\d{5}\s+([^,]+)$", (f.get("address") or "").strip())
    if m:
        company["city"] = m.group(1).strip()
    if company:
        d["company"] = company
    return d


def pruefwert(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


# ── Nextcloud ────────────────────────────────────────────────────────────────

class Ablage:
    """Schreibt unter <Kundenpfad>/<Firma>/ACOS/Wissen. Legt nur an, ueberschreibt nie."""

    def __init__(self):
        z = ws.lade_zugang()
        url = z.get("WEBDAV_URL") or ""
        if not url or not z.get("WEBDAV_USER"):
            raise AcosFehler("Nextcloud-Zugang fehlt (secrets/wissen.env)")
        m = re.match(r"^(https?://.+?/remote\.php/dav/files/[^/]+/)", url)
        basis = m.group(1) if m else url.rstrip("/").rsplit("/", 1)[0] + "/"
        basis += urllib.parse.quote(core.kunden_ablage_basis(), safe="/") + "/"
        self.dav = ws.Dav(basis, z["WEBDAV_USER"], z.get("WEBDAV_PASSWORD", ""))

    def gibt_es(self, rel):
        try:
            with self.dav._req("PROPFIND", rel, {"Depth": "0"}, timeout=30):
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            raise

    def ordner(self, rel):
        try:
            with self.dav._req("MKCOL", rel.rstrip("/") + "/", timeout=30):
                pass
        except urllib.error.HTTPError as e:
            if e.code != 405:          # 405 = gibt es schon
                raise

    def datei(self, rel, daten):
        """Anlegen mit If-None-Match: * - eine vorhandene Datei wird nie ersetzt."""
        with self.dav._req("PUT", rel, {"Content-Type": "text/markdown; charset=utf-8", "If-None-Match": "*"},
                           daten, timeout=60):
            pass


    def dateien(self, firma, tiefe=3):
        """Dateien im Kundenordner (ohne den Unterordner ACOS, der kommt aus ACOS)."""
        aus = []

        def lauf(rel, t):
            for e in self.dav.liste(rel):
                name = e["pfad"].rsplit("/", 1)[-1]
                if name.startswith(".") or name in ws.UEBERSPRINGEN:
                    continue
                if e["ordner"]:
                    if t > 1 and not (rel == firma and name == "ACOS"):
                        lauf(e["pfad"], t - 1)
                else:
                    aus.append(dict(e, rel=e["pfad"][len(firma) + 1:]))
        lauf(firma, tiefe)
        return sorted(aus, key=lambda e: e["rel"].lower())

    def ordner_inhalt(self, rel):
        """Eine Ebene: (unterordner, dateien) eines Ordners, ohne versteckte Eintraege."""
        ordner, dateien = [], []
        for e in self.dav.liste(rel):
            name = e["pfad"].rsplit("/", 1)[-1]
            if name.startswith(".") or name in ws.UEBERSPRINGEN:
                continue
            (ordner if e["ordner"] else dateien).append(dict(e, name=name))
        return ordner, dateien

    def info(self, rel):
        """Groesse und ETag einer Datei (PROPFIND Tiefe 0), None wenn es sie nicht gibt."""
        body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                b'<d:resourcetype/><d:getetag/><d:getcontentlength/></d:prop></d:propfind>')
        try:
            with self.dav._req("PROPFIND", rel, {"Depth": "0", "Content-Type": "application/xml"}, body, timeout=30) as r:
                xml = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        import xml.etree.ElementTree as ET
        ns = {"d": "DAV:"}
        prop = ET.fromstring(xml).find("d:response/d:propstat/d:prop", ns)
        if prop is None or prop.find("d:resourcetype/d:collection", ns) is not None:
            return None
        groesse = prop.findtext("d:getcontentlength", "", ns)
        return {"etag": (prop.findtext("d:getetag", "", ns) or "").strip('"'),
                "groesse": int(groesse) if groesse.isdigit() else None}

    def hole(self, rel, max_bytes):
        return self.dav.hole_bytes(rel, max_bytes)


# ── Dokument an ACOS senden (Knopf am Unternehmen) ───────────────────────────

MAX_UPLOAD = 25 * 1024 * 1024
DIREKT_UPLOAD = 1024 * 1024
MIME = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".vtt": "text/vtt",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
LESBAR = {".pdf", ".docx", ".txt", ".md", ".vtt"}


def ausgeblendete_ordner():
    werte = core._system_raw().get("acos_ordner_ausblenden") or []
    return [str(w) for w in werte if str(w).strip()] if isinstance(werte, list) else []


def kundenordner_dateien(firma_id, pfad=""):
    """Eine Ebene des Kundenordners: Unterordner (mit Zahl der Dateien darin) und
    Dateien, neueste zuerst. Ordner aus der Ausblendeliste und der Unterordner
    ACOS (kommt aus ACOS) erscheinen nicht."""
    f = core._q1("SELECT id, name FROM firmen WHERE id=%s", (int(firma_id),))
    if not f:
        raise FileNotFoundError(f"Firma nicht gefunden: {firma_id}")
    pfad = (pfad or "").strip("/")
    if ".." in pfad.split("/") or (pfad.split("/")[0] == "ACOS"):
        raise ValueError("Ungültiger Ordner")
    aus_liste = {w.lower() for w in ausgeblendete_ordner()}
    basis = f["name"] + ("/" + pfad if pfad else "")
    try:
        ablage = Ablage()
        if not pfad and not ablage.gibt_es(f["name"]):
            return {"ok": False, "meldung": f"Kundenordner „{f['name']}“ fehlt unter /{core.kunden_ablage_basis()}.",
                    "pfad": pfad, "ordner": [], "dateien": [], "ausgeblendet": []}
        ordner, dateien = ablage.ordner_inhalt(basis)
        unter, versteckt = [], []
        for o in sorted(ordner, key=lambda o: o["name"].lower()):
            if not pfad and o["name"] == "ACOS":
                continue
            if o["name"].lower() in aus_liste:
                versteckt.append(o["name"])
                continue
            try:
                u_ordner, u_dateien = ablage.ordner_inhalt(o["pfad"])
                anzahl, u_anzahl = len(u_dateien), len(u_ordner)
            except urllib.error.HTTPError:
                anzahl, u_anzahl = None, None
            unter.append({"name": o["name"], "pfad": (pfad + "/" if pfad else "") + o["name"],
                          "dateien": anzahl, "unterordner": u_anzahl})
    except AcosFehler as e:
        return {"ok": False, "meldung": str(e), "pfad": pfad, "ordner": [], "dateien": [], "ausgeblendet": []}
    except urllib.error.HTTPError as e:
        meldung = "Ordner nicht gefunden" if e.code == 404 else f"Nextcloud meldet Fehler {e.code}"
        return {"ok": False, "meldung": meldung, "pfad": pfad, "ordner": [], "dateien": [], "ausgeblendet": []}
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "meldung": f"Nextcloud nicht erreichbar ({e.__class__.__name__})",
                "pfad": pfad, "ordner": [], "dateien": [], "ausgeblendet": []}
    gesendet = {}
    for r in core._q("""SELECT DISTINCT ON (pfad) pfad, etag, status, meldung,
                               to_char(gesendet_am AT TIME ZONE 'Europe/Berlin', 'DD.MM.YYYY') AS am
                        FROM acos_uploads WHERE firma_id=%s ORDER BY pfad, id DESC""", (f["id"],)):
        gesendet[r["pfad"]] = r
    aus = []
    jetzt = datetime.now().astimezone()
    for d in sorted(dateien, key=lambda d: d["geaendert_am"] or datetime.min.replace(tzinfo=jetzt.tzinfo), reverse=True):
        rel = (pfad + "/" if pfad else "") + d["name"]
        g = gesendet.get(rel)
        endung = Path(d["name"]).suffix.lower()
        aus.append({"pfad": rel, "name": d["name"], "groesse": d["groesse"],
                    "geaendert": d["geaendert_am"].astimezone().strftime("%d.%m.%Y") if d["geaendert_am"] else "",
                    "alter_tage": (jetzt - d["geaendert_am"]).days if d["geaendert_am"] else None,
                    "zu_gross": bool(d["groesse"] and d["groesse"] > MAX_UPLOAD), "lesbar": endung in LESBAR,
                    "gesendet_am": g["am"] if g and g["status"] == "gesendet" else "",
                    "geaendert_seit_senden": bool(g and g["status"] == "gesendet" and g["etag"] and g["etag"] != d["etag"]),
                    "fehler": g["meldung"] if g and g["status"] == "fehler" else ""})
    in_acos = core._q1("SELECT count(DISTINCT pfad) AS n FROM acos_uploads WHERE firma_id=%s AND status='gesendet'", (f["id"],))["n"]
    return {"ok": True, "meldung": "", "pfad": pfad, "ordner": unter, "dateien": aus, "ausgeblendet": versteckt,
            "in_acos": in_acos}


def an_acos_senden(firma_id, pfad, username=None):
    f = core._q1("""SELECT f.id, f.name, v.acos_client_id, v.zustand FROM firmen f
                    LEFT JOIN acos_verknuepfung v ON v.firma_id=f.id WHERE f.id=%s""", (int(firma_id),))
    if not f:
        raise FileNotFoundError(f"Firma nicht gefunden: {firma_id}")
    if f["zustand"] != "bestaetigt" or not f["acos_client_id"]:
        raise ValueError("Erst das Unternehmen mit einem ACOS-Mandanten verknüpfen.")
    pfad = (pfad or "").strip("/")
    if not pfad or ".." in pfad.split("/") or pfad.split("/")[0] == "ACOS":
        raise ValueError("Ungültiger Dateipfad")
    rel = f"{f['name']}/{pfad}"
    name = pfad.rsplit("/", 1)[-1]
    mime = MIME.get(Path(name).suffix.lower(), "application/octet-stream")
    zeile = None
    try:
        ablage = Ablage()
        info = ablage.info(rel)
        if not info:
            raise ValueError("Datei nicht im Kundenordner gefunden")
        if info["groesse"] and info["groesse"] > MAX_UPLOAD:
            raise ValueError("Datei ist größer als 25 MB")
        daten, _ = ablage.hole(rel, MAX_UPLOAD)
        if len(daten) > MAX_UPLOAD:
            raise ValueError("Datei ist größer als 25 MB")
        zug = lade_acos_zugang()
        if not zug.get("ACOS_TOKEN") or not zug.get("ACOS_MCP_URL"):
            raise AcosFehler("Zugang zu ACOS fehlt (secrets/acos.env)")
        mcp = Mcp(zug["ACOS_MCP_URL"], zug["ACOS_TOKEN"])
        mcp.start()
        beschreibung = f"Aus dem Kundenordner der Nextcloud übertragen ({pfad})"
        if len(daten) <= DIREKT_UPLOAD:
            import base64
            res = mcp.aendern("am_acos_file_upload", {"client_id": f["acos_client_id"], "filename": name, "mime_type": mime,
                                                      "content_base64": base64.b64encode(daten).decode("ascii"),
                                                      "description": beschreibung})
        else:
            vor = mcp.aendern("am_acos_file_prepare_upload", {"client_id": f["acos_client_id"], "filename": name,
                                                             "mime_type": mime, "size_bytes": len(daten),
                                                             "description": beschreibung})
            url = _feld(vor, "upload_url", "url", "put_url", "upload.url")
            file_id = _feld(vor, "file_id", "file.id", "id")
            if not url or not file_id:
                raise AcosFehler("ACOS hat keine Upload-Adresse geliefert")
            kopf = {"Content-Type": mime}
            extra = _feld(vor, "headers", "upload_headers", "upload.headers")
            if isinstance(extra, dict):
                kopf.update({str(k): str(v) for k, v in extra.items()})
            req = urllib.request.Request(url, data=daten, method=str(_feld(vor, "method", "upload_method") or "PUT"), headers=kopf)
            try:
                with urllib.request.urlopen(req, timeout=300):
                    pass
            except urllib.error.HTTPError as e:
                raise AcosFehler(f"Hochladen abgelehnt ({e.code})")
            res = mcp.aendern("am_acos_file_attach", {"file_id": file_id, "description": beschreibung})
        doc_id = str(_feld(res if isinstance(res, dict) else {}, "document_id", "object_id", "document.id", "id") or "")
        file_id = str(_feld(res if isinstance(res, dict) else {}, "file_id", "file.id", "fileId") or "")
        zeile = core._x("""INSERT INTO acos_uploads (firma_id, pfad, groesse, etag, acos_client_id, acos_file_id,
                                                    acos_document_id, status, gesendet_von)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,'gesendet',%s) RETURNING id""",
                        (f["id"], pfad, len(daten), info["etag"], f["acos_client_id"], file_id or None, doc_id or None, username))
        core._x("""INSERT INTO aktivitaeten (firma_id, art, datum, quelle, titel, notiz, payload)
                   VALUES (%s,'acos',CURRENT_DATE,'acos',%s,%s,%s)""",
                (f["id"], name, f"Dokument an ACOS gesendet: {pfad}",
                 json.dumps({"pfad": pfad, "acos_document_id": doc_id or None})))
        return {"ok": True, "meldung": f"„{name}“ ist in ACOS.", "lesbar": Path(name).suffix.lower() in LESBAR}
    except (AcosFehler, ValueError, urllib.error.URLError, OSError) as e:
        meldung = str(e) if isinstance(e, (AcosFehler, ValueError)) else f"Nextcloud nicht erreichbar ({e.__class__.__name__})"
        if zeile is None:
            core._x("""INSERT INTO acos_uploads (firma_id, pfad, acos_client_id, status, meldung, gesendet_von)
                       VALUES (%s,%s,%s,'fehler',%s,%s)""", (f["id"], pfad, f["acos_client_id"], meldung[:300], username))
        return {"ok": False, "meldung": meldung}


def dateiname(datum, titel):
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", titel or "Ohne Titel")
    t = re.sub(r"\s+", " ", t).strip(" .")[:120] or "Ohne Titel"
    return f"{datum:%Y-%m-%d} {t}"


def inhalt_holen(mcp, acos_id):
    res = mcp.lesen("am_acos_knowledge_get", {"id": acos_id, "content_limit": 24000})
    if isinstance(res, dict) and "data_slice" in res:
        teile, gesamt, pos = [res["data_slice"]], int(res.get("data_total_length") or 0), len(res["data_slice"])
        while pos < gesamt:
            r = mcp.lesen("am_acos_knowledge_get", {"id": acos_id, "content_offset": pos, "content_limit": 24000})
            stueck = r.get("data_slice") or ""
            if not stueck:
                break
            teile.append(stueck)
            pos += len(stueck)
        try:
            res = dict(res, data=json.loads("".join(teile)))
        except ValueError:
            res = dict(res, data={"text": "".join(teile)})
    daten = res.get("data", res) if isinstance(res, dict) else res
    if isinstance(daten, dict):
        for k in ("markdown", "content", "body", "text"):
            if isinstance(daten.get(k), str) and daten[k].strip():
                return daten[k]
    return "```json\n" + json.dumps(daten, ensure_ascii=False, indent=2) + "\n```"


# ── Lauf ─────────────────────────────────────────────────────────────────────

def modus():
    return "scharf" if core._system_raw().get("acos_modus") == "scharf" else "trocken"


def _verkn(firma_id, **felder):
    spalten = list(felder)
    werte = [json.dumps(v) if k == "vorschlaege" else v for k, v in felder.items()]
    core._x(f"""INSERT INTO acos_verknuepfung (firma_id, {', '.join(spalten)}, updated_at)
                VALUES (%s, {', '.join('%s' for _ in spalten)}, now())
                ON CONFLICT (firma_id) DO UPDATE SET {', '.join(f'{s}=EXCLUDED.{s}' for s in spalten)}, updated_at=now()""",
            [firma_id] + werte)


def abgleich(ausgeloest_von="timer"):
    md = modus()
    scharf = md == "scharf"
    lauf = core._x("INSERT INTO acos_laeufe (modus, ausgeloest_von) VALUES (%s,%s) RETURNING id",
                   (md, ausgeloest_von))[0]["id"]
    zahl = {"vorschlaege": 0, "angelegt": 0, "gesendet": 0, "archiviert": 0, "wissen_neu": 0, "abgelegt": 0, "fehler": 0}
    bericht = []

    def notiz(firma, aktion, text):
        bericht.append({"firma": firma, "aktion": aktion, "text": text})
        log(f"{firma}: {aktion} - {text}")

    ok, meldung = True, ""
    try:
        zug = lade_acos_zugang()
        if not zug.get("ACOS_TOKEN") or not zug.get("ACOS_MCP_URL"):
            raise AcosFehler("Zugang fehlt: secrets/acos.env mit ACOS_TOKEN und ACOS_MCP_URL anlegen")
        mcp = Mcp(zug["ACOS_MCP_URL"], zug["ACOS_TOKEN"])
        mcp.start()
        mandanten = [mandant(c) for c in _liste(mcp.lesen("am_acos_clients_list"))]
        nach_id = {m["id"]: m for m in mandanten if m["id"]}

        firmen = core._q("""
            SELECT f.id, f.name, f.status, f.branch, f.address, f.acos_fuehren, f.archiviert_am,
                   v.zustand, v.acos_client_id, v.anlegen, v.pruefwert
            FROM firmen f LEFT JOIN acos_verknuepfung v ON v.firma_id = f.id
            WHERE f.acos_fuehren OR v.zustand IN ('vorgeschlagen', 'bestaetigt')
            ORDER BY f.name""")
        belegt = {f["acos_client_id"] for f in firmen if f["zustand"] == "bestaetigt" and f["acos_client_id"]}

        ablage, ablage_fehler = None, ""
        try:
            ablage = Ablage()
        except AcosFehler as e:
            ablage_fehler = str(e)
        abgelegt_gesamt = 0

        for f in firmen:
            name, fid = f["name"], f["id"]
            zustand = f["zustand"] or "offen"
            aktiv = f["acos_fuehren"] and f["archiviert_am"] is None
            try:
                # ── ausgeschaltet oder archiviert ──
                if not aktiv:
                    if zustand == "bestaetigt" and f["acos_client_id"]:
                        m = nach_id.get(f["acos_client_id"])
                        if m and m["status"] != "archived":
                            if scharf:
                                mcp.aendern("am_acos_clients_save", {"client_id": f["acos_client_id"], "status": "archived"})
                            notiz(name, "archivieren", ("Mandant in ACOS archiviert" if scharf else "würde den Mandanten in ACOS archivieren")
                                  + (" (Unternehmen im CRM archiviert)" if f["archiviert_am"] else " (Schalter aus)"))
                            zahl["archiviert"] += 1
                        if scharf or not m or m["status"] == "archived":
                            _verkn(fid, zustand="beendet", meldung=None, letzter_abgleich=datetime.now().astimezone())
                    elif zustand in ("vorgeschlagen", "bestaetigt"):
                        _verkn(fid, zustand="offen", vorschlaege=[], anlegen=False, meldung=None)
                    continue

                # ── zuordnen ──
                if zustand in ("offen", "vorgeschlagen", "beendet") or (zustand == "bestaetigt" and not f["acos_client_id"] and not f["anlegen"]):
                    vs = vorschlaege_fuer(name, mandanten, belegt)
                    if vs:
                        txt = f"{len(vs)} möglicher Treffer in ACOS" if len(vs) == 1 else f"{len(vs)} mögliche Treffer in ACOS"
                        txt += ": " + ", ".join(v["name"] for v in vs) + ". Bitte im Unternehmen bestätigen."
                    else:
                        txt = "Kein Mandant mit diesem Namen in ACOS. Im Unternehmen „Neu in ACOS anlegen“ bestätigen."
                    _verkn(fid, zustand="vorgeschlagen", vorschlaege=vs, meldung=None,
                           letzter_abgleich=datetime.now().astimezone())
                    notiz(name, "vorschlag", txt)
                    zahl["vorschlaege"] += 1
                    continue

                # ── neu anlegen (bestaetigt) ──
                d_neu = nutzdaten(f)
                if f["anlegen"] and not f["acos_client_id"]:
                    if scharf:
                        res = mcp.aendern("am_acos_clients_save", d_neu)
                        neu_id = str(_feld(res if isinstance(res, dict) else {}, "id", "client_id", "client.id") or "")
                        if not neu_id:
                            raise AcosFehler("ACOS hat beim Anlegen keine Mandanten-ID zurückgegeben")
                        _verkn(fid, acos_client_id=neu_id, acos_name=name, anlegen=False,
                               pruefwert=pruefwert(nutzdaten(f, neu_id)), meldung=None,
                               letzter_abgleich=datetime.now().astimezone())
                        notiz(name, "angelegt", "Mandant in ACOS angelegt")
                    else:
                        notiz(name, "anlegen", "würde in ACOS anlegen: " + json.dumps(d_neu, ensure_ascii=False))
                    zahl["angelegt"] += 1
                    continue

                cid = f["acos_client_id"]
                m = nach_id.get(cid)
                if not m:
                    _verkn(fid, meldung="Der verknüpfte Mandant ist in ACOS nicht mehr zu finden.",
                           letzter_abgleich=datetime.now().astimezone())
                    notiz(name, "fehler", "verknüpfter Mandant in ACOS nicht gefunden")
                    zahl["fehler"] += 1
                    continue

                # ── Stammdaten senden ──
                d = nutzdaten(f, cid)
                pw = pruefwert(d)
                if pw != f["pruefwert"] or m["status"] == "archived":
                    if m["status"] == "archived" and "status" not in d:
                        d["status"] = "lead"
                    teile = [k for k in d if k != "client_id"]
                    if scharf:
                        mcp.aendern("am_acos_clients_save", d)
                        _verkn(fid, pruefwert=pw)
                    aenderung = ""
                    if m["name"] != name:
                        aenderung = f" – Name in ACOS bisher „{m['name']}“"
                    notiz(name, "senden", ("gesendet: " if scharf else "würde senden: ") + ", ".join(teile)
                          + (f" (Status {d['status']})" if "status" in d else "") + aenderung)
                    zahl["gesendet"] += 1

                # ── Wissensobjekte (additiv) ──
                antwort = mcp.lesen("am_acos_knowledge_list", {"client_id": cid, "limit": 200})
                objekte = [wissensobjekt(k) for k in _liste(antwort)]
                abgeschnitten = isinstance(antwort, dict) and bool(antwort.get("truncated"))
                gesehen = []
                for o in objekte:
                    if not o["id"]:
                        continue
                    gesehen.append(o["id"])
                    r = core._x("""
                        INSERT INTO acos_artefakte (firma_id, quelle, acos_id, titel, art, acos_erstellt_am,
                                                    acos_geaendert_am, acos_projekt, acos_link)
                        VALUES (%s,'wissen',%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (quelle, acos_id) DO UPDATE SET zuletzt_gesehen = now(), firma_id = EXCLUDED.firma_id,
                            titel = EXCLUDED.titel, acos_projekt = EXCLUDED.acos_projekt,
                            acos_link = COALESCE(EXCLUDED.acos_link, acos_artefakte.acos_link),
                            status = CASE WHEN acos_artefakte.status = 'entfernt' THEN 'neu' ELSE acos_artefakte.status END
                        RETURNING (xmax = 0) AS neu""",
                        (fid, o["id"], o["titel"], o["art"], o["erstellt"], o["geaendert"], o["projekt"], o["link"]))
                    if r and r[0]["neu"]:
                        zahl["wissen_neu"] += 1
                if abgeschnitten:
                    # ACOS liefert hoechstens 200 je Abruf - dann nichts als entfernt markieren
                    notiz(name, "hinweis", "mehr als 200 Wissensobjekte in ACOS, nur die ersten 200 übernommen")
                else:
                    core._x("""UPDATE acos_artefakte SET status='entfernt' WHERE firma_id=%s AND quelle='wissen'
                               AND status <> 'entfernt' AND NOT (acos_id = ANY(%s))""", (fid, gesehen or ["-"]))

                # Dokumente, die das CRM selbst aus dem Kundenordner gesendet hat, liegen
                # dort schon im Original - nicht noch einmal ablegen.
                core._x("""UPDATE acos_artefakte a SET status='abgelegt', meldung=NULL, abgelegt_am=coalesce(a.abgelegt_am, u.gesendet_am),
                               nextcloud_pfad=%s || '/' || u.pfad
                           FROM acos_uploads u
                           WHERE a.firma_id=%s AND u.firma_id=a.firma_id AND u.status='gesendet' AND a.status <> 'abgelegt'
                             AND (u.acos_document_id = a.acos_id
                                  OR (u.acos_document_id IS NULL AND a.titel = regexp_replace(u.pfad, '^.*/', '')))""",
                        (f"{core.kunden_ablage_basis()}/{name}", fid))

                # ── Ablage in der Nextcloud ──
                offen = core._q("""SELECT id, acos_id, titel, art,
                                          coalesce(acos_erstellt_am, acos_geaendert_am, erstmals_gesehen) AS datum
                                   FROM acos_artefakte WHERE firma_id=%s AND status IN ('neu','fehler')
                                   ORDER BY datum""", (fid,))
                dokumente = [a for a in offen if (a["art"] or "") == "document"]
                if dokumente:
                    # Hochgeladene Dateien: knowledge_get liefert nur Metadaten, die Datei selbst
                    # kommt ueber die Datei-Werkzeuge - folgt in einem spaeteren Schritt.
                    core._x("""UPDATE acos_artefakte SET meldung='Datei aus ACOS – Ablage folgt in einem späteren Schritt'
                               WHERE id = ANY(%s)""", ([a["id"] for a in dokumente],))
                    offen = [a for a in offen if a not in dokumente]
                meldung_firma = None
                if offen:
                    if ablage is None:
                        meldung_firma = ablage_fehler
                        notiz(name, "ablage", f"{len(offen)} Wissensobjekt(e) warten: {ablage_fehler}")
                    elif not ablage.gibt_es(name):
                        meldung_firma = f"Kundenordner „{name}“ fehlt unter /{core.kunden_ablage_basis()}. Bitte von Hand anlegen."
                        core._x("UPDATE acos_artefakte SET meldung=%s WHERE firma_id=%s AND status IN ('neu','fehler')",
                                ("Kundenordner fehlt in der Nextcloud", fid))
                        notiz(name, "ablage", f"{len(offen)} Wissensobjekt(e) warten, Kundenordner fehlt")
                    else:
                        for a in offen:
                            if abgelegt_gesamt >= MAX_ABLAGE_JE_LAUF:
                                break
                            datum = a["datum"].astimezone() if a["datum"] else datetime.now().astimezone()
                            basisname = dateiname(datum, a["titel"])
                            rel_ordner = f"{name}/ACOS/Wissen"
                            if not scharf:
                                notiz(name, "ablage", f"würde ablegen: /{core.kunden_ablage_basis()}/{rel_ordner}/{basisname}.md")
                                continue
                            try:
                                text = inhalt_holen(mcp, a["acos_id"])
                                kopf = (f"# {a['titel'] or 'Ohne Titel'}\n\n"
                                        f"*Aus ACOS übernommen am {date.today():%d.%m.%Y}, Wissensobjekt {a['acos_id']}.*\n\n")
                                ablage.ordner(f"{name}/ACOS")
                                ablage.ordner(rel_ordner)
                                ziel, nr = f"{rel_ordner}/{basisname}.md", 1
                                while ablage.gibt_es(ziel):
                                    nr += 1
                                    ziel = f"{rel_ordner}/{basisname} ({nr}).md"
                                ablage.datei(ziel, (kopf + text).encode("utf-8"))
                                pfad = f"{core.kunden_ablage_basis()}/{ziel}"
                                core._x("""UPDATE acos_artefakte SET status='abgelegt', nextcloud_pfad=%s, abgelegt_am=now(),
                                           meldung=NULL WHERE id=%s""", (pfad, a["id"]))
                                core._x("""INSERT INTO aktivitaeten (firma_id, art, datum, quelle, titel, notiz, payload)
                                           VALUES (%s,'acos',CURRENT_DATE,'acos',%s,%s,%s)""",
                                        (fid, a["titel"], f"Neues Wissensobjekt aus ACOS, abgelegt unter /{pfad}",
                                         json.dumps({"acos_id": a["acos_id"], "nextcloud_pfad": pfad})))
                                notiz(name, "ablage", f"abgelegt: /{pfad}")
                                zahl["abgelegt"] += 1
                                abgelegt_gesamt += 1
                            except Exception as e:  # eine Datei darf den Lauf nicht abbrechen
                                fehler = f"{e.__class__.__name__}: {e}"[:300]
                                core._x("UPDATE acos_artefakte SET status='fehler', meldung=%s WHERE id=%s", (fehler, a["id"]))
                                notiz(name, "fehler", f"Ablage fehlgeschlagen: {a['titel']} ({fehler})")
                                zahl["fehler"] += 1
                _verkn(fid, acos_name=m["name"], meldung=meldung_firma, letzter_abgleich=datetime.now().astimezone())
            except AcosFehler as e:
                _verkn(fid, meldung=str(e)[:300], letzter_abgleich=datetime.now().astimezone())
                notiz(name, "fehler", str(e))
                zahl["fehler"] += 1

        if not firmen:
            meldung = "Kein Unternehmen ist als „In ACOS führen“ markiert."
        else:
            meldung = ("Trockenlauf: nichts nach ACOS oder in die Nextcloud geschrieben." if not scharf else "Abgleich ausgeführt.")
    except AcosFehler as e:
        ok, meldung = False, str(e)
        log(meldung)
    except Exception as e:
        ok, meldung = False, f"Unerwarteter Fehler: {e.__class__.__name__}: {e}"[:500]
        log(traceback.format_exc())
    core._x("UPDATE acos_laeufe SET ende=now(), ok=%s, meldung=%s, zahlen=%s, bericht=%s WHERE id=%s",
            (ok, meldung, json.dumps(zahl), json.dumps(bericht, ensure_ascii=False), lauf))
    core._x("DELETE FROM acos_laeufe WHERE id < %s - 200", (lauf,))
    return ok


def struktur():
    """Zeigt nur Feldnamen und Typen der ACOS-Antworten, keine Inhalte."""
    def form(o, tiefe=0):
        if isinstance(o, dict):
            return {k: form(v, tiefe + 1) for k, v in o.items()} if tiefe < 3 else "{…}"
        if isinstance(o, list):
            return [form(o[0], tiefe + 1), f"… {len(o)} Einträge"] if o else []
        return type(o).__name__
    zug = lade_acos_zugang()
    mcp = Mcp(zug["ACOS_MCP_URL"], zug["ACOS_TOKEN"])
    mcp.start()
    print("Werkzeuge direkt erreichbar:", len(mcp.werkzeuge))
    for w in ("am_acos_clients_list", "am_acos_knowledge_list", "am_acos_knowledge_get", "am_acos_clients_save"):
        print(f"  {w}: {'direkt' if w in mcp.werkzeuge else 'über am_acos_call_tool/_action'}")
    c = mcp.lesen("am_acos_clients_list")
    print("am_acos_clients_list:", json.dumps(form(c), ensure_ascii=False, indent=1))
    liste = _liste(c)
    print("erkannte Mandanten:", len(liste), "- Felder erkannt:",
          {k: bool(v) for k, v in (mandant(liste[0]) if liste else {}).items()})
    for m in liste[:10]:
        cid = mandant(m)["id"]
        k = mcp.lesen("am_acos_knowledge_list", {"client_id": cid, "limit": 5})
        if _liste(k):
            print("am_acos_knowledge_list:", json.dumps(form(k), ensure_ascii=False, indent=1))
            print("Felder erkannt:", {kk: vv is not None and vv != "" for kk, vv in wissensobjekt(_liste(k)[0]).items()})
            break
    else:
        print("am_acos_knowledge_list: bei den ersten Mandanten keine Wissensobjekte gefunden")


def main():
    if "--struktur" in sys.argv:
        struktur()
        return 0
    ausgeloest = next((a for a in sys.argv[1:] if not a.startswith("-")), "timer")
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Abgleich läuft bereits - beende.")
            return 0
        return 0 if abgleich(ausgeloest) else 1


if __name__ == "__main__":
    sys.exit(main())
