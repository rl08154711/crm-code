#!/usr/bin/env python3
"""Pruefung ACOS-Dokumente als Verweis (04.11.2026, Migration 024), nur gegen crm_test.

Spielt einen scharfen ACOS-Abgleich mit erfundenen Daten durch. ACOS und Nextcloud sind
durch Attrappen ersetzt, es geht nichts nach aussen. Prueft:
  - Dokumente (art=document) landen auf Status 'verweis', nicht 'neu' ("wartet auf Ablage")
  - Berichte werden weiterhin in der Nextcloud abgelegt
  - vom CRM selbst gesendete Dokumente bleiben 'abgelegt'
  - ein in ACOS entferntes und wieder aufgetauchtes Dokument wird wieder 'verweis'
  - die Oberflaeche kennt das Etikett "nur in ACOS"

Aufruf (Sandbox):  sudo -u crmapp env CRM_DB_NAME=crm_test python3 test_acos_verweis.py /pfad/zu/CPX12-Postgres
"""
import os, sys

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core
import acos_sync

FIRMA, CID = "ZZ Verweis-Test (fiktiv)", "00000000-test-0000-0000-000000000024"
ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1

WISSEN = [
    {"id": "v-doc-1", "kind": "document", "title": "Testplan v2.docx", "updated_at": "2026-11-03T10:00:00Z"},
    {"id": "v-doc-2", "kind": "document", "title": "Testplan v3.docx", "updated_at": "2026-11-03T11:00:00Z"},
    {"id": "v-doc-3", "kind": "document", "title": "Selbst gesendet.pdf", "updated_at": "2026-11-02T09:00:00Z"},
    {"id": "v-rep-1", "kind": "report", "title": "Testbericht", "updated_at": "2026-11-03T12:00:00Z"},
]

class MockMcp:
    def __init__(self, *a): pass
    def start(self): pass
    def lesen(self, name, args=None):
        if name == "am_acos_clients_list":
            return {"clients": [{"id": CID, "name": FIRMA, "status": "lead"}]}
        if name == "am_acos_knowledge_list":
            return {"objects": list(WISSEN), "truncated": False}
        if name == "am_acos_knowledge_get":
            return {"id": args.get("id"), "data": {"markdown": "Inhalt (fiktiv)"}}
        raise AssertionError("unerwarteter Lesezugriff: " + name)
    def aendern(self, name, args):
        return {}

class MockAblage:
    dateien_angelegt = []
    def __init__(self): pass
    def gibt_es(self, rel): return rel == FIRMA or rel.startswith(FIRMA + "/ACOS") and rel.count("/") < 3
    def ordner(self, rel): pass
    def datei(self, rel, daten): MockAblage.dateien_angelegt.append(rel)

acos_sync.Mcp = MockMcp
acos_sync.Ablage = MockAblage
acos_sync.lade_acos_zugang = lambda: {"ACOS_TOKEN": "x", "ACOS_MCP_URL": "https://acos.invalid/mcp"}
acos_sync.modus = lambda: "scharf"
acos_sync.pruefwert = lambda d: "fest"
acos_sync.log = lambda m: None

# andere Firmen der Testdatenbank aus dem Abgleich heraushalten
andere = core._q("SELECT id FROM firmen WHERE acos_fuehren AND name <> %s", (FIRMA,))
core._x("UPDATE firmen SET acos_fuehren=false WHERE id = ANY(%s)", ([r["id"] for r in andere] or [0],))

fid = core._x("INSERT INTO firmen (name, status, acos_fuehren) VALUES (%s,'Lead',true) RETURNING id", (FIRMA,))[0]["id"]
try:
    core._x("""INSERT INTO acos_verknuepfung (firma_id, acos_client_id, acos_name, zustand, pruefwert)
               VALUES (%s,%s,%s,'bestaetigt','fest')""", (fid, CID, FIRMA))
    # Altbestand wie live: ein Dokument steht schon auf 'neu'
    core._x("""INSERT INTO acos_artefakte (firma_id, quelle, acos_id, titel, art, status)
               VALUES (%s,'wissen','v-doc-1','Testplan v2.docx','document','neu')""", (fid,))
    # vom CRM selbst an ACOS gesendet
    core._x("""INSERT INTO acos_uploads (firma_id, pfad, acos_client_id, status, acos_document_id, gesendet_am)
               VALUES (%s,'Unterlagen/Selbst gesendet.pdf',%s,'gesendet','v-doc-3',now())""", (fid, CID))

    pruef("Abgleich laeuft ohne Fehler", acos_sync.abgleich("test") is True)
    st = {r["acos_id"]: r for r in core._q("SELECT acos_id, status, meldung FROM acos_artefakte WHERE firma_id=%s", (fid,))}
    pruef("Altbestand-Dokument: verweis statt neu", st["v-doc-1"]["status"] == "verweis")
    pruef("Neues Dokument: verweis statt neu", st["v-doc-2"]["status"] == "verweis")
    pruef("Verweis mit Hinweistext", "bleibt in ACOS" in (st["v-doc-2"]["meldung"] or ""))
    pruef("Selbst gesendetes Dokument bleibt abgelegt", st["v-doc-3"]["status"] == "abgelegt")
    pruef("Bericht weiterhin in der Nextcloud abgelegt", st["v-rep-1"]["status"] == "abgelegt")
    pruef("Keine Dokument-Datei in die Nextcloud geschrieben",
          len(MockAblage.dateien_angelegt) == 1 and "Testbericht" in MockAblage.dateien_angelegt[0])
    pruef("Kein Artefakt mehr auf 'neu'", not any(r["status"] == "neu" for r in st.values()))

    # zweiter Lauf: nichts aendert sich, nichts wird doppelt abgelegt
    acos_sync.abgleich("test")
    st2 = {r["acos_id"]: r["status"] for r in core._q("SELECT acos_id, status FROM acos_artefakte WHERE firma_id=%s", (fid,))}
    pruef("Zweiter Lauf stabil", st2 == {k: v["status"] for k, v in st.items()} and len(MockAblage.dateien_angelegt) == 1)

    # in ACOS entfernt, dann wieder da
    WISSEN[:] = [w for w in WISSEN if w["id"] != "v-doc-2"]
    acos_sync.abgleich("test")
    pruef("In ACOS entfernt -> entfernt", core._q1("SELECT status FROM acos_artefakte WHERE acos_id='v-doc-2'")["status"] == "entfernt")
    WISSEN.append({"id": "v-doc-2", "kind": "document", "title": "Testplan v3.docx", "updated_at": "2026-11-03T11:00:00Z"})
    acos_sync.abgleich("test")
    pruef("Wieder aufgetaucht -> verweis", core._q1("SELECT status FROM acos_artefakte WHERE acos_id='v-doc-2'")["status"] == "verweis")

    # Kundenwissen zeigt Verweise weiterhin
    titel = [x["titel"] for x in core.kundenwissen_firma(fid, {})["acos_dokumente"]]
    pruef("Kundenwissen listet die Verweise", "Testplan v3.docx" in titel and "Testplan v2.docx" in titel)

    pruef("Oberflaeche: Etikett 'nur in ACOS'", "verweis: ['nur in ACOS'" in core.ACOS_JS)
finally:
    core._x("DELETE FROM acos_uploads WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM firmen WHERE id=%s", (fid,))
    core._x("UPDATE firmen SET acos_fuehren=true WHERE id = ANY(%s)", ([r["id"] for r in andere] or [0],))
print(f"\n{ok} von {ok} Pruefungen gruen.")
