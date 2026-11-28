#!/usr/bin/env python3
"""Pruefung Tagesabschluss-Automatik (28.11.2026), nur gegen crm_test.
23:30-Lauf: Werktag immer (auch ohne Eintrag), Wochenende nur mit Aktivitaet; Nachholer morgens: fehlende Tage der letzten 7
mit Aktivitaet plus der Vortag. Aufruf: CRM_DB_NAME=crm_test python3 test_tagesabschluss_auto.py /pfad/zu/CPX12-Postgres"""
import os, sys
from datetime import datetime, date, timedelta
if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core
import tagesabschluss as ta
from zoneinfo import ZoneInfo

ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1
def da(t): return core._q1("SELECT 1 FROM tagesabschluss WHERE datum=%s", (t,)) is not None
TZ = ZoneInfo("Europe/Berlin")
q = open(os.path.join(sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres", "crm-tagesabschluss.timer")).read()
pruef("Timer um 23:30", "23:30:00" in q and "23:40" not in q)

# feste, ruhige Tage weit in der Zukunft (keine Testdaten dort)
mi = date(2031, 1, 8)            # Mittwoch
sa = date(2031, 1, 11)           # Samstag
core._x("DELETE FROM tagesabschluss WHERE datum >= '2031-01-01'")
ta.lauf(datetime(2031, 1, 8, 23, 30, tzinfo=TZ), bewertungen=False)
pruef("Werktag ohne Eintrag: Abschluss geschrieben", da(mi))
ta.lauf(datetime(2031, 1, 11, 23, 30, tzinfo=TZ), bewertungen=False)
pruef("Wochenende ohne Eintrag: kein Abschluss", not da(sa))
ta.lauf(datetime(2031, 1, 8, 23, 30, tzinfo=TZ), bewertungen=False)
pruef("Zweiter Lauf: nichts doppelt", core._q1("SELECT count(*) n FROM tagesabschluss WHERE datum=%s", (mi,))["n"] == 1)
# Nachholer: Server war Do+Fr aus; Do hatte einen Journaleintrag, Fr nicht
do, fr = date(2031, 1, 9), date(2031, 1, 10)
fid = core._q1("INSERT INTO firmen (name) VALUES ('ZZ Abschluss-Test') RETURNING id")["id"]
core._x("INSERT INTO aktivitaeten (firma_id, datum, art, titel) VALUES (%s, %s, 'notiz', 'Test')", (fid, do))
ta.lauf(datetime(2031, 1, 11, 6, 30, tzinfo=TZ), bewertungen=False)
pruef("Nachholer: Tag mit Aktivität nachgeholt", da(do))
pruef("Nachholer: Vortag (Werktag) immer", da(fr))
ta.lauf(datetime(2031, 1, 13, 6, 30, tzinfo=TZ), bewertungen=False)   # Montag frueh: Vortag ist Sonntag
pruef("Nachholer am Montag: leeres Wochenende bleibt leer", not da(sa) and not da(date(2031, 1, 12)))
core._x("DELETE FROM aktivitaeten WHERE firma_id=%s", (fid,))
core._x("DELETE FROM firmen WHERE id=%s", (fid,))
core._x("DELETE FROM tagesabschluss WHERE datum >= '2031-01-01'")
print(f"{ok} von {ok} Pruefungen gruen.")
