#!/usr/bin/env python3
"""Pruefung "Aufgabe als Auftrag an ACOS" (Migration 026/027), nur gegen crm_test.

Spielt den ganzen Weg mit erfundenen Daten durch. ACOS und Nextcloud sind durch Attrappen
ersetzt, es geht nichts nach aussen:
  Aufgabe -> Vorpruefung Kundenordner -> Auftragsdatei -> Rueckfrage -> Antwort (Folgeauftrag) ->
  Artefakt (Auftrags-ID im Titel) -> Abgleich legt es ab -> Auftrag "bearbeitet", Aufgabe
  "Bearbeitet", Verlauf, Journal -> Status gesperrt -> "Geprueft, abschliessen" -> erledigt.
Dazu: Webseite am Unternehmen geht mit dem Abgleich an ACOS.

Aufruf (Sandbox):  CRM_DB_NAME=crm_test python3 test_acos_auftraege.py /pfad/zu/CPX12-Postgres
"""
import json, os, sys

if os.environ.get("CRM_DB_NAME") != "crm_test":
    sys.exit("Nur gegen crm_test (CRM_DB_NAME=crm_test).")
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "../CPX12-Postgres")
import crm_core as core
import acos_sync
import acos_auftraege as auf

FIRMA, CID = "ZZ Auftrag-Test (fiktiv)", "00000000-test-0000-0000-000000000026"
FIRMA2 = "ZZ Ohne ACOS (fiktiv)"
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

WISSEN = []
OBJEKTE = {}      # in ACOS angelegte Auftrags-/Rueckfrage-Objekte: id -> {kind, title, data, client_id}
ACOS_AUS = {"an": True}
SPECS = [{"slug": "mandatsstart-analyse", "title": "Mandatsstart-Analyse für die Geschäftsführung", "number": "21",
          "purpose": "Vollständige Mandatsstart-Analyse.", "required_inputs": [{"type": "master_data"}, {"type": "intelligence", "kind": "website_profile"}]},
         {"slug": "executive-summary", "title": "Executive Summary", "number": "3", "purpose": "Kompakte Standortbestimmung.",
          "required_inputs": [{"type": "master_data"}]},
         {"slug": "marketing-strategie", "title": "Marketing-Strategie", "number": "5", "purpose": "Strategie.",
          "required_inputs": [{"type": "artifact", "spec": "executive-summary"}]}]
GESENDET = []
GEAENDERT = []    # an ACOS gesendete Stammdaten
DATEIEN = {}      # (basis, rel) -> bytes
ORDNER = {("kunden", FIRMA), ("auftraege", "")}

class MockMcp:
    def __init__(self, *a): pass
    def start(self): pass
    def lesen(self, name, args=None):
        if name == "am_acos_clients_list":
            return {"clients": [{"id": CID, "name": FIRMA, "status": "lead"}]}
        if name == "am_acos_knowledge_list":
            eigene = [{"id": k, "kind": o["kind"], "title": o["title"], "updated_at": "2026-11-17T10:00:00Z"}
                      for k, o in OBJEKTE.items() if o["client_id"] == (args or {}).get("client_id")]
            if (args or {}).get("kind"):
                return {"objects": [o for o in eigene if o["kind"] == args["kind"]], "truncated": False}
            return {"objects": list(WISSEN) + eigene, "truncated": False}
        if name == "am_acos_artifact_specs_list":
            return {"count": len(SPECS), "specs": list(SPECS)}
        if name == "am_acos_context_pack":
            gaps = [{"input": {"type": "intelligence", "kind": "website_profile"}, "required": True},
                    {"input": {"type": "intelligence", "kind": "visibility_index"}, "required": False}]
            return {"gaps": gaps if args.get("slug") == "mandatsstart-analyse" else []}
        if name == "am_acos_knowledge_get":
            if args.get("id") in OBJEKTE:
                return {"id": args["id"], "data": OBJEKTE[args["id"]]["data"]}
            return {"id": args.get("id"), "data": {"markdown": "Analyse (fiktiv)"}}
        raise AssertionError("unerwarteter Lesezugriff: " + name)
    def aendern(self, name, args):
        GEAENDERT.append((name, args))
        if name == "am_acos_knowledge_save":
            if not ACOS_AUS["an"]:
                raise RuntimeError("ACOS antwortet nicht")
            oid = f"obj-{len(OBJEKTE) + 1}"
            OBJEKTE[oid] = {"kind": args["kind"], "title": args["title"], "data": args["data"], "client_id": args["client_id"]}
            return {"status": "created", "id": oid, "kind": args["kind"]}
        return {"id": CID}

def rueckfrage(aid, status, text):
    OBJEKTE[f"rf-{aid}"] = {"kind": "crm_rueckfrage", "title": f"Rückfrage {aid}", "client_id": CID,
                            "data": {"auftrags_id": aid, "status": status, "text": text}}

def auftragsobjekt(aid):
    return next((o for o in OBJEKTE.values() if o["kind"] == "crm_auftrag" and aid in o["title"]), None)

class MockAblage:
    def __init__(self, basis_pfad=None): self.b = "auftraege" if basis_pfad else "kunden"
    def gibt_es(self, rel):
        return (self.b, rel) in DATEIEN or (self.b, rel) in ORDNER or any(
            b == self.b and r.startswith(rel + "/") for b, r in list(DATEIEN) + list(ORDNER))
    def ordner(self, rel): ORDNER.add((self.b, rel.rstrip("/")))
    def datei(self, rel, daten):
        if (self.b, rel) in DATEIEN:
            raise AssertionError("Nextcloud: vorhandene Datei darf nie ueberschrieben werden: " + rel)
        DATEIEN[(self.b, rel)] = daten
    def ordner_inhalt(self, rel):
        return [], [{"name": r.rsplit("/", 1)[-1], "pfad": r} for b, r in DATEIEN if b == self.b and r.rsplit("/", 1)[0] == rel]
    def hole(self, rel, max_bytes): return DATEIEN[(self.b, rel)], "application/json"
    def dateien(self, firma):
        return [{"rel": "Unterlagen/Bilanz.pdf", "groesse": 1000}, {"rel": "Unterlagen/Vertrag.docx", "groesse": 2000},
                {"rel": "Unterlagen/Film.mov", "groesse": 5000}, {"rel": "Unterlagen/schon da.pdf", "groesse": 10}]

acos_sync.Mcp = MockMcp
acos_sync.Ablage = MockAblage
acos_sync.lade_acos_zugang = lambda: {"ACOS_TOKEN": "x", "ACOS_MCP_URL": "https://acos.invalid/mcp"}
acos_sync.modus = lambda: "scharf"
acos_sync.log = lambda m: None
acos_sync.an_acos_senden = lambda fid, pfad, user=None: GESENDET.append(pfad) or {"ok": True}
modus = {"scharf": False}
auf._modus_scharf = lambda: modus["scharf"]

def status(aid):
    return core._q1("SELECT * FROM acos_auftraege WHERE auftrags_id=%s", (aid,))
def aufgabe(t):
    return core._q1("SELECT status, notes, completed_at FROM tasks WHERE task_id=%s", (t,))
def verlauf(t):
    return [r["art"] for r in core._q("SELECT art FROM acos_auftrag_verlauf WHERE task_id=%s ORDER BY id", (t,))]

andere = core._q("SELECT id FROM firmen WHERE acos_fuehren AND name <> %s", (FIRMA,))
core._x("UPDATE firmen SET acos_fuehren=false WHERE id = ANY(%s)", ([r["id"] for r in andere] or [0],))
fid = core._x("INSERT INTO firmen (name, status, acos_fuehren) VALUES (%s,'Lead',true) RETURNING id", (FIRMA,))[0]["id"]
fid2 = core._x("INSERT INTO firmen (name, status) VALUES (%s,'Lead') RETURNING id", (FIRMA2,))[0]["id"]
try:
    core._x("""INSERT INTO acos_verknuepfung (firma_id, acos_client_id, acos_name, zustand, pruefwert)
               VALUES (%s,%s,%s,'bestaetigt','fest')""", (fid, CID, FIRMA))
    core._x("""INSERT INTO acos_uploads (firma_id, pfad, acos_client_id, status, gesendet_am)
               VALUES (%s,'Unterlagen/schon da.pdf',%s,'gesendet',now())""", (fid, CID))

    # ── Webseite (Migration 027) ──
    pruef("Webseite: unsinnige Eingabe abgelehnt", wirft(lambda: core.update_contact(fid, {"website": "kein link"}), "Adresse"))
    core.update_contact(fid, {"website": " www.zz-test-fiktiv.example/ "})
    pruef("Webseite gespeichert und vereinheitlicht", core._q1("SELECT webseite FROM firmen WHERE id=%s", (fid,))["webseite"] == "www.zz-test-fiktiv.example")
    pruef("Akte liefert die Webseite", core.load_firma_akte(fid)["website"] == "www.zz-test-fiktiv.example")
    f = core._q1("SELECT id, name, status, branch, address, webseite FROM firmen WHERE id=%s", (fid,))
    pruef("Abgleich gibt die Webseite als company.website an ACOS", acos_sync.nutzdaten(f, CID)["company"]["website"] == "https://www.zz-test-fiktiv.example")

    # ── Skills aus ACOS ──
    core._x("DELETE FROM system_einstellungen WHERE schluessel='acos_skills'")
    o = auf.optionen(fid)
    pruef("Skills: beim ersten Bedarf aus ACOS geholt (3 Stueck, mit Stand)", len(o["typen"]) == 3 and o["skills_stand"])
    ms = next(x for x in o["typen"] if x["slug"] == "mandatsstart-analyse")
    pruef("Skills: Titel und Voraussetzungen lesbar", ms["titel"].startswith("Mandatsstart") and ms["voraussetzungen"] == ["Stammdaten", "Website-Profil"])
    pruef("Skills: Verweis auf anderen Skill mit Titel", next(x for x in o["typen"] if x["slug"] == "marketing-strategie")["voraussetzungen"] == ["Artefakt „Executive Summary“"])
    vs = auf.voraussetzungen(fid, "mandatsstart-analyse")
    pruef("Voraussetzungen: nur Pflichtluecken aus ACOS", vs["ok"] and vs["fehlt"] == ["Website-Profil"])
    pruef("Voraussetzungen: erfuellt", auf.voraussetzungen(fid, "executive-summary")["fehlt"] == [])
    pruef("Voraussetzungen: ohne ACOS-Verknuepfung kein Abruf", not auf.voraussetzungen(fid2, "executive-summary")["ok"])

    # ── Voraussetzungen ──
    pruef("Optionen: Unternehmen mit ACOS moeglich", auf.optionen(fid)["verfuegbar"])
    pruef("Optionen: Unternehmen ohne ACOS nicht moeglich", not auf.optionen(fid2)["verfuegbar"])
    t = core.create_task({"title": "Marktumfeld analysieren", "firma_id": fid, "notes": "meine Notiz"})
    t2 = core.create_task({"title": "Aufgabe ohne ACOS", "firma_id": fid2})
    pruef("Uebergabe ohne Verknuepfung abgelehnt", wirft(lambda: auf.uebergeben(t2, {"thema": "X"}), "nicht mit einem ACOS-Mandanten"))
    pruef("Uebergabe im Trockenlauf abgelehnt", wirft(lambda: auf.uebergeben(t, {"thema": "Wettbewerb"}), "Trockenlauf"))
    modus["scharf"] = True
    pruef("Thema ohne Inhalt abgelehnt", wirft(lambda: auf.uebergeben(t, {"thema": "  "}), "Thema"))
    pruef("Firmenname im Thema abgelehnt", wirft(lambda: auf.uebergeben(t, {"thema": f"Markt von {FIRMA}"}), "Unternehmensnamen"))
    ACOS_AUS["an"] = False
    pruef("ACOS nicht erreichbar: verstaendliche Meldung, Auftrag als Fehler", wirft(lambda: auf.uebergeben(t, {"thema": "Markt"}), "nicht in ACOS angelegt")
          and core._q1("SELECT status FROM acos_auftraege WHERE task_id=%s", (t,))["status"] == "fehler")
    ACOS_AUS["an"] = True

    # ── Vorpruefung ──
    v = auf.vorpruefung_firma(fid)
    namen = {x["pfad"]: x for x in v["fehlend"]}
    pruef("Vorpruefung: nur Dateien, die noch nicht in ACOS sind", set(namen) == {"Unterlagen/Bilanz.pdf", "Unterlagen/Vertrag.docx", "Unterlagen/Film.mov"})
    pruef("Vorpruefung: Dateityp ohne Uebertragung nicht sendbar", not namen["Unterlagen/Film.mov"]["sendbar"])

    # ── Uebergabe ──
    d = auf.uebergeben(t, {"thema": "Wettbewerbsumfeld im regionalen Markt", "dateien_senden": ["Unterlagen/Bilanz.pdf"]}, "tester")
    a1 = d["aktiv"]
    pruef("Auftrag AUF-JJJJ-NNNN, Stufe 'bei ACOS'", a1["auftrags_id"].startswith("AUF-") and a1["status"] == "uebergeben" and a1["stufe"] == 2)
    pruef("Gewaehlte Datei vorab an ACOS gesendet", GESENDET == ["Unterlagen/Bilanz.pdf"])
    obj = auftragsobjekt(a1["auftrags_id"])
    pruef("Auftrag als Wissensobjekt crm_auftrag beim Mandanten in ACOS", obj and obj["client_id"] == CID and obj["title"] == f"ACOS-Auftrag {a1['auftrags_id']}")
    pruef("Auftragsobjekt mit Skill und Thema, ohne Namen", obj["data"]["artefakttyp"] == "mandatsstart-analyse" and "Wettbewerb" in obj["data"]["thema"]
          and FIRMA not in json.dumps(obj, ensure_ascii=False))
    pruef("Nichts mehr in der Nextcloud fuer den Auftrag", not any(b == "auftraege" for b, r in DATEIEN))
    pruef("ID des Auftragsobjekts im CRM", status(a1["auftrags_id"])["auftrag_objekt_id"] == next(k for k, o in OBJEKTE.items() if o is obj))
    tk = aufgabe(t)
    pruef("Aufgabe 'In Bearbeitung', Notizen unveraendert", tk["status"] == "In Bearbeitung" and tk["notes"] == "meine Notiz")
    pruef("Verlauf statt Notizen (Fehlversuch, dann Uebergabe)", verlauf(t) == ["fehler", "uebergeben"])
    pruef("Status gesperrt solange der Auftrag laeuft", wirft(lambda: core.update_task(t, {"status": "Erledigt"}), "ACOS-Auftrag"))
    core.update_task(t, {"status": "In Bearbeitung", "notes": "meine Notiz, ergaenzt", "title": "Marktumfeld analysieren (neu)"})
    pruef("Speichern mit unveraendertem Status geht weiter", aufgabe(t)["notes"] == "meine Notiz, ergaenzt")
    pruef("Listen: Etikett 'ACOS'", next(x for x in core.load_tasks() if x["taskId"] == t)["acos"] == "uebergeben")
    pruef("Neuer Auftrag ohne Ergebnis abgelehnt", wirft(lambda: auf.uebergeben(t, {"thema": "Anderes"}), "liegt noch bei ACOS"))

    # ── Rueckfrage und Antwort ──
    rueckfrage(a1["auftrags_id"], "rueckfrage", "Welche Region ist gemeint?")
    acos_sync.abgleich("test")
    pruef("Auftrags- und Rueckfrage-Objekte nicht als Kundenwissen abgelegt",
          not core._q("SELECT 1 FROM acos_artefakte WHERE titel LIKE 'ACOS-Auftrag %%' OR titel LIKE 'Rückfrage %%'"))
    pruef("Rueckfrage uebernommen", status(a1["auftrags_id"])["status"] == "rueckfrage")
    pruef("Rueckfrage im Verlauf, Etikett 'Rueckfrage'", verlauf(t)[-1] == "rueckfrage"
          and next(x for x in core.load_tasks() if x["taskId"] == t)["acos"] == "rueckfrage")
    pruef("Antwort ohne Text abgelehnt", wirft(lambda: auf.uebergeben(t, {"antwort": " "}), "beantworten"))
    d = auf.uebergeben(t, {"antwort": "Region Oberbayern"}, "tester")
    a2 = d["aktiv"]
    inhalt2 = auftragsobjekt(a2["auftrags_id"])["data"]
    pruef("Antwort: Folgeauftrag mit Thema vom Vorgaenger, alter ersetzt", a2["auftrags_id"] != a1["auftrags_id"]
          and a2["thema"] == a1["thema"] and status(a1["auftrags_id"])["status"] == "ersetzt")
    pruef("Antwort steht in den Hinweisen des Auftragsobjekts", "Oberbayern" in inhalt2["hinweise"] and inhalt2["ersetzt"] == a1["auftrags_id"])

    # ── Ergebnis ──
    WISSEN.append({"id": "w-art-1", "kind": "report", "title": f"Mandatsstart-Analyse [{a2['auftrags_id']}]", "updated_at": "2026-11-17T10:00:00Z"})
    acos_sync.abgleich("test")
    r2 = status(a2["auftrags_id"])
    pruef("Auftrag 'bearbeitet', Artefakt zugeordnet", r2["status"] == "bearbeitet" and r2["acos_artefakt_id"] == "w-art-1")
    pruef("Kopie im Kundenordner unter <Kunde>/ACOS/Wissen", f"{FIRMA}/ACOS/Wissen/" in (r2["nextcloud_pfad"] or ""))
    tk = aufgabe(t)
    pruef("Aufgabe 'Bearbeitet', nicht erledigt, Notizen unveraendert", tk["status"] == "Bearbeitet" and tk["completed_at"] is None
          and tk["notes"] == "meine Notiz, ergaenzt")
    pruef("Journal-Eintrag zum Ergebnis", core._q1("SELECT count(*) n FROM aktivitaeten WHERE payload->>'auftrags_id'=%s", (a2["auftrags_id"],))["n"] == 1)
    pruef("Fenster: Stufe 'Ergebnis da' mit Dateiname", auf.auftraege_zu_aufgabe(t)["aktiv"]["stufe"] == 3
          and auf.auftraege_zu_aufgabe(t)["aktiv"]["ergebnis_name"].endswith(".md"))
    pruef("Auch mit Ergebnis: Erledigt nur ueber Abschliessen", wirft(lambda: core.update_task(t, {"status": "Erledigt"}), "Geprüft"))
    n_dat = len(DATEIEN)
    acos_sync.abgleich("test")
    pruef("Zweiter Lauf: nichts doppelt", len(DATEIEN) == n_dat and verlauf(t).count("bearbeitet") == 1)

    # ── Abschliessen ──
    t3 = core.create_task({"title": "Ohne Ergebnis", "firma_id": fid})
    pruef("Abschliessen ohne Ergebnis abgelehnt", wirft(lambda: auf.abschliessen(t3), "kein Ergebnis"))
    auf.abschliessen(t, "tester")
    tk = aufgabe(t)
    pruef("Abschliessen: Aufgabe Erledigt mit Datum, Auftrag erledigt", tk["status"] == "Erledigt" and tk["completed_at"] is not None
          and status(a2["auftrags_id"])["status"] == "erledigt")
    pruef("Abschliessen: Journal und Verlauf", core._q1("SELECT count(*) n FROM aktivitaeten WHERE payload->>'auftrags_id'=%s", (a2["auftrags_id"],))["n"] == 2
          and verlauf(t)[-1] == "erledigt")
    pruef("Nach Abschluss kein Etikett, Status wieder frei", not next((x for x in core.load_tasks() if x["taskId"] == t), {"acos": ""})["acos"]
          and core.update_task(t, {"status": "Erledigt"}) is None)

    # ── Skill-Liste aendert sich in ACOS ──
    a_es = auf.uebergeben(t3, {"typ": "executive-summary", "thema": "Lage vor dem Jahresgespraech"}, "tester")["aktiv"]
    pruef("Anderer Skill waehlbar, Titel im Auftrag", a_es["typ_text"] == "Executive Summary")
    SPECS[:] = [x for x in SPECS if x["slug"] != "executive-summary"] + [{"slug": "nachfrage-matrix", "title": "Nachfrage-Matrix", "required_inputs": [{"type": "master_data"}]}]
    acos_sync.abgleich("test")
    sl = {x["slug"] for x in auf.optionen(fid)["typen"]}
    pruef("Abgleich: neuer Skill erscheint, entfallener nicht mehr waehlbar", "nachfrage-matrix" in sl and "executive-summary" not in sl)
    pruef("Entfallener Skill: laufender Auftrag zeigt weiter den Titel", auf.auftraege_zu_aufgabe(t3)["aktiv"]["typ_text"] == "Executive Summary")
    pruef("Entfallener Skill: neue Uebergabe abgelehnt", wirft(lambda: auf.uebergeben(t2, {"typ": "executive-summary", "thema": "X"}), "nicht"))
    pruef("Fenster: Zeitpunkt des letzten Abgleichs", auf.auftraege_zu_aufgabe(t3)["abgleich"]["zuletzt"] != "")
    rueckfrage(a_es["auftrags_id"], "fehler", "Test")
    acos_sync.abgleich("test")

    # ── Fehler von Claude ──
    a3 = auf.uebergeben(t3, {"thema": "Risiken im Markt"}, "tester")["aktiv"]
    rueckfrage(a3["auftrags_id"], "fehler", "Website-Profil fehlt")
    acos_sync.abgleich("test")
    pruef("Fehler: Auftrag 'fehler', Aufgabe wieder 'Offen'", status(a3["auftrags_id"])["status"] == "fehler" and aufgabe(t3)["status"] == "Offen")
    pruef("Nach Fehler neuer Auftrag moeglich", auf.uebergeben(t3, {"thema": "Risiken im Markt"}, "tester")["aktiv"]["status"] == "uebergeben")

    # ── Oberflaeche ──
    quelle = open(core.__file__, encoding="utf-8").read()
    pruef("Fenster: Schalter, Abschliessen, Antwort, Verlauf", all(x in quelle for x in
          ("Von ACOS bearbeiten lassen", "function aufAbschliessen", "Antwort an ACOS senden", "auf-verlauf", "Speichern und übergeben")))
    pruef("Akte und Heute: Etikett und gesperrter Haken", "_acosPill(a.acos)" in quelle and "_acosPill(t.acos)" in quelle)
    pruef("Tab-Wechsel aktualisiert die Daten", "_crmGeaendert" in quelle)
finally:
    core._x("DELETE FROM acos_auftrag_verlauf WHERE task_id IN (SELECT task_id FROM tasks WHERE firma_id = ANY(%s))", ([fid, fid2],))
    core._x("DELETE FROM acos_auftraege WHERE firma_id = ANY(%s)", ([fid, fid2],))
    core._x("DELETE FROM aktivitaeten WHERE firma_id = ANY(%s)", ([fid, fid2],))
    core._x("DELETE FROM acos_artefakte WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM acos_uploads WHERE firma_id=%s", (fid,))
    core._x("DELETE FROM tasks WHERE firma_id = ANY(%s)", ([fid, fid2],))
    core._x("DELETE FROM firmen WHERE id = ANY(%s)", ([fid, fid2],))
    core._x("UPDATE firmen SET acos_fuehren=true WHERE id = ANY(%s)", ([r["id"] for r in andere] or [0],))
print(f"\n{ok} von {ok} Pruefungen gruen.")
