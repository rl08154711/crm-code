#!/usr/bin/env python3
"""Pruefung Kundenwissen / ACOS-Dokumente (03.11.2026), nur gegen crm_test.

Legt eine fiktive Firma mit ACOS-Verknuepfung und vier Dokumenten an, prueft
Liste, Suche, Link-Bildung und Ausschluesse und raeumt danach wieder auf.

Aufruf (Sandbox):  sudo -u crmapp env CRM_DB_NAME=crm_test python3 test_kundenwissen_acos.py /pfad/zu/CPX12-Postgres
"""
import os, sys

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core

FIRMA, CID = "ZZ Kundenwissen-Test (fiktiv)", "00000000-test-0000-0000-000000000001"
ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1

fid = core._x("INSERT INTO firmen (name, status) VALUES (%s,'Lead') RETURNING id", (FIRMA,))[0]["id"]
try:
    core._x("INSERT INTO acos_verknuepfung (firma_id, acos_client_id, zustand) VALUES (%s,%s,'bestaetigt')", (fid, CID))
    for aid, titel, art, datum, status, link in [
        ("t-doc-1", "Testbilanz 2025.pdf", "document", "2026-10-12 09:00+02", "neu", None),
        ("t-doc-2", "Stundungsantrag Test.pdf", "document", "2026-10-27 08:30+01", "abgelegt", None),
        ("t-doc-3", "Entfernt.pdf", "document", "2026-09-01 10:00+02", "entfernt", None),
        ("t-doc-4", "Mit eigenem Link.pdf", "document", "2026-10-01 10:00+02", "neu", "https://acos.example/x"),
        ("t-rep-1", "Bericht Stundung", "report", "2026-10-20 10:00+02", "abgelegt", None)]:
        core._x("""INSERT INTO acos_artefakte (firma_id, quelle, acos_id, titel, art, acos_geaendert_am, status, acos_link)
                   VALUES (%s,'wissen',%s,%s,%s,%s,%s,%s)""", (fid, aid, titel, art, datum, status, link))

    d = core.kundenwissen_firma(fid, {})
    docs = d["acos_dokumente"]
    titel = [x["titel"] for x in docs]
    pruef("Liste: drei Dokumente, neueste zuerst", titel == ["Stundungsantrag Test.pdf", "Testbilanz 2025.pdf", "Mit eigenem Link.pdf"])
    pruef("Liste: entfernte Dokumente fehlen", "Entfernt.pdf" not in titel)
    pruef("Liste: Berichte (kein document) fehlen", "Bericht Stundung" not in titel)
    pruef("Liste: Datum gesetzt", docs[0]["datum"] == "2026-10-27")
    pruef("Link: aus Vorlage mit Mandant", CID in docs[0]["link"] and docs[0]["link"].startswith("https://"))
    pruef("Link: von ACOS gelieferter Link hat Vorrang", docs[2]["link"] == "https://acos.example/x")
    pruef("Kein Inhalt, kein Download", all(set(x) == {"id", "quelle", "quelle_label", "titel", "datum", "link"} for x in docs))

    t = core.kundenwissen_firma(fid, {"q": "gestundet"})["treffer"]
    pruef("Suche: Wortwurzel findet Dokumenttitel", [x["titel"] for x in t if x["art"] == "acos_dok"] == ["Stundungsantrag Test.pdf"])
    t = core.kundenwissen_firma(fid, {"q": "Testbilanz"})["treffer"]
    pruef("Suche: Titeltreffer mit Link", len(t) == 1 and t[0]["link"])
    t = core.kundenwissen_firma(fid, {"q": "Entfernt"})["treffer"]
    pruef("Suche: entfernte Dokumente nicht gefunden", not any(x["art"] == "acos_dok" for x in t))

    core._x("DELETE FROM acos_verknuepfung WHERE firma_id=%s", (fid,))
    d = core.kundenwissen_firma(fid, {})
    pruef("Ohne Verknuepfung: Dokument ohne Link, kein Fehler", all(x["link"] == "" or x["link"].startswith("https://acos.example") for x in d["acos_dokumente"]))
finally:
    core._x("DELETE FROM firmen WHERE id=%s", (fid,))   # CASCADE raeumt Artefakte mit ab
print(f"\n{ok} von {ok} Pruefungen gruen.")
