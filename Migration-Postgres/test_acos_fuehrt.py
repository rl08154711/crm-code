#!/usr/bin/env python3
"""Pruefung "ACOS fuehrt" (Migration 031, 25.11.2026), nur gegen crm_test, erfundene Daten.

Auftrag zurueckziehen, Doppelklick-Sperre, Rueckfrage mit Auswahl (data.optionen bzw. aus dem Text),
Abgleich: in ACOS geloeschte Auftraege/Rueckfragen, entfernte und neu gefasste Wissensobjekte
(Kopie umbenannt mit Vorsatz ARCHIVIERT_, 27.11.2026), direkt hochgeladene Dokumente als Textauszug. ACOS und Nextcloud sind Attrappen.

Aufruf:  CRM_DB_NAME=crm_test python3 test_acos_fuehrt.py /pfad/zu/CPX12-Postgres
"""
import os, sys, threading, urllib.error

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core
import acos_sync
import acos_auftraege as auf

FIRMA, CID = "ZZ Fuehrt-Test (fiktiv)", "00000000-test-0000-0000-000000000031"
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

OBJEKTE = {}   # Auftraege, Rueckfragen, Wissen: id -> dict
TEXTE = {}     # Dokument-ID -> Text (am_acos_file_read)
LESEFEHLER = {"an": False}
DATEIEN, ORDNER = {}, {FIRMA}
SPERRE = {"an": False}

class MockMcp:
    def __init__(self, *a): pass
    def start(self): pass
    def lesen(self, name, args=None):
        args = args or {}
        if name == "am_acos_clients_list":
            return {"clients": [{"id": CID, "name": FIRMA, "status": "lead"}]}
        if name == "am_acos_knowledge_list":
            if LESEFEHLER["an"] and args.get("kind"):
                raise acos_sync.AcosFehler("am_acos_knowledge_list: Zeitüberschreitung")
            l = [{"id": k, "kind": o["kind"], "title": o["title"], "updated_at": o.get("upd", "2026-11-20T10:00:00Z"),
                  "created_at": "2026-11-20T10:00:00Z"} for k, o in OBJEKTE.items()]
            if args.get("kind"):
                l = [o for o in l if o["kind"] == args["kind"]]
            return {"objects": l, "truncated": False}
        if name == "am_acos_knowledge_get":
            o = OBJEKTE.get(args.get("id")) or {}
            return {"id": args.get("id"), "data": o.get("data") or {"markdown": o.get("md", "Inhalt (fiktiv)")}}
        if name == "am_acos_file_read":
            t = TEXTE.get(args.get("document_id"), "")
            return {"text": t, "next_offset": None}
        if name == "am_acos_artifact_specs_list":
            return {"specs": [{"slug": "mandatsstart-analyse", "title": "Mandatsstart-Analyse", "number": "21", "required_inputs": []}]}
        raise AssertionError("unerwarteter Lesezugriff: " + name)
    def aendern(self, name, args):
        if name == "am_acos_knowledge_save":
            oid = f"obj-{len(OBJEKTE) + 1}"
            OBJEKTE[oid] = {"kind": args["kind"], "title": args["title"], "data": args["data"]}
            return {"id": oid}
        return {"id": CID}

class MockAblage:
    def __init__(self, basis_pfad=None): pass
    def gibt_es(self, rel):
        return rel in DATEIEN or rel in ORDNER or any(r.startswith(rel + "/") for r in list(DATEIEN) + list(ORDNER))
    def ordner(self, rel): ORDNER.add(rel.rstrip("/"))
    def datei(self, rel, daten):
        assert rel not in DATEIEN, "nie ueberschreiben"
        DATEIEN[rel] = daten
    def verschieben(self, rel, ziel):
        # wie die echte Nextcloud ohne Loeschrecht (27.11.2026): in einen anderen Ordner -> 403,
        # Umbenennen im selben Ordner erlaubt
        if SPERRE["an"] or rel.rsplit("/", 1)[0] != ziel.rsplit("/", 1)[0]:
            raise urllib.error.HTTPError("https://nc.invalid/" + rel, 403, "Forbidden", {}, None)
        assert ziel not in DATEIEN, "nie ueberschreiben"
        DATEIEN[ziel] = DATEIEN.pop(rel)
    def dateien(self, firma): return []

acos_sync.Mcp = MockMcp
acos_sync.Ablage = MockAblage
acos_sync.lade_acos_zugang = lambda: {"ACOS_TOKEN": "x", "ACOS_MCP_URL": "https://acos.invalid/mcp"}
acos_sync.modus = lambda: "scharf"
acos_sync.log = lambda m: None
auf._modus_scharf = lambda: True
auf._mcp = lambda: MockMcp()

def status(aid): return core._q1("SELECT * FROM acos_auftraege WHERE auftrags_id=%s", (aid,))
def tstatus(t): return core._q1("SELECT status FROM tasks WHERE task_id=%s", (t,))["status"]
def rueckfrage(aid, text, optionen=None, st="rueckfrage"):
    d = {"auftrags_id": aid, "status": st, "text": text}
    if optionen:
        d["optionen"] = optionen
    OBJEKTE[f"rf-{aid}"] = {"kind": "crm_rueckfrage", "title": f"Rückfrage {aid}", "data": d}
def objekt_id(aid): return status(aid)["auftrag_objekt_id"]

pruef("Migration 031: Spalten da", core._spalte_da("acos_auftraege", "rueckfrage_optionen") and core._spalte_da("acos_auftraege", "zurueckgezogen_am"))

# ── Optionen aus dem Text ──
T12 = ("Der Auftrag ist inhaltsgleich mit AUF-2026-0013/0014, und die Mandatsstart-Analyse braucht als Pflicht-Input ein Webprofil. "
       "Bitte wählen: A) Auftrag entfällt, erledigt über AUF-2026-0014; B) eigene Analyse nur aus den Unterlagen der Kundenakte, "
       "Website-Kapitel als Lücke, ohne kostenpflichtige Abrufe; C) wie B, zusätzlich Recherche freigegeben (Northdata, Fördermittel-Match).")
o = auf.optionen_aus_text(T12)
pruef("Optionen aus dem Text: A, B, C", [x["key"] for x in o] == ["A", "B", "C"])
pruef("Optionstext ohne Trennzeichen", o[0]["text"] == "Auftrag entfällt, erledigt über AUF-2026-0014" and o[2]["text"].endswith("Fördermittel-Match)."))
pruef("Frage ohne Optionsteil", auf.frage_ohne_optionen(T12, o).endswith("ein Webprofil."))
pruef("Ohne Optionen: leer", auf.optionen_aus_text("Welche Region soll es sein?") == [])
pruef("Klammer im Fließtext ist keine Option", auf.optionen_aus_text("Siehe Anlage a) und Punkt B) weiter.") == [])

andere = core._q("SELECT id FROM firmen WHERE acos_fuehren AND name <> %s", (FIRMA,))
core._x("UPDATE firmen SET acos_fuehren=false WHERE id = ANY(%s)", ([r["id"] for r in andere] or [0],))
fid = core._x("INSERT INTO firmen (name, status, acos_fuehren) VALUES (%s,'Lead',true) RETURNING id", (FIRMA,))[0]["id"]
try:
    core._x("""INSERT INTO acos_verknuepfung (firma_id, acos_client_id, acos_name, zustand, pruefwert)
               VALUES (%s,%s,%s,'bestaetigt','fest')""", (fid, CID, FIRMA))
    t1 = core.create_task({"title": "Analyse A", "firma_id": fid})
    t2 = core.create_task({"title": "Analyse B", "firma_id": fid})
    t3 = core.create_task({"title": "Analyse C", "firma_id": fid})

    # ── Doppelklick ──
    sperre = auf._SPERREN.setdefault(str(t1), threading.Lock()); sperre.acquire()
    pruef("Doppelklick: zweite Übergabe während der ersten abgelehnt", wirft(lambda: auf.uebergeben(t1, {"thema": "Markt"}), "läuft bereits"))
    sperre.release()
    a1 = auf.uebergeben(t1, {"thema": f"Markt von {FIRMA}, Website www.zz-fuehrt-test.example"}, "tester")["aktiv"]["auftrags_id"]
    pruef("Klartext: Firmenname und Website im Thema gehen an ACOS", FIRMA in OBJEKTE[objekt_id(a1)]["data"]["thema"])
    pruef("Danach zweite Übergabe: 'liegt noch bei ACOS'", wirft(lambda: auf.uebergeben(t1, {"thema": "Markt"}), "liegt noch bei ACOS"))
    pruef("Nur ein Auftrag angelegt", core._q1("SELECT count(*) n FROM acos_auftraege WHERE task_id=%s", (t1,))["n"] == 1)

    # ── Rueckfrage mit data.optionen ──
    rueckfrage(a1, "Welche Region?", [{"key": "A", "text": "Landkreis"}, {"key": "B", "text": "Oberbayern"}])
    acos_sync.abgleich("test")
    s1 = status(a1)
    pruef("Rückfrage übernommen, Optionen aus ACOS gespeichert", s1["status"] == "rueckfrage" and [x["key"] for x in s1["rueckfrage_optionen"]] == ["A", "B"])
    akt = auf.auftraege_zu_aufgabe(t1)["aktiv"]
    pruef("Aufgabenfenster bekommt Optionen und Frage", [x["text"] for x in akt["optionen"]] == ["Landkreis", "Oberbayern"] and akt["frage"] == "Welche Region?")
    pruef("Unbekannte Option abgelehnt", wirft(lambda: auf.uebergeben(t1, {"antwort_option": "Z"}), "gibt es nicht"))
    neu = auf.uebergeben(t1, {"antwort_option": "B", "ergaenzung": "nur Kernthema"}, "tester")["aktiv"]["auftrags_id"]
    hinw = OBJEKTE[objekt_id(neu)]["data"]["hinweise"]
    pruef("Antwort an ACOS im Wortlaut mit Frage", f"Antwort auf die Rückfrage zu {a1}" in hinw and "„Welche Region?“" in hinw
          and "B) Oberbayern. Ergänzung: nur Kernthema" in hinw)
    pruef("Alter Auftrag ersetzt", status(a1)["status"] == "ersetzt")

    # ── Zurueckziehen: uebergeben ──
    vorher = len(OBJEKTE)
    d = auf.zurueckziehen(t1, "tester")
    pruef("Zurückziehen: Status zurückgezogen, Aufgabe wieder Offen", status(neu)["status"] == "zurueckgezogen" and tstatus(t1) == "Offen")
    marke = [x for x in OBJEKTE.values() if x["title"] == f"Zurückgezogen {neu}"]
    pruef("Zurückziehen: Vermerk in ACOS angelegt (nichts gelöscht)", len(marke) == 1 and len(OBJEKTE) == vorher + 1
          and marke[0]["kind"] == "crm_rueckfrage" and marke[0]["data"]["status"] == "zurueckgezogen")
    pruef("Zurückziehen: Aufgabe nicht mehr gesperrt", core.update_task(t1, {"status": "Erledigt"}) is not None or tstatus(t1) == "Erledigt")
    pruef("Zurückziehen: Verlauf und Fenster", "zurueckgezogen" in [v["art"] for v in d["verlauf"]] and d["aktiv"]["status"] == "zurueckgezogen")
    pruef("Zurückziehen: keine offene Meldung", not [m for m in auf.meldungen() if m["taskId"] == t1])
    pruef("Zweimal zurückziehen abgelehnt", wirft(lambda: auf.zurueckziehen(t1), "kein Auftrag"))

    # ── Zurueckziehen: Rueckfrage aus dem Text (Altfall) ──
    a2 = auf.uebergeben(t2, {"thema": "Markt"})["aktiv"]["auftrags_id"]
    rueckfrage(a2, T12)
    acos_sync.abgleich("test")
    akt2 = auf.auftraege_zu_aufgabe(t2)["aktiv"]
    pruef("Altfall: Optionen aus dem Text erkannt", [x["key"] for x in akt2["optionen"]] == ["A", "B", "C"])
    n = len(OBJEKTE)
    auf.zurueckziehen(t2)
    pruef("Rückfrage zurückgezogen: kein zusätzlicher Vermerk nötig", len(OBJEKTE) == n and status(a2)["status"] == "zurueckgezogen")

    # ── zwei Auftraege an einer Aufgabe (Fall 0012/0014): gezielt den aelteren zurueckziehen ──
    t4 = core.create_task({"title": "Analyse D", "firma_id": fid})
    alt = auf.uebergeben(t4, {"thema": "Markt"})["aktiv"]["auftrags_id"]
    core._x("UPDATE acos_auftraege SET angelegt_am = angelegt_am - interval '2 minutes' WHERE auftrags_id=%s", (alt,))
    rueckfrage(alt, "Alt? A) ja B) nein")
    acos_sync.abgleich("test")
    core._x("UPDATE acos_auftraege SET status='uebergeben' WHERE auftrags_id=%s", (alt,))   # Doppelklick-Altfall nachstellen:
    jung = auf._uebergeben(t4, {"thema": "Markt", "ersetzen": True})["aktiv"]["auftrags_id"]
    core._x("UPDATE acos_auftraege SET status='rueckfrage', ersetzt_durch=NULL WHERE auftrags_id=%s", (alt,))
    pruef("Altfall: zwei offene Aufträge an einer Aufgabe", status(alt)["status"] == "rueckfrage" and status(jung)["status"] == "uebergeben")
    auf.zurueckziehen(t4, auftrags_id=alt)
    pruef("Gezielt den älteren zurückgezogen, der jüngere läuft weiter", status(alt)["status"] == "zurueckgezogen" and status(jung)["status"] == "uebergeben")
    pruef("…Aufgabe bleibt in Bearbeitung", tstatus(t4) == "In Bearbeitung")
    pruef("Falsche Auftrags-ID abgelehnt", wirft(lambda: auf.zurueckziehen(t4, auftrags_id=alt), "nicht (mehr)"))
    auf.zurueckziehen(t4, auftrags_id=jung)
    pruef("…danach der jüngere, Aufgabe frei", tstatus(t4) == "Offen")
    core._x("UPDATE acos_auftraege SET status='rueckfrage' WHERE auftrags_id=%s", (jung,))
    pruef("…Firma steht in der Liste", fid in acos_sync.offene_auftrags_firmen())
    core._x("UPDATE acos_auftraege SET status='zurueckgezogen' WHERE auftrags_id=%s", (jung,))

    # ── Aufgabe geloescht (Fall 0009/PROJ-056) ──
    t5 = core.create_task({"title": "Analyse E", "firma_id": fid})
    a5 = auf.uebergeben(t5, {"thema": "Markt"})["aktiv"]["auftrags_id"]
    core._x("DELETE FROM tasks WHERE task_id=%s", (t5,))   # Altfall: Aufgabe weg, Auftrag noch offen
    pruef("Verwaist: Zurückziehen mit Auftrags-ID geht trotzdem", auf.zurueckziehen(t5, auftrags_id=a5)["ok"] and status(a5)["status"] == "zurueckgezogen")
    t6 = core.create_task({"title": "Analyse F", "firma_id": fid})
    a6 = auf.uebergeben(t6, {"thema": "Markt"})["aktiv"]["auftrags_id"]
    core._x("DELETE FROM tasks WHERE task_id=%s", (t6,))
    acos_sync.abgleich("test")
    pruef("Verwaist: Abgleich beendet den Auftrag von selbst", status(a6)["status"] == "zurueckgezogen")
    t7 = core.create_task({"title": "Analyse G", "firma_id": fid})
    a7 = auf.uebergeben(t7, {"thema": "Markt"})["aktiv"]["auftrags_id"]
    core.delete_task(t7)
    pruef("Aufgabe löschen zieht laufenden Auftrag zurück", status(a7)["status"] == "zurueckgezogen")
    pruef("…nicht mehr im Streifen", a7 not in [x["auftrags_id"] for x in core.acos_streifen()])

    # ── ACOS fuehrt: Auftrag in ACOS geloescht ──
    a3 = auf.uebergeben(t3, {"thema": "Markt"})["aktiv"]["auftrags_id"]
    LESEFEHLER["an"] = True
    del OBJEKTE[objekt_id(a3)]
    acos_sync.abgleich("test")
    pruef("Lesefehler: nichts verändert", status(a3)["status"] == "uebergeben")
    LESEFEHLER["an"] = False
    acos_sync.abgleich("test")
    pruef("Auftrag in ACOS gelöscht: im CRM beendet, Aufgabe frei", status(a3)["status"] == "zurueckgezogen" and tstatus(t3) == "Offen")
    pruef("…mit Meldung auf Heute", any(m["auftrags_id"] == a3 and m["art"] == "zurueckgezogen" for m in auf.meldungen()))
    pruef("…und nicht mehr im Streifen", a3 not in [x["auftrags_id"] for x in core.acos_streifen()])

    # ── ACOS fuehrt: Rueckfrage in ACOS geloescht ──
    a4 = auf.uebergeben(t3, {"thema": "Neu"})["aktiv"]["auftrags_id"]
    rueckfrage(a4, "Welche Region? A) Landkreis B) Oberbayern")
    acos_sync.abgleich("test")
    pruef("Rückfrage da", status(a4)["status"] == "rueckfrage")
    del OBJEKTE[f"rf-{a4}"]
    acos_sync.abgleich("test")
    s4 = status(a4)
    pruef("Rückfrage in ACOS gelöscht: zurück auf übergeben", s4["status"] == "uebergeben" and s4["rueckfrage"] is None and tstatus(t3) == "In Bearbeitung")
    pruef("…Rückfrage-Meldung als gesehen", not [m for m in auf.meldungen() if m["auftrags_id"] == a4 and m["art"] == "rueckfrage"])

    # ── Vermerk 'zurueckgezogen' von anderswo ──
    rueckfrage(a4, "Bitte nicht bearbeiten", st="zurueckgezogen")
    acos_sync.abgleich("test")
    pruef("Vermerk 'zurückgezogen' in ACOS beendet den Auftrag", status(a4)["status"] == "zurueckgezogen")

    # ── Wissensobjekte: entfernt -> archiviert ──
    basis = core.kunden_ablage_basis()
    OBJEKTE["w-1"] = {"kind": "report", "title": "Bericht eins", "md": "Fassung 1", "upd": "2026-11-20T10:00:00Z"}
    OBJEKTE["w-2"] = {"kind": "report", "title": "Bericht zwei", "md": "Inhalt", "upd": "2026-11-20T10:00:00Z"}
    acos_sync.abgleich("test")
    p1 = core._q1("SELECT nextcloud_pfad FROM acos_artefakte WHERE acos_id='w-1'")["nextcloud_pfad"]
    p2 = core._q1("SELECT nextcloud_pfad FROM acos_artefakte WHERE acos_id='w-2'")["nextcloud_pfad"]
    pruef("Wissen abgelegt unter ACOS/Wissen", "/ACOS/Wissen/" in p1 and p1[len(basis) + 1:] in DATEIEN)
    rel2 = p2[len(basis) + 1:]
    core._x("""INSERT INTO kundenwissen (firma_id, pfad, quelle, name, titel, typ, status, abgeglichen_am)
               VALUES (%s,%s,'acos','x.md','Bericht zwei','md','ok',now())""", (fid, rel2))
    del OBJEKTE["w-2"]
    acos_sync.abgleich("test")
    r2 = core._q1("SELECT status, nextcloud_pfad FROM acos_artefakte WHERE acos_id='w-2'")
    pruef("In ACOS entfernt: Kopie im selben Ordner mit ARCHIVIERT_ umbenannt", r2["status"] == "entfernt"
          and r2["nextcloud_pfad"].rsplit("/", 1)[0] == p2.rsplit("/", 1)[0]
          and r2["nextcloud_pfad"].rsplit("/", 1)[1] == "ARCHIVIERT_" + p2.rsplit("/", 1)[1]
          and rel2 not in DATEIEN and r2["nextcloud_pfad"][len(basis) + 1:] in DATEIEN)
    pruef("…nicht mehr im Kundenwissen", not core._q1("SELECT 1 FROM kundenwissen WHERE pfad=%s", (rel2,)))
    pruef("…nicht mehr in der ACOS-Liste am Unternehmen", "Bericht zwei" not in [a["titel"] for a in core.load_acos_firma(fid)["artefakte"]])
    acos_sync.abgleich("test")
    pruef("Zweiter Lauf: nichts doppelt archiviert", sum(1 for k in DATEIEN if "/ARCHIVIERT_" in k) == 1)
    pruef("Kein Ordner archiviert/ mehr nötig", not any("/archiviert" in k for k in ORDNER))
    pruef("Archivierte Kopie gilt als archiviert", acos_sync.ist_archiviert(r2["nextcloud_pfad"])
          and acos_sync.ist_archiviert("Kunden/X/ACOS/Wissen/archiviert/a.md") and not acos_sync.ist_archiviert(p1))

    # ── Nextcloud verweigert (z. B. 403): einmal Fehler mit Code, dann kein neuer Versuch ──
    OBJEKTE["w-3"] = {"kind": "report", "title": "Bericht drei", "md": "Inhalt", "upd": "2026-11-20T10:00:00Z"}
    acos_sync.abgleich("test")
    p3 = core._q1("SELECT nextcloud_pfad FROM acos_artefakte WHERE acos_id='w-3'")["nextcloud_pfad"]
    del OBJEKTE["w-3"]
    SPERRE["an"] = True
    acos_sync.abgleich("test")
    r3 = core._q1("SELECT status, nextcloud_pfad, meldung FROM acos_artefakte WHERE acos_id='w-3'")
    n1 = "Kopie nicht archiviert: Bericht drei" in str(core._q1("SELECT bericht FROM acos_laeufe ORDER BY id DESC LIMIT 1")["bericht"])
    pruef("Verweigert: Kopie bleibt, Meldung mit HTTP-Code", n1 and r3["nextcloud_pfad"] == p3 and p3[len(basis) + 1:] in DATEIEN
          and "HTTP 403" in (r3["meldung"] or "") and "von Hand" in r3["meldung"])
    acos_sync.abgleich("test")
    n2 = "Kopie nicht archiviert: Bericht drei" in str(core._q1("SELECT bericht FROM acos_laeufe ORDER BY id DESC LIMIT 1")["bericht"])
    pruef("Verweigert: kein neuer Versuch und keine neue Fehlermeldung beim nächsten Lauf", not n2
          and core._q1("SELECT nextcloud_pfad FROM acos_artefakte WHERE acos_id=%s", ("w-3",))["nextcloud_pfad"] == p3)
    SPERRE["an"] = False

    # ── neue Fassung ──
    OBJEKTE["w-1"].update(md="Fassung 2", upd="2026-11-25T10:00:00Z")
    acos_sync.abgleich("test")
    r1 = core._q1("SELECT status, nextcloud_pfad FROM acos_artefakte WHERE acos_id='w-1'")
    arch = [k for k in DATEIEN if "/ARCHIVIERT_" in k and "Bericht eins" in k]
    pruef("Neue Fassung: alte Kopie archiviert", len(arch) == 1 and b"Fassung 1" in DATEIEN[arch[0]])
    pruef("Neue Fassung: neue Kopie abgelegt", r1["status"] == "abgelegt" and b"Fassung 2" in DATEIEN[r1["nextcloud_pfad"][len(basis) + 1:]])
    acos_sync.abgleich("test")
    pruef("Unveränderte Fassung: kein weiterer Durchlauf", len([k for k in DATEIEN if "Bericht eins" in k]) == 2)

    # ── direkt hochgeladene Dokumente ──
    OBJEKTE["d-1"] = {"kind": "document", "title": "Gesprächsunterlage.docx"}
    OBJEKTE["d-2"] = {"kind": "document", "title": "Foto.png"}
    TEXTE["d-1"] = "Text der Unterlage (fiktiv)"
    acos_sync.abgleich("test")
    d1 = core._q1("SELECT status, nextcloud_pfad, meldung FROM acos_artefakte WHERE acos_id='d-1'")
    pruef("Direkt hochgeladen: Textauszug unter ACOS/Dokumente", d1["status"] == "abgelegt" and "/ACOS/Dokumente/" in d1["nextcloud_pfad"]
          and b"Text der Unterlage" in DATEIEN[d1["nextcloud_pfad"][len(basis) + 1:]] and "Original in ACOS" in d1["meldung"])
    d2 = core._q1("SELECT status, meldung FROM acos_artefakte WHERE acos_id='d-2'")
    pruef("Ohne lesbaren Text: bleibt Verweis, mit Hinweis", d2["status"] == "verweis" and d2["meldung"].startswith("Kein Text"))
    kw = [x["titel"] for x in core._kw_acos_dokumente(fid)] if hasattr(core, "_kw_acos_dokumente") else []
    pruef("Kundenwissen: Textauszug nicht doppelt als ACOS-Dokument", "Gesprächsunterlage.docx" not in kw)
    n_dok = len(DATEIEN)
    acos_sync.abgleich("test")
    pruef("Zweiter Lauf: kein zweiter Auszug", len(DATEIEN) == n_dok)

    # ── Oberflaeche ──
    q = open(core.__file__, encoding="utf-8").read()
    pruef("Oberfläche: Auswahl, Zurückziehen, Doppelklick-Sperre", all(x in q for x in
          ("auf-opts", "function aufZurueckziehen", "function fkZurueckziehen", "_akaLaeuft", "sb.disabled = true")))
finally:
    core._x("DELETE FROM acos_auftrag_verlauf WHERE task_id IN (SELECT task_id FROM tasks WHERE firma_id=%s)", (fid,))
    core._x("DELETE FROM acos_auftraege WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM aktivitaeten WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM acos_artefakte WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM kundenwissen WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM tasks WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM acos_verknuepfung WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM firmen WHERE id=%s", (fid,))
    core._x("UPDATE firmen SET acos_fuehren=true WHERE id = ANY(%s)", ([r["id"] for r in andere] or [0],))
print(f"\n{ok} von {ok} Pruefungen gruen.")
