---
type: anleitung
title: CRM – Umstieg auf Postgres (CPX12)
stand: 2026-09-25
ersetzt: Fassung vom 2026-09-11 (Auslieferung per scp)
---

# Umstieg CPX12-Generalprobe auf Postgres

Voraussetzung: `CRM-Konzept-Postgres-Migration.md` gelesen, und der Server ist
nach `DEPLOY-Git-CPX12.md` eingerichtet – also Deploy Key gesetzt und das
Repository nach `/opt/crm-repo` geklont.

**Was sich gegenüber der Fassung vom 11.09. geändert hat:** Code und Skripte
kommen nicht mehr per `scp` auf den Server, sondern liegen durch den Klon
bereits dort. Damit entfallen das Zwischenverzeichnis `/opt/crm-pg-test`, die
Uploads nach `/tmp` und das Nachziehen der Dateirechte. Der Umzug selbst ist
am Ende kein Überschreiben mehr, sondern ein Umschalten der Dienste.

**Prinzip bleibt: nichts direkt am Live-Server verändern.** Der produktive
`crm.service` läuft während der gesamten Vorbereitung unverändert aus
`/opt/crm` auf dem alten Datei-Code weiter. Der Klon unter `/opt/crm-repo`
liegt daneben und tut nichts, solange ihn niemand startet.

## Wo was liegt

| Pfad | Inhalt |
|---|---|
| `/opt/crm` | Altinstallation: alter Code, Markdown-Altdaten (`Kontakte/`, `Opportunities/`, `tasks.json`, `Aktivitäten/`), `secrets/` |
| `/opt/crm-repo` | Klon des Repositorys – neuer Code unter `CPX12-Postgres/`, Skripte unter `Migration-Postgres/` |

## Schritt 1 – Postgres-Grundsetup

Auf dem Server, als root:

```
cd /opt/crm-repo/Migration-Postgres
chmod +x setup_postgres.sh
./setup_postgres.sh
```

Das Skript ist idempotent und legt `crm_test` + `crm` mit deploytem Schema an.
Peer-Auth heißt: die DB-Verbindung läuft über den OS-User (`crmapp`), kein
Passwort, keine Secrets-Datei.

Dass das Skript aus `/opt/crm-repo` statt aus `/tmp` läuft, ist kein Detail:
`/opt` ist für `crmapp` durchquerbar, `/root` war es nicht – daran ist der
erste Versuch gescheitert.

## Schritt 2 – Testweise starten (Port 8091, DB crm_test)

Kein Hochladen nötig, der Code liegt bereits da:

```
sudo -u crmapp CRM_PORT=8091 CRM_DB_NAME=crm_test CRM_COOKIE_SECURE=0 \
  python3 /opt/crm-repo/CPX12-Postgres/crm_serve.py &
```

Login-Nutzer für den Test anlegen:

```
cd /opt/crm-repo/CPX12-Postgres
sudo -u crmapp CRM_DB_NAME=crm_test python3 manage_users.py add smoketest
```

## Schritt 3 – Smoke-Test

```
python3 /opt/crm-repo/Migration-Postgres/smoke_test.py \
  --base http://127.0.0.1:8091 --user smoketest --password <gerade gesetztes Passwort>
```

Läuft lokal auf dem Server (Port 8091 geht nicht durch Firewall/Caddy nach
außen). Erwartet: alle Schritte `OK`, Exit-Code 0. Ergebnis bitte
zurückmelden, bevor es weitergeht.

## Schritt 4 – Datenimport gegen crm_test

Erst NACHDEM Schritt 3 grün ist.

`import_data.py` erwartet als Wurzelverzeichnis den Ordner, der `Kontakte/`,
`Opportunities/`, `tasks.json` und `Aktivitäten/` enthält – und darunter einen
Ordner `Migration-Postgres/` mit dem Skript selbst. Diese Daten liegen bereits
auf dem Server unter `/opt/crm`, und zwar im aktuellen Stand; die Kopie auf dem
Mac kann älter sein. Deshalb wird von dort importiert, nicht vom Mac.

`import_data.py` nimmt das Wurzelverzeichnis per `--root` entgegen, das Skript
muss also nirgendwohin kopiert werden.

Zuerst prüfen, dass die Struktur wirklich so daliegt:

```
ls -d /opt/crm/Kontakte /opt/crm/Opportunities /opt/crm/Aktivitäten /opt/crm/tasks.json
```

Dann importieren:

```
IMP=/opt/crm-repo/Migration-Postgres/import_data.py
python3 $IMP --root /opt/crm                                      # Dry-Run, keine DB noetig
sudo -u crmapp CRM_DB_NAME=crm_test python3 $IMP --root /opt/crm --live
```

Der Dry-Run auf dem Mac ergab 29 Tasks, 22 Firmen, 25 Personen, 12 Projekte,
5 Aktivitäten. Auf dem Server dürfen es mehr sein – dort wird ja gearbeitet.
Deutlich weniger wäre ein Warnsignal und ein Grund, innezuhalten.

Stichproben danach:

```
sudo -u crmapp psql -d crm_test -c "SELECT count(*) FROM tasks;"
sudo -u crmapp psql -d crm_test -c "SELECT name FROM projekte WHERE firma_id IS NULL;"
```

Smoke-Test anschließend erneut laufen lassen – die Datenbank ist jetzt nicht
mehr leer, sondern realistisch befüllt.

## Schritt 5 – Produktiv-Import

Erst nach vollständig grünem Test gegen `crm_test`:

Dafür gibt es `cutover.sh`. Es friert die Live-Daten zuerst in
`/opt/crm-import` ein, damit der Import einen stabilen Stand liest, während das
alte System weiterläuft, sichert die Dienstdateien und importiert dann gegen die
Produktiv-Datenbank:

```
/opt/crm-repo/Migration-Postgres/cutover.sh
```

Das Skript fragt vor dem Schreiben interaktiv nach, tippt „ja".

Produktiv-Login-Nutzer anlegen (Passwörter wurden bewusst NICHT migriert,
siehe Kommentar in `import_data.py`):

```
cd /opt/crm-repo/CPX12-Postgres
sudo -u crmapp python3 manage_users.py add ronald
```

## Schritt 6 – Dienste umschalten

Die Dienstdateien im Repository zeigen auf `/opt/crm-repo/CPX12-Postgres/`.
Installieren und neu starten:

```
cp /opt/crm-repo/CPX12-Postgres/crm.service /etc/systemd/system/
cp /opt/crm-repo/CPX12-Postgres/crm-mailpoll.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart crm crm-mailpoll
systemctl status crm --no-pager
```

`crm.service` braucht keine `Environment=`-Zeile für die Datenbank – der
Standardwert von `CRM_DB_NAME` ist bereits `crm` (siehe `crm_core.py`).

Danach manueller Browser-Check: Login, Dashboard lädt, ein paar Firmen und
Aufgaben stichprobenartig prüfen, eine Aufgabe über das Projekt-Auswahlfeld
anlegen.

Zum Schluss den Testprozess auf Port 8091 beenden:

```
pkill -f "CRM_PORT=8091"
```

## Rollback

Die Altinstallation unter `/opt/crm` bleibt vollständig liegen. Zurückschalten
heißt: die alten Dienstdateien wieder einsetzen.

```
sed -i 's|/opt/crm-repo/CPX12-Postgres|/opt/crm|g' /etc/systemd/system/crm.service
sed -i 's|/opt/crm-repo/CPX12-Postgres|/opt/crm|g' /etc/systemd/system/crm-mailpoll.service
systemctl daemon-reload && systemctl restart crm crm-mailpoll
```

Keine Datenverluste möglich: Die Markdown-Dateien unter `/opt/crm` werden vom
Import nur gelesen, nie verändert. Und der Code liegt ohnehin im Repository.

## Danach

Läuft die Umstellung über einige Wochen stabil, kann `/opt/crm` weg. Die
Markdown-Altdaten vorher einmal sichern, sie sind dann das letzte Zeugnis der
alten Welt.

`CPX12-Generalprobe/` bleibt dagegen vorerst im Repository: Die Vorführ-Instanz
läuft weiterhin auf diesem Code. Erst wenn auch sie auf Postgres umgestellt ist
(siehe Abschnitt „Offen: Vorführ-Instanz" in der README), ist die Markdown-Linie
endgültig Geschichte.
