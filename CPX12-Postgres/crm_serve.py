#!/usr/bin/env python3
"""
crm_serve.py – CRM-Dashboard als dauerhaft laufender HTTP-Server (systemd)
============================================================================
Ersetzt fuer den Produktivbetrieb sowohl crm_server.py (macOS/launchd) als
auch crm_cgi.py (CGI/All-Inkl-Demo) durch eine dritte, gleichwertige
Transport-Schicht: ein dauerhaft laufender Prozess, gedacht fuer den
Betrieb unter systemd, mit Caddy als vorgeschaltetem Reverse-Proxy
(TLS + Login uebernimmt Caddy, siehe Caddyfile).

Die eigentliche Business-Logik (Dashboard-HTML, Datenzugriff, CRUD) steckt
unveraendert in crm_core.py – dieses Skript ist nur die Transport-Schicht,
genau wie crm_cgi.py es fuer CGI ist. Bewusst OHNE Angebote-Feature
(Entscheidung 2026-07-25: Angebote bleibt separat, nicht Teil des
Basissetups).

Bindet standardmaessig nur an 127.0.0.1 – von aussen ist der Dienst nur
ueber Caddy (Reverse-Proxy) erreichbar, nie direkt.
"""

import hmac
import http.cookies
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crm_core as core

HOST = os.environ.get("CRM_HOST", "127.0.0.1")
PORT = int(os.environ.get("CRM_PORT", "8080"))
COOKIE_SECURE = os.environ.get("CRM_COOKIE_SECURE", "1") != "0"

SESSION_COOKIE = "crm_session"
PUBLIC_PATHS = {"/healthz", "/login", "/manifest.webmanifest", "/apple-touch-icon.png",
                "/apple-touch-icon-precomposed.png", "/static/icon-192.png", "/static/icon-512.png"}
# Oeffentliche Icon-Dateien (Home-Bildschirm-Symbol), alles andere bleibt hinter dem Login
_STATIC_FILES = {"/apple-touch-icon.png": "apple-touch-icon.png",
                 "/apple-touch-icon-precomposed.png": "apple-touch-icon.png",
                 "/static/icon-192.png": "icon-192.png", "/static/icon-512.png": "icon-512.png"}
PUBLIC_API_PATHS = {"/api/login", "/api/logout"}
INTERNAL_TOKEN_PATHS = {"/api/mail-intake"}

_failed_logins = {}


def _login_delay(username):
    n = _failed_logins.get(username, 0)
    if n:
        time.sleep(min(n * 0.5, 3.0))


def _register_failed_login(username):
    _failed_logins[username] = _failed_logins.get(username, 0) + 1


def _register_login_success(username):
    _failed_logins.pop(username, None)


class CRMHandler(BaseHTTPRequestHandler):
    server_version = "CRMServe/1.0"

    def _send(self, status, reason, content_type, body_bytes, extra_headers=None):
        self.send_response(status, reason)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_json(self, data, status=200, reason="OK"):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(status, reason, "application/json; charset=utf-8", body)

    def _send_html(self, html):
        self._send(200, "OK", "text/html; charset=utf-8", html.encode("utf-8"))

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw)

    def log_message(self, fmt, *args):
        # Kompaktes Logging fuer journald/systemd statt Default-Format.
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- Auth -------------------------------------------------------------

    def _current_user(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
        except Exception:
            return None
        morsel = jar.get(SESSION_COOKIE)
        if not morsel:
            return None
        return core.verify_session_token(morsel.value)

    def _set_session_cookie(self, username):
        token = core.create_session_token(username)
        flags = "Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % core.SESSION_TTL_SECONDS
        if COOKIE_SECURE:
            flags += "; Secure"
        return ("Set-Cookie", f"{SESSION_COOKIE}={token}; {flags}")

    def _clear_session_cookie(self):
        flags = "Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        if COOKIE_SECURE:
            flags += "; Secure"
        return ("Set-Cookie", f"{SESSION_COOKIE}=; {flags}")

    def _check_internal_token(self):
        provided = self.headers.get("X-Internal-Token", "")
        expected = core.get_internal_token()
        return bool(provided) and hmac.compare_digest(provided, expected)

    def _enforce_auth(self, path, is_api):
        if path in PUBLIC_PATHS or path in PUBLIC_API_PATHS:
            return False
        if path in INTERNAL_TOKEN_PATHS:
            if self._check_internal_token():
                return False
            self._send_json({"error": "Unauthorized"}, 401, "Unauthorized")
            return True
        user = self._current_user()
        if user:
            # Fuer den audit_log-Eintrag jeder schreibenden Funktion in
            # crm_core.py (ThreadingHTTPServer -> ein Thread pro Request,
            # daher thread-lokal statt globaler Variable).
            core.set_current_actor(user)
            return False
        if is_api:
            self._send_json({"error": "Unauthorized"}, 401, "Unauthorized")
        else:
            self._send(303, "See Other", "text/plain", b"", extra_headers=[("Location", "/login")])
        return True

    # ---- Routing --------------------------------------------------------

    def do_OPTIONS(self):
        self._send(204, "No Content", "text/plain", b"", extra_headers=[
            ("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ])

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = path.strip("/").split("/")
        is_api = path.startswith("/api/")
        if self._enforce_auth(path, is_api):
            return
        try:
            if path in ("", "/"):
                self._send_html(core.build_dashboard())
            elif path == "/login":
                if self._current_user():
                    self._send(303, "See Other", "text/plain", b"", extra_headers=[("Location", "/")])
                else:
                    self._send_html(core.build_login_page())
            elif path == "/healthz":
                self._send_json({"ok": True})
            elif path == "/m":
                self._send_html(core.build_mobile())
            elif path == "/manifest.webmanifest":
                self._send(200, "OK", "application/manifest+json; charset=utf-8", core.MANIFEST_JSON.encode("utf-8"))
            elif path in _STATIC_FILES:
                datei = core.STATIC_DIR / _STATIC_FILES[path]
                if datei.exists():
                    self._send(200, "OK", "image/png", datei.read_bytes(),
                               extra_headers=[("Cache-Control", "public, max-age=604800")])
                else:
                    self._send_json({"error": "Not Found"}, 404, "Not Found")
            elif path == "/api/tasks":
                self._send_json(core.load_tasks())
            elif path == "/api/contacts":
                self._send_json(core.load_contacts())
            elif len(parts) == 4 and parts[0] == "api" and parts[1] in ("persons", "opportunities") and parts[3] == "akte":
                try:
                    lade = core.load_person_akte if parts[1] == "persons" else core.load_projekt_akte
                    self._send_json(lade(unquote(parts[2])))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "kundenwissen":
                # Kundenwissen (Migration 012): nur fuer diese Firma
                try:
                    self._send_json(core.kundenwissen_firma(unquote(parts[2]), parse_qs(urlparse(self.path).query)))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "kundenwissen":
                try:
                    self._send_json(core.kundenwissen_dokument(parts[2]))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "akte":
                # Akte: alles zu einem Unternehmen (UX-Sprint 2026-10-24)
                try:
                    self._send_json(core.load_firma_akte(unquote(parts[2])))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif len(parts) == 5 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "acos" and parts[4] == "dateien":
                # Dateien im Kundenordner der Nextcloud (Migration 008)
                import acos_sync
                try:
                    qs = parse_qs(urlparse(self.path).query)
                    self._send_json(acos_sync.kundenordner_dateien(unquote(parts[2]), (qs.get("pfad", [""])[0])))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "acos":
                # Bereich "Artefakte (ACOS)" am Unternehmen (Migration 006)
                try:
                    self._send_json(core.load_acos_firma(unquote(parts[2])))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif path == "/api/persons":
                # Personen-Tab (2026-08-21) - flache Liste aller Ansprechpartner
                self._send_json(core.load_persons())
            elif path == "/api/person-activities":
                # Eigener Namespace, bewusst NICHT "/api/activities" - kollidiert sonst mit
                # dem bestehenden firma-bezogenen Log direkt darunter.
                qs = parse_qs(urlparse(self.path).query)
                person = (qs.get("person", [""])[0])
                self._send_json(core.load_person_activities(person) if person else [])
            elif path == "/api/heute":
                contacts = core.load_contacts(); tasks = core.load_tasks()
                self._send_json({"candidates": core.build_heute_candidates(contacts, tasks)})
            elif path == "/api/opportunities":
                self._send_json(core.load_opportunities())
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "activities":
                self._send_json(core.load_activities(unquote(parts[2])))
            elif path == "/api/mail-review":
                self._send_json(core.load_mail_review_queue())
            elif path == "/api/mail-ignore":
                self._send_json(core.load_mail_ignore())
            elif path == "/api/heute/start":
                # Startseite Heute (Umbau Schritt 11): Aufgaben, Mails, Termine, Im Blick
                self._send_json(core.heute_start_view())
            elif path == "/api/heute/tag":
                # Heute-Ansicht (Migration 010): Journal des Tages, Abschluss, Briefing
                self._send_json(core.heute_tag_view())
            elif path == "/api/tagesabschluss":
                self._send_json({"abschluesse": core.tagesabschluss_liste()})
            elif path == "/api/dubletten":
                self._send_json(core.dubletten_liste())
            elif path == "/api/dubletten/pruefen":
                self._send_json(core.dubletten_pruefen_api(parse_qs(urlparse(self.path).query)))
            elif path == "/api/wissen/status":
                self._send_json(core.wissen_status())
            elif path == "/api/acos/status":
                self._send_json(core.acos_status_view())
            elif path == "/api/recherche":
                self._send_json(core.recherche(parse_qs(urlparse(self.path).query)))
            elif path == "/api/wissen/suche":
                self._send_json(core.wissen_suche(parse_qs(urlparse(self.path).query)))
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "wissen" and parts[2] == "datei":
                try:
                    name, daten, ctype, art = core.wissen_datei(parts[3])
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
                    return
                from urllib.parse import quote as _quote
                kopf = [("Content-Disposition", art + "; filename*=UTF-8''" + _quote(name)),
                        ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "private, no-store")]
                if ctype != "application/pdf":   # Chrome zeigt PDFs mit Sandbox-Regel nicht an
                    kopf.append(("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"))
                self._send(200, "OK", ctype, daten, extra_headers=kopf)
            elif path == "/api/einstellungen":
                self._send_json(core.load_settings_view(self._current_user()))
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "journal":
                try:
                    self._send_json(core.load_journal_entry(parts[2]))
                except (FileNotFoundError, ValueError) as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
            elif path == "/api/journal":
                # Journal (2026-10-19): fachliche Eintraege, gefiltert und seitenweise
                self._send_json(core.load_journal(parse_qs(urlparse(self.path).query)))
            elif path == "/api/audit":
                # Technisches Protokoll, nur lesend
                self._send_json(core.load_audit(parse_qs(urlparse(self.path).query)))
            elif path == "/api/archive":
                # Archiv-Reiter (Migration 002): alle archivierten Datensaetze
                self._send_json(core.load_archive())
            elif path == "/api/server/restart":
                # Re-execv ersetzt den laufenden Prozess in-place (gleiche PID) -
                # funktioniert unter systemd genauso wie im lokalen Betrieb,
                # ohne dass systemd einen Absturz/Neustart-Zyklus sieht.
                self._send_json({"ok": True, "action": "restart"})
                import threading

                def _restart():
                    import time
                    time.sleep(0.5)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                threading.Thread(target=_restart, daemon=True).start()
            elif path == "/api/server/shutdown":
                # Sauberer Exit (Code 0). Bei Restart=on-failure im systemd-Unit
                # startet der Dienst danach NICHT automatisch neu - das ist hier
                # gewollt (echtes "Stop"), erfordert danach aber "systemctl start
                # crm" per SSH, um ihn wieder hochzufahren.
                self._send_json({"ok": True, "action": "shutdown"})
                import threading

                def _stop():
                    import time
                    time.sleep(0.5)
                    self.server.shutdown()
                threading.Thread(target=_stop, daemon=True).start()
            else:
                self._send_json({"error": "Not Found"}, 404, "Not Found")
        except Exception:
            self._send_json({"error": "Serverfehler", "traceback": traceback.format_exc()}, 500, "Internal Server Error")

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        parts = path.strip("/").split("/")
        if self._enforce_auth(path, True):
            return
        try:
            body = self._read_body()
            if path == "/api/login":
                username = (body.get("username") or "").strip()
                password = body.get("password") or ""
                _login_delay(username)
                if core.verify_login(username, password):
                    try:
                        cookie_header = self._set_session_cookie(username)
                    except core.SecretFileError as e:
                        # Passwort war richtig, aber die Session kann mangels
                        # Schreibrechten auf secrets/ nicht erstellt werden -
                        # klare Meldung statt Traceback, siehe Kommentar in
                        # crm_core._read_or_create_secret_file.
                        self._send_json({"ok": False, "error": f"Server-Konfigurationsfehler: {e}"}, 500, "Internal Server Error")
                        return
                    _register_login_success(username)
                    self._send(200, "OK", "application/json; charset=utf-8", b'{"ok": true}',
                               extra_headers=[cookie_header])
                else:
                    _register_failed_login(username)
                    self._send_json({"ok": False, "error": "Nutzername oder Passwort falsch"}, 401, "Unauthorized")
                return
            elif path == "/api/logout":
                self._send(200, "OK", "application/json; charset=utf-8", b'{"ok": true}',
                           extra_headers=[self._clear_session_cookie()])
                return
            elif path == "/api/tasks":
                core.create_task(body)
            elif path == "/api/contacts":
                core.create_contact(body)
            elif path == "/api/opportunities":
                core.create_opp(body)
            elif path == "/api/person-activities":
                core.create_person_activity(body)
            elif path == "/api/tagesabschluss":
                self._send_json({"ok": True, "abschluss": core.tagesabschluss_erstellen(
                    von=self._current_user(), notiz=body.get("notiz"))})
                return
            elif path == "/api/tagesabschluss/bewertung":
                try:
                    self._send_json({"ok": True, "geholt": core.tagesbewertungen_abholen()})
                except Exception as e:
                    self._send_json({"ok": False, "error": f"ACOS nicht erreichbar: {str(e)[:200]}"}, 502, "Bad Gateway")
                return
            elif path == "/api/dubletten/zusammenfuehren":
                try:
                    self._send_json({"ok": True, **core.personen_zusammenfuehren(body.get("behalten"), body.get("weg"))})
                except (ValueError, TypeError) as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                except FileNotFoundError as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                return
            elif path == "/api/dubletten/ignorieren":
                try:
                    core.dublette_ignorieren(body.get("a"), body.get("b"))
                except (ValueError, TypeError) as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                    return
            elif path == "/api/heute/dismiss":
                dismissed = core.load_dismissed(); dismissed.add(body.get("key", "")); core.save_dismissed(dismissed)
            elif path == "/api/heute/convert":
                # Seit Umbau Schritt 5 ohne Sammelprojekt: direkt am Unternehmen
                # bzw. als eigene Aufgabe, wenn kein Unternehmen dabei ist.
                core.create_task({
                    "title": body.get("text", ""), "firma": body.get("firma", ""), "herkunft": "heute",
                    "category": "Follow-up", "priority": "Mittel", "status": "Offen",
                })
                dismissed = core.load_dismissed(); dismissed.add(body.get("key", "")); core.save_dismissed(dismissed)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "activities":
                entries = core.add_activity(unquote(parts[2]), body)
                self._send_json(entries)
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] in ("archive", "restore"):
                # /api/archive/<typ>/<id> bzw. /api/restore/<typ>/<id>,
                # typ = firma | person | projekt | aufgabe (Migration 002)
                if parts[1] == "archive":
                    core.archive_entity(parts[2], unquote(parts[3]))
                else:
                    core.restore_entity(parts[2], unquote(parts[3]))
            elif path == "/api/tasks/archive-done":
                n = core.archive_done_tasks(body.get("older_than_days", 0))
                self._send_json({"ok": True, "archiviert": n})
                return
            elif path == "/api/kalender/abgleich":
                self._send_json(core.kalender_abgleich())
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "termine" and parts[3] in ("notiz", "firma"):
                try:
                    fn = core.termin_notiz if parts[3] == "notiz" else core.termin_firma
                    self._send_json(fn(parts[2], body))
                except FileNotFoundError as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400, "Bad Request")
                return
            elif path == "/api/mail-intake":
                result = core.handle_mail_intake(body)
                self._send_json(result)
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "confirm":
                # Seit Migration 009 mit Auswahl der Anhaenge: {"anhaenge": [{id, ablegen, acos}]}
                try:
                    self._send_json(core.confirm_mail_review_item(parts[2], body if "anhaenge" in body else None))
                except ValueError as e:
                    self._send_json({"error": str(e)}, 500, "Internal Server Error")
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "discard":
                core.discard_mail_review_item(parts[2], body.get("ignorieren"))
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "spaeter":
                try:
                    core.mail_review_spaeter(parts[2])
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                    return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "rueckgaengig":
                self._send_json(core.mail_review_rueckgaengig(parts[2]))
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "assign":
                self._send_json({"ok": True, "match": core.assign_mail_review_item(parts[2], body)})
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "ignore":
                core.ignore_mail_review_item(parts[2], body.get("scope", "adresse"))
            elif path == "/api/mail-ignore":
                core.add_mail_ignore(body.get("muster", ""), body.get("art", "adresse"))
            elif path == "/api/wissen/abgleich":
                self._send_json(core.wissen_abgleich_starten(self._current_user()))
                return
            elif path == "/api/acos/abgleich":
                self._send_json(core.acos_abgleich_starten(self._current_user()))
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "aufgabe":
                try:
                    self._send_json(core.akte_aufgabe(unquote(parts[2]), body))
                except FileNotFoundError as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400, "Bad Request")
                return
            elif len(parts) == 5 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "acos" and parts[4] == "senden":
                # Dokument aus dem Kundenordner direkt vom Server an ACOS (ohne Claude)
                import acos_sync
                try:
                    self._send_json(acos_sync.an_acos_senden(unquote(parts[2]), body.get("pfad", ""), self._current_user()))
                except FileNotFoundError as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400, "Bad Request")
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "acos":
                # Zuordnung zu ACOS bestaetigen / neu anlegen / loesen (Migration 007)
                try:
                    self._send_json(core.acos_zuordnen(unquote(parts[2]), body, self._current_user()))
                except FileNotFoundError as e:
                    self._send_json({"error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"error": str(e)}, 400, "Bad Request")
                return
            elif path == "/api/einstellungen/mailkonto/test":
                if not core.may_change_system(self._current_user()):
                    self._send_json({"ok": False, "meldung": "Keine Berechtigung"}, 403, "Forbidden")
                else:
                    self._send_json(core.test_mail_account(body))
                return
            elif path == "/api/einstellungen/passwort":
                try:
                    core.change_own_password(self._current_user(), body.get("alt", ""),
                                             body.get("neu", ""), body.get("neu2", ""))
                    self._send_json({"ok": True})
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "journal" and parts[3] == "aktion":
                try:
                    self._send_json({"ok": True, **core.journal_aktion(parts[2], body)})
                except FileNotFoundError as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "vertraege":
                # Vertraege bei Lieferanten (Umbau Schritt 4, Migration 015)
                try:
                    self._send_json({"ok": True, **core.create_vertrag(unquote(parts[2]), body)})
                except FileNotFoundError as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            elif path == "/api/beteiligung":
                # Beteiligte (Umbau Schritt 3, Migration 014)
                try:
                    self._send_json({"ok": True, **core.create_beteiligung(body)})
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            elif path == "/api/journal":
                try:
                    self._send_json({"ok": True, **core.create_journal_entry(body)})
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            else:
                self._send_json({"error": "Not Found"}, 404, "Not Found")
                return
            self._send_json({"ok": True})
        except core.DubletteFehler as e:
            # Migration 010: moegliche Dublette - die Oberflaeche fragt nach und schickt ggf. trotz_dublette mit
            self._send_json({"ok": False, "error": str(e), "dubletten": e.kandidaten}, 409, "Conflict")
        except Exception:
            self._send_json({"error": "Serverfehler", "traceback": traceback.format_exc()}, 500, "Internal Server Error")

    def do_PUT(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if self._enforce_auth(path.rstrip("/"), True):
            return
        try:
            body = self._read_body()
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "tasks":
                core.update_task(parts[2], body)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "contacts":
                core.update_contact(unquote(parts[2]), body)
            elif len(parts) == 5 and parts[0] == "api" and parts[1] == "contacts" and parts[3] == "persons":
                core.update_person(unquote(parts[2]), unquote(parts[4]), body)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "opportunities":
                core.update_opp(unquote(parts[2]), body)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "vertraege":
                try:
                    core.update_vertrag(parts[2], body)
                except FileNotFoundError as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                    return
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                    return
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "journal":
                try:
                    self._send_json({"ok": True, "eintrag": core.update_journal_entry(parts[2], body)})
                except FileNotFoundError as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            elif path.rstrip("/") in ("/api/einstellungen/persoenlich", "/api/einstellungen/system",
                                      "/api/einstellungen/mailkonto"):
                user = self._current_user()
                ziel = path.rstrip("/").rsplit("/", 1)[1]
                try:
                    if ziel == "persoenlich":
                        res = core.save_user_settings(user, body)
                    elif ziel == "system":
                        res = core.save_system_settings(user, body)
                    else:
                        res = core.save_mail_account(user, body)
                    self._send_json({"ok": True, "werte": res})
                except PermissionError as e:
                    self._send_json({"ok": False, "error": str(e)}, 403, "Forbidden")
                except (ValueError, TypeError) as e:
                    self._send_json({"ok": False, "error": str(e)}, 400, "Bad Request")
                return
            else:
                self._send_json({"error": "Not Found"}, 404, "Not Found")
                return
            self._send_json({"ok": True})
        except Exception:
            self._send_json({"error": "Serverfehler", "traceback": traceback.format_exc()}, 500, "Internal Server Error")

    def do_DELETE(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if self._enforce_auth(path.rstrip("/"), True):
            return
        try:
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "tasks":
                core.delete_task(parts[2])
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "contacts":
                # Archivieren statt Loeschen (Entscheidung 2026-07-25) - seit dem
                # Postgres-Umstieg archiviert_am statt Verschieben in _Archiv/ (Migration 002)..
                core.archive_contact(unquote(parts[2]))
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "opportunities":
                core.archive_opp(unquote(parts[2]))
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "person-activities":
                core.delete_person_activity(unquote(parts[2]))
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "mail-ignore":
                core.remove_mail_ignore(unquote(parts[2]))
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "vertraege":
                try:
                    core.archiviere_vertrag(parts[2])
                except (ValueError, FileNotFoundError) as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                    return
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "beteiligung":
                try:
                    core.loese_beteiligung(parts[2])
                except (ValueError, FileNotFoundError) as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                    return
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "journal":
                try:
                    core.delete_journal_entry(parts[2])
                except (ValueError, FileNotFoundError) as e:
                    self._send_json({"ok": False, "error": str(e)}, 404, "Not Found")
                    return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "activities":
                firma = unquote(parts[2])
                try:
                    idx = int(parts[3])
                except ValueError:
                    self._send_json({"error": "Ungueltiger Index"}, 400, "Bad Request")
                    return
                entries = core.delete_activity(firma, idx)
                self._send_json(entries)
                return
            else:
                self._send_json({"error": "Not Found"}, 404, "Not Found")
                return
            self._send_json({"ok": True})
        except Exception:
            self._send_json({"error": "Serverfehler", "traceback": traceback.format_exc()}, 500, "Internal Server Error")


def main():
    server = ThreadingHTTPServer((HOST, PORT), CRMHandler)
    print(f"CRM-Server laeuft auf {HOST}:{PORT} (nur lokal, Zugriff von aussen ueber Caddy)")
    server.serve_forever()


if __name__ == "__main__":
    main()
