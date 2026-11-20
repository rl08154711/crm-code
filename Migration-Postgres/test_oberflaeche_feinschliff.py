#!/usr/bin/env python3
"""Pruefungen fuer den Oberflaechen-Feinschliff (20.11.2026), nur gegen crm_test.

A1: Restart/Stop nur fuer Admins (Knopf und Endpunkt). H5: Faelligkeit verschieben,
einzeln und gesammelt. H8: Abhaken aus /m. Dazu: eine Leiste, keine Emojis in
Navigation und Ueberschriften, Personen als eigener Reiter, Filter-IDs unveraendert.

Aufruf (Sandbox, Server auf 8091 laeuft gegen crm_test):
  sudo -u crmapp env CRM_DB_NAME=crm_test python3 test_oberflaeche_feinschliff.py /pfad/zu/CPX12-Postgres --user smoketest --password ...
"""
import argparse, http.cookiejar, json, os, re, sys, urllib.request, urllib.error
from datetime import date, timedelta

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
ap = argparse.ArgumentParser()
ap.add_argument("code"); ap.add_argument("--base", default="http://127.0.0.1:8091")
ap.add_argument("--user", required=True); ap.add_argument("--password", required=True)
a = ap.parse_args()
sys.path.insert(0, a.code)
import crm_core as core

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def req(m, p, b=None):
    r = urllib.request.Request(a.base + p, data=json.dumps(b).encode() if b is not None else None, method=m,
                               headers={"Content-Type": "application/json"})
    try:
        with op.open(r) as x:
            t = x.read().decode(); return x.status, (json.loads(t) if t.startswith(("{", "[")) else t)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1

st, _ = req("POST", "/api/login", {"username": a.user, "password": a.password})
pruef("Anmeldung", st == 200)
rolle_vorher = core._q1("SELECT rolle FROM users WHERE username=%s", (a.user,))["rolle"]
admin_da = core._q1("SELECT 1 FROM users WHERE username='zz_admin_test'")
try:
    # ── A1: Nicht-Admin ──
    if not admin_da:
        core._x("INSERT INTO users (username, password_hash, rolle, aktiv) VALUES ('zz_admin_test', 'x:y', 'admin', true)")
    core._x("UPDATE users SET rolle='mitarbeiter' WHERE username=%s", (a.user,))
    st, seite = req("GET", "/")
    pruef("A1 Nicht-Admin: kein Neustart/Stopp im Menü", st == 200 and "serverAction('restart')" not in seite and "serverAction('shutdown')" not in seite)
    pruef("A1 Nicht-Admin: Abmelden im Nutzermenü", 'id="kl-nutzer"' in seite and "onclick=\"logout()\"" in seite)
    pruef("A1 Nicht-Admin: Restart abgelehnt (403)", req("GET", "/api/server/restart")[0] == 403)
    pruef("A1 Nicht-Admin: Stop abgelehnt (403)", req("GET", "/api/server/shutdown")[0] == 403)
    # ── A1: Admin (Endpunkt wird nicht aufgerufen) ──
    core._x("UPDATE users SET rolle='admin' WHERE username=%s", (a.user,))
    st, seite = req("GET", "/")
    pruef("A1 Admin: Neustart und Stopp im Nutzermenü", "serverAction('restart')" in seite and "serverAction('shutdown')" in seite)
    # ── Leiste, Emojis, Reiter ──
    pruef("A1 eine Leiste mit Suchfeld", 'class="kopfleiste"' in seite and 'id="kl-q"' in seite and 'class="header"' not in seite)
    kopf = seite[seite.index('id="kopfleiste"'):seite.index('<div class="panels">')]
    emo = re.compile("[\U0001F300-\U0001FAFF\u2600\u2699\u2709]")   # u. a. Sonne, Klemmbrett, Gebaeude, Ordner, Lupe, Zahnrad, Kompass, Buch, Mond, Person, Brief
    pruef("A2 keine Emojis in der Navigation", not emo.search(kopf))
    h = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", seite)
    pruef("A2 keine Emojis in Überschriften", not any(emo.search(x) for x in h))
    pruef("S6 Reiter heißt Personen", 'data-panel="persons" onclick="showPanel(\'persons\',this)">Personen' in seite)
    pruef("S1/S2 Filter-IDs unverändert", all(x in seite for x in ('id="fx-c-tbl"', 'id="fx-per-tbl"', 'id="fx-q-c-tbl"', 'id="fx-sichten-per-tbl"')))
    pruef("A3 Badges getönt", 'class="badge" style="background:' not in seite)
    # ── H5: verschieben ──
    heute, morgen = date.today(), date.today() + timedelta(days=1)
    ids = []
    for i, tage in enumerate((-3, -1)):
        core._x("""INSERT INTO tasks (task_id, title, status, priority, deadline, herkunft)
                   VALUES (%s, %s, 'Offen', 'mittel', %s, 'manuell')""", (f"ZZ-UI-{i}", f"ZZ Feinschliff {i}", heute + timedelta(days=tage)))
        ids.append(f"ZZ-UI-{i}")
    st, v = req("GET", "/api/heute/start")
    ueber = [t for t in v["aufgaben"]["ueber"] if t["taskId"] in ids]
    pruef("H5 Überfällige mit Tagen seit Fälligkeit", len(ueber) == 2 and sorted(t["tage"] for t in ueber) == [1, 3])
    for t in ids:
        req("PUT", "/api/tasks/" + t, {"deadline": heute.isoformat()})
    st, v = req("GET", "/api/heute/start")
    pruef("H5 Alle auf heute", all(t["taskId"] in [x["taskId"] for x in v["aufgaben"]["heute"]] for t in [{"taskId": i} for i in ids]))
    req("PUT", "/api/tasks/" + ids[0], {"deadline": morgen.isoformat()})
    pruef("H5 → Morgen", core._q1("SELECT deadline FROM tasks WHERE task_id=%s", (ids[0],))["deadline"] == morgen)
    pruef("H2 Lagezeile: offene Termine und nächster", "termine_offen" in v and "naechster" in v)
    pruef("H6 Mails mit Etiketten und Zeit", all("etiketten" in m and "zeit" in m for m in v["mails"]))
    st, t = req("GET", "/api/heute/tag")
    pruef("H7 Uhrzeit an Erledigtem und Journal", st == 200 and all("zeit" in x for x in t["tag"]["erledigt"] + t["tag"]["journal"]))
    # ── H8: /m ──
    st, m = req("GET", "/m")
    pruef("H8 /m mit Abhaken, nächstem Termin und Mails", st == 200 and "function abhaken" in m and '"naechster"' in m and '"mails"' in m)
    pruef("S8 /m Kontakte mit Umschalter Unternehmen/Personen", "kModus('personen')" in m and '"personen"' in m)
    st, _ = req("PUT", "/api/tasks/" + ids[1], {"status": "Erledigt"})
    pruef("H8 Abhaken (gleicher Aufruf wie /m)", st == 200 and core._q1("SELECT status FROM tasks WHERE task_id=%s", (ids[1],))["status"] == "Erledigt")
finally:
    core._x("DELETE FROM tasks WHERE task_id LIKE 'ZZ-UI-%%'")
    core._x("UPDATE users SET rolle=%s WHERE username=%s", (rolle_vorher, a.user))
    if not admin_da:
        core._x("DELETE FROM users WHERE username='zz_admin_test'")
print(f"\n{ok} von {ok} Pruefungen gruen.")
