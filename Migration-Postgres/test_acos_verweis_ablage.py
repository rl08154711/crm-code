#!/usr/bin/env python3
"""Pruefung Variante A (04.11.2026): ACOS-Dokument "nur in ACOS" wird "in Nextcloud",
sobald eine gleichnamige Datei im Kundenordner derselben Firma liegt. Nur gegen crm_test.

Aufruf (Sandbox):  sudo -u crmapp env CRM_DB_NAME=crm_test python3 test_acos_verweis_ablage.py /pfad/zu/CPX12-Postgres
"""
import os, sys

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core

A, B = "ZZ Ablage-Test A (fiktiv)", "ZZ Ablage-Test B (fiktiv)"
ok = 0
def pruef(name, bed):
    global ok
    print(("[OK]     " if bed else "[FEHLER] ") + name)
    if not bed:
        sys.exit(1)
    ok += 1

fa = core._x("INSERT INTO firmen (name, status) VALUES (%s,'Lead') RETURNING id", (A,))[0]["id"]
fb = core._x("INSERT INTO firmen (name, status) VALUES (%s,'Lead') RETURNING id", (B,))[0]["id"]
def status(aid):
    return core._q1("SELECT status, nextcloud_pfad, meldung FROM acos_artefakte WHERE acos_id=%s", (aid,))
try:
    for aid, fid, titel, art, st in [
        ("x1", fa, "Plan v3.docx", "document", "verweis"),          # exakt
        ("x2", fa, "VERTRAG Muster.pdf", "document", "verweis"),    # andere Schreibweise
        ("x3", fa, "Bilanz 2025", "document", "verweis"),           # Titel ohne Endung
        ("x4", fa, "Nur in ACOS.pdf", "document", "verweis"),       # keine Datei
        ("x5", fa, "Fremd.pdf", "document", "verweis"),             # Datei nur bei Firma B
        ("x6", fa, "Geloescht.pdf", "document", "verweis"),         # Datei entfernt
        ("x7", fa, "Plan v2.docx", "document", "verweis"),          # nur v3 vorhanden
        ("x8", fa, "Bericht.md", "report", "neu"),                  # kein Dokument
    ]:
        core._x("""INSERT INTO acos_artefakte (firma_id, quelle, acos_id, titel, art, status, meldung)
                   VALUES (%s,'wissen',%s,%s,%s,%s,'Datei bleibt in ACOS')""", (fid, aid, titel, art, st))
    for did, pfad, fid, weg in [
        ("ta-1", A + "/Planung/Plan v3.docx", fa, False),
        ("ta-2", A + "/Vertraege/Vertrag Muster.pdf", fa, False),
        ("ta-3", A + "/Bilanz 2025.pdf", fa, False),
        ("ta-4", B + "/Fremd.pdf", fb, False),
        ("ta-5", A + "/Geloescht.pdf", fa, True),
        ("ta-6", A + "/Bericht.md", fa, False),
    ]:
        core._x("INSERT INTO ablage_datei (datei_id, pfad, firma_id, entfernt) VALUES (%s,%s,%s,%s)", (did, pfad, fid, weg))

    n = core.acos_verweise_mit_ablage()
    basis = core.kunden_ablage_basis()
    pruef("Drei Dokumente umgestellt", n == 3)
    pruef("Exakter Name -> in Nextcloud", status("x1")["status"] == "abgelegt")
    pruef("Pfad zeigt auf die Datei im Kundenordner", status("x1")["nextcloud_pfad"] == f"{basis}/{A}/Planung/Plan v3.docx")
    pruef("Hinweis 'bleibt in ACOS' entfernt", status("x1")["meldung"] is None)
    pruef("Gross-/Kleinschreibung egal", status("x2")["status"] == "abgelegt")
    pruef("Titel ohne Endung findet Datei mit Endung", status("x3")["status"] == "abgelegt")
    pruef("Ohne Datei bleibt 'nur in ACOS'", status("x4")["status"] == "verweis")
    pruef("Datei einer anderen Firma zaehlt nicht", status("x5")["status"] == "verweis")
    pruef("Entfernte Datei zaehlt nicht", status("x6")["status"] == "verweis")
    pruef("Andere Version (v2 statt v3) zaehlt nicht", status("x7")["status"] == "verweis")
    pruef("Berichte werden nicht angefasst", status("x8")["status"] == "neu")
    pruef("Zweiter Lauf: nichts mehr zu tun", core.acos_verweise_mit_ablage() == 0)

    core._x("INSERT INTO ablage_datei (datei_id, pfad, firma_id) VALUES ('ta-7', %s, %s)", (A + "/Nur in ACOS.pdf", fa))
    pruef("Nur fuer eine Firma aufrufbar", core.acos_verweise_mit_ablage(fb) == 0 and core.acos_verweise_mit_ablage(fa) == 1)

    import wissen_sync
    pruef("Wissens-Abgleich ruft die Pruefung auf", "acos_verweise_mit_ablage" in open(wissen_sync.__file__).read())
finally:
    core._x("DELETE FROM ablage_datei WHERE datei_id LIKE 'ta-%%'")
    core._x("DELETE FROM firmen WHERE id IN (%s,%s)", (fa, fb))
print(f"\n{ok} von {ok} Pruefungen gruen.")
