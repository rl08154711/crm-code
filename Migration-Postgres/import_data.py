#!/usr/bin/env python3
"""
import_data.py – Einmaliger Import der Bestandsdaten (Markdown/JSON) nach Postgres
====================================================================================
Liest die echten Bestandsdaten aus dem Root-Verzeichnis `CRM/` (NICHT aus
`CPX12-Generalprobe/` - dessen tasks.json ist ein veralteter 26-Task-Snapshot,
das Root-tasks.json hat 29 Tasks und deckt sich exakt mit der Analyse in
CRM-Konzept-Postgres-Migration.md) und befüllt die Postgres-Tabellen aus
schema.sql.

Setzt die dort beschlossene Sonderlogik für die projektlosen Alt-Tasks um:
  1) "Intern / DK Marketing" -> eigenes Projekt "DK Marketing" unter Firma "Intern".
  2) Freitext-Wert passt auf eine echte Firmenakte ohne passende Opportunity
     (STAHL Holding GmbH, Nexxivon AG, Trufflepig IT-Forensics GmbH,
     Liscia Consulting GbR, Freiberger Steuerberatungsgesellschaft mbH,
     David Gagliardi - UND "Intern" selbst, im Konzeptdokument nicht einzeln
     aufgeführt, fällt aber unter dieselbe Regel: Akte vorhanden, keine
     Opportunity) -> automatisches Sammelprojekt "<Firma> – laufende Betreuung".
  3) Alles andere ohne Firmenakte -> gemeinsames Archiv-Projekt
     "Altvorgänge vor CRM-Umstellung" (firma_id NULL). Das Konzeptdokument nennt
     hierfür 8 konkrete Fälle (alle bereits "Erledigt"); diese Implementierung
     wendet die allgemeine Regel an (Freitext ohne Firmenakte -> Archiv) statt
     eine feste Namensliste zu hardcoden, was zusätzlich einen im Dokument nicht
     erwähnten 9. Fall korrekt mit abdeckt (Task ADM-001 "SRI Unterlagen
     zusenden", ebenfalls bereits erledigt, Freitext-Kontakt "SRI" ohne Akte).

Sicherheitsprinzip: Standardmäßig NUR Dry-Run (liest & parst alles, druckt eine
Zusammenfassung, schreibt NICHTS) - erst mit --live werden tatsächlich Daten
geschrieben (und dabei vorher die Zieltabellen geleert, siehe --live-Hilfetext).
Im Dry-Run wird keinerlei Datenbankverbindung benötigt (funktioniert daher auch
lokal ohne installiertes psycopg2/Postgres) - IDs werden im Dry-Run fortlaufend
im Speicher vergeben, rein zur Plausibilitätsprüfung der Zuordnungslogik.

Aufruf:
    python3 import_data.py                       # Dry-Run, keine DB noetig
    CRM_DB_NAME=crm_test python3 import_data.py --live   # echter Import in crm_test
    CRM_DB_NAME=crm      python3 import_data.py --live   # echter Import in crm (erst NACH
                                                           # erfolgreichem Smoke-Test gegen crm_test!)

--live braucht crm_core.py (fuer die eigentliche DB-Verbindung/_x/_q1). Das
liegt auf dem Server nicht neben diesem Skript, sondern unter /opt/crm-pg-test
(vor dem Cutover) bzw. /opt/crm (danach) - wird per CRM_CORE_DIR ueberschrieben
oder automatisch anhand ein paar ueblicher Pfade gesucht, siehe
_ensure_crm_core_importable().
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # Default: CRM/ (lokale Entwicklung)
FIRMEN_DIR = PERS_DIR = OPPS_DIR = TASKS_FILE = AKT_DIR = None


def _set_root(root):
    """Setzt ROOT und die davon abgeleiteten Quellpfade. Per --root
    ueberschreibbar (2026-09-14 ergaenzt) - auf dem Server landen die
    Quelldaten per FileZilla nicht zwingend in derselben verschachtelten
    Struktur wie lokal (Migration-Postgres/ als Unterordner von CRM/),
    daher darf der Skript-Ort nicht mehr die Quelldaten-Lage vorschreiben."""
    global ROOT, FIRMEN_DIR, PERS_DIR, OPPS_DIR, TASKS_FILE, AKT_DIR
    ROOT = Path(root).resolve()
    FIRMEN_DIR = ROOT / "Kontakte" / "Firmen"
    PERS_DIR = ROOT / "Kontakte" / "Personen"
    OPPS_DIR = ROOT / "Opportunities"
    TASKS_FILE = ROOT / "tasks.json"
    AKT_DIR = ROOT / "Aktivitäten"


_set_root(ROOT)


def _ensure_crm_core_importable():
    """crm_core.py liegt auf dem Server nicht neben diesem Skript (sondern
    unter /opt/crm-pg-test bzw. spaeter /opt/crm) - ohne das hier laeuft
    'import crm_core' bei --live ins Leere ('No module named crm_core').

    Wichtig: die bekannten Kandidatenpfade werden VOR einem blinden
    'import crm_core' geprueft, nicht danach - sonst gewinnt eine zufaellig
    im Arbeitsverzeichnis des Skripts liegende (ggf. veraltete) crm_core.py,
    weil Python das Skriptverzeichnis automatisch auf sys.path[0] setzt
    (genau das ist am 2026-09-12 beim Import passiert: eine alte crm_core.py
    lag versehentlich direkt neben import_data.py)."""
    candidates = []
    if os.environ.get("CRM_CORE_DIR"):
        candidates.append(os.environ["CRM_CORE_DIR"])
    candidates += ["/opt/crm-pg-test", "/opt/crm", str(ROOT / "CPX12-Postgres")]
    for c in candidates:
        if Path(c).is_dir() and (Path(c) / "crm_core.py").exists():
            sys.path.insert(0, c)
            return
    try:
        import crm_core  # noqa: F401
        return
    except ImportError:
        pass
    print(
        "FEHLER: crm_core.py nicht gefunden (gesucht in: " + ", ".join(candidates) + "). "
        "Pfad per CRM_CORE_DIR=<Verzeichnis> angeben.", file=sys.stderr,
    )
    sys.exit(1)

ARCHIVE_PROJECT_NAME = "Altvorgänge vor CRM-Umstellung"
DK_MARKETING_FIRMA = "Intern"
DK_MARKETING_PROJECT = "DK Marketing"

DRY_RUN = True
_next_fake_id = 1
_warnings = []


def warn(msg):
    _warnings.append(msg)
    print(f"  WARNUNG: {msg}")


# ── Parser-Helfer ────────────────────────────────────────────────────────────
# Kopiert aus der Markdown-Fassung von crm_core.py (vor dem Postgres-Umstieg) -
# der laufende Code hat diese Funktionen nicht mehr, dieses Einmal-Skript
# braucht sie aber noch, um die Alt-Daten zu lesen.

def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("-"):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def parse_md_field(text, field):
    m = re.search(rf"\*\*{field}:\*\*[ \t]*(.+)", text)
    return m.group(1).strip() if m else ""


def _link(s):
    return (s or "").replace("[[", "").replace("]]", "").strip()


def _section(text, heading):
    m = re.search(rf"## {heading}\s*\n(.+?)(?=\n##|\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _bool(s):
    s = (s or "").strip().lower()
    if s in ("ja", "true", "yes"):
        return True
    if s in ("nein", "false", "no"):
        return False
    return None


def _date_or_none(s):
    s = (s or "").strip()
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return None


def _int_or_none(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() else None


def _money_or_none(s):
    if s in (None, ""):
        return None
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


def _percent_or_none(s):
    return _money_or_none(s)


# ── DB-Abstraktion (echt oder Dry-Run) ──────────────────────────────────────

def _insert(table, sql, params, dry_label=""):
    global _next_fake_id
    if DRY_RUN:
        rid = _next_fake_id
        _next_fake_id += 1
        return rid
    import crm_core as core
    return core._x(sql, params)[0]["id"]


def wipe():
    if DRY_RUN:
        print("(Dry-Run: kein TRUNCATE, keine Datenbankverbindung)")
        return
    import crm_core as core
    core._x(
        "TRUNCATE audit_log, mail_review_queue, heute_dismissed, aktivitaeten, "
        "tasks, projekte, personen, firmen RESTART IDENTITY CASCADE"
    )


# ── Firmen ───────────────────────────────────────────────────────────────────

def import_firmen():
    id_by_name = {}
    for f in sorted(FIRMEN_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        name = parse_md_field(text, "Firma") or fm.get("Firma") or f.stem

        dsgvo_added_raw = fm.get("dsgvo_added", "")
        dsgvo_added = _date_or_none(dsgvo_added_raw)
        if dsgvo_added is None and dsgvo_added_raw.strip().lower() == "ja":
            warn(f"{name}: dsgvo_added='ja' ist kein echtes Datum - wird als NULL importiert (Info geht verloren).")

        rid = _insert("firmen", """
            INSERT INTO firmen (name, status, branch, source, address, kundennr,
                                 next_action, last_contact, dsgvo_consent, dsgvo_added, beziehung_notiz)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (
            name, fm.get("status", "lead"),
            fm.get("branch") or parse_md_field(text, "Branche"),
            fm.get("source") or parse_md_field(text, "Quelle"),
            fm.get("address") or parse_md_field(text, "Adresse"),
            _int_or_none(fm.get("kundennr")),
            fm.get("next_action"),
            _date_or_none(fm.get("last_contact")),
            _bool(fm.get("dsgvo_consent")),
            dsgvo_added,
            _section(text, "Beziehung"),
        ))
        id_by_name[name.lower()] = rid
    return id_by_name


# ── Personen ─────────────────────────────────────────────────────────────────

def import_personen(firma_id_by_name):
    id_by_name = {}
    for pf in sorted(PERS_DIR.glob("*.md")):
        text = pf.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        firma_link = _link(fm.get("firma", ""))
        firma_id = firma_id_by_name.get(firma_link.lower())
        if firma_id is None:
            warn(f"Person {pf.stem}: referenziert unbekannte Firma '{firma_link}' - firma_id bleibt NULL.")
        name = parse_md_field(text, "Name") or pf.stem
        rid = _insert("personen", """
            INSERT INTO personen (firma_id, name, titel, abteilung, email, telefon, status,
                                   source, kampagne, hinzugefuegt, last_contact)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (
            firma_id, name, parse_md_field(text, "Titel"), parse_md_field(text, "Abteilung"),
            fm.get("email") or parse_md_field(text, "E-Mail"),
            fm.get("tel") or parse_md_field(text, "Telefon"),
            fm.get("status"), fm.get("source"), fm.get("kampagne"),
            _date_or_none(fm.get("hinzugefuegt")), _date_or_none(fm.get("last_contact")),
        ))
        id_by_name[name.lower()] = rid
    return id_by_name


# ── Projekte (Opportunities, inkl. _Archiv) ─────────────────────────────────

def import_opportunities(firma_id_by_name, person_id_by_name):
    projekt_ids_by_firma = {}      # firma_id -> [projekt_id, ...] in Dateireihenfolge
    projekt_id_by_name = {}        # opportunity-Dateiname (lower) -> projekt_id, fuer Aktivitaeten-Verknuepfung

    def _one(f, archiviert):
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        kontakt = _link(fm.get("kontakt", ""))
        firma_id = firma_id_by_name.get(kontakt.lower())
        if firma_id is None and kontakt:
            warn(f"Opportunity {f.stem}: referenziert unbekannte Firma '{kontakt}' - firma_id bleibt NULL.")
        ansprechpartner = fm.get("ansprechpartner", "")
        person_id = person_id_by_name.get(ansprechpartner.lower()) if ansprechpartner else None
        status = "archiviert" if archiviert else (fm.get("status") or "aktiv")
        rid = _insert("projekte", """
            INSERT INTO projekte (name, firma_id, person_id, status, value, probability,
                                   next_action, deadline, beschreibung)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (
            f.stem, firma_id, person_id, status,
            _money_or_none(fm.get("value") or parse_md_field(text, "Umsatz")),
            _percent_or_none(fm.get("probability") or parse_md_field(text, "Wahrscheinlichkeit")),
            fm.get("next_action"), _date_or_none(fm.get("deadline")),
            _section(text, "Zusammenfassung"),
        ))
        if firma_id:
            projekt_ids_by_firma.setdefault(firma_id, []).append(rid)
        projekt_id_by_name[f.stem.lower()] = rid

    for f in sorted(OPPS_DIR.glob("*.md")):
        _one(f, archiviert=False)
    archiv_dir = OPPS_DIR / "_Archiv"
    if archiv_dir.exists():
        for f in sorted(archiv_dir.glob("*.md")):
            _one(f, archiviert=True)

    return projekt_ids_by_firma, projekt_id_by_name


# ── Tasks (mit Sonderlogik fuer projektlose Alt-Tasks) ──────────────────────

_projekt_cache = {}   # (name, firma_id) -> projekt_id, fuer die automatisch angelegten Sammelprojekte


def _find_or_create_projekt(name, firma_id):
    key = (name, firma_id)
    if key in _projekt_cache:
        return _projekt_cache[key]
    rid = _insert("projekte", """
        INSERT INTO projekte (name, firma_id, status) VALUES (%s,%s,'aktiv') RETURNING id
    """, (name, firma_id))
    _projekt_cache[key] = rid
    return rid


def resolve_projekt_for_contact(contact, firma_id_by_name, projekt_ids_by_firma):
    if contact == "Intern / DK Marketing":
        firma_id = firma_id_by_name.get(DK_MARKETING_FIRMA.lower())
        return _find_or_create_projekt(DK_MARKETING_PROJECT, firma_id)

    firma_id = firma_id_by_name.get(contact.lower())
    if firma_id:
        existing = projekt_ids_by_firma.get(firma_id)
        if existing:
            return existing[0]
        pid = _find_or_create_projekt(f"{contact} – laufende Betreuung", firma_id)
        projekt_ids_by_firma.setdefault(firma_id, []).append(pid)
        return pid

    return _find_or_create_projekt(ARCHIVE_PROJECT_NAME, None)


def import_tasks(firma_id_by_name, projekt_ids_by_firma):
    data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    tasks = data.get("tasks", [])
    resolved = []
    for t in tasks:
        contact = (t.get("contact") or "").strip()
        projekt_id = resolve_projekt_for_contact(contact, firma_id_by_name, projekt_ids_by_firma)
        resolved.append((t, projekt_id, contact))

    for t, projekt_id, contact in resolved:
        deps = t.get("dependencies") or {}
        _insert("tasks", """
            INSERT INTO tasks (task_id, projekt_id, title, description, category, priority,
                                status, value, deadline, assigned_to, notes, tags, blocked_by, blocks,
                                quelle_mail_id, created_at, updated_at, completed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    COALESCE(%s::timestamptz, now()), COALESCE(%s::timestamptz, now()), %s::timestamptz)
            RETURNING id
        """, (
            t["taskId"], projekt_id, t.get("title", ""), t.get("description", ""),
            t.get("category"), t.get("priority"), t.get("status", "Offen"),
            _money_or_none(t.get("value")), _date_or_none(t.get("deadline")),
            t.get("assignedTo"), t.get("notes"),
            t.get("tags") or [], deps.get("blockedBy") or [], deps.get("blocks") or [],
            t.get("quelle_mail_id"),
            t.get("createdAt"), t.get("updatedAt"), t.get("completedAt"),
        ))
    return resolved


# ── Aktivitaeten (bisher Aktivitaeten/*.md, Sichtbarkeits-Monitoring) ───────

def import_aktivitaeten(firma_id_by_name, projekt_id_by_name):
    if not AKT_DIR.exists():
        return 0
    count = 0
    for f in sorted(AKT_DIR.glob("*.md")):
        if not f.is_file() or f.suffix != ".md":
            continue
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        kontakt = _link(fm.get("kontakt", ""))
        firma_id = firma_id_by_name.get(kontakt.lower())
        if firma_id is None and kontakt:
            warn(f"Aktivität {f.stem}: referenziert unbekannte Firma '{kontakt}' - firma_id bleibt NULL.")
        opp_name = _link(fm.get("opportunity", ""))
        projekt_id = projekt_id_by_name.get(opp_name.lower()) if opp_name else None

        titel_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        titel = titel_m.group(1).strip() if titel_m else f.stem
        notiz = _section(text, "Ergebnis")
        payload = {}
        naechste = _section(text, "Nächste Schritte")
        if naechste:
            payload["naechste_schritte"] = naechste

        _insert("aktivitaeten", """
            INSERT INTO aktivitaeten (firma_id, projekt_id, art, datum, dauer_minuten,
                                       quelle, pulse_id, titel, notiz, payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING id
        """, (
            firma_id, projekt_id, fm.get("art", "sonstiges"),
            _date_or_none(fm.get("datum")) or date.today().isoformat(),
            _int_or_none(fm.get("dauer_minuten")) or 0,
            fm.get("quelle"), fm.get("pulse_id") or None, titel, notiz,
            json.dumps(payload, ensure_ascii=False),
        ))
        count += 1
    return count


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global DRY_RUN
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true",
                     help="Tatsaechlich in die per CRM_DB_NAME (Default: crm) gewaehlte Datenbank "
                          "schreiben - LEERT vorher alle betroffenen Tabellen (TRUNCATE ... CASCADE). "
                          "Ohne dieses Flag: reiner Dry-Run, keine DB-Verbindung noetig.")
    ap.add_argument("--root", default=None,
                     help="Verzeichnis mit Kontakte/, Opportunities/, tasks.json, Aktivitäten/ "
                          "(Default: zwei Ebenen ueber diesem Skript, wie in der lokalen "
                          "CRM/Migration-Postgres/-Struktur). Auf dem Server z.B. /opt/crm-import.")
    args = ap.parse_args()
    if args.root:
        _set_root(args.root)
    DRY_RUN = not args.live
    if not DRY_RUN:
        _ensure_crm_core_importable()

    if not FIRMEN_DIR.exists() or not TASKS_FILE.exists():
        print(f"FEHLER: Erwartete Quelldaten nicht gefunden unter {ROOT} "
              f"(Kontakte/Firmen bzw. tasks.json fehlen).", file=sys.stderr)
        return 1

    print(f"{'DRY-RUN' if DRY_RUN else 'LIVE-IMPORT'} - Quelle: {ROOT}")
    if not DRY_RUN:
        import os
        db_name = os.environ.get("CRM_DB_NAME", "crm")
        print(f"Ziel-Datenbank: {db_name}")
        confirm = input(f"Alle Tabellen in '{db_name}' werden geleert und neu befuellt. Fortfahren? [ja/Nein] ")
        if confirm.strip().lower() != "ja":
            print("Abgebrochen.")
            return 1
        wipe()

    firma_id_by_name = import_firmen()
    person_id_by_name = import_personen(firma_id_by_name)
    projekt_ids_by_firma, projekt_id_by_name = import_opportunities(firma_id_by_name, person_id_by_name)
    resolved_tasks = import_tasks(firma_id_by_name, projekt_ids_by_firma)
    n_aktivitaeten = import_aktivitaeten(firma_id_by_name, projekt_id_by_name)

    print()
    print(f"Firmen:       {len(firma_id_by_name)}")
    print(f"Personen:     {len(person_id_by_name)}")
    print(f"Projekte:     {len(projekt_id_by_name) + len(_projekt_cache)} "
          f"({len(projekt_id_by_name)} aus Opportunity-Dateien, {len(_projekt_cache)} "
          f"automatisch angelegte Sammelprojekte)")
    print(f"Tasks:        {len(resolved_tasks)}")
    print(f"Aktivitaeten: {n_aktivitaeten}")
    if _warnings:
        print(f"\n{len(_warnings)} Warnung(en), siehe oben.")

    print("\nAuflösung der Sammelprojekte:")
    for (name, firma_id), pid in sorted(_projekt_cache.items()):
        contacts = sorted({c for _, p, c in resolved_tasks if p == pid})
        print(f"  [{pid}] {name} (firma_id={firma_id}) <- Tasks mit contact in {contacts}")

    if DRY_RUN:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben. Mit --live gegen CRM_DB_NAME "
              "ausfuehren (erst crm_test, nach erfolgreichem Smoke-Test dann crm).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
