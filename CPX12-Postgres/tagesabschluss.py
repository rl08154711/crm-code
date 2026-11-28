#!/usr/bin/env python3
"""
tagesabschluss.py – Nacht-Automatik fuer den Tagesabschluss (Migration 010, 2026-10-30)

Wer den Tag im CRM mit "Tag abschliessen" beendet, braucht das hier nicht.
Fuer alle anderen Tage springt dieses Skript ein (systemd-Timer
crm-tagesabschluss.timer, abends und als Nachholer morgens):

  abends  (ab 18 Uhr deutscher Zeit): schliesst den heutigen Tag ab, falls
          noch kein Abschluss existiert.
  morgens (vor 18 Uhr):               holt den Abschluss des Vortags nach,
          falls der Server abends nicht lief, und holt fertige Bewertungen
          ("Tagesbewertung JJJJ-MM-TT") aus ACOS ab.

Seit 28.11.2026: abends um 23:30. Werktage bekommen immer einen Abschluss (auch ohne
Eintrag, damit morgens ein Briefing da ist), Wochenendtage nur bei Aktivitaet. Morgens
werden alle fehlenden Tage der letzten 7 nachgeholt. Einen von Hand
gemachten Abschluss ueberschreibt die Automatik nie.

Aufruf von Hand:
    sudo -u crmapp python3 /opt/crm/tagesabschluss.py            # wie der Timer
    sudo -u crmapp python3 /opt/crm/tagesabschluss.py 2026-10-30 # bestimmter Tag
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crm_core as core  # noqa: E402


def main():
    if len(sys.argv) > 1:
        tag = date.fromisoformat(sys.argv[1])
        res = core.tagesabschluss_erstellen(tag, von="automatik")
        print(f"Abschluss {tag} geschrieben: {res['resuemee']['zahlen']}")
        return
    try:
        from zoneinfo import ZoneInfo
        jetzt = datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        jetzt = datetime.now()
    lauf(jetzt)


def lauf(jetzt, bewertungen=True):
    if jetzt.hour < 18 and bewertungen:
        try:
            geholt = core.tagesbewertungen_abholen()
            print("Bewertungen abgeholt:", ", ".join(geholt) if geholt else "keine neuen")
        except Exception as e:
            print(f"Bewertungen nicht abgeholt: {e}")
    # 28.11.2026: Abschluss fest um 23:30. Werktage (Mo-Fr) immer, auch ohne Eintrag - dann steht morgens
    # trotzdem ein Briefing da. Wochenende nur bei Aktivitaet. Der Nachholer morgens holt alle fehlenden
    # Tage der letzten 7 nach (bisher nur den Vortag), falls der Server zur Zeit aus war.
    bis = jetzt.date() if jetzt.hour >= 18 else jetzt.date() - timedelta(days=1)
    tage = [bis] if jetzt.hour >= 18 else [bis - timedelta(days=i) for i in range(6, -1, -1)]
    for tag in tage:
        if core._q1("SELECT 1 FROM tagesabschluss WHERE datum=%s", (tag,)):
            if tag == bis:
                print(f"{tag}: Abschluss liegt schon vor, nichts zu tun.")
            continue
        # leere Werktage nur fuer den gerade abzuschliessenden Tag, nicht rueckwirkend (sonst 7 leere Abschluesse)
        res = core.tagesabschluss_erstellen(tag, von="automatik", nur_wenn_aktiv=tag.weekday() >= 5 or tag != bis)
        if res is None:
            print(f"{tag}: ohne Aktivitaet, kein Abschluss.")
        else:
            print(f"{tag}: Abschluss geschrieben, {res['resuemee']['zahlen']}")


if __name__ == "__main__":
    main()
