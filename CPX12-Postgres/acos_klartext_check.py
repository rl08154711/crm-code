#!/usr/bin/env python3
"""
Prueft, ob der CRM-Zugang zu ACOS Klartext bekommt (Pseudonymisierung "Aus").

Liest nur, schreibt nichts. Gibt keine Inhalte aus, nur Zaehler je Platzhalter-Art.

  1. Mandantenliste: Platzhalter in Mandantennamen
  2. Testmandant (Name beginnt mit "ZZ Test"): alle Wissensobjekte und Dokumente
  3. CRM-Datenbank: Platzhalter, die frueher aus ACOS uebernommen wurden

Aufruf:
    sudo -u crmapp python3 /opt/crm/acos_klartext_check.py
    sudo -u crmapp python3 /opt/crm/acos_klartext_check.py --mandant <ACOS-ID>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crm_core as core  # noqa: E402
import acos_sync as a  # noqa: E402

MUSTER = re.compile(r"\b(PERSON|EMAIL|IBAN|PHONE|ADDRESS|TAX_NUMBER|ORGANIZATION|LOCATION|VAT_ID|CREDIT_CARD|DATE|URL)_[A-Z0-9]{6,}\b")


def zaehle(text, z):
    for m in MUSTER.finditer(text or ""):
        z[m.group(1)] += 1


def zeile(titel, z):
    n = sum(z.values())
    teile = ", ".join(f"{k} {v}" for k, v in sorted(z.items())) or "-"
    print(f"  {titel:<38} {n:>5}   {teile}")
    return n


def main():
    zug = a.lade_acos_zugang()
    if not zug.get("ACOS_TOKEN") or not zug.get("ACOS_MCP_URL"):
        print("Zugang fehlt (secrets/acos.env)")
        return 2
    mcp = a.Mcp(zug["ACOS_MCP_URL"], zug["ACOS_TOKEN"])
    mcp.start()
    gesamt = 0
    print("Platzhalter je Quelle (0 = Klartext):")

    mandanten = [a.mandant(m) for m in a._liste(mcp.lesen("am_acos_clients_list"))]
    z = Counter()
    for m in mandanten:
        zaehle(m.get("name"), z)
    gesamt += zeile(f"Mandantennamen ({len(mandanten)})", z)

    ziel = None
    if "--mandant" in sys.argv:
        ziel = sys.argv[sys.argv.index("--mandant") + 1]
    else:
        ziel = next((m["id"] for m in mandanten if (m.get("name") or "").startswith("ZZ Test")), None)
    if not ziel:
        print("  Testmandant nicht gefunden (Name beginnt nicht mit 'ZZ Test'); --mandant <ID> angeben")
    else:
        objekte = a._liste(mcp.lesen("am_acos_knowledge_list", {"client_id": ziel, "limit": 50}))
        zt, zi, dok = Counter(), Counter(), 0
        for o in objekte:
            w = a.wissensobjekt(o)
            zaehle(w.get("titel"), zt)
            try:
                if (w.get("art") or "") == "document":
                    r = mcp.lesen("am_acos_file_read", {"document_id": w["id"], "limit": 24000})
                    zaehle(r.get("title"), zt)
                    zaehle(r.get("text"), zi)
                    dok += 1
                else:
                    zaehle(a.inhalt_holen(mcp, w["id"]), zi)
            except a.AcosFehler as e:
                print(f"  Hinweis: ein Objekt nicht lesbar ({str(e)[:80]})")
        gesamt += zeile(f"Testmandant: Titel ({len(objekte)})", zt)
        gesamt += zeile(f"Testmandant: Inhalte ({dok} Dokumente)", zi)

    print("Bereits im CRM gespeichert (aus früheren Läufen):")
    for titel, sql in (
        ("acos_verknuepfung.acos_name", "SELECT acos_name AS t FROM acos_verknuepfung"),
        ("acos_verknuepfung.vorschlaege", "SELECT vorschlaege::text AS t FROM acos_verknuepfung"),
        ("acos_artefakte.titel", "SELECT titel AS t FROM acos_artefakte"),
        ("acos_artefakte.acos_projekt", "SELECT acos_projekt AS t FROM acos_artefakte"),
        ("acos_laeufe.bericht", "SELECT bericht::text AS t FROM acos_laeufe"),
    ):
        z = Counter()
        try:
            for r in core._q(sql):
                zaehle(r.get("t"), z)
        except Exception as e:  # Spalte fehlt o. ae.
            print(f"  {titel}: nicht prüfbar ({str(e)[:60]})")
            core.get_conn().rollback()
            continue
        zeile(titel, z)
    print()
    print("ERGEBNIS:", "Klartext - CRM-Zugang ohne Pseudonymisierung" if gesamt == 0
          else f"{gesamt} Platzhalter aus ACOS - Zugang noch pseudonymisiert")
    return 0 if gesamt == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
