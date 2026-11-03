#!/usr/bin/env python3
"""
mail_poller.py – IMAP-Postfach-Poller fuer die CRM-Mail-Anbindung
====================================================================
Eigener, schlanker Hintergrund-Prozess (Konzept 1.2/1.3): fragt das
konfigurierte IMAP-Postfach in regelmaessigen Abstaenden nach neuen Mails ab
und meldet jede neue Mail per HTTP an POST /api/mail-intake auf dem lokal
laufenden crm_serve.py. Die eigentliche Fachlogik (Kontakt-Zuordnung,
LLM-Bewertung, Review-Warteschlange) steckt bewusst NICHT hier, sondern in
crm_core.py - dieses Skript ist reine Poller/Transport-Logik, austauschbar
gegen einen spaeteren n8n-Workflow, der dieselbe Schnittstelle aufruft
(Konzept 1.3, Ergaenzung 2026-07-25).

Nutzt ausschliesslich Python-Stdlib (imaplib, email) - keine neue
Abhaengigkeit, passt zur bestehenden Low-Dependency-Philosophie.

Betrieb: eigener systemd-Service (crm-mailpoll.service), unabhaengig vom
Dashboard-Prozess - ein Absturz/Neustart des Pollers beeintraechtigt das
Dashboard nicht und umgekehrt.
"""

import email
import imaplib
import json
import os
import sys
import time
import traceback
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crm_core as core

STATE_FILE = core.BASE_DIR / "secrets" / "poller_state.json"
API_BASE = os.environ.get("CRM_API_BASE", "http://127.0.0.1:%s" % os.environ.get("CRM_PORT", "8080"))
REVIEW_RETENTION_DAYS = 90  # Konzept 1.7 - unbestaetigte Review-Eintraege nicht ewig aufbewahren


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def decode_mime_words(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _html_zu_text(html_text):
    """Einfacher HTML-zu-Text-Wandler (Stdlib) fuer Mails ohne text/plain-Teil."""
    from html.parser import HTMLParser
    import re
    class _P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.teile, self.weg = [], 0
        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "head"):
                self.weg += 1
            elif tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"):
                self.teile.append("\n")
        def handle_endtag(self, tag):
            if tag in ("script", "style", "head"):
                self.weg = max(0, self.weg - 1)
            elif tag in ("p", "div", "tr", "li", "table", "h1", "h2", "h3"):
                self.teile.append("\n")
        def handle_data(self, data):
            if not self.weg:
                self.teile.append(data)
    p = _P()
    try:
        p.feed(html_text)
    except Exception:
        return ""
    text = re.sub(r"[ \t\xa0]+", " ", "".join(p.teile))
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_body(msg):
    def _dekodiert(part):
        try:
            return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            return None
    if msg.is_multipart():
        # bevorzugt text/plain, sonst der HTML-Teil als Text
        plain = html = None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and plain is None:
                plain = _dekodiert(part)
            elif ctype == "text/html" and html is None:
                html = _dekodiert(part)
        return plain or (_html_zu_text(html) if html else "")
    text = _dekodiert(msg) or ""
    return _html_zu_text(text) if msg.get_content_type() == "text/html" else text


# ── Anhaenge (Migration 009, 2026-10-26) ─────────────────────────────────────
ANHANG_MAX = 25 * 1024 * 1024
ANHANG_UEBERSPRINGEN_TYP = {"text/calendar", "application/pkcs7-signature", "application/x-pkcs7-signature",
                            "text/vcard", "text/x-vcard", "application/ms-tnef"}
ANHANG_UEBERSPRINGEN_ENDUNG = {".ics", ".p7s", ".vcf", ".p7m"}


def _sicherer_name(name):
    import re
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name or "Anhang").strip(" .")
    return (n or "Anhang")[:150]


def anhaenge_sichern(msg):
    """Legt Anhaenge vorlaeufig unter secrets/mail-anhaenge/<zufall>/ ab (nur
    crmapp) und liefert die Liste fuer /api/mail-intake. Signatur-Logos,
    Kalendereintraege, Visitenkarten und Signaturdateien werden uebersprungen."""
    import os, uuid
    from pathlib import Path
    liste, ordner = [], None
    for part in msg.walk():
        if part.is_multipart():
            continue
        name = part.get_filename()
        if not name:
            continue
        name = decode_mime_words(name)
        ctype = (part.get_content_type() or "application/octet-stream").lower()
        endung = Path(name).suffix.lower()
        if ctype in ANHANG_UEBERSPRINGEN_TYP or endung in ANHANG_UEBERSPRINGEN_ENDUNG or name.lower() == "winmail.dat":
            continue
        try:
            daten = part.get_payload(decode=True) or b""
        except Exception:
            continue
        disp = str(part.get("Content-Disposition") or "").lower()
        if ctype.startswith("image/") and (part.get("Content-ID") or disp.startswith("inline")) and len(daten) < 100_000:
            continue   # eingebettetes Bild, meist Logo in der Signatur
        eintrag = {"name": name, "mime": ctype, "groesse": len(daten), "datei": None, "hinweis": None}
        if len(daten) > ANHANG_MAX:
            eintrag["hinweis"] = "größer als 25 MB, nicht übernommen"
        elif daten:
            if ordner is None:
                ordner = uuid.uuid4().hex
                pfad = core.ANHANG_DIR / ordner
                pfad.mkdir(parents=True, exist_ok=True)
                os.chmod(core.ANHANG_DIR, 0o700)
                os.chmod(pfad, 0o700)
            datei = f"{ordner}/{len(liste):02d}_{_sicherer_name(name)}"
            ziel = core.ANHANG_DIR / datei
            fd = os.open(ziel, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(daten)
            eintrag["datei"] = datei
        else:
            continue
        liste.append(eintrag)
    return liste


# ── ORDNER (Umbau Schritt 9, 2026-10-31) ─────────────────────────────────────
# Gelesen werden Posteingang und Gesendet. Das Postfach wird nur lesend
# geoeffnet (EXAMINE) und Mails mit BODY.PEEK geholt: Der Abruf setzt kein
# "gelesen"-Flag und veraendert nichts im Postfach.
SENT_NAMEN = ["Sent", "INBOX.Sent", "Gesendet", "INBOX.Gesendet", "Gesendete Objekte", "INBOX.Gesendete Objekte",
              "Gesendete Elemente", "Sent Items", "Sent Messages", "INBOX/Sent"]


def _ordnerliste(conn):
    """[(name, flags)] aus IMAP LIST."""
    import re
    typ, data = conn.list()
    if typ != "OK":
        return []
    out = []
    for zeile in data or []:
        if isinstance(zeile, tuple):
            zeile = b" ".join(x for x in zeile if isinstance(x, bytes))
        if not isinstance(zeile, bytes):
            continue
        m = re.match(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$', zeile)
        if not m:
            continue
        name = m.group("name").strip()
        if name.startswith(b'"') and name.endswith(b'"'):
            name = name[1:-1].replace(b'\\"', b'"')
        out.append((name.decode("utf-8", errors="replace"), m.group("flags").decode("ascii", errors="replace")))
    return out


def gesendet_ordner(conn, secrets):
    wunsch = (secrets.get("IMAP_SENT_FOLDER") or "").strip()
    ordner = _ordnerliste(conn)
    namen = [n for n, _ in ordner]
    if wunsch:
        return wunsch if wunsch in namen else None
    for n, flags in ordner:
        if "\\sent" in flags.lower():
            return n
    for kandidat in SENT_NAMEN:
        for n in namen:
            if n.lower() == kandidat.lower():
                return n
    return None


def _eigene_adressen(secrets):
    eigene = {(secrets.get("IMAP_USER") or "").strip().lower()}
    for a in (secrets.get("MAIL_EIGENE_ADRESSEN") or "").split(","):
        if a.strip():
            eigene.add(a.strip().lower())
    return {a for a in eigene if "@" in a}


def _quote(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ordner_oeffnen(conn, name):
    typ, _ = conn.select(_quote(name), readonly=True)
    if typ != "OK":
        return None
    typ, val = conn.response("UIDVALIDITY")
    try:
        return int(val[0]) if val and val[0] else 0
    except (TypeError, ValueError):
        return 0


def _hoechste_uid(conn):
    typ, data = conn.uid("search", None, "ALL")
    if typ != "OK" or not data or not data[0]:
        return 0
    return max(int(u) for u in data[0].split())


def _newsletter(msg):
    prec = (msg.get("Precedence") or "").strip().lower()
    return bool(msg.get("List-Unsubscribe")) or prec in ("bulk", "list", "junk")


def _imap_datum(d):
    monate = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{d.day:02d}-{monate[d.month - 1]}-{d.year}"


def _uids_melden(conn, name, richtung, uids, zustand, eigene):
    """Mails mit diesen UIDs holen (ohne Gelesen-Markierung) und ans CRM melden."""
    for uid in uids:
        typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        message_id = (msg.get("Message-ID") or "").strip()
        sender_name, sender_email = email.utils.parseaddr(msg.get("From") or "")
        sender_name = decode_mime_words(sender_name or "")
        empfaenger = [a.strip().lower() for _, a in email.utils.getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []))
                      if a and "@" in a]
        ich = eigene | ({(sender_email or "").strip().lower()} if richtung == "aus" else set())
        empfaenger = [a for a in empfaenger if a not in ich]
        try:
            mail_date = email.utils.parsedate_to_datetime(msg.get("Date") or "").date().isoformat()
        except Exception:
            mail_date = datetime.now().date().isoformat()
        try:
            anhaenge = anhaenge_sichern(msg)
        except Exception as e:
            log(f"Anhaenge konnten nicht gesichert werden: {e}")
            anhaenge = []
        ok = _post_mail_intake({
            "anhaenge": anhaenge,
            "message_id": message_id,
            "from": sender_email,
            "from_name": sender_name,
            "subject": decode_mime_words(msg.get("Subject") or ""),
            "date": mail_date,
            "body": extract_body(msg),
            "richtung": richtung,
            "an": empfaenger,
            "ordner": name,
            "newsletter": _newsletter(msg),
            "reply_to": email.utils.parseaddr(msg.get("Reply-To") or "")[1],
        })
        if not ok:
            # CRM nicht erreichbar: Stand nicht weiterschieben, beim naechsten Abruf erneut
            break
        zustand["last_uid"] = max(int(zustand.get("last_uid", 0)), int(uid))
    return len(uids)


def _seit_tagen(conn, tage):
    seit = _imap_datum(datetime.now().date() - timedelta(days=tage))
    typ, data = conn.uid("search", None, f"SINCE {seit}")
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _ordner_abholen(conn, name, richtung, zustand, eigene, nur_zaehlen=False, nachholen_tage=0):
    """Neue Mails eines Ordners an /api/mail-intake melden. zustand wird angepasst.
    Ein Ordner, der zum ersten Mal (oder nach UIDVALIDITY-Wechsel) gelesen wird,
    startet beim aktuellen Stand. Nur bei einem neuen Postfach (nachholen_tage)
    werden die Mails der letzten Tage einmalig nachgeholt."""
    uidv = _ordner_oeffnen(conn, name)
    if uidv is None:
        log(f"Ordner {name!r} laesst sich nicht oeffnen.")
        return 0
    if zustand.get("uidvalidity") not in (None, uidv) or "last_uid" not in zustand:
        start = _hoechste_uid(conn)
        if nur_zaehlen:
            return 0
        zustand.update({"uidvalidity": uidv, "last_uid": start})
        log(f"Ordner {name!r}: ab jetzt beobachtet (Start bei UID {start}).")
        if nachholen_tage:
            alte = _seit_tagen(conn, nachholen_tage)
            if alte:
                log(f"{name}: {len(alte)} Mail(s) der letzten {nachholen_tage} Tage werden nachgeholt.")
                _uids_melden(conn, name, richtung, alte, zustand, eigene)
                zustand["last_uid"] = max(start, zustand["last_uid"])
        return 0
    zustand["uidvalidity"] = uidv
    last_uid = int(zustand.get("last_uid", 0))
    typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*")
    if typ != "OK":
        log(f"IMAP-SEARCH in {name!r} fehlgeschlagen: {typ}")
        return 0
    uids = [u for u in (data[0] or b"").split() if int(u) > last_uid]
    if nur_zaehlen or not uids:
        return len(uids)
    log(f"{name}: {len(uids)} neue Mail(s).")
    return _uids_melden(conn, name, richtung, uids, zustand, eigene)


NACHHOLEN_NEUES_POSTFACH = 14


def nachholen(secrets, tage):
    """Von Hand: Mails der letzten <tage> Tage aus Posteingang und Gesendet ans CRM melden.
    Schon bekannte Mails ueberspringt das CRM selbst (Message-ID)."""
    conn = imaplib.IMAP4_SSL(secrets.get("IMAP_HOST"), int(secrets.get("IMAP_PORT", "993")))
    state = load_state()
    try:
        conn.login(secrets.get("IMAP_USER"), secrets.get("IMAP_PASSWORD"))
        sent = gesendet_ordner(conn, secrets)
        for name, richtung in [("INBOX", "ein")] + ([(sent, "aus")] if sent else []):
            uidv = _ordner_oeffnen(conn, name)
            if uidv is None:
                continue
            uids = _seit_tagen(conn, tage)
            log(f"{name}: {len(uids)} Mail(s) der letzten {tage} Tage.")
            zustand = state.setdefault("ordner", {}).setdefault(name, {})
            if zustand.get("uidvalidity") not in (None, uidv):
                zustand.clear()
            zustand["uidvalidity"] = uidv
            zustand.setdefault("last_uid", _hoechste_uid(conn))
            _uids_melden(conn, name, richtung, uids, zustand, _eigene_adressen(secrets))
        state["konto"] = f"{secrets.get('IMAP_USER', '').strip().lower()}@{secrets.get('IMAP_HOST', '').strip().lower()}"
        save_state(state)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def poll_once(secrets, nur_pruefen=False):
    host = secrets.get("IMAP_HOST")
    port = int(secrets.get("IMAP_PORT", "993"))
    user = secrets.get("IMAP_USER")
    password = secrets.get("IMAP_PASSWORD")
    if not (host and user and password):
        log("Unvollstaendige IMAP-Zugangsdaten in secrets/mail.env - ueberspringe Zyklus.")
        return

    state = load_state()
    if "ordner" not in state:
        # Stand vor Umbau 9: nur last_uid fuer den Posteingang
        state["ordner"] = {"INBOX": {"uidvalidity": None, "last_uid": int(state.get("last_uid", 0))}} if "last_uid" in state else {}
    # Zustand gehoert zu genau einem Postfach. Wird in den Einstellungen ein anderes
    # eingetragen, beginnt der Abruf dort neu und holt die letzten 14 Tage einmal nach.
    konto = f"{user.strip().lower()}@{host.strip().lower()}"
    nachholen = 0
    if state.get("konto") and state["konto"] != konto:
        if not nur_pruefen:
            log(f"Anderes Postfach eingetragen ({konto}) - Abruf beginnt dort neu, die letzten {NACHHOLEN_NEUES_POSTFACH} Tage werden nachgeholt.")
        state["ordner"], nachholen = {}, NACHHOLEN_NEUES_POSTFACH
    state["konto"] = konto

    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        sent = gesendet_ordner(conn, secrets)
        if nur_pruefen:
            print(f"Anmeldung ok: {user}@{host}")
            print("Ordner im Postfach: " + ", ".join(n for n, _ in _ordnerliste(conn)))
            print(f"Gesendet-Ordner erkannt: {sent or 'KEINER (IMAP_SENT_FOLDER in mail.env setzen)'}")
        ordner = [("INBOX", "ein")] + ([(sent, "aus")] if sent else [])
        for name, richtung in ordner:
            zustand = state["ordner"].setdefault(name, {})
            n = _ordner_abholen(conn, name, richtung, zustand if not nur_pruefen else dict(zustand),
                                _eigene_adressen(secrets), nur_zaehlen=nur_pruefen, nachholen_tage=nachholen)
            if nur_pruefen:
                print(f"{name}: " + (f"{n} neue Mail(s) seit dem letzten Abruf" if "last_uid" in zustand
                                     else "wird beim ersten Abruf ab jetzt beobachtet (alte Mails werden nicht geholt)"))
        if not nur_pruefen:
            state.pop("last_uid", None)
            save_state(state)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _post_mail_intake(payload):
    req = urllib.request.Request(
        API_BASE + "/api/mail-intake",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Internal-Token": core.get_internal_token(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("skipped"):
            log(f"Übersprungen ({result.get('reason')}): {payload.get('subject')!r}")
        else:
            log(f"Verarbeitet: {payload.get('subject')!r} -> Kategorie {result.get('category')}")
        return True
    except Exception as e:
        log(f"FEHLER beim Melden an /api/mail-intake: {e} - wird beim nächsten Abruf erneut versucht")
        return False


def cleanup_stale_review_items():
    """Offene Review-Eintraege nach 90 Tagen ausblenden, erledigte nach 30 Tagen
    entfernen (Umbau Schritt 9; Logik in crm_core.mail_review_aufraeumen)."""
    n = core.mail_review_aufraeumen()
    if n:
        log(f"Mail-Review aufgeraeumt: {n} erledigte Eintraege entfernt.")


def main():
    interval_minutes = 10
    log(f"Mail-Poller gestartet, API-Basis: {API_BASE}")
    cycle = 0
    letzter_kalender = 0
    while True:
        try:
            # Seit Migration 004: Einstellungen > System hat Vorrang vor config.json
            mail_cfg = core.mail_settings()
            interval_minutes = mail_cfg["intervall"]
            if cycle % 12 == 0:
                try:
                    weg = core.mail_anhaenge_aufraeumen()
                    if weg:
                        log(f"Vorläufige Mail-Anhänge aufgeräumt: {weg}")
                except Exception as e:
                    log(f"Aufräumen der Mail-Anhänge fehlgeschlagen: {e}")
                try:
                    n = core.run_auto_archive()
                    if n:
                        log(f"Automatisch archiviert: {n} erledigte Aufgabe(n).")
                except Exception:
                    log("Auto-Archiv fehlgeschlagen:\n" + traceback.format_exc())
            # Kalender (Umbau Schritt 11): alle 15 Minuten, unabhaengig vom Mail-Abruf
            if time.time() - letzter_kalender >= 15 * 60:
                letzter_kalender = time.time()
                try:
                    import kalender
                    if kalender.eingerichtet():
                        r = kalender.abgleich()
                        if not r["ok"]:
                            log(f"Kalender: {r['meldung']}")
                        elif cycle % 12 == 0:
                            log(f"Kalender: {r['anzahl']} Termine im Zeitfenster.")
                except Exception:
                    log("Kalender-Abgleich fehlgeschlagen:\n" + traceback.format_exc())
            if not mail_cfg["aktiv"]:
                if cycle % 6 == 0:  # nicht bei jedem Zyklus loggen
                    log("Mail-Abruf ist ausgeschaltet (Einstellungen bzw. config.json) - warte.")
            else:
                secrets = core.load_secrets()
                poll_once(secrets)
                if cycle % 12 == 0:
                    cleanup_stale_review_items()
        except Exception:
            log("Unerwarteter Fehler im Poll-Zyklus:\n" + traceback.format_exc())
        cycle += 1
        time.sleep(max(60, interval_minutes * 60))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--nachholen":
        # Von Hand: sudo -u crmapp python3 /opt/crm/mail_poller.py --nachholen 30
        nachholen(core.load_secrets(), max(1, min(365, int(sys.argv[2]))))
    elif len(sys.argv) > 1 and sys.argv[1] == "--pruefen":
        # Nur lesen: Anmeldung, Ordner, Anzahl neuer Mails. Meldet nichts ans CRM,
        # schreibt keinen Zustand. Optional Pfad zu einer anderen mail.env.
        sec = core.load_secrets()
        if len(sys.argv) > 2:
            sec = {}
            for zeile in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if zeile and not zeile.startswith("#") and "=" in zeile:
                    k, _, v = zeile.partition("=")
                    sec[k.strip()] = v.strip()
            STATE_FILE = Path(sys.argv[2]).parent / "poller_state.json"
        poll_once(sec, nur_pruefen=True)
    else:
        main()
