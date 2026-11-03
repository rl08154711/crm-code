# Ausrollen: Update Oktober 2026 (Migrationen 002 und 003)

Stand 2026-10-19. Enthält drei Bausteine, die zusammen ausgerollt werden.

**Archiv und Stammdaten (Migration 002)**
- Unternehmen, Personen, Projekte und Aufgaben lassen sich archivieren und im neuen
  Reiter „🗄 Archiv“ wieder aktivieren. Der fachliche Status bleibt dabei erhalten.
- Erledigte Aufgaben gesammelt („Erledigte archivieren“) oder einzeln archivieren.
- Neue Felder: Telefon Zentrale (Unternehmen), Mobil, zweite E-Mail, LinkedIn (Personen).

**Statusfilter für Projekte**
- Filter-Knöpfe im Reiter „Projekt“: Angebahnt, Aktiv, Pausiert, Gewonnen, Verloren,
  Inaktiv. Standard: Angebahnt, Aktiv, Pausiert. Die Auswahl merkt sich der Browser.
- Neuer Projektstatus „Pausiert“.

**Mail-Review (Migration 003)**
- Unbekannte Absender verschwinden nicht mehr. Sie lassen sich einem bestehenden oder
  neuen Unternehmen zuordnen, optional mit neuer Person (Name aus dem Absender vorbefüllt).
- Absender oder ganze Domains ignorieren (z. B. Newsletter).
- KI-Bewertung der Mails ist standardmäßig **aus** (`config.json` → `llm.enabled: false`).
  Damit gehen keine Mailinhalte mehr an einen externen Anbieter.

## Ausrollen per scp (wie bisher)

Der Server holt sich den Code noch nicht aus GitHub. Dieses Update geht deshalb
wie gewohnt per Dateikopie hinauf. Die Umstellung auf Git folgt danach als eigener
Schritt (`DEPLOY-Git-CPX12.md`).

Server: `root@46.225.13.130`. Alle Befehle mit `[Mac]` laufen im Terminal auf dem
Mac, alle mit `[Server]` nach `ssh root@46.225.13.130`.

### Schritt 0 – Wo läuft das CRM, und ist es der erwartete Stand?

```bash
# [Server]
systemctl cat crm | grep -E 'WorkingDirectory|ExecStart'
```

Der Ordner hinter `WorkingDirectory` ist das Ziel, z. B. `/opt/crm`. Für alle
weiteren Befehle einmal festlegen (Pfad anpassen):

```bash
# [Server]
ZIEL=/opt/crm
cd $ZIEL && sha1sum crm_core.py crm_serve.py mail_poller.py config.json
```

Erwartet (Ausgangsstand, auf dem das Update aufbaut):

```
75df80335222633b260cd8273e638cffad079d93  crm_core.py
44a210ee82283a56f8a66f97d88cf6b15c5d0308  crm_serve.py
5c5d3e59221845fee8695f7445f09eda448dd7fa  mail_poller.py
69b35f46acf7a9d89805ac6dd80cb1edd11f335d  config.json
```

- Alle vier gleich: weiter.
- `config.json` weicht ab, der Rest stimmt: weiter, aber `config.json` in
  Schritt 4 **nicht** kopieren, sondern dort nur `llm.enabled` nachtragen.
- `mail_poller.py` zeigt `9b30416ca9495cc7…`: Das ist der alte Markdown-Poller aus
  `CPX12-Generalprobe`. Beim Umstieg am 14.09. wurde er nicht mitkopiert und bricht
  mit dem Postgres-Code bei der Aufräumfunktion ab. Weiter, das Update ersetzt ihn.
- Eine andere `.py`-Datei weicht ab: **stoppen**. Auf dem Server liegt dann ein
  anderer Code als angenommen, das Update würde ihn überschreiben.
- `ZIEL` liegt unter `/opt/crm-repo` (also schon ein Git-Klon): ebenfalls stoppen,
  dann läuft das Update besser per `git pull`.

### Schritt 1 – Dateien hochladen

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
git branch --show-current          # muss feature/archiv-stammdaten zeigen
ssh root@46.225.13.130 "mkdir -p /tmp/crm-update"
scp CPX12-Postgres/{crm_core.py,crm_serve.py,mail_poller.py,config.json} \
    Migration-Postgres/{migration_002_archiv_stammdaten.sql,migration_003_mail_review.sql,smoke_test.py} \
    root@46.225.13.130:/tmp/crm-update/
```

```bash
# [Server]
chmod 644 /tmp/crm-update/*
cd /tmp/crm-update && sha1sum crm_core.py crm_serve.py mail_poller.py config.json
```

Erwartet (neuer Stand):

```
4a79c400f5a31134eb3d5c46eafcbc3c2ea6f22c  crm_core.py
ce9fb87e9a641e637444a0f9f86a7f176df029e2  crm_serve.py
ac08a45bb41e27e08d07e0f341a8b91b11a9ae24  mail_poller.py
b5ff437ba696c31818f17dee5ba2be86ac0a8f4f  config.json
```

### Schritt 2 – Probelauf gegen die Test-Datenbank

```bash
# [Server]
sudo -u crmapp psql -d crm_test -f /tmp/crm-update/migration_002_archiv_stammdaten.sql
sudo -u crmapp psql -d crm_test -f /tmp/crm-update/migration_003_mail_review.sql
```

Es dürfen nur Meldungen wie `ALTER TABLE`, `UPDATE …`, `CREATE …` kommen,
kein `ERROR`. Gibt es `crm_test` nicht mehr, diesen Schritt auslassen; die
Migrationen sind lokal auf altem und neuem Schema getestet.

Optional, falls `/opt/crm-pg-test` noch existiert: neuen Code dorthin, Test-Instanz
auf Port 8091 starten und den Smoke-Test laufen lassen.

```bash
# [Server]
install -o crmapp -g crmapp -m 644 /tmp/crm-update/{crm_core.py,crm_serve.py,mail_poller.py,config.json,smoke_test.py} /opt/crm-pg-test/
sudo -u crmapp CRM_PORT=8091 CRM_DB_NAME=crm_test CRM_COOKIE_SECURE=0 python3 /opt/crm-pg-test/crm_serve.py &
python3 /opt/crm-pg-test/smoke_test.py --base http://127.0.0.1:8091 --user smoketest \
  --password <pw> --internal-token "$(cat /opt/crm-pg-test/secrets/internal_token.key)"
kill %1                            # Test-Instanz wieder beenden
```

### Schritt 3 – Sichern

```bash
# [Server]
sudo -u crmapp pg_dump -Fc crm > /root/crm-vor-update-2026-10_$(date +%F_%H%M).dump
mkdir -p /root/crm-code-vor-update-2026-10
cp -p $ZIEL/{crm_core.py,crm_serve.py,mail_poller.py,config.json} /root/crm-code-vor-update-2026-10/
ls -l /root/crm-vor-update-2026-10_*.dump /root/crm-code-vor-update-2026-10/
```

Die Dump-Datei muss größer als ein paar KB sein.

### Schritt 4 – Datenbank und Code auf dem Live-System

```bash
# [Server]
sudo -u crmapp psql -d crm -f /tmp/crm-update/migration_002_archiv_stammdaten.sql
sudo -u crmapp psql -d crm -f /tmp/crm-update/migration_003_mail_review.sql

install -o crmapp -g crmapp -m 644 /tmp/crm-update/{crm_core.py,crm_serve.py,mail_poller.py} $ZIEL/
install -o crmapp -g crmapp -m 644 /tmp/crm-update/config.json $ZIEL/   # nur wenn config.json in Schritt 0 übereinstimmte
```

Stimmte `config.json` in Schritt 0 nicht überein: die Datei auf dem Server von Hand
öffnen (`nano $ZIEL/config.json`) und im Abschnitt `"llm"` die Zeile
`"enabled": false,` ergänzen.

### Schritt 5 – Neu starten und prüfen

```bash
# [Server]
systemctl restart crm crm-mailpoll
systemctl status crm crm-mailpoll --no-pager
journalctl -u crm -n 30 --no-pager
```

Im Browser: Anmelden, Reiter „Projekt“ zeigt die Filter-Knöpfe, Reiter „🗄 Archiv“
öffnet sich, ein Unternehmen zeigt das Feld „Telefon Zentrale“, Mail-Review lädt.

Zum Schluss aufräumen: `rm -r /tmp/crm-update`

### Was die Migrationen ändern

Die Migrationen sind rein additiv: Sie fügen Spalten und eine Tabelle hinzu. Bisher
archivierte Unternehmen und Projekte bekommen archiviert_am gesetzt und den Status
„inaktiv“ (der ursprüngliche Status ist nicht mehr bekannt). Gelöscht wird nichts.

## Rückweg, falls etwas nicht passt

Code zurück:

```bash
# [Server]
install -o crmapp -g crmapp -m 644 /root/crm-code-vor-update-2026-10/* $ZIEL/
systemctl restart crm crm-mailpoll
```

Die neuen Spalten stören den alten Code nicht, die Datenbank kann also bleiben.
Nur wer wirklich auf den alten Datenstand zurück will:
`sudo -u crmapp pg_restore --clean -d crm /root/crm-vor-update-2026-10_….dump`
