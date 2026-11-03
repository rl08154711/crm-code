#!/usr/bin/env python3
"""
manage_users.py – Login-Nutzer fuer das CRM-Dashboard anlegen/aendern
========================================================================
Kleines CLI-Tool fuer den App-Login (Konzept 2.6, Punkt 4a). Bewusst
getrennt vom Dashboard selbst: Passwoerter sollen nie ueber eine
Web-Oberflaeche im Klartext durchs Netz oder in einen Chat-Verlauf
wandern, sondern nur direkt auf dem Server per SSH gesetzt werden.

WICHTIG (2026-08-07 in der Praxis aufgetreten): Bitte NICHT als root
ausfuehren, sondern als der Nutzer, unter dem auch der CRM-Dienst laeuft
('crmapp', siehe crm.service) - sonst gehoert die neu angelegte Datei
secrets/users.json root und der Dienst darf sie nicht mehr lesen, jeder
Login schlaegt dann unabhaengig vom Passwort fehl:

    sudo -u crmapp python3 manage_users.py add ronald

Falls schon als root ausgefuehrt: hinterher einmalig
    chown crmapp:crmapp /opt/crm/secrets/users.json
nachziehen.

Weitere Nutzung auf dem Server:
    python3 manage_users.py list              # zeigt vorhandene Nutzernamen (keine Passwoerter/Hashes)
    python3 manage_users.py remove ronald

"add" legt den Nutzer an, falls er noch nicht existiert, oder setzt sein
Passwort neu, falls er schon existiert - beides ueber denselben Befehl.
"""

import getpass
import sys
import os

try:
    import pwd
except ImportError:
    pwd = None  # nicht verfuegbar unter Windows - hier nur zur Info, kein Blocker

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crm_core as core


def cmd_add(username):
    if not username:
        print("Bitte Nutzernamen angeben: python3 manage_users.py add <nutzername>")
        return 1
    pw1 = getpass.getpass(f"Neues Passwort fuer '{username}': ")
    if not pw1:
        print("Abgebrochen: Passwort darf nicht leer sein.")
        return 1
    pw2 = getpass.getpass("Nochmal zur Bestaetigung: ")
    if pw1 != pw2:
        print("Abgebrochen: Passwoerter stimmen nicht ueberein.")
        return 1
    core.set_user_password(username, pw1)
    print(f"OK: Login fuer '{username}' gespeichert (secrets/users.json).")
    print("Hinweis: 'systemctl restart crm' ist dafuer NICHT noetig - die Datei wird bei jedem Login-Versuch frisch gelesen.")

    # Gegentest im eigenen Prozess - faengt Tippfehler/leere Datei ab, aber
    # NICHT das Rechteproblem (siehe unten), weil dieser Prozess seine
    # eigene, gerade erst angelegte Datei natuerlich lesen darf, egal als
    # welcher Unix-Nutzer er laeuft.
    if core.verify_login(username, pw1):
        print("Gegentest OK: Login mit dem gerade gesetzten Passwort funktioniert (in diesem Prozess).")
    else:
        print("WARNUNG: Gegentest fehlgeschlagen - selbst das gerade gesetzte Passwort "
              "wird nicht akzeptiert. Bitte Nutzernamen auf Tippfehler pruefen.")

    # Der eigentlich haeufige Fehler: Datei gehoert einem anderen Unix-Nutzer
    # als 'crmapp' (z.B. root, wenn dieses Skript per SSH als root statt via
    # 'sudo -u crmapp' ausgefuehrt wurde) - dann kann DIESER Prozess die
    # Datei zwar lesen, der laufende crm-Dienst (User 'crmapp') aber nicht,
    # und jeder Login im Browser schlaegt trotzdem fehl. Das explizit prüfen
    # und ansagen, statt den Nutzer raten zu lassen.
    if pwd is not None:
        try:
            file_owner = pwd.getpwuid(core.USERS_FILE.stat().st_uid).pw_name
            current_user = pwd.getpwuid(os.geteuid()).pw_name
            if file_owner != "crmapp":
                print(f"WARNUNG: secrets/users.json gehoert '{file_owner}' (dieses Skript lief als "
                      f"'{current_user}'), der CRM-Dienst laeuft aber als 'crmapp' (siehe crm.service) "
                      f"und kann die Datei dann NICHT lesen - Login schlaegt im Browser trotzdem fehl. "
                      f"Beheben mit: chown crmapp:crmapp {core.USERS_FILE}")
            elif current_user != "crmapp":
                print(f"Hinweis: Datei gehoert bereits korrekt 'crmapp', passt.")
        except Exception:
            pass  # reine Komfort-Warnung, kein Grund den Befehl fehlschlagen zu lassen
    return 0


def cmd_list():
    users = core.load_users()
    if not users:
        print("Keine Nutzer angelegt (oder secrets/users.json nicht lesbar - siehe journalctl -u crm fuer Warnungen).")
        return 0
    for u in users:
        print(u.get("username"))
    return 0


def cmd_remove(username):
    if not username:
        print("Bitte Nutzernamen angeben: python3 manage_users.py remove <nutzername>")
        return 1
    users = core.load_users()
    remaining = [u for u in users if u.get("username") != username]
    if len(remaining) == len(users):
        print(f"Nutzer '{username}' nicht gefunden.")
        return 1
    core.save_users(remaining)
    print(f"OK: '{username}' entfernt.")
    return 0


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("add", "list", "remove"):
        print(__doc__)
        return 1
    if args[0] == "add":
        return cmd_add(args[1] if len(args) > 1 else "")
    if args[0] == "remove":
        return cmd_remove(args[1] if len(args) > 1 else "")
    if args[0] == "list":
        return cmd_list()


if __name__ == "__main__":
    sys.exit(main())
