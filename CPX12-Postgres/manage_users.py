#!/usr/bin/env python3
"""
manage_users.py – Login-Nutzer fuer das CRM-Dashboard anlegen/aendern
========================================================================
Kleines CLI-Tool fuer den App-Login (Konzept 2.6, Punkt 4a). Bewusst
getrennt vom Dashboard selbst: Passwoerter sollen nie ueber eine
Web-Oberflaeche im Klartext durchs Netz oder in einen Chat-Verlauf
wandern, sondern nur direkt auf dem Server per SSH gesetzt werden.

Seit dem Postgres-Umstieg (2026-09-11) liegen Nutzer in der users-Tabelle
statt in secrets/users.json - die DB-Verbindung laeuft ueber Peer-Auth am
Unix-Socket (OS-User <-> gleichnamige DB-Rolle), daher gilt weiterhin:
bitte NICHT als root ausfuehren, sondern als der Nutzer, unter dem auch
der CRM-Dienst laeuft ('crmapp', siehe crm.service) - sonst hat dieser
Prozess schlicht keinen Zugriff auf die crmapp-Datenbankrolle:

    sudo -u crmapp python3 manage_users.py add ronald

Weitere Nutzung auf dem Server:
    python3 manage_users.py list              # zeigt vorhandene Nutzernamen (keine Passwoerter/Hashes)
    python3 manage_users.py remove ronald

"add" legt den Nutzer an, falls er noch nicht existiert, oder setzt sein
Passwort neu, falls er schon existiert - beides ueber denselben Befehl.
"""

import getpass
import sys
import os

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
    try:
        core.set_user_password(username, pw1)
    except Exception as e:
        print(f"FEHLER: Konnte Nutzer nicht speichern ({e}). Laeuft dieses Skript als 'crmapp' "
              f"(sudo -u crmapp python3 manage_users.py add {username})? Die DB-Verbindung nutzt "
              f"Peer-Auth ueber den OS-User, ein anderer Nutzer hat keinen Zugriff auf die "
              f"crmapp-Datenbankrolle.")
        return 1
    print(f"OK: Login fuer '{username}' gespeichert (Postgres users-Tabelle).")

    if core.verify_login(username, pw1):
        print("Gegentest OK: Login mit dem gerade gesetzten Passwort funktioniert.")
    else:
        print("WARNUNG: Gegentest fehlgeschlagen - selbst das gerade gesetzte Passwort "
              "wird nicht akzeptiert. Bitte Nutzernamen auf Tippfehler pruefen.")
    return 0


def cmd_list():
    users = core.load_users()
    if not users:
        print("Keine Nutzer angelegt.")
        return 0
    for u in users:
        status = "" if u.get("aktiv") else "  (deaktiviert)"
        print(f"{u.get('username')}{status}")
    return 0


def cmd_remove(username):
    if not username:
        print("Bitte Nutzernamen angeben: python3 manage_users.py remove <nutzername>")
        return 1
    if not core.remove_user(username):
        print(f"Nutzer '{username}' nicht gefunden.")
        return 1
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
