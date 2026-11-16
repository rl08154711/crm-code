#!/usr/bin/env python3
"""Prüfungen für das Umbenennen von Unternehmen (16.11.2026).

Nur gegen die Sandbox (crm_test, Port 8091) mit fiktiven Daten laufen lassen:
    python3 test_firma_umbenennen.py --base http://127.0.0.1:8091 --user smoketest --password <pw>
Legt Projekte direkt per psql an (sudo -u crmapp, Datenbank --db, Standard crm_test).
"""
import argparse, json, subprocess, sys, time, urllib.request, urllib.error, http.cookiejar

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8091")
ap.add_argument("--user", required=True)
ap.add_argument("--password", required=True)
ap.add_argument("--db", default="crm_test")
args = ap.parse_args()
if args.db == "crm":
    sys.exit("Nicht gegen die Live-Datenbank laufen lassen.")

op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(m, p, b=None):
    r = urllib.request.Request(args.base + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                               headers={"Content-Type": "application/json"})
    try:
        x = op.open(r); return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
def sql(q):
    return subprocess.run(["sudo", "-u", "crmapp", "psql", "-At", args.db, "-c", q],
                          capture_output=True, text=True).stdout.strip()

ok = fail = 0
def check(name, cond):
    global ok, fail
    print(("[OK]     " if cond else "[FEHLER] ") + name)
    ok += bool(cond); fail += (not cond)

t = str(int(time.time()))[-6:]
ALT, ANDERE, NEU = f"ZZ Alt {t} Fiktiv GmbH", f"ZZ Andere {t} Fiktiv GmbH", f"ZZ Neu {t} Fiktiv GmbH"
req("POST", "/api/login", {"username": args.user, "password": args.password})
req("POST", "/api/contacts", {"firma": ALT, "ansprechpartner": f"Frieda Probe{t}", "email": f"f{t}@example.invalid"})
req("POST", "/api/contacts", {"firma": ANDERE, "ansprechpartner": f"Karl Probe{t}"})
c = json.loads(req("GET", "/api/contacts")[1])
fid = [x for x in c if x["firma"] == ALT][0]["id"]
sql(f"INSERT INTO projekte (name, firma_id, status) VALUES ('{ALT} – laufende Betreuung', {fid}, 'laeuft')")
sql(f"INSERT INTO projekte (name, firma_id, status) VALUES ('Website-Relaunch {t}', {fid}, 'laeuft')")

s, _ = req("PUT", f"/api/contacts/{fid}", {"firma": "  " + NEU.replace(" Fiktiv", "   Fiktiv") + " ", "branch": "Fitness"})
check("Umbenennen liefert 200", s == 200)
n = [x for x in json.loads(req("GET", "/api/contacts")[1]) if x["id"] == fid][0]
check("Neuer Name gespeichert, Leerzeichen bereinigt", n["firma"] == NEU)
check("Andere Felder mitgespeichert", n.get("branch") == "Fitness")
check("Ansprechpartner bleibt verknüpft", any(p["name"] == f"Frieda Probe{t}" for p in n.get("ansprechpartner_list", [])))
check("Sammelprojekt mitumbenannt", sql(f"SELECT count(*) FROM projekte WHERE firma_id={fid} AND name='{NEU} – laufende Betreuung'") == "1")
check("Anderes Projekt unverändert", sql(f"SELECT count(*) FROM projekte WHERE firma_id={fid} AND name='Website-Relaunch {t}'") == "1")
check("Audit-Eintrag vorhanden", int(sql(f"SELECT count(*) FROM audit_log WHERE tabelle='firmen' AND datensatz_id={fid} AND aktion='update'") or 0) >= 1)
s, b = req("PUT", f"/api/contacts/{fid}", {"firma": ANDERE.lower()})
check("Name einer anderen Firma abgelehnt (400)", s == 400 and "bereits" in json.loads(b).get("error", ""))
s, _ = req("PUT", f"/api/contacts/{fid}", {"firma": "   "})
check("Leerer Name abgelehnt (400)", s == 400)
s, _ = req("PUT", f"/api/contacts/{fid}", {"firma": NEU, "source": "Empfehlung"})
check("Gleicher Name: normales Speichern geht", s == 200)
s, _ = req("PUT", f"/api/contacts/{fid}", {"source": "Messe"})
check("Speichern ohne Namensfeld weiter möglich", s == 200)
print(f"\n{ok} OK, {fail} FEHLER")
sys.exit(1 if fail else 0)
