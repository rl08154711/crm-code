#!/usr/bin/env python3
"""
smoke_test.py – End-to-End-Test gegen einen laufenden crm_serve.py (Postgres-Fassung)
========================================================================================
Prueft den kompletten CRUD-Weg ueber die echte HTTP-API - genau das, was der
Migrationsplan als Sandbox-Smoke-Test vor dem Cutover verlangt. Reine Stdlib
(urllib), keine Abhaengigkeit von curl/jq auf dem Server.

Voraussetzung: ein Login-Nutzer wurde bereits angelegt, z.B.
    sudo -u crmapp python3 manage_users.py add smoketest

Aufruf (auf dem Server, gegen die testweise auf Port 8091 laufende Instanz):
    python3 smoke_test.py --base http://127.0.0.1:8091 --user smoketest --password <pw>

Legt einen Test-Kontakt/-Projekt/-Task an, prueft CRUD + Archivieren, und
raeumt danach nichts automatisch weg (bewusst - fuer manuelle Nachkontrolle
in der Sandbox-DB). Bricht beim ersten Fehler mit klarer Meldung ab (Exit 1).
"""

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

PASS = "\033[32mOK\033[0m"
FAIL = "\033[31mFEHLER\033[0m"


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def req(self, method, path, body=None, expect=200, headers=None):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        h = {"Content-Type": "application/json"} if data else {}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=10) as resp:
                status = resp.status
                raw = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read()
        if status != expect:
            raise AssertionError(f"{method} {path} -> {status} (erwartet {expect}): {raw[:500]!r}")
        try:
            return json.loads(raw) if raw else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw          # Binaerdaten (z. B. PNG-Icon)


def step(name, fn):
    try:
        result = fn()
        print(f"[{PASS}] {name}")
        return result
    except Exception as e:
        print(f"[{FAIL}] {name}: {e}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8091")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--internal-token", default="",
                    help="Inhalt von secrets/internal_token.key - aktiviert die Mail-Review-Tests (optional)")
    args = ap.parse_args()

    c = Client(args.base)

    step("healthz erreichbar", lambda: c.req("GET", "/healthz"))
    step("Login", lambda: c.req("POST", "/api/login", {"username": args.user, "password": args.password}))
    step("Dashboard laedt (HTML)", lambda: c.req("GET", "/"))

    firma = "Smoketest GmbH"
    person = "Test Person"

    step("Kontakt anlegen", lambda: c.req("POST", "/api/contacts", {
        "firma": firma, "ansprechpartner": person, "email": "test@example.invalid",
        "status": "lead",
    }))

    contacts = step("Kontakte laden + neuen Kontakt finden", lambda: c.req("GET", "/api/contacts"))
    contact = next((x for x in contacts if x["firma"] == firma), None)
    assert contact, f"Kontakt '{firma}' nicht in /api/contacts gefunden"
    contact_id = contact["id"]
    print(f"      -> contact_id={contact_id}")

    step("Kontakt aktualisieren", lambda: c.req("PUT", f"/api/contacts/{contact_id}", {"status": "kunde"}))

    step("Projekt anlegen", lambda: c.req("POST", "/api/opportunities", {
        "title": "Smoketest-Projekt", "kontakt": firma, "ansprechpartner": person,
        "status": "aktiv", "value": "1000",
    }))
    opps = step("Projekte laden + neues Projekt finden", lambda: c.req("GET", "/api/opportunities"))
    opp = next((o for o in opps if o["title"] == "Smoketest-Projekt" and o["kontakt"] == firma), None)
    assert opp, "Smoketest-Projekt nicht in /api/opportunities gefunden"
    opp_id = opp["id"]
    print(f"      -> projekt_id={opp_id}")

    task_id_holder = {}

    def _create_task():
        c.req("POST", "/api/tasks", {"title": "Smoketest-Aufgabe", "projekt_id": opp_id, "status": "Offen"})
    step("Aufgabe anlegen (mit projekt_id)", _create_task)

    def _create_task_without_projekt():
        # Seit Umbau 5 (Migration 016) erlaubt: eigene Aufgabe ohne Projekt
        c.req("POST", "/api/tasks", {"title": "Aufgabe ohne Projekt"})
        t = next((x for x in c.req("GET", "/api/tasks") if x["title"] == "Aufgabe ohne Projekt"), None)
        assert t and not t.get("projektId"), t
        c.req("DELETE", f"/api/tasks/{t['taskId']}")
    step("Aufgabe ohne Projekt anlegen und wieder loeschen (Umbau 5)", _create_task_without_projekt)

    tasks = step("Aufgaben laden + neue Aufgabe finden", lambda: c.req("GET", "/api/tasks"))
    task = next((t for t in tasks if t["title"] == "Smoketest-Aufgabe" and str(t["projektId"]) == str(opp_id)), None)
    assert task, "Smoketest-Aufgabe nicht gefunden oder projektId stimmt nicht"
    task_id = task["taskId"]
    print(f"      -> task_id={task_id}, contact (aus Projekt abgeleitet)={task['contact']!r}")
    assert task["contact"] == firma, f"Task.contact sollte '{firma}' sein (aus Projekt abgeleitet), war {task['contact']!r}"

    step("Aufgabe aktualisieren (Status)", lambda: c.req("PUT", f"/api/tasks/{task_id}", {"status": "Erledigt"}))

    step("Aktivitaet anlegen", lambda: c.req("POST", f"/api/activities/{quote(firma)}", {"text": "Smoketest-Aktivitaet", "source": "kontakt"}))
    acts = step("Aktivitaeten laden", lambda: c.req("GET", f"/api/activities/{quote(firma)}"))
    assert any(a["text"] == "Smoketest-Aktivitaet" for a in acts), "Aktivitaet nicht gefunden"

    step("Heute-Kandidaten laden", lambda: c.req("GET", "/api/heute"))
    step("Mail-Review-Queue laden", lambda: c.req("GET", "/api/mail-review"))
    step("Personen laden", lambda: c.req("GET", "/api/persons"))

    # ── Migration 002: Stammdaten + Archiv ──
    step("Firma: Zentrale speichern", lambda: c.req("PUT", f"/api/contacts/{contact_id}", {"phone_central": "+49 89 1234-0"}))
    p_id = next(x for x in c.req("GET", "/api/contacts") if x["id"] == contact_id)["ansprechpartner_list"][0]["id"]
    step("Person: Mobil, Mail 2, LinkedIn speichern", lambda: c.req("PUT", f"/api/contacts/{contact_id}/persons/{p_id}", {
        "mobil": "+49 170 1111111", "email2": "privat@example.invalid", "linkedin": "https://www.linkedin.com/in/test"}))
    def _check_fields():
        k = next(x for x in c.req("GET", "/api/contacts") if x["id"] == contact_id)
        assert k["phone_central"] == "+49 89 1234-0", k
        pp = k["ansprechpartner_list"][0]
        assert pp["mobil"] == "+49 170 1111111" and pp["email2"] == "privat@example.invalid" and pp["linkedin"].endswith("/test"), pp
    step("Neue Stammdatenfelder kommen zurueck", _check_fields)

    step("Erledigte Aufgaben archivieren", lambda: c.req("POST", "/api/tasks/archive-done", {}))
    def _task_in_archive():
        assert not any(t["taskId"] == task_id for t in c.req("GET", "/api/tasks")), "archivierte Aufgabe noch in /api/tasks"
        assert any(t["id"] == task_id for t in c.req("GET", "/api/archive")["aufgaben"]), "Aufgabe nicht im Archiv"
    step("Aufgabe nur noch im Archiv", _task_in_archive)
    step("Aufgabe reaktivieren", lambda: c.req("POST", f"/api/restore/aufgabe/{task_id}"))
    def _task_back():
        t = next((t for t in c.req("GET", "/api/tasks") if t["taskId"] == task_id), None)
        assert t and t["status"] == "Erledigt", "Aufgabe nach Reaktivieren nicht zurueck oder Status verloren"
    step("Aufgabe wieder da, Status erhalten", _task_back)

    step("Person archivieren", lambda: c.req("POST", f"/api/archive/person/{p_id}"))
    step("Person ausgeblendet", lambda: (_ for _ in ()).throw(AssertionError("Person noch sichtbar"))
         if any(x["id"] == p_id for x in c.req("GET", "/api/persons")) else None)
    step("Person reaktivieren", lambda: c.req("POST", f"/api/restore/person/{p_id}"))
    step("Person wieder sichtbar", lambda: None if any(x["id"] == p_id for x in c.req("GET", "/api/persons"))
         else (_ for _ in ()).throw(AssertionError("Person fehlt nach Reaktivieren")))
    step("Unbekannter Archiv-Typ -> Fehler", lambda: c.req("POST", "/api/archive/quatsch/1", expect=500))

    # ── Schritt 3: Mail-Review mit unbekannten Absendern ──
    if args.internal_token:
        tok = {"X-Internal-Token": args.internal_token}
        def _intake(frm, name, mid):
            return c.req("POST", "/api/mail-intake", {"message_id": mid, "from": frm, "from_name": name,
                                                       "subject": "Smoketest-Anfrage", "date": "2026-10-19",
                                                       "body": "Hallo, ich haette eine Frage."}, headers=tok)
        res = step("Mail von unbekanntem Absender einliefern", lambda: _intake("nora@unbekannt-smoke.example", "Nora Neu", "<smoke-1@x>"))
        assert res.get("match") is None, res
        mr_id = res["id"]
        def _item():
            return next((i for i in c.req("GET", "/api/mail-review") if i["id"] == mr_id), None)
        def _check_unknown():
            it = _item()
            assert it and it["from_name"] == "Nora Neu" and it["match"] is None, it
            assert it["category"] == "Unbewertet" and not it.get("llm_error"), "KI-Bewertung sollte aus sein"
        step("Eintrag mit Anzeigename, ohne Zuordnung, KI aus", _check_unknown)
        step("Uebernehmen ohne Zuordnung wird abgelehnt", lambda: c.req("POST", f"/api/mail-review/{mr_id}/confirm", expect=500))
        step("Eintrag ist danach noch da (verschwindet nicht mehr)", lambda: None if _item() else (_ for _ in ()).throw(AssertionError("Eintrag verschwunden")))
        step("Absender zuordnen: neue Firma + Person", lambda: c.req("POST", f"/api/mail-review/{mr_id}/assign",
             {"firma": "Unbekannt Smoke GmbH", "name": "Nora Neu", "email": "nora@unbekannt-smoke.example"}))
        def _check_assigned():
            k = next((x for x in c.req("GET", "/api/contacts") if x["firma"] == "Unbekannt Smoke GmbH"), None)
            assert k and any(p["name"] == "Nora Neu" for p in k["ansprechpartner_list"]), "Firma/Person nicht angelegt"
            assert _item()["match"]["type"] == "person"
        step("Firma und Person angelegt, Eintrag zugeordnet", _check_assigned)
        step("Jetzt uebernehmen", lambda: c.req("POST", f"/api/mail-review/{mr_id}/confirm"))
        def _check_activity():
            acts = c.req("GET", "/api/activities/" + quote("Unbekannt Smoke GmbH"))
            assert any("Smoketest-Anfrage" in a["text"] for a in acts), "Aktivitaet fehlt"
        step("Aktivitaet beim neuen Unternehmen angelegt", _check_activity)
        sp = step("Newsletter einliefern", lambda: _intake("news@spam-smoke.example", "", "<smoke-2@x>"))
        step("Domain ignorieren", lambda: c.req("POST", f"/api/mail-review/{sp['id']}/ignore", {"scope": "domain"}))
        def _check_ignored():
            r2 = _intake("andere@spam-smoke.example", "", "<smoke-3@x>")
            assert r2.get("skipped") and "Ignorierliste" in r2.get("reason", ""), r2
            assert any(x["muster"] == "spam-smoke.example" for x in c.req("GET", "/api/mail-ignore"))
        step("Weitere Mail der Domain wird uebersprungen", _check_ignored)
        step("Ignorier-Eintrag wieder entfernen", lambda: c.req("DELETE", "/api/mail-ignore/spam-smoke.example"))
    else:
        print("[--] Mail-Review-Tests uebersprungen (--internal-token nicht angegeben)")

    # ── Schritt 4: Journal ──
    step("Journal: Eintrag mit Person und Projekt anlegen", lambda: c.req("POST", "/api/journal", {
        "firma": firma, "art": "telefonat", "person": person, "projekt": "Smoketest-Projekt",
        "datum": "2026-10-01", "text": "Smoketest-Telefonat 100% erledigt"}))
    step("Journal: fremde Person wird abgelehnt", lambda: c.req("POST", "/api/journal", {
        "firma": firma, "art": "notiz", "person": "Niemand Unbekannt", "text": "x"}, expect=400))
    step("Journal: ohne Text abgelehnt", lambda: c.req("POST", "/api/journal", {"firma": firma, "art": "notiz"}, expect=400))
    step("Journal: unbekannte Art abgelehnt", lambda: c.req("POST", "/api/journal", {"firma": firma, "art": "quatsch", "text": "x"}, expect=400))
    def _check_journal():
        j = c.req("GET", "/api/journal?firma=" + quote(firma))
        assert j["total"] >= 2, j["total"]
        it = next(i for i in j["items"] if i["text"].startswith("Smoketest-Telefonat"))
        assert it["person"] == person and it["projekt"] == "Smoketest-Projekt" and it["art_label"] == "Telefonat", it
        assert j["items"][0]["datum"] >= j["items"][-1]["datum"], "Sortierung falsch"
        return it["id"]
    jid = step("Journal: Filter Firma, Person/Projekt aufgeloest, neueste zuerst", _check_journal)
    def _check_filters():
        assert c.req("GET", "/api/journal?q=" + quote("100%"))["total"] >= 1, "Volltext mit % findet nichts"
        assert c.req("GET", "/api/journal?q=" + quote("100%25x"))["total"] == 0
        assert all(i["art"] == "telefonat" for i in c.req("GET", "/api/journal?art=telefonat")["items"])
        assert c.req("GET", "/api/journal?von=2026-10-01&bis=2026-10-01&firma=" + quote(firma))["total"] == 1
        assert c.req("GET", "/api/journal?von=2030-01-01")["total"] == 0
        assert c.req("GET", "/api/journal?anzahl=1&seite=2")["seite"] == 2
    step("Journal: Suche, Art, Zeitraum, Seiten", _check_filters)
    step("Journal: Eintrag erscheint auch im Firmen-Log", lambda: None if any(
        a.get("id") == jid for a in c.req("GET", f"/api/activities/{quote(firma)}")) else (_ for _ in ()).throw(AssertionError("fehlt im Firmen-Log")))
    def _check_audit():
        a = c.req("GET", "/api/audit?tabelle=aktivitaeten")
        assert a["total"] >= 1 and a["items"][0]["benutzer"] == args.user, a["items"][:1]
    step("Technisches Protokoll lesbar, mit Benutzer", _check_audit)
    # ── Journal bearbeiten und ableiten (2026-10-20) ──
    step("Journal: Eintrag einzeln laden", lambda: c.req("GET", f"/api/journal/{jid}"))
    def _edit():
        r = c.req("PUT", f"/api/journal/{jid}", {"text": "Smoketest-Telefonat geändert", "art": "meeting", "datum": "2026-10-02"})
        e = r["eintrag"]
        assert e["text"] == "Smoketest-Telefonat geändert" and e["art"] == "meeting" and e["datum"] == "2026-10-02", e
        assert e["person"] == person and e["projekt"] == "Smoketest-Projekt", "Person/Projekt verloren"
    step("Journal: Eintrag bearbeiten, Verknuepfungen bleiben", _edit)
    step("Journal: leerer Text abgelehnt", lambda: c.req("PUT", f"/api/journal/{jid}", {"text": "  "}, expect=400))
    step("Journal: fremde Person abgelehnt", lambda: c.req("PUT", f"/api/journal/{jid}", {"person": "Niemand Unbekannt"}, expect=400))
    def _aktionen():
        r = c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "person", "name": "Neue Kontaktperson", "titel": "Prokurist"})
        assert r["eintrag"]["person"] == "Neue Kontaktperson", r
        assert any(p["name"] == "Neue Kontaktperson" for p in c.req("GET", "/api/persons")), "Person fehlt"
        r = c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "person", "name": "Neue Kontaktperson"})
        assert "gab es schon" in r["meldung"], r
        r = c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "aufgabe", "title": "Rückruf aus Journal", "priority": "Hoch"})
        tid = r["eintrag"]["aufgaben"][-1]
        t = next(t for t in c.req("GET", "/api/tasks") if t["taskId"] == tid)
        assert t["title"] == "Rückruf aus Journal" and t["projekt"] == "Smoketest-Projekt" and "Aus dem Journal" in t["notes"], t
        c.req("DELETE", f"/api/tasks/{tid}")
        r = c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "projekt", "name": "Projekt aus Journal", "status": "lead"})
        assert r["eintrag"]["projekt"] == "Projekt aus Journal", r
        pr = next(o for o in c.req("GET", "/api/opportunities") if o["title"] == "Projekt aus Journal")
        assert pr["kontakt"] == firma and pr["status"] == "anbahnung" and pr["ansprechpartner"] == "Neue Kontaktperson", pr
        c.req("DELETE", f"/api/opportunities/{pr['id']}")
        r = c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "firma", "name": "Journal Neufirma GmbH", "zuordnen": True})
        assert r["eintrag"]["firma"] == "Journal Neufirma GmbH" and r["eintrag"]["person"] == "", r
        c.req("PUT", f"/api/journal/{jid}", {"firma": firma})
        c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "quatsch"}, expect=400)
        c.req("POST", f"/api/journal/{jid}/aktion", {"typ": "person", "name": ""}, expect=400)
        c.req("POST", "/api/journal/99999999/aktion", {"typ": "person", "name": "x"}, expect=404)
    step("Journal: +Person, +Aufgabe, +Projekt, +Unternehmen", _aktionen)
    step("Journal: Favoriten speichern", lambda: c.req("PUT", "/api/einstellungen/persoenlich", {"favoriten": ["journal", "heute"]}))
    step("Journal: zu viele Favoriten abgelehnt", lambda: c.req("PUT", "/api/einstellungen/persoenlich",
         {"favoriten": ["heute", "tasks", "contacts", "persons", "pipeline", "journal", "wissen"]}, expect=400))
    step("Favoriten im Dashboard", lambda: None if '"favoriten": ["journal", "heute"]' in c.req("GET", "/") else (_ for _ in ()).throw(AssertionError("fehlt")))
    step("Favoriten zuruecksetzen", lambda: c.req("PUT", "/api/einstellungen/persoenlich", {"favoriten": ["heute", "tasks", "contacts", "pipeline"]}))
    step("Journal: Eintrag loeschen", lambda: c.req("DELETE", f"/api/journal/{jid}"))
    step("Journal: Eintrag weg", lambda: None if not any(i["id"] == jid for i in c.req("GET", "/api/journal")["items"]) else (_ for _ in ()).throw(AssertionError("noch da")))
    step("Journal: Loeschen unbekannter ID -> 404", lambda: c.req("DELETE", "/api/journal/99999999", expect=404))

    # ── Schritt 5: Einstellungen ──
    def _check_settings_defaults():
        e = c.req("GET", "/api/einstellungen")
        assert e["benutzer"] == args.user and e["darf_system"] is True, e
        assert e["persoenlich"]["startansicht"] in e["optionen"]["startansichten"], e["persoenlich"]
        assert "IMAP_PASSWORD" not in json.dumps(e) and "passwort\":" not in json.dumps(e).replace("passwort_gesetzt", ""), "Passwort im Klartext"
        return e
    e0 = step("Einstellungen laden", _check_settings_defaults)
    step("Persoenlich speichern", lambda: c.req("PUT", "/api/einstellungen/persoenlich",
         {"startansicht": "journal", "akzent": "petrol", "projekt_status": ["laeuft"]}))
    step("Unbekannte Startansicht abgelehnt", lambda: c.req("PUT", "/api/einstellungen/persoenlich", {"startansicht": "quatsch"}, expect=400))
    def _check_dashboard_user():
        html = c.req("GET", "/")
        assert "#0f766e" in html and '"startansicht": "journal"' in html and '"projekt_status": ["laeuft"]' in html
    step("Dashboard uebernimmt Farbe, Startansicht, Projektfilter", _check_dashboard_user)
    step("System speichern", lambda: c.req("PUT", "/api/einstellungen/system",
         {"auto_archiv_tage": 7, "mail_intervall": 15, "mail_aktiv": False, "ki_bewertung": False}))
    step("Ungueltige Frist abgelehnt", lambda: c.req("PUT", "/api/einstellungen/system", {"auto_archiv_tage": 3}, expect=400))
    def _check_system():
        sy = c.req("GET", "/api/einstellungen")["system"]
        assert sy["auto_archiv_tage"] == 7 and sy["mail_intervall"] == 15 and sy["mail_aktiv"] is False, sy
    step("Systemwerte kommen zurueck", _check_system)
    step("Mail-Konto speichern", lambda: c.req("PUT", "/api/einstellungen/mailkonto",
         {"host": "imap.smoke.invalid", "port": "993", "user": "smoke@smoke.invalid", "passwort": "Geheim-Smoke-123"}))
    def _check_mailkonto():
        raw = json.dumps(c.req("GET", "/api/einstellungen"))
        assert "Geheim-Smoke-123" not in raw, "Passwort wird ausgeliefert"
        mk = json.loads(raw)["mail_konto"]
        assert mk["host"] == "imap.smoke.invalid" and mk["passwort_gesetzt"] is True, mk
    step("Mail-Konto gespeichert, Passwort nicht auslesbar", _check_mailkonto)
    step("Mail-Konto: Zeilenumbruch abgelehnt", lambda: c.req("PUT", "/api/einstellungen/mailkonto",
         {"host": "imap.smoke.invalid", "user": "a", "passwort": "x\nIMAP_HOST=evil"}, expect=400))
    step("Verbindungstest meldet Fehler sauber", lambda: None if c.req("POST", "/api/einstellungen/mailkonto/test",
         {"host": "imap.smoke.invalid", "port": "993", "user": "x", "passwort": "y"})["ok"] is False else (_ for _ in ()).throw(AssertionError("ok?")))
    step("Passwort: falsches altes abgelehnt", lambda: c.req("POST", "/api/einstellungen/passwort",
         {"alt": "falsch", "neu": "NeuesPasswort1", "neu2": "NeuesPasswort1"}, expect=400))
    step("Passwort: zu kurz abgelehnt", lambda: c.req("POST", "/api/einstellungen/passwort",
         {"alt": args.password, "neu": "kurz", "neu2": "kurz"}, expect=400))
    def _pw_roundtrip():
        c.req("POST", "/api/einstellungen/passwort", {"alt": args.password, "neu": "NeuesPasswort1", "neu2": "NeuesPasswort1"})
        c2 = Client(args.base)
        c2.req("POST", "/api/login", {"username": args.user, "password": "NeuesPasswort1"})
        c.req("POST", "/api/einstellungen/passwort", {"alt": "NeuesPasswort1", "neu": args.password, "neu2": args.password})
    step("Passwort aendern, damit anmelden, zuruecksetzen", _pw_roundtrip)
    step("Einstellungen zuruecksetzen", lambda: (
        c.req("PUT", "/api/einstellungen/persoenlich", e0["persoenlich"]),
        c.req("PUT", "/api/einstellungen/system", {"auto_archiv_tage": 0, "mail_intervall": e0["system"]["mail_intervall"],
                                                  "mail_aktiv": e0["system"]["mail_aktiv"]})))

    # ── Schritt 6: Mobile Statusansicht ──
    def _check_mobile():
        html = c.req("GET", "/m")
        assert "const D = " in html
        import re as _re
        data = json.loads(_re.search(r"const D = (\{.*?\});\n", html, _re.S).group(1))
        assert any(k["firma"] == firma for k in data["kontakte"]), "Firma fehlt in /m"
        assert all(t["status"] != "Erledigt" for t in data["aufgaben"]), "Erledigte Aufgabe in /m"
        assert "Geheim" not in html
    step("Mobile Ansicht /m laedt mit Daten", _check_mobile)
    def _check_public_icons():
        anon = Client(args.base)
        anon.req("GET", "/manifest.webmanifest")
        icon = anon.req("GET", "/apple-touch-icon.png")
        assert isinstance(icon, bytes) and icon[:4] == b"\x89PNG", "Icon ist kein PNG"
        page = anon.req("GET", "/m")          # ohne Login -> Weiterleitung zur Anmeldung
        assert "const D = " not in page, "Mobile Ansicht ohne Login erreichbar"
        anon.req("GET", "/api/journal", expect=401)
    step("Icons/Manifest oeffentlich, /m und API nur mit Login", _check_public_icons)

    # ── Wissen (Migration 005) – ohne Nextcloud pruefbar ──
    def _check_wissen():
        st = c.req("GET", "/api/wissen/status")
        assert "eingerichtet" in st and "dokumente" in st, st
        r = c.req("GET", "/api/wissen/suche?q=" + quote("Test"))
        assert "items" in r and "total" in r, r
        c.req("GET", "/api/wissen/datei/99999999", expect=404)
    step("Wissen: Status, Suche, unbekannte Datei -> 404", _check_wissen)
    step("Wissen: ohne Login gesperrt", lambda: Client(args.base).req("GET", "/api/wissen/suche?q=x", expect=401))

    # ── ACOS-Vorbereitung (Migration 006) – ohne ACOS pruefbar ──
    def _check_acos():
        d = c.req("GET", f"/api/contacts/{contact_id}/acos")
        assert d.get("eingerichtet"), f"Migration 006 fehlt? {d}"
        assert d["fuehren"] is False and d["zustand"] == "offen" and d["artefakte"] == [], d
        assert d["ablage"].endswith("/" + firma + "/ACOS"), d["ablage"]
        c.req("PUT", f"/api/contacts/{contact_id}", {"acos_fuehren": True})
        k = next(x for x in c.req("GET", "/api/contacts") if x["id"] == contact_id)
        assert k["acos_fuehren"] is True, k
        assert c.req("GET", f"/api/contacts/{contact_id}/acos")["fuehren"] is True
        c.req("PUT", f"/api/contacts/{contact_id}", {"status": "kunde"})   # andere Felder lassen den Schalter stehen
        assert next(x for x in c.req("GET", "/api/contacts") if x["id"] == contact_id)["acos_fuehren"] is True
        c.req("PUT", f"/api/contacts/{contact_id}", {"acos_fuehren": False})
        assert c.req("GET", f"/api/contacts/{contact_id}/acos")["fuehren"] is False
        c.req("GET", "/api/contacts/99999999/acos", expect=404)
    step("ACOS: Schalter setzen/loeschen, Bereich am Unternehmen, unbekannte Firma -> 404", _check_acos)
    def _check_acos_abgleich():
        st = c.req("GET", "/api/acos/status")
        assert "eingerichtet" in st and ("laeufe" in st or st.get("grund")), st
        c.req("POST", f"/api/contacts/{contact_id}/acos", {"aktion": "quatsch"}, expect=400)
        c.req("POST", f"/api/contacts/{contact_id}/acos", {"aktion": "verknuepfen", "acos_id": "x"}, expect=400)
        c.req("PUT", "/api/einstellungen/system", {"acos_modus": "quatsch"}, expect=400)
    step("ACOS-Abgleich: Status, ungültige Zuordnung und Modus abgelehnt", _check_acos_abgleich)
    step("ACOS: ohne Login gesperrt", lambda: Client(args.base).req("GET", f"/api/contacts/{contact_id}/acos", expect=401))

    # ── Akte (UX-Sprint 2026-10-24) ──
    def _check_akte():
        a = c.req("GET", f"/api/contacts/{contact_id}/akte")
        assert a["firma"] == firma and isinstance(a["personen"], list) and isinstance(a["journal"], list), a.keys()
        assert any(t["taskId"] == task_id for t in a["aufgaben"]), "Aufgabe fehlt in der Akte"
        assert any(str(p["id"]) == str(opp_id) for p in a["projekte"]), "Projekt fehlt in der Akte"
        c.req("PUT", f"/api/contacts/{contact_id}", {"next_action": "Smoke: Rückruf"})
        assert c.req("GET", f"/api/contacts/{contact_id}/akte")["next_action"] == "Smoke: Rückruf"
        n = len(a["aufgaben"])
        a2 = c.req("POST", f"/api/contacts/{contact_id}/aufgabe", {"title": "Smoke-Aufgabe aus der Akte", "projekt_id": opp_id})
        assert len(a2["aufgaben"]) == n + 1, "Aufgabe aus der Akte nicht angelegt"
        c.req("POST", f"/api/contacts/{contact_id}/aufgabe", {"title": ""}, expect=400)
        c.req("GET", "/api/contacts/99999999/akte", expect=404)
        neu = next(t for t in a2["aufgaben"] if t["title"] == "Smoke-Aufgabe aus der Akte")
        c.req("DELETE", f"/api/tasks/{neu['taskId']}")
    step("Akte: laden, nächster Schritt, Aufgabe anlegen, Fehlerfälle", _check_akte)
    def _check_akte_person_projekt():
        a = c.req("GET", f"/api/contacts/{contact_id}/akte")
        if a["personen"]:
            pa = c.req("GET", f"/api/persons/{a['personen'][0]['id']}/akte")
            assert pa["firma"] == firma and "journal" in pa, pa.keys()
        ra = c.req("GET", f"/api/opportunities/{opp_id}/akte")
        assert ra["firma"] == firma and any(t["taskId"] == task_id for t in ra["aufgaben"]), ra.keys()
        c.req("GET", "/api/persons/99999999/akte", expect=404)
        c.req("GET", "/api/opportunities/99999999/akte", expect=404)
        j = c.req("GET", f"/api/journal?projekt_id={opp_id}")
        assert "items" in j
    step("Akte: Person und Projekt laden", _check_akte_person_projekt)
    step("Akte: ohne Login gesperrt", lambda: Client(args.base).req("GET", f"/api/contacts/{contact_id}/akte", expect=401))

    step("Aufgabe loeschen", lambda: c.req("DELETE", f"/api/tasks/{task_id}"))
    step("Projekt archivieren", lambda: c.req("DELETE", f"/api/opportunities/{opp_id}"))
    step("Kontakt archivieren", lambda: c.req("DELETE", f"/api/contacts/{contact_id}"))

    opps_after = step("Projekte laden (archiviertes Projekt darf nicht mehr auftauchen)", lambda: c.req("GET", "/api/opportunities"))
    assert not any(o["id"] == opp_id for o in opps_after), "Archiviertes Projekt taucht noch in /api/opportunities auf"

    def _restore_contact_and_project():
        a = c.req("GET", "/api/archive")
        assert any(f["id"] == contact_id for f in a["firmen"]), "Firma nicht im Archiv"
        assert any(o["id"] == opp_id for o in a["projekte"]), "Projekt nicht im Archiv"
        c.req("POST", f"/api/restore/firma/{contact_id}")
        c.req("POST", f"/api/restore/projekt/{opp_id}")
        k = next((x for x in c.req("GET", "/api/contacts") if x["id"] == contact_id), None)
        assert k and k["status"] == "kunde", f"Firma nach Reaktivieren fehlt oder Status verloren: {k and k['status']}"
        assert any(o["id"] == opp_id for o in c.req("GET", "/api/opportunities")), "Projekt nach Reaktivieren fehlt"
    step("Firma und Projekt reaktivieren, Status bleibt erhalten", _restore_contact_and_project)
    # ── Migration 010: Dublettenpruefung und Tagesabschluss ──
    def _dubletten():
        neu = {"firma": firma, "ansprechpartner": "Test Persn", "email": "test@example.invalid"}
        c.req("POST", "/api/contacts", neu, expect=409)
        k = c.req("GET", "/api/dubletten/pruefen?name=Test%20Persn&email=test@example.invalid")
        assert k["kandidaten"] and k["kandidaten"][0]["stufe"] == "sicher", k
        c.req("POST", "/api/contacts", dict(neu, trotz_dublette=True))
        liste = c.req("GET", "/api/dubletten")
        paar = next(p for p in liste["paare"] if "Test Persn" in (p["a"]["name"], p["b"]["name"]))
        behalten, weg = (paar["a"], paar["b"]) if paar["a"]["name"] == "Test Person" else (paar["b"], paar["a"])
        r = c.req("POST", "/api/dubletten/zusammenfuehren", {"behalten": behalten["id"], "weg": weg["id"]})
        assert r["archiviert"] == weg["id"], r
        assert not any(weg["id"] in (p["a"]["id"], p["b"]["id"]) for p in c.req("GET", "/api/dubletten")["paare"])
        c.req("POST", "/api/dubletten/zusammenfuehren", {"behalten": behalten["id"], "weg": weg["id"]}, expect=400)
    step("Dubletten: Rueckfrage, trotzdem anlegen, zusammenfuehren", _dubletten)

    def _tagesabschluss():
        h = c.req("GET", "/api/heute/tag")
        assert "tag" in h and "journal" in h["tag"], h.keys()
        a = c.req("POST", "/api/tagesabschluss", {"notiz": "Smoketest"})["abschluss"]
        assert a["notiz"] == "Smoketest" and "zahlen" in a["resuemee"] and a["briefing"]["fuer"] > a["datum"], a
        assert c.req("GET", "/api/heute/tag")["abschluss"]["datum"] == a["datum"]
        assert c.req("GET", "/api/tagesabschluss")["abschluesse"][0]["datum"] == a["datum"]
    step("Tagesabschluss: Heute laden, abschliessen, Briefing", _tagesabschluss)

    # ── Kundenwissen: ACOS-Dokumente als Verweis (03.11.2026) ──
    def _kw_acos_dok():
        d = c.req("GET", f"/api/contacts/{contact_id}/kundenwissen")
        assert isinstance(d.get("acos_dokumente"), list), d.keys()
        for x in d["acos_dokumente"]:
            assert x["quelle"] == "acos_dok" and "inhalt" not in x and "link" in x, x
        t = c.req("GET", f"/api/contacts/{contact_id}/kundenwissen?q=Smoketest")
        assert isinstance(t.get("treffer"), list), t.keys()
    step("Kundenwissen: Liste mit ACOS-Dokumenten, Suche", _kw_acos_dok)
    step("Dashboard laedt nach allen Aenderungen", lambda: c.req("GET", "/"))

    step("Logout", lambda: c.req("POST", "/api/logout"))

    print("\nAlle Smoke-Tests erfolgreich.")


if __name__ == "__main__":
    main()
