# Ausrollen: Journal, Einstellungen, Handy-Ansicht (Oktober 2026, Teil 2)

Stand 2026-10-19. Baut auf Teil 1 auf (`DEPLOY-Update-2026-10.md`: Archiv,
Stammdaten, Mail-Review), der bereits live ist.

**Was neu ist**

*Journal (Schritt 4)*
- Reiter „📓 Journal“: alle fachlichen Einträge über alle Unternehmen, neueste zuerst,
  50 pro Seite. Filter Zeitraum, Art, Unternehmen, Volltextsuche.
- „＋ Eintrag“ direkt im Journal (Telefonat, Termin, E-Mail, Kontakt, Notiz),
  optional mit Person und Projekt.
- Umschalter „Technisch“: Protokoll, wer wann was geändert hat. Nur lesen.
- Log am Unternehmen: letzte 10 Einträge, Link ins Journal.

*Einstellungen (Schritt 5)* – Reiter „⚙️ Einstellungen“
- Persönlich: Startansicht, Standard-Projektfilter (jetzt pro Benutzer auf dem
  Server statt im Browser), Akzentfarbe, Passwort ändern (mind. 10 Zeichen).
- System: Mail-Konto (Server, Port, Benutzer, Passwort, „Verbindung testen“),
  Abruf an/aus und Intervall, automatisches Archivieren erledigter Aufgaben,
  KI-Bewertung an/aus (Standard aus), Liste ignorierter Absender.

*Handy-Ansicht (Schritt 6)*
- Auf dem Handy öffnet sich automatisch `/m`: Heute, Aufgaben, Projekte, Kontakte.
  Nur lesen. Telefon, Mail und Karte antippbar, letzte drei Journal-Einträge je Firma.
- „Vollansicht“ wechselt für die Sitzung zur großen Ansicht.
- Symbol für den Home-Bildschirm (iPhone: Teilen → „Zum Home-Bildschirm“,
  Android/Chrome: Menü → „Zum Startbildschirm hinzufügen“).

**Geänderte Dateien:** `crm_core.py`, `crm_serve.py`, `mail_poller.py`, neuer Ordner
`static/` mit drei Symbolen. **Datenbank:** Migration 004 (zwei neue Tabellen, rein additiv).

## Schritte

Server: `root@46.225.13.130`. `[Mac]` = Terminal auf dem Mac, `[Server]` = nach
`ssh root@46.225.13.130`. Befehle einzeln einfügen.

### 0 – Ausgangsstand prüfen

```bash
# [Server]
cd /opt/crm && sha1sum crm_core.py crm_serve.py mail_poller.py
ls -ld /opt/crm/secrets
```
Erwartet:
```
4a79c400f5a31134eb3d5c46eafcbc3c2ea6f22c  crm_core.py
ce9fb87e9a641e637444a0f9f86a7f176df029e2  crm_serve.py
ac08a45bb41e27e08d07e0f341a8b91b11a9ae24  mail_poller.py
```
`secrets` muss `crmapp` gehören (das CRM schreibt dort künftig die Mail-Zugangsdaten,
wenn du sie in den Einstellungen änderst). Weicht etwas ab: stoppen.

### 1 – Hochladen

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
ssh root@46.225.13.130 "mkdir -p /tmp/crm-update"
scp CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/mail_poller.py CPX12-Postgres/static/*.png Migration-Postgres/migration_004_einstellungen.sql Migration-Postgres/smoke_test.py root@46.225.13.130:/tmp/crm-update/
```

```bash
# [Server]
chmod 644 /tmp/crm-update/*
cd /tmp/crm-update && sha1sum crm_core.py crm_serve.py mail_poller.py
```
Erwartet:
```
2ce9021166e6db71a4065d0dc69d945098a51826  crm_core.py
b0ddaff7c413be9200e69b526eb75c17a0af3996  crm_serve.py
4f67b46175b46e5407b87a3ac1dbd0aff6e1d09c  mail_poller.py
```

### 2 – Probelauf gegen die Testdatenbank

```bash
# [Server]
sudo -u crmapp psql -d crm_test -f /tmp/crm-update/migration_004_einstellungen.sql
```
Erwartet: zweimal `CREATE TABLE`, kein `ERROR`.

### 3 – Sichern

```bash
# [Server]
sudo -u crmapp pg_dump -Fc crm > /root/crm-vor-teil2_$(date +%F_%H%M).dump
mkdir -p /root/crm-code-vor-teil2 && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/mail_poller.py /root/crm-code-vor-teil2/
ls -l /root/crm-vor-teil2_*.dump /root/crm-code-vor-teil2/
```

### 4 – Datenbank und Code

```bash
# [Server]
sudo -u crmapp psql -d crm -f /tmp/crm-update/migration_004_einstellungen.sql
install -o crmapp -g crmapp -m 644 /tmp/crm-update/crm_core.py /tmp/crm-update/crm_serve.py /tmp/crm-update/mail_poller.py /opt/crm/
install -d -o crmapp -g crmapp -m 755 /opt/crm/static
install -o crmapp -g crmapp -m 644 /tmp/crm-update/apple-touch-icon.png /tmp/crm-update/icon-192.png /tmp/crm-update/icon-512.png /opt/crm/static/
```

### 5 – Neu starten und prüfen

```bash
# [Server]
systemctl restart crm crm-mailpoll
systemctl status crm crm-mailpoll --no-pager
journalctl -u crm -u crm-mailpoll -n 20 --no-pager
```

Im Browser (`Cmd + Shift + R`):
- Reiter „📓 Journal“ öffnet sich, Einträge erscheinen.
- Reiter „⚙️ Einstellungen“: Mail-Konto zeigt Server und Benutzer, Passwort
  „unverändert (gespeichert)“. „Verbindung testen“ sollte „Anmeldung erfolgreich“ melden.
- Auf dem Handy die Adresse des CRM öffnen: Es erscheint die kompakte Ansicht.

Aufräumen: `rm -r /tmp/crm-update`

## Rückweg

```bash
# [Server]
install -o crmapp -g crmapp -m 644 /root/crm-code-vor-teil2/* /opt/crm/
systemctl restart crm crm-mailpoll
```
Die neuen Tabellen stören den alten Code nicht. Nur für den alten Datenstand:
`sudo -u crmapp pg_restore --clean -d crm /root/crm-vor-teil2_….dump`
