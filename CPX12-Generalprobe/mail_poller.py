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


def extract_body(msg):
    if msg.is_multipart():
        # bevorzugt text/plain, sonst erste lesbare Alternative
        plain = None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and plain is None:
                try:
                    plain = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
        return plain or ""
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            return ""


def poll_once(secrets):
    host = secrets.get("IMAP_HOST")
    port = int(secrets.get("IMAP_PORT", "993"))
    user = secrets.get("IMAP_USER")
    password = secrets.get("IMAP_PASSWORD")
    if not (host and user and password):
        log("Unvollstaendige IMAP-Zugangsdaten in secrets/mail.env - ueberspringe Zyklus.")
        return

    state = load_state()
    last_uid = int(state.get("last_uid", 0))

    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        conn.select("INBOX")
        typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*")
        if typ != "OK":
            log(f"IMAP-SEARCH fehlgeschlagen: {typ}")
            return
        uids = [u for u in data[0].split() if int(u) > last_uid]
        if not uids:
            log("Keine neuen Mails.")
            return
        log(f"{len(uids)} neue Mail(s) gefunden.")

        max_uid = last_uid
        for uid in uids:
            typ, msg_data = conn.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            message_id = (msg.get("Message-ID") or "").strip()
            sender_raw = msg.get("From") or ""
            _, sender_email = email.utils.parseaddr(sender_raw)
            subject = decode_mime_words(msg.get("Subject") or "")
            date_hdr = msg.get("Date") or ""
            try:
                dt = email.utils.parsedate_to_datetime(date_hdr)
                mail_date = dt.date().isoformat()
            except Exception:
                mail_date = datetime.now().date().isoformat()
            body = extract_body(msg)

            payload = {
                "message_id": message_id,
                "from": sender_email,
                "subject": subject,
                "date": mail_date,
                "body": body,
            }
            _post_mail_intake(payload)
            max_uid = max(max_uid, int(uid))

        state["last_uid"] = max_uid
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
    except Exception as e:
        log(f"FEHLER beim Melden an /api/mail-intake: {e}")


def cleanup_stale_review_items():
    """Loescht unbestaetigte Review-Eintraege, die aelter als
    REVIEW_RETENTION_DAYS sind (Konzept 1.7 - Aufbewahrungsfrist fuer rohe
    Mailkopien/Auszuege)."""
    if not core.MAIL_QUEUE_DIR.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=REVIEW_RETENTION_DAYS)
    for item in core.load_mail_review_queue():
        try:
            received = datetime.fromisoformat(item["received_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if received < cutoff:
            core.discard_mail_review_item(item["id"])
            log(f"Review-Eintrag verworfen (>{REVIEW_RETENTION_DAYS} Tage unbestaetigt): {item.get('subject')!r}")


def main():
    interval_minutes = 10
    log(f"Mail-Poller gestartet, API-Basis: {API_BASE}")
    cycle = 0
    while True:
        try:
            cfg = core.load_config()
            mail_cfg = cfg.get("mail") or {}
            interval_minutes = mail_cfg.get("poll_interval_minutes", 10)
            if not mail_cfg.get("enabled"):
                if cycle % 6 == 0:  # nicht bei jedem Zyklus loggen
                    log("Mail-Anbindung in config.json deaktiviert (mail.enabled=false) - warte.")
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
    main()
