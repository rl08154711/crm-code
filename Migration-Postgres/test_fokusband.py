#!/usr/bin/env python3
"""Pruefung Fokusband auf "Heute" (Migration 030, 23.11.2026), nur gegen crm_test, erfundene Daten.

Pipeline-Stand (Summe, Tageswert, Vorwoche, 8 Wochen), Auswahl "der eine Schritt",
ACOS-Streifen. Aufruf:  CRM_DB_NAME=crm_test python3 test_fokusband.py /pfad/zu/CPX12-Postgres
"""
import os, sys
from datetime import timedelta

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core

ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1

tag = core.heute_lokal()
pruef("Tabelle pipeline_stand da (Migration 030)", core._tabelle_da("pipeline_stand"))
core._x("DELETE FROM pipeline_stand")
fid = core._q1("INSERT INTO firmen (name) VALUES ('ZZ Fokus-Test (fiktiv)') RETURNING id")["id"]
pids = [core._q1("INSERT INTO projekte (name, firma_id, status, value) VALUES (%s, %s, %s, %s) RETURNING id", r)["id"]
        for r in (("ZZ P1", fid, "anbahnung", 10000), ("ZZ P2", fid, "angebot", 2500), ("ZZ P3", fid, "laeuft", 99000),
                  ("ZZ P4", fid, "angebot", None))]
basis = core._q1("""SELECT coalesce(sum(value),0) s, count(*) n FROM projekte WHERE archiviert_am IS NULL
                    AND status IN ('anbahnung','angebot')""")

# 1) Pipeline
p = core.pipeline_stand(tag)
pruef("Summe nur Anbahnung und Angebot (Läuft zählt nicht)", abs(p["summe"] - float(basis["s"])) < 0.01)
pruef("Anzahl Projekte", p["anzahl"] == basis["n"])
pruef("Projekte ohne Wert gezählt", p["ohne_wert"] >= 1)
pruef("Tageswert geschrieben", core._q1("SELECT summe FROM pipeline_stand WHERE tag=%s", (tag,)) is not None)
pruef("Ohne Vorwoche kein Vergleich", p["diff"] is None and p["diff_text"] == "")
pruef("Verlauf hat 8 Wochen, nur die aktuelle gefüllt", len(p["verlauf"]) == 8 and p["verlauf"][-1] is not None and p["verlauf"][0] is None)
core.pipeline_stand(tag)
pruef("Zweiter Aufruf am selben Tag: weiter ein Wert", core._q1("SELECT count(*) n FROM pipeline_stand")["n"] == 1)
core._x("INSERT INTO pipeline_stand (tag, summe, anzahl) VALUES (%s, %s, 1)", (tag - timedelta(days=8), float(basis["s"]) - 1500))
p = core.pipeline_stand(tag)
pruef("Vergleich zur Vorwoche: +1.500 €", p["diff"] == 1500 and p["diff_text"] == "+1.500 € zur Vorwoche")
pruef("Verlauf: Vorwoche gefüllt", p["verlauf"][-2] is not None)
core._x("UPDATE projekte SET value = 1 WHERE id = %s", (pids[0],))
p = core.pipeline_stand(tag)
pruef("Rückgang mit Minuszeichen", p["diff"] < 0 and p["diff_text"].startswith("−"))
core._x("UPDATE projekte SET value = 10000 WHERE id = %s", (pids[0],))

# 2) Der eine Schritt
def aufgabe(tid, titel, tage, projekt=None):
    core._x("""INSERT INTO tasks (task_id, title, status, firma_id, projekt_id, deadline) VALUES (%s, %s, 'Offen', %s, %s, %s)""",
            (tid, titel, fid, projekt, tag - timedelta(days=tage)))
core._x("UPDATE tasks SET status='Erledigt' WHERE status <> 'Erledigt' AND task_id NOT LIKE 'ZZF-%%'")
aufgabe("ZZF-1", "Überfällig 2 Tage", 2)
aufgabe("ZZF-2", "Überfällig 9 Tage", 9)
aufgabe("ZZF-3", "Heute, kleines Projekt", 0, pids[1])
aufgabe("ZZF-4", "Heute, großes Projekt", 0, pids[0])
aufgabe("ZZF-5", "Nächste Woche", -3)
aufgabe("ZZF-6", "Liegt bei ACOS", 5)
core._x("""INSERT INTO acos_auftraege (auftrags_id, task_id, firma_id, acos_client_id, artefakttyp, status)
           VALUES ('AUF-2099-8001', 'ZZF-6', %s, 'x', 'executive-summary', 'uebergeben')""", (fid,))
f = core.fokus_kandidaten(tag)
ids = [k["taskId"] for k in f]
pruef("Älteste Überfällige zuerst", ids[:2] == ["ZZF-2", "ZZF-1"])
pruef("Heute nach Projektwert", ids[2:4] == ["ZZF-4", "ZZF-3"])
pruef("Woche danach", ids[4:] == ["ZZF-5"])
pruef("Aufgabe bei ACOS ausgelassen", "ZZF-6" not in ids)
pruef("Grund und Wert gesetzt", f[0]["grund"] == "seit 9 Tagen überfällig" and f[2]["wert"] == "10.000 €")
for i in range(7, 12):
    aufgabe(f"ZZF-X{i}", f"Weitere {i}", 1)
pruef("Höchstens 5 Vorschläge", len(core.fokus_kandidaten(tag)) == 5)
v = core.heute_start_view()
pruef("Heute liefert fokus, pipeline, acos_streifen", all(k in v for k in ("fokus", "pipeline", "acos_streifen")))

# 3) ACOS-Streifen
core._x("""INSERT INTO acos_auftraege (auftrags_id, task_id, firma_id, acos_client_id, artefakttyp, status, rueckfrage) VALUES
           ('AUF-2099-8002', 'ZZF-1', %s, 'x', 'executive-summary', 'rueckfrage', 'Landkreis oder Oberbayern?'),
           ('AUF-2099-8003', 'ZZF-3', %s, 'x', 'executive-summary', 'erledigt', NULL),
           ('AUF-2099-8004', 'ZZF-4', %s, 'x', 'executive-summary', 'bearbeitet', NULL)""", (fid, fid, fid))
s = [a for a in core.acos_streifen() if a["auftrags_id"].startswith("AUF-2099-80")]
pruef("Abgeschlossene nicht im Streifen", "AUF-2099-8003" not in [a["auftrags_id"] for a in s])
pruef("Rückfrage zuerst, mit Frage", s[0]["auftrags_id"] == "AUF-2099-8002" and s[0]["frage"] == "Landkreis oder Oberbayern?")
pruef("Abgelegt und in Arbeit dabei", {"AUF-2099-8001", "AUF-2099-8004"} <= {a["auftrags_id"] for a in s})
pruef("'seit' gesetzt", all(a["seit"] for a in s))

# Aufraeumen
core._x("DELETE FROM acos_auftraege WHERE auftrags_id LIKE 'AUF-2099-80%%'")
core._x("DELETE FROM tasks WHERE task_id LIKE 'ZZF-%%'")
core._x("DELETE FROM projekte WHERE id = ANY(%s)", (pids,))
core._x("DELETE FROM firmen WHERE id=%s", (fid,))
core._x("DELETE FROM pipeline_stand")
print(f"{ok} von {ok} Pruefungen gruen.")
