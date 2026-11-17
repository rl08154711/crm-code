#!/usr/bin/env python3
"""
acos_auftraege.py – Aufgabe als Auftrag an ACOS (Migration 026/027, 2026-11-17)
===============================================================================
Ablauf:
  1. Im Aufgabenfenster "Von ACOS bearbeiten lassen" -> "Speichern und übergeben": das CRM legt
     die Auftragsdatei AUF-JJJJ-NNNN.json in der Nextcloud ab (<Aufträge>/offen/, nur anlegen).
     Die Datei enthaelt nur die ACOS-Mandanten-ID, den Artefakttyp und das Thema - keine Namen.
  2. Claude arbeitet den Auftrag am Mac ueber ACOS ab (Stealth) und speichert das Artefakt mit
     der Auftrags-ID im Titel. Bei Rueckfrage oder Fehler legt Claude eine NEUE Datei
     <Aufträge>/ergebnis/AUF-JJJJ-NNNN.json an.
  3. Der ACOS-Abgleich legt das Artefakt in <Kunde>/ACOS/Wissen ab und ruft nachlauf() auf:
     Auftrag -> "bearbeitet", Aufgabe -> "Bearbeitet", Verlauf, Journal.
  4. Abschliessen nur ueber "Geprueft, Aufgabe abschliessen" (abschliessen()).
Solange ein Auftrag laeuft, steuert er den Status der Aufgabe (update_task lehnt Aenderungen ab).
Die automatischen Hinweise stehen im Verlauf (acos_auftrag_verlauf), nicht in den Notizen.
Nextcloud: nur lesen und neu anlegen. ACOS: es wird hier nichts geschrieben.
"""

import json
import re
from datetime import datetime, date
from pathlib import Path

import crm_core as core

# Skills (Artifact Specs) kommen aus ACOS: acos_sync.abgleich() holt die Liste bei jedem Lauf und legt sie
# in system_einstellungen['acos_skills'] ab. Entfallene bleiben (aktiv=false) fuer bestehende Auftraege lesbar.
SKILLS_KEY = "acos_skills"
STANDARD_SKILLS = [{"slug": "mandatsstart-analyse", "titel": "Mandatsstart-Analyse", "nummer": "21", "zweck": "",
                    "voraussetzungen": ["Stammdaten", "Website-Profil"], "aktiv": True}]
VORAUSSETZUNG = {"master_data": "Stammdaten", "website_profile": "Website-Profil", "financial_snapshot": "Finanzdaten",
                 "foerdermittel_match": "Fördermittel-Treffer", "visibility_index": "Sichtbarkeit",
                 "capture_submission": "Fragebogen-Antworten", "collaboration_frame": "Ziel und Zusammenarbeit",
                 "project_goal": "Projektziel"}
OFFEN = ("uebergeben", "rueckfrage", "bearbeitet")
STATUS_TEXT = {
    "uebergeben": "wartet auf Bearbeitung",
    "rueckfrage": "Rückfrage",
    "bearbeitet": "Ergebnis da",
    "erledigt": "abgeschlossen",
    "fehler": "Fehler",
    "ersetzt": "ersetzt",
}
STUFE = {"uebergeben": 2, "rueckfrage": 2, "bearbeitet": 3, "erledigt": 4}
ANWEISUNG = ("Auftrag aus dem CRM. Skill mandantenfiles, datenschutz stealth, Mandant nur über acos_client_id. "
             "Artefakt nach der Vorlage 'artefakttyp' erstellen und mit am_acos_artifact_save speichern; der Titel "
             "MUSS die Auftrags-ID in eckigen Klammern enthalten, z. B. 'Mandatsstart-Analyse [AUF-2026-0007]', "
             "und keinen Mandantennamen. Platzhalter unverändert lassen. Bei Rückfrage oder Fehler eine NEUE Datei "
             "ergebnis/<auftrags_id>.json mit {auftrags_id, status: rueckfrage|fehler, text} anlegen. "
             "Nichts überschreiben oder löschen.")


def _voraussetzung_text(inp):
    inp = inp or {}
    if inp.get("type") == "artifact":
        spec = inp.get("spec") or ""
        titel = next((x["titel"] for x in skills(alle=True) if x["slug"] == spec), spec)
        return f"Artefakt „{titel}“"
    schluessel = inp.get("kind") or inp.get("type") or "?"
    return VORAUSSETZUNG.get(schluessel, schluessel)


def _skill(roh):
    zweck = " ".join(str(roh.get("purpose") or roh.get("promise") or "").split())
    if len(zweck) > 240:
        zweck = zweck[:237].rstrip() + " …"
    zweck = zweck.replace(" …", "").rstrip(" .…") + ("." if zweck else "")
    return {"slug": str(roh.get("slug") or "").strip(), "titel": str(roh.get("title") or roh.get("slug") or "").strip(),
            "nummer": str(roh.get("number") or ""), "zweck": zweck, "version": roh.get("version"),
            "inputs": [i for i in (roh.get("required_inputs") or []) if isinstance(i, dict)], "aktiv": True}


def skills_speichern(roh_liste):
    """Liste aus am_acos_artifact_specs_list uebernehmen. Rueckgabe: (neu, entfallen)."""
    alt = {x["slug"]: x for x in skills(alle=True, holen=False)}
    neu = [_skill(r) for r in roh_liste if isinstance(r, dict) and r.get("slug")]
    if not neu:
        raise ValueError("ACOS hat keine Skills geliefert")
    slugs = {x["slug"] for x in neu}
    for x in neu:
        x["voraussetzungen"] = []
    entfallen = [dict(x, aktiv=False) for k, x in alt.items() if k not in slugs]
    liste = sorted(neu, key=lambda x: x["titel"].lower()) + entfallen
    for x in liste:   # Texte erst, wenn alle Titel bekannt sind (Verweise auf andere Skills)
        x["voraussetzungen"] = [_voraussetzung_text_aus(i, liste) for i in x.get("inputs") or []] or x.get("voraussetzungen") or []
    wert = {"stand": _jetzt().isoformat(timespec="seconds"), "skills": liste}
    core._x("""INSERT INTO system_einstellungen (schluessel, wert, geaendert_am) VALUES (%s,%s::jsonb,now())
               ON CONFLICT (schluessel) DO UPDATE SET wert=EXCLUDED.wert, geaendert_am=now()""",
            (SKILLS_KEY, json.dumps(wert, ensure_ascii=False)))
    return len([k for k in slugs if k not in alt]), len([x for x in entfallen if alt[x["slug"]].get("aktiv", True)])


def _voraussetzung_text_aus(inp, liste):
    if inp.get("type") == "artifact":
        spec = inp.get("spec") or ""
        return "Artefakt „" + next((x["titel"] for x in liste if x["slug"] == spec), spec) + "“"
    schluessel = inp.get("kind") or inp.get("type") or "?"
    return VORAUSSETZUNG.get(schluessel, schluessel)


def _mcp():
    import acos_sync
    zug = acos_sync.lade_acos_zugang()
    if not zug.get("ACOS_TOKEN") or not zug.get("ACOS_MCP_URL"):
        raise ValueError("Zugang zu ACOS fehlt (secrets/acos.env).")
    m = acos_sync.Mcp(zug["ACOS_MCP_URL"], zug["ACOS_TOKEN"])
    m.start()
    return m


def skills_aus_acos(mcp=None):
    """Skill-Liste in ACOS abfragen und speichern (aus dem Abgleich oder beim ersten Bedarf)."""
    antwort = (mcp or _mcp()).lesen("am_acos_artifact_specs_list", {})
    liste = antwort.get("specs") if isinstance(antwort, dict) else None
    if not isinstance(liste, list):
        import acos_sync
        liste = acos_sync._liste(antwort, ("specs", "items", "data", "results"))
    return skills_speichern(liste)


def skills(alle=False, holen=True):
    """Gespeicherte Skill-Liste; ist noch keine da, einmal in ACOS holen, sonst die Grundausstattung."""
    wert = core._system_raw().get(SKILLS_KEY) or {}
    liste = wert.get("skills") if isinstance(wert, dict) else None
    if not liste and holen:
        try:
            skills_aus_acos()
            liste = (core._system_raw().get(SKILLS_KEY) or {}).get("skills")
        except Exception:
            liste = None
    liste = liste or STANDARD_SKILLS
    return liste if alle else [x for x in liste if x.get("aktiv", True)]


def skills_stand():
    wert = core._system_raw().get(SKILLS_KEY) or {}
    try:
        return datetime.fromisoformat(wert["stand"]).astimezone().strftime("%d.%m.%Y %H:%M")
    except Exception:
        return ""


def typ_titel(slug):
    return next((x["titel"] for x in skills(alle=True, holen=False) if x["slug"] == slug), slug)


def voraussetzungen(firma_id, slug):
    """Fragt ACOS, welche Pflicht-Grundlagen dieser Skill beim Mandanten vermisst (Context Pack, nur 'gaps')."""
    v = _verknuepfung(int(firma_id)) if firma_id else None
    if not v or v["zustand"] != "bestaetigt" or not v["acos_client_id"]:
        return {"ok": False, "meldung": "Unternehmen nicht mit ACOS verknüpft.", "fehlt": []}
    try:
        pack = _mcp().lesen("am_acos_context_pack", {"client_id": v["acos_client_id"], "slug": slug})
    except ValueError as e:
        return {"ok": False, "meldung": str(e), "fehlt": []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "meldung": f"ACOS nicht erreichbar ({e.__class__.__name__}).", "fehlt": []}
    gaps = pack.get("gaps") if isinstance(pack, dict) else None
    fehlt = [_voraussetzung_text(g.get("input")) for g in (gaps or []) if isinstance(g, dict) and g.get("required")]
    return {"ok": True, "meldung": "", "fehlt": fehlt}


def abgleich_stand():
    """Wann zuletzt in ACOS nachgesehen wurde und ob gerade ein Abgleich laeuft."""
    if not core._tabelle_da("acos_laeufe"):
        return {"zuletzt": "", "laeuft": False}
    r = core._q1("""SELECT max(ende) FILTER (WHERE ende IS NOT NULL AND modus='scharf') AS zuletzt,
                           bool_or(ende IS NULL AND start > now() - interval '15 minutes') AS laeuft
                    FROM acos_laeufe""")
    return {"zuletzt": r["zuletzt"].astimezone().strftime("%d.%m. %H:%M") if r and r["zuletzt"] else "",
            "laeuft": bool(r and r["laeuft"])}


def auftraege_basis():
    """Ordner der Auftragsdateien in der Nextcloud, relativ zum Nutzer (ohne fuehrenden /)."""
    try:
        import wissen_sync
        pfad = wissen_sync.lade_zugang().get("AUFTRAEGE_PFAD") or ""
    except Exception:
        pfad = ""
    return (pfad or "Arbeitsdateien/Aufträge").strip("/")


def _ablage():
    import acos_sync
    return acos_sync.Ablage(auftraege_basis())


def _modus_scharf():
    return core._system_raw().get("acos_modus") == "scharf"


def _jetzt():
    return datetime.now().astimezone()


def _verlauf(task_id, auftrags_id, art, text):
    core._x("""INSERT INTO acos_auftrag_verlauf (task_id, auftrags_id, art, text) VALUES (%s,%s,%s,%s)""",
            (task_id, auftrags_id, art, text))


def _task_status(task_id, status):
    """Status der Aufgabe setzen (vom Auftrag gesteuert). Erledigt setzt completed_at, alles andere loescht es."""
    core._x("""UPDATE tasks SET status=%s, updated_at=now(),
                   completed_at = CASE WHEN %s = 'Erledigt' THEN coalesce(completed_at, now()) ELSE NULL END
               WHERE task_id=%s""", (status, status, task_id))


def _journal(firma_id, titel, notiz, payload):
    core._x("""INSERT INTO aktivitaeten (firma_id, art, datum, quelle, titel, notiz, payload)
               VALUES (%s,'acos',CURRENT_DATE,'acos',%s,%s,%s)""",
            (firma_id, titel, notiz, json.dumps(payload, ensure_ascii=False)))


def _next_auftrags_id():
    jahr = date.today().year
    rows = core._q("SELECT auftrags_id FROM acos_auftraege WHERE auftrags_id LIKE %s", (f"AUF-{jahr}-%",))
    nums = [int(r["auftrags_id"].rsplit("-", 1)[1]) for r in rows if re.search(r"-\d+$", r["auftrags_id"])] or [0]
    return f"AUF-{jahr}-{max(nums) + 1:04d}"


def _aufgabe(task_id):
    t = core._q1("""SELECT t.task_id, t.title, t.status, COALESCE(t.firma_id, p.firma_id) AS firma_id, t.archiviert_am,
                           f.name AS firma
                    FROM tasks t LEFT JOIN projekte p ON p.id = t.projekt_id
                    LEFT JOIN firmen f ON f.id = COALESCE(t.firma_id, p.firma_id) WHERE t.task_id=%s""", (task_id,))
    if not t:
        raise FileNotFoundError(f"Aufgabe nicht gefunden: {task_id}")
    return t


def _verknuepfung(firma_id):
    return core._q1("SELECT acos_client_id, zustand FROM acos_verknuepfung WHERE firma_id=%s", (firma_id,))


def aktiver_auftrag(task_id):
    """Der juengste nicht ersetzte Auftrag einer Aufgabe, oder None."""
    if not core._tabelle_da("acos_auftraege"):
        return None
    return core._q1("""SELECT * FROM acos_auftraege WHERE task_id=%s AND status <> 'ersetzt'
                       ORDER BY id DESC LIMIT 1""", (task_id,))


def status_gesperrt(task_id):
    """Laeuft ein Auftrag, steuert er den Status der Aufgabe (fuer update_task)."""
    a = aktiver_auftrag(task_id)
    return a if a and a["status"] in OFFEN else None


def _auftrag_dict(r):
    r = dict(r)
    for k in ("angelegt_am", "uebergeben_am", "bearbeitet_am", "erledigt_am", "geaendert_am"):
        if r.get(k):
            r[k] = r[k].astimezone().strftime("%d.%m.%Y %H:%M")
    r["status_text"] = STATUS_TEXT.get(r["status"], r["status"])
    r["typ_text"] = typ_titel(r["artefakttyp"])
    r["stufe"] = STUFE.get(r["status"], 0)
    r["ergebnis_link"] = core._nextcloud_ordner_link(r["nextcloud_pfad"].rsplit("/", 1)[0]) if r.get("nextcloud_pfad") else ""
    r["ergebnis_name"] = r["nextcloud_pfad"].rsplit("/", 1)[-1] if r.get("nextcloud_pfad") else ""
    return r


def optionen(firma_id):
    """Kann fuer dieses Unternehmen ein Auftrag an ACOS gehen?"""
    if not core._tabelle_da("acos_auftraege"):
        return {"verfuegbar": False, "grund": "Datenbank noch nicht vorbereitet (Migration 026 fehlt)", "typen": [], "scharf": False}
    grund = ""
    if not firma_id:
        grund = "Nur für Aufgaben eines Unternehmens."
    else:
        v = _verknuepfung(int(firma_id))
        if not v or v["zustand"] != "bestaetigt" or not v["acos_client_id"]:
            grund = "Das Unternehmen ist noch nicht mit einem ACOS-Mandanten verknüpft."
    return {"verfuegbar": not grund, "grund": grund, "scharf": _modus_scharf(),
            "typen": [{"slug": x["slug"], "titel": x["titel"], "zweck": x.get("zweck") or "",
                       "voraussetzungen": x.get("voraussetzungen") or []} for x in skills()] if not grund else [],
            "skills_stand": skills_stand()}


def auftraege_zu_aufgabe(task_id):
    """Alles, was das Aufgabenfenster fuer den Bereich 'ACOS' braucht."""
    t = _aufgabe(task_id)
    o = optionen(t["firma_id"])
    if not core._tabelle_da("acos_auftraege"):
        return dict(o, aktiv=None, auftraege=[], verlauf=[])
    if t["archiviert_am"]:
        o = dict(o, verfuegbar=False, grund="Die Aufgabe ist archiviert.")
    rows = core._q("SELECT * FROM acos_auftraege WHERE task_id=%s ORDER BY id DESC", (task_id,))
    akt = next((r for r in rows if r["status"] != "ersetzt"), None)
    verlauf = []
    if core._tabelle_da("acos_auftrag_verlauf"):
        verlauf = [{"zeit": r["zeit"].astimezone().strftime("%d.%m. %H:%M"), "auftrags_id": r["auftrags_id"],
                    "art": r["art"], "text": r["text"]}
                   for r in core._q("SELECT * FROM acos_auftrag_verlauf WHERE task_id=%s ORDER BY id DESC", (task_id,))]
    return dict(o, aktiv=_auftrag_dict(akt) if akt else None, auftraege=[_auftrag_dict(r) for r in rows],
                verlauf=verlauf, task_status=t["status"], abgleich=abgleich_stand())


def _klartext_pruefen(text, firma):
    """Thema und Hinweise gehen in die Auftragsdatei - ohne Firmennamen."""
    import acos_sync
    n = acos_sync.norm(text)
    fn = acos_sync.norm(firma or "")
    if fn and len(fn) >= 4 and fn in n:
        raise ValueError("Thema oder Hinweis enthält den Unternehmensnamen. Bitte ohne Namen formulieren "
                         "(der Mandant ist über die Nummer eindeutig).")


def vorpruefung_firma(firma_id):
    """Dateien im Kundenordner, die noch nicht in der ACOS-Kundenakte liegen."""
    import acos_sync
    f = core._q1("SELECT id, name FROM firmen WHERE id=%s", (int(firma_id),)) if firma_id else None
    if not f:
        raise ValueError("Kein Unternehmen gewählt.")
    try:
        ablage = acos_sync.Ablage()
        if not ablage.gibt_es(f["name"]):
            return {"ok": False, "meldung": f"Kundenordner „{f['name']}“ fehlt in der Nextcloud.", "fehlend": [], "gesamt": 0}
        dateien = ablage.dateien(f["name"])
    except acos_sync.AcosFehler as e:
        return {"ok": False, "meldung": str(e), "fehlend": [], "gesamt": 0}
    except Exception as e:
        return {"ok": False, "meldung": f"Nextcloud nicht erreichbar ({e.__class__.__name__})", "fehlend": [], "gesamt": 0}
    gesendet = {r["pfad"] for r in core._q(
        "SELECT DISTINCT pfad FROM acos_uploads WHERE firma_id=%s AND status='gesendet'", (f["id"],))}
    fehlend = []
    for d in dateien:
        if d["rel"] in gesendet:
            continue
        endung = Path(d["rel"]).suffix.lower()
        grund = ""
        if endung not in acos_sync.MIME:
            grund = "Dateityp wird nicht übertragen"
        elif d.get("groesse") and d["groesse"] > acos_sync.MAX_UPLOAD:
            grund = "Datei ist zu groß"
        fehlend.append({"pfad": d["rel"], "name": d["rel"].rsplit("/", 1)[-1], "sendbar": not grund, "grund": grund})
    return {"ok": True, "meldung": "", "fehlend": fehlend, "gesamt": len(dateien)}


def vorpruefung(task_id):
    t = _aufgabe(task_id)
    if not t["firma_id"]:
        raise ValueError("Die Aufgabe gehört zu keinem Unternehmen.")
    return vorpruefung_firma(t["firma_id"])


def uebergeben(task_id, body, username=None):
    """Auftrag anlegen und die Auftragsdatei in der Nextcloud ablegen.
    body: typ, thema, hinweise, dateien_senden; bei Rueckfrage 'antwort', zum Nachbessern 'nachbessern'
    (dann werden Typ und Thema vom laufenden Auftrag uebernommen und er wird ersetzt)."""
    import acos_sync
    t = _aufgabe(task_id)
    if not t["firma_id"]:
        raise ValueError("Die Aufgabe gehört zu keinem Unternehmen.")
    if t["archiviert_am"]:
        raise ValueError("Die Aufgabe ist archiviert.")
    v = _verknuepfung(t["firma_id"])
    if not v or v["zustand"] != "bestaetigt" or not v["acos_client_id"]:
        raise ValueError("Das Unternehmen ist noch nicht mit einem ACOS-Mandanten verknüpft.")

    akt = aktiver_auftrag(task_id)
    folge = (body.get("antwort") or body.get("nachbessern") or "").strip()
    if akt and akt["status"] == "uebergeben" and not body.get("ersetzen"):
        raise ValueError(f"{akt['auftrags_id']} liegt noch bei ACOS. Bitte erst das Ergebnis oder die Rückfrage abwarten.")
    if akt and akt["status"] in ("rueckfrage", "bearbeitet") and not folge and not body.get("ersetzen"):
        raise ValueError("Bitte die Rückfrage beantworten bzw. beschreiben, was nachgebessert werden soll.")
    ersetzt = akt if akt and akt["status"] in OFFEN else None

    typ = (body.get("typ") or (ersetzt["artefakttyp"] if ersetzt else "") or "mandatsstart-analyse").strip()
    gueltig = {x["slug"] for x in skills()}
    if typ not in gueltig and not (ersetzt and typ == ersetzt["artefakttyp"]):
        raise ValueError("Diesen Skill gibt es in ACOS nicht (mehr). Bitte einen anderen wählen.")
    thema = " ".join((body.get("thema") or (ersetzt["thema"] if ersetzt else "") or "").split())
    if not thema:
        raise ValueError("Bitte ein Thema angeben.")
    if len(thema) > 500:
        raise ValueError("Das Thema ist zu lang (höchstens 500 Zeichen).")
    hinweise = (body.get("hinweise") or "").strip()
    if folge:
        art = "Antwort auf die Rückfrage" if body.get("antwort") else "Nachbesserung"
        hinweise = (f"{art} zu {ersetzt['auftrags_id']}: {folge}" if ersetzt else folge) + (f"\n{hinweise}" if hinweise else "")
    hinweise = hinweise[:2000]
    _klartext_pruefen(thema + " " + hinweise, t["firma"])
    if not _modus_scharf():
        raise ValueError("ACOS steht auf Trockenlauf – es wird nichts geschrieben. Modus in den Einstellungen auf scharf stellen.")

    try:
        ablage = _ablage()
        ordner_da = ablage.gibt_es("")
    except acos_sync.AcosFehler as e:
        raise ValueError(str(e))
    except Exception as e:
        raise ValueError(f"Nextcloud nicht erreichbar ({e.__class__.__name__}). Bitte später noch einmal versuchen.")
    if not ordner_da:
        raise ValueError(f"Der Ordner /{auftraege_basis()} fehlt in der Nextcloud. Bitte dort in der Weboberfläche "
                         "anlegen und dann noch einmal übergeben.")

    # fehlende Dateien aus dem Kundenordner vorher an ACOS senden (nur die angehakten)
    gesendet = []
    for pfad in (body.get("dateien_senden") or []):
        acos_sync.an_acos_senden(t["firma_id"], pfad, username)
        gesendet.append(pfad)

    aid = _next_auftrags_id()
    datei_rel = f"offen/{aid}.json"
    inhalt = {"auftrags_id": aid, "erstellt_am": _jetzt().isoformat(timespec="seconds"),
              "acos_client_id": v["acos_client_id"], "artefakttyp": typ, "artefakttyp_titel": typ_titel(typ),
              "thema": thema, "hinweise": hinweise, "anweisung": ANWEISUNG}
    if ersetzt:
        inhalt["ersetzt"] = ersetzt["auftrags_id"]
    core._x("""INSERT INTO acos_auftraege (auftrags_id, task_id, firma_id, acos_client_id, artefakttyp, thema,
                                          status, auftragsdatei, angelegt_von)
               VALUES (%s,%s,%s,%s,%s,%s,'uebergeben',%s,%s)""",
            (aid, task_id, t["firma_id"], v["acos_client_id"], typ, thema,
             f"{auftraege_basis()}/{datei_rel}", username))
    try:
        ablage.ordner("offen")
        ablage.datei(datei_rel, json.dumps(inhalt, ensure_ascii=False, indent=2).encode("utf-8"))
    except Exception as e:
        fehler = f"{e.__class__.__name__}: {e}"[:300]
        core._x("UPDATE acos_auftraege SET status='fehler', meldung=%s, geaendert_am=now() WHERE auftrags_id=%s", (fehler, aid))
        _verlauf(task_id, aid, "fehler", f"Auftragsdatei konnte nicht abgelegt werden ({fehler})")
        raise ValueError(f"Die Auftragsdatei konnte nicht in der Nextcloud abgelegt werden ({fehler}).")
    core._x("UPDATE acos_auftraege SET uebergeben_am=now(), geaendert_am=now() WHERE auftrags_id=%s", (aid,))
    if ersetzt:
        core._x("""UPDATE acos_auftraege SET status='ersetzt', ersetzt_durch=%s, geaendert_am=now()
                   WHERE auftrags_id=%s""", (aid, ersetzt["auftrags_id"]))
    text = f"An ACOS übergeben ({typ_titel(typ)}). Thema: {thema}"
    if folge:
        text += f" – {('Antwort' if body.get('antwort') else 'Nachbesserung')}: {folge}"
    if gesendet:
        text += f" – {len(gesendet)} Datei(en) mitgesendet"
    _verlauf(task_id, aid, "uebergeben", text)
    _task_status(task_id, "In Bearbeitung")
    core._audit("acos_auftraege", t["firma_id"], "uebergeben", neu={"auftrags_id": aid, "task_id": task_id, "typ": typ})
    return auftraege_zu_aufgabe(task_id)


def abschliessen(task_id, username=None):
    """'Geprueft, Aufgabe abschliessen': Auftrag erledigt, Aufgabe Erledigt, Journal."""
    t = _aufgabe(task_id)
    a = aktiver_auftrag(task_id)
    if not a or a["status"] != "bearbeitet":
        raise ValueError("Es liegt noch kein Ergebnis von ACOS vor.")
    core._x("UPDATE acos_auftraege SET status='erledigt', erledigt_am=now(), geaendert_am=now() WHERE id=%s", (a["id"],))
    _task_status(task_id, "Erledigt")
    _verlauf(task_id, a["auftrags_id"], "erledigt", f"Ergebnis geprüft, Aufgabe abgeschlossen{f' ({username})' if username else ''}")
    _journal(a["firma_id"], f"Auftrag {a['auftrags_id']} abgeschlossen",
             f"Aufgabe „{t['title']}“ ({task_id}) abgeschlossen. Ergebnis: /{a['nextcloud_pfad'] or '–'}",
             {"auftrags_id": a["auftrags_id"], "task_id": task_id})
    return auftraege_zu_aufgabe(task_id)


def etiketten(task_ids):
    """Fuer Listen: task_id -> Status des aktiven Auftrags (nur laufende)."""
    if not task_ids or not core._tabelle_da("acos_auftraege"):
        return {}
    rows = core._q("""SELECT DISTINCT ON (task_id) task_id, status FROM acos_auftraege
                      WHERE task_id = ANY(%s) AND status <> 'ersetzt' ORDER BY task_id, id DESC""", (list(task_ids),))
    return {r["task_id"]: r["status"] for r in rows if r["status"] in OFFEN}


def _ergebnisdateien(notiz):
    """Rueckfragen und Fehler, die Claude als neue Datei unter ergebnis/ abgelegt hat."""
    offene = core._q("SELECT * FROM acos_auftraege WHERE status='uebergeben'")
    if not offene:
        return 0
    try:
        ablage = _ablage()
        if not ablage.gibt_es("ergebnis"):
            return 0
        _, dateien = ablage.ordner_inhalt("ergebnis")
    except Exception as e:
        notiz("Aufträge", "hinweis", f"Ergebnisordner nicht lesbar ({e.__class__.__name__})")
        return 0
    namen = {d["name"] for d in dateien}
    n = 0
    for a in offene:
        name = f"{a['auftrags_id']}.json"
        if name not in namen:
            continue
        try:
            roh, _ = ablage.hole(f"ergebnis/{name}", 100_000)
            d = json.loads(roh.decode("utf-8"))
        except Exception as e:
            core._x("UPDATE acos_auftraege SET meldung=%s, geaendert_am=now() WHERE id=%s",
                    (f"Ergebnisdatei nicht lesbar: {e.__class__.__name__}", a["id"]))
            continue
        status = d.get("status")
        text = " ".join(str(d.get("text") or "").split())[:1500]
        if status == "rueckfrage":
            core._x("UPDATE acos_auftraege SET status='rueckfrage', rueckfrage=%s, geaendert_am=now() WHERE id=%s", (text, a["id"]))
            _verlauf(a["task_id"], a["auftrags_id"], "rueckfrage", f"Rückfrage von ACOS: {text}")
        elif status == "fehler":
            core._x("UPDATE acos_auftraege SET status='fehler', meldung=%s, geaendert_am=now() WHERE id=%s", (text, a["id"]))
            _verlauf(a["task_id"], a["auftrags_id"], "fehler", f"ACOS konnte den Auftrag nicht bearbeiten: {text}")
            _task_status(a["task_id"], "Offen")
        else:
            continue
        n += 1
    return n


def _artefakte_zuordnen(notiz):
    """Artefakte mit der Auftrags-ID im Titel, die der Abgleich schon in die Nextcloud abgelegt hat."""
    n = 0
    for a in core._q("SELECT * FROM acos_auftraege WHERE status IN ('uebergeben','rueckfrage')"):
        r = core._q1("""SELECT acos_id, titel, acos_link, nextcloud_pfad, status FROM acos_artefakte
                        WHERE firma_id=%s AND quelle='wissen' AND status IN ('abgelegt','neu','fehler')
                          AND position(%s in titel) > 0
                        ORDER BY (status='abgelegt') DESC, id DESC LIMIT 1""", (a["firma_id"], a["auftrags_id"]))
        if not r:
            continue
        if r["status"] != "abgelegt":
            core._x("UPDATE acos_auftraege SET meldung=%s, geaendert_am=now() WHERE id=%s",
                    ("Ergebnis ist in ACOS, die Kopie in die Nextcloud steht noch aus.", a["id"]))
            continue
        core._x("""UPDATE acos_auftraege SET status='bearbeitet', acos_artefakt_id=%s, acos_link=%s, nextcloud_pfad=%s,
                          meldung=NULL, rueckfrage=NULL, bearbeitet_am=now(), geaendert_am=now() WHERE id=%s""",
                (r["acos_id"], r["acos_link"], r["nextcloud_pfad"], a["id"]))
        _verlauf(a["task_id"], a["auftrags_id"], "bearbeitet",
                 f"Ergebnis von ACOS: „{r['titel']}“, abgelegt unter /{r['nextcloud_pfad']} und im Kundenwissen")
        _task_status(a["task_id"], "Bearbeitet")
        _journal(a["firma_id"], f"ACOS-Ergebnis zu {a['auftrags_id']}: {r['titel']}",
                 f"Auftrag aus Aufgabe {a['task_id']} ({typ_titel(a['artefakttyp'])}) von ACOS bearbeitet. "
                 f"Abgelegt unter /{r['nextcloud_pfad']}.",
                 {"auftrags_id": a["auftrags_id"], "task_id": a["task_id"], "acos_id": r["acos_id"],
                  "nextcloud_pfad": r["nextcloud_pfad"]})
        notiz("Aufträge", "ablage", f"{a['auftrags_id']}: Ergebnis zugeordnet, Aufgabe {a['task_id']} auf Bearbeitet")
        n += 1
    return n


def nachlauf(notiz=lambda *a, **k: None):
    """Wird am Ende von acos_sync.abgleich() aufgerufen (scharfer Lauf). Darf den Abgleich nie stoeren."""
    try:
        if not core._tabelle_da("acos_auftraege"):
            return {"rueckmeldungen": 0, "ergebnisse": 0}
        return {"rueckmeldungen": _ergebnisdateien(notiz), "ergebnisse": _artefakte_zuordnen(notiz)}
    except Exception as e:  # noqa: BLE001
        notiz("Aufträge", "fehler", f"Aufträge konnten nicht abgeglichen werden ({e.__class__.__name__}: {e})"[:300])
        return {"rueckmeldungen": 0, "ergebnisse": 0}
