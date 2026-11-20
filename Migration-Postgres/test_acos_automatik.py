#!/usr/bin/env python3
"""Pruefung ACOS-Automatik (Migration 029, 20.11.2026), nur gegen crm_test, erfundene Daten.

Takt-Einstellungen (Auftragspruefung, voller Abgleich), Faelligkeit im Minutentakt,
Meldungen fuer Heute/Einblendung, "gesehen", Aufraeumen der schnellen Laeufe.
Es geht nichts nach aussen: der Abgleich selbst wird durch eine Attrappe ersetzt.

Aufruf (Sandbox):  CRM_DB_NAME=crm_test python3 test_acos_automatik.py /pfad/zu/CPX12-Postgres
"""
import os, sys
from datetime import datetime, timedelta

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core
import acos_sync
import acos_auftraege as auf

ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1

def wirft(fn, teil):
    try:
        fn()
    except ValueError as e:
        return teil in str(e)
    return False

ADMIN = core._q1("SELECT username FROM users ORDER BY id LIMIT 1")["username"]
alt = dict(core._system_raw())
core._x("DELETE FROM acos_laeufe")

# 1) Einstellungen
s = core.load_system_settings()
pruef("Standard: alle 5 Minuten, täglich 06:30", (s["acos_auftrag_takt"], s["acos_voll_art"], s["acos_voll_uhrzeit"]) == (5, "taeglich", "06:30"))
core.save_system_settings(ADMIN, {"acos_auftrag_takt": 10, "acos_voll_art": "stuendlich", "acos_voll_uhrzeit": "07:15"})
s = core.load_system_settings()
pruef("Gespeichert: 10 Minuten, stündlich", (s["acos_auftrag_takt"], s["acos_voll_art"]) == (10, "stuendlich"))
pruef("Ungültiger Takt abgelehnt", wirft(lambda: core.save_system_settings(ADMIN, {"acos_auftrag_takt": 7}), "Takt"))
pruef("Ungültige Uhrzeit abgelehnt", wirft(lambda: core.save_system_settings(ADMIN, {"acos_voll_art": "taeglich", "acos_voll_uhrzeit": "25:00"}), "HH:MM"))
pruef("Ungültige Art abgelehnt", wirft(lambda: core.save_system_settings(ADMIN, {"acos_voll_art": "woechentlich"}), "vollen Abgleich"))
pruef("acos_sync liest dieselben Werte", acos_sync.takt_einstellungen()["auftrag_takt"] == 10)
pruef("Text im Aufgabenfenster", auf.takt_text() == "prüft automatisch alle 10 Minuten")
core.save_system_settings(ADMIN, {"acos_auftrag_takt": 0})
pruef("Takt 'aus' → Text sagt ausgeschaltet", "ausgeschaltet" in auf.takt_text())
pruef("Status-Ansicht liefert Takt", core.acos_status_view()["auftrag_takt"] == 0)

# 2) Faelligkeit voller Abgleich
core.save_system_settings(ADMIN, {"acos_voll_art": "taeglich", "acos_voll_uhrzeit": "06:30"})
tz = datetime.now().astimezone().tzinfo
heute = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
pruef("Täglich 06:30: um 06:00 ohne Lauf nicht fällig", not acos_sync.voll_faellig(heute.replace(hour=6)))
pruef("Täglich 06:30: um 06:31 ohne Lauf fällig", acos_sync.voll_faellig(heute.replace(hour=6, minute=31)))
core._x("INSERT INTO acos_laeufe (start, ausgeloest_von, ok) VALUES (%s, 'timer', true)", (heute.replace(hour=6, minute=30, second=5),))
pruef("Nach dem 06:30-Lauf nicht noch einmal fällig", not acos_sync.voll_faellig(heute.replace(hour=14)))
core._x("INSERT INTO acos_laeufe (start, ausgeloest_von, ok) VALUES (%s, 'auftraege', true)", (heute.replace(hour=13),))
pruef("Schnelle Prüfung zählt nicht als voller Lauf", acos_sync._letzter_start(True) == heute.replace(hour=6, minute=30, second=5))
core.save_system_settings(ADMIN, {"acos_voll_art": "stuendlich"})
pruef("Stündlich: 61 Min. nach letztem vollen Lauf fällig", acos_sync.voll_faellig(heute.replace(hour=7, minute=31, second=10)))
pruef("Stündlich: 30 Min. danach nicht fällig", not acos_sync.voll_faellig(heute.replace(hour=7, minute=0)))

# 3) Faelligkeit Auftragspruefung
core.save_system_settings(ADMIN, {"acos_auftrag_takt": 5, "acos_modus": "scharf"})
fid = core._q1("""INSERT INTO firmen (name) VALUES ('ZZ Takt-Test (fiktiv)') RETURNING id""")["id"]
pruef("Ohne offenen Auftrag keine Prüfung", acos_sync.auftraege_faellig() == [])
core._x("""INSERT INTO acos_auftraege (auftrags_id, task_id, firma_id, acos_client_id, artefakttyp, status)
           VALUES ('AUF-2099-9001', 'ZZTEST-1', %s, 'test-client', 'executive-summary', 'uebergeben')""", (fid,))
jetzt = datetime.now(tz)
core._x("DELETE FROM acos_laeufe WHERE ausgeloest_von='auftraege'")
pruef("Offener Auftrag → Prüfung nur für diese Firma", acos_sync.auftraege_faellig(jetzt) == [fid])
core._x("INSERT INTO acos_laeufe (start, ausgeloest_von, ok) VALUES (%s, 'auftraege', true)", (jetzt - timedelta(minutes=2),))
pruef("Vor Ablauf des Takts keine neue Prüfung", acos_sync.auftraege_faellig(jetzt) == [])
pruef("Nach 5 Minuten wieder fällig", acos_sync.auftraege_faellig(jetzt + timedelta(minutes=3, seconds=30)) == [fid])
core.save_system_settings(ADMIN, {"acos_modus": "trocken"})
pruef("Im Trockenlauf keine Auftragsprüfung", acos_sync.auftraege_faellig(jetzt + timedelta(minutes=10)) == [])
core.save_system_settings(ADMIN, {"acos_modus": "scharf"})

# 4) takt(): was wird aufgerufen?
aufrufe = []
echt = acos_sync.abgleich
acos_sync.abgleich = lambda von="timer", nur_firmen=None: aufrufe.append((von, nur_firmen)) or True
try:
    core.save_system_settings(ADMIN, {"acos_voll_art": "taeglich", "acos_voll_uhrzeit": "00:00"})
    core._x("INSERT INTO acos_laeufe (start, ausgeloest_von, ok) VALUES (now(), 'timer', true)")
    core._x("DELETE FROM acos_laeufe WHERE ausgeloest_von='auftraege'")
    acos_sync.takt()
    pruef("takt(): schnelle Prüfung mit Firmenfilter", aufrufe == [("auftraege", [fid])])
    aufrufe.clear()
    core._x("UPDATE acos_auftraege SET status='bearbeitet' WHERE auftrags_id='AUF-2099-9001'")
    acos_sync.takt()
    pruef("takt(): ohne offenen Auftrag kein Abruf", aufrufe == [])
    core._x("DELETE FROM acos_laeufe WHERE ausgeloest_von IS DISTINCT FROM 'auftraege'")
    acos_sync.takt()
    pruef("takt(): voller Abgleich, wenn fällig", aufrufe == [("timer", None)])
finally:
    acos_sync.abgleich = echt

# 5) Meldungen
pruef("Spalte gesehen_am vorhanden (Migration 029)", core._spalte_da("acos_auftrag_verlauf", "gesehen_am"))
core._x("DELETE FROM acos_auftrag_verlauf WHERE task_id LIKE 'ZZTEST-%%'")
for art, text in (("uebergeben", "An ACOS übergeben"), ("rueckfrage", "Rückfrage von ACOS: Welche Region?"),
                  ("in_acos", "Ergebnis liegt in ACOS: „Analyse“"), ("bearbeitet", "In der Nextcloud abgelegt: /x")):
    core._x("INSERT INTO acos_auftrag_verlauf (task_id, auftrags_id, art, text) VALUES ('ZZTEST-1', 'AUF-2099-9001', %s, %s)", (art, text))
m = [x for x in auf.meldungen() if x["taskId"] == "ZZTEST-1"]
pruef("Drei Meldungen (ohne 'übergeben')", sorted(x["art"] for x in m) == ["bearbeitet", "in_acos", "rueckfrage"])
pruef("Meldung kennt Firma und Auftrags-ID", all(x["firma"] == "ZZ Takt-Test (fiktiv)" and x["auftrags_id"] == "AUF-2099-9001" for x in m))
auf.meldungen_gesehen({"ids": [x["id"] for x in m if x["art"] == "rueckfrage"]})
pruef("Einzeln als gesehen markiert", sorted(x["art"] for x in auf.meldungen() if x["taskId"] == "ZZTEST-1") == ["bearbeitet", "in_acos"])
auf.meldungen_gesehen({"task_id": "ZZTEST-1"})
pruef("Aufgabe geöffnet → alle gesehen", not [x for x in auf.meldungen() if x["taskId"] == "ZZTEST-1"])
pruef("Unsinnige IDs werden ignoriert", auf.meldungen_gesehen({"ids": ["x; DROP", None]}) == {"ok": True})

# 6) Aufraeumen: schnelle Laeufe nur 2 Tage, volle bleiben
core._x("INSERT INTO acos_laeufe (start, ausgeloest_von, ok) VALUES (now() - interval '3 days', 'auftraege', true), (now() - interval '3 days', 'timer', true)")
quelle = open(acos_sync.__file__, encoding="utf-8").read()
sql = quelle.split('core._x("""DELETE FROM acos_laeufe', 1)[1].split('"""', 1)[0]
lauf = core._q1("INSERT INTO acos_laeufe (ausgeloest_von, ok) VALUES ('auftraege', true) RETURNING id")["id"]
core._x("DELETE FROM acos_laeufe" + sql, (lauf, lauf))
pruef("Alte schnelle Läufe entfernt", not core._q1("SELECT 1 FROM acos_laeufe WHERE ausgeloest_von='auftraege' AND start < now() - interval '2 days'"))
pruef("Volle Läufe bleiben", core._q1("SELECT 1 FROM acos_laeufe WHERE ausgeloest_von='timer' AND start < now() - interval '2 days'") is not None)
v = core.acos_status_view()
pruef("Status-Ansicht listet keine schnellen Läufe", all(l.get("ausgeloest_von", l.get("von")) != "auftraege" for l in v["laeufe"]))
pruef("Status-Ansicht nennt letzte Auftragsprüfung", bool(v["letzte_auftragspruefung"]))

# Aufraeumen
core._x("DELETE FROM acos_auftrag_verlauf WHERE task_id LIKE 'ZZTEST-%%'")
core._x("DELETE FROM acos_auftraege WHERE auftrags_id='AUF-2099-9001'")
core._x("DELETE FROM firmen WHERE id=%s", (fid,))
core._x("DELETE FROM acos_laeufe")
print(f"{ok} von {ok} Pruefungen gruen.")
