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
PUBLIC_PATHS = {"/healthz", "/login"}
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
        if self._current_user():
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
            elif path == "/api/tasks":
                self._send_json(core.load_tasks())
            elif path == "/api/contacts":
                self._send_json(core.load_contacts())
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
            elif path == "/api/heute/dismiss":
                dismissed = core.load_dismissed(); dismissed.add(body.get("key", "")); core.save_dismissed(dismissed)
            elif path == "/api/heute/convert":
                core.create_task({
                    "title": body.get("text", ""), "contact": body.get("firma", ""),
                    "category": "Follow-up", "priority": "Mittel", "status": "Offen",
                })
                dismissed = core.load_dismissed(); dismissed.add(body.get("key", "")); core.save_dismissed(dismissed)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "activities":
                entries = core.add_activity(unquote(parts[2]), body)
                self._send_json(entries)
                return
            elif path == "/api/mail-intake":
                result = core.handle_mail_intake(body)
                self._send_json(result)
                return
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "confirm":
                core.confirm_mail_review_item(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "mail-review" and parts[3] == "discard":
                core.discard_mail_review_item(parts[2])
            else:
                self._send_json({"error": "Not Found"}, 404, "Not Found")
                return
            self._send_json({"ok": True})
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
                tasks = core.load_tasks()
                tasks = [t for t in tasks if t["taskId"] != parts[2]]
                core.save_tasks(tasks)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "contacts":
                # Archivieren statt Loeschen (Entscheidung 2026-07-25) -
                # identisch zur bestehenden CGI-Logik in crm_cgi.py.
                contact_id = unquote(parts[2])
                filepath = core.FIRMEN_DIR / (core.safe_filename(contact_id) + ".md")
                if not filepath.exists():
                    self._send_json({"error": "Nicht gefunden"}, 404, "Not Found")
                    return
                archive_dir = core.FIRMEN_DIR / "_Archiv"
                archive_dir.mkdir(exist_ok=True)
                filepath.rename(archive_dir / filepath.name)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "opportunities":
                opp_id = unquote(parts[2])
                filepath = core.OPPS_DIR / (opp_id + ".md")
                if not filepath.exists():
                    self._send_json({"error": "Nicht gefunden"}, 404, "Not Found")
                    return
                archive_dir = core.OPPS_DIR / "_Archiv"
                archive_dir.mkdir(exist_ok=True)
                filepath.rename(archive_dir / filepath.name)
            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "person-activities":
                core.delete_person_activity(unquote(parts[2]))
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
