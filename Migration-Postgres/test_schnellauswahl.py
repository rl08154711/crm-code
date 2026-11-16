#!/usr/bin/env python3
"""Prüfungen für die Schnellauswahl in Unternehmen/Kontakte und die gespeicherten Sichten
(16.11.2026, Migration 025). Nur gegen die Sandbox mit fiktiven Daten:
    python3 test_schnellauswahl.py --base http://127.0.0.1:8091 --user smoketest --password <pw>
"""
import argparse, html, json, re, sys, time, urllib.request, urllib.error, http.cookiejar

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:8091")
ap.add_argument("--user", required=True)
ap.add_argument("--password", required=True)
args = ap.parse_args()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(m, p, b=None):
    r = urllib.request.Request(args.base + p, method=m, data=json.dumps(b).encode() if b is not None else None,
                               headers={"Content-Type": "application/json"})
    try:
        x = op.open(r); return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
ok = fail = 0
def check(name, cond):
    global ok, fail
    print(("[OK]     " if cond else "[FEHLER] ") + name); ok += bool(cond); fail += (not cond)

t = str(int(time.time()))[-6:]
req("POST", "/api/login", {"username": args.user, "password": args.password})
req("POST", "/api/contacts", {"firma": f"Ölmühle {t} Fiktiv GmbH", "ansprechpartner": f"Uwe Zander{t}",
                              "branch": "Fahrschule", "address": "Teststr. 1, 85276 Pfaffenhofen", "status": "kunde"})
s, b = req("GET", "/")
seite = b.decode("utf-8", "replace")
zeile = re.search(r'<tr data-firma="Ölmühle ' + t + r'[^"]*"[^>]*data-fx="([^"]+)"', seite)
check("Firmenzeile trägt Filterdaten", bool(zeile))
if zeile:
    fx = json.loads(html.unescape(zeile.group(1)))
    check("A–Z: Umlaut zum Grundbuchstaben (Ö → O)", fx.get("az") == "O")
    check("Ort ohne Postleitzahl", fx.get("ort") == ["Pfaffenhofen"])
    check("Branche und Status übernommen", fx.get("br") == ["Fahrschule"] and "kunde" in fx.get("st", []))
    check("Letzter Kontakt heute → bis 30 Tage", fx.get("kt") == ["w"])
pzeile = re.search(r'data-person-name="Uwe Zander' + t + r'"[^>]*data-fx="([^"]+)"', seite)
check("Kontaktzeile trägt Filterdaten", bool(pzeile))
if pzeile:
    pfx = json.loads(html.unescape(pzeile.group(1)))
    check("Kontakt: A–Z nach Nachname, Unternehmen als Chip", pfx.get("az") == "Z" and pfx.get("fi") == [f"Ölmühle {t} Fiktiv GmbH"])
check("Suchfeld und Chip-Bereich für beide Listen vorhanden",
      all(x in seite for x in ('id="fx-c-tbl"', 'id="fx-per-tbl"', 'id="fx-q-c-tbl"', 'id="fx-sichten-per-tbl"')))

s, b = req("GET", "/api/sichten?bereich=firmen")
check("Sichten abrufbar (Startsichten da)", s == 200 and any(v["name"] == "Aktive Mandanten" for v in json.loads(b)))
name = f"ZZ Sicht {t}"
f1 = {"chips": {"br": ["Fahrschule"], "kt": ["r"]}, "q": ""}
s, b = req("POST", "/api/sichten", {"bereich": "firmen", "name": name, "filter": f1})
sid = json.loads(b).get("id") if s == 200 else None
check("Sicht speichern", s == 200 and sid)
s, b = req("POST", "/api/sichten", {"bereich": "firmen", "name": name.lower(), "filter": f1})
check("Gleicher Name (Groß/klein egal) wird gemeldet", s == 400 and "gibt es schon" in json.loads(b)["error"])
f2 = {"chips": {"br": ["Logistik"]}, "q": "spedition"}
s, b = req("POST", "/api/sichten", {"bereich": "firmen", "name": name, "filter": f2, "ueberschreiben": True})
check("Überschreiben behält die Sicht", s == 200 and json.loads(b).get("id") == sid)
liste = json.loads(req("GET", "/api/sichten?bereich=firmen")[1])
v = [x for x in liste if x["id"] == sid]
check("Überschriebener Filter gespeichert, Urheber vermerkt", v and v[0]["filter"] == f2 and v[0]["von"] == args.user)
s, _ = req("POST", "/api/sichten", {"bereich": "firmen", "name": "Leer", "filter": {"chips": {}, "q": ""}})
check("Sicht ohne Filter abgelehnt", s == 400)
s, _ = req("POST", "/api/sichten", {"bereich": "projekte", "name": "X", "filter": f1})
check("Unbekannter Bereich abgelehnt", s == 400)
s, b = req("POST", "/api/sichten", {"bereich": "personen", "name": name, "filter": {"chips": {"kp": ["Herbst"]}}})
check("Gleicher Name in anderem Bereich erlaubt", s == 200)
pid = json.loads(b).get("id")
check("Bereiche getrennt", all(x["id"] != pid for x in json.loads(req("GET", "/api/sichten?bereich=firmen")[1])))
s, _ = req("DELETE", f"/api/sichten/{sid}")
check("Sicht löschen", s == 200 and all(x["id"] != sid for x in json.loads(req("GET", "/api/sichten?bereich=firmen")[1])))
s, _ = req("DELETE", f"/api/sichten/{sid}")
check("Nochmals löschen → 404", s == 404)
req("DELETE", f"/api/sichten/{pid}")
print(f"\n{ok} OK, {fail} FEHLER"); sys.exit(1 if fail else 0)
