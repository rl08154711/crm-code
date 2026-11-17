# Nächstes Update – gesammelte Änderungen

Liegt im Zweig `feature/naechstes-update`. Stand live: Mail-Anhänge (Migration 009) und
ACOS-Zugang im Klartext, beide seit 28.10.2026. Die Anleitungen dazu stehen in der
Git-Historie dieser Datei.

| Datum | Änderung | Dateien | Migration |
|---|---|---|---|
| 2026-10-30 | **Menü neu:** zwei Gruppen. Tagesgeschäft mit Heute, Aufgaben, Projekte, Mail-Review. Stammdaten mit Unternehmen, Kontakte (bisher „Personen“) und Recherche (bisher „Wissen“). Das Journal steht nicht mehr im Menü, ist aber aus Heute („Ganzes Journal →“), aus den Akten und als Favorit erreichbar. | `crm_core.py` | – |
| 2026-10-30 | **Heute ausgebaut:** oben das Briefing aus dem letzten Abschluss, dann die Tagesaufgaben wie bisher, dann „Heute erledigt und erfasst“ (erledigte Aufgaben und Journal des Tages), unten der Tagesabschluss. „Tag abschließen“ erzeugt ein Resümee (Zahlen, offen Gebliebenes, regelbasierte Hinweise) und das Briefing für den nächsten Arbeitstag. Wer es vergisst: Nacht-Automatik um 23:40, Nachholer um 6:30, Tage ohne jede Aktivität werden übersprungen. | `crm_core.py`, `crm_serve.py`, `tagesabschluss.py` (neu), `crm-tagesabschluss.service/.timer` (neu) | **010** |
| 2026-10-30 | **Tagesabschluss an ACOS (abschaltbar, Standard aus):** Einstellungen → System. Jeder Abschluss geht als Markdown in `<Inhaber>/Tagesabschluss/` der Nextcloud und von dort in dessen ACOS-Akte. Empfänger ist fest das Unternehmen, dem das CRM gehört (`inhaber_firma` in `config.json`), nicht wählbar. Ein Wissensobjekt „Tagesbewertung JJJJ-MM-TT“ beim selben Mandanten erscheint nach dem ACOS-Abgleich als Link am Tag und im Briefing. | `crm_core.py` | 010 |
| 2026-10-30 | **Dublettenprüfung Kontakte:** Rückfrage beim Anlegen (Akte, Kontaktformular, Mail-Review, Journal-Aktion) bei gleicher E-Mail, gleichem oder ähnlichem Namen oder gleicher Mobilnummer. Unter Stammdaten → Kontakte → „Dubletten“ die Liste aller Verdachtspaare mit Zusammenführen (Journal und Projekte wandern mit, leere Felder werden ergänzt, der zweite Datensatz kommt ins Archiv) und „Keine Dublette“. | `crm_core.py`, `crm_serve.py` | 010 |

Getestet in der Sandbox gegen `crm_test` mit Migrationen 002–010: `smoke_test.py` 83/83 grün
(zwei neue Prüfungen für Dubletten und Tagesabschluss), Oberfläche per Browser auf
Desktop und Handy ohne JavaScript-Fehler.

## Ausrollen

```bash
# [Server] Ausgangsstand
cd /opt/crm && sha1sum crm_core.py crm_serve.py
#   14e22e18961c589b6e36f5a4a10c5a476c818ebc  crm_core.py
#   8b5cc90e9c99699f0e46bc2c24fbc78faf8cb433  crm_serve.py

# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
ssh root@46.225.13.130 "mkdir -p /tmp/crm-update"
scp CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/tagesabschluss.py \
    CPX12-Postgres/crm-tagesabschluss.service CPX12-Postgres/crm-tagesabschluss.timer \
    Migration-Postgres/migration_010_tagesabschluss_dubletten.sql root@46.225.13.130:/tmp/crm-update/

# [Server] Prüfen
cd /tmp/crm-update && sha1sum *
#   8caccb6a9b9e7ba7126a8bb8255a6d615f222608  crm-tagesabschluss.service
#   fc325df12b323217b65b6581a9c54c4938414d37  crm-tagesabschluss.timer
#   00a93c63dd0f551b82bc4462d083a0803d5f9d29  crm_core.py
#   dd7a02de43cde9b428393b60c2807cc8cf309f4a  crm_serve.py
#   d1255e60448f9de69aa7914b4af481d13ce9e7b3  migration_010_tagesabschluss_dubletten.sql
#   24530fd5100442855f8ef568cf30c109d995dfe2  tagesabschluss.py

# [Server] Probelauf, Sicherung, Migration
cd /tmp
sudo -u crmapp psql -d crm_test < /tmp/crm-update/migration_010_tagesabschluss_dubletten.sql
sudo -u crmapp pg_dump -Fc crm > /root/crm-vor-tagesabschluss_$(date +%F_%H%M).dump
mkdir -p /root/crm-code-vor-tagesabschluss && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /root/crm-code-vor-tagesabschluss/
sudo -u crmapp psql -d crm < /tmp/crm-update/migration_010_tagesabschluss_dubletten.sql
#   erwartet: CREATE TABLE, ALTER TABLE, CREATE INDEX, kein ERROR

# [Server] Code einspielen, Dienst neu starten
cp /tmp/crm-update/crm_core.py /tmp/crm-update/crm_serve.py /tmp/crm-update/tagesabschluss.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/tagesabschluss.py
cd /opt/crm && sha1sum crm_core.py crm_serve.py tagesabschluss.py
systemctl restart crm
systemctl status crm --no-pager

# [Server] Nacht-Automatik einrichten
cp /tmp/crm-update/crm-tagesabschluss.service /tmp/crm-update/crm-tagesabschluss.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now crm-tagesabschluss.timer
systemctl list-timers crm-tagesabschluss.timer --no-pager
#   erwartet: naechster Lauf 23:40 bzw. 06:30

# [Server] Einmal von Hand pruefen (schreibt den Abschluss von gestern, falls es dort Aktivitaet gab)
cd /tmp && sudo -u crmapp python3 /opt/crm/tagesabschluss.py
rm -r /tmp/crm-update
```

Rückweg Code: `cp /root/crm-code-vor-tagesabschluss/* /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py && systemctl restart crm`,
dazu `systemctl disable --now crm-tagesabschluss.timer`. Die Migration darf bleiben, sie ist rein additiv.

## Danach im CRM

1. **Dubletten bereinigen:** Stammdaten → Kontakte → „⧉ Dubletten“. Je Paar „Diesen behalten“ oder „Keine Dublette“.
2. **Tagesabschluss an ACOS** (optional): Einstellungen → System → „Tagesabschluss an ACOS“. Eigenes Unternehmen
   eintragen (muss in ACOS verknüpft sein), Haken setzen, speichern. Erst einschalten, wenn die Bewertung in ACOS
   eingerichtet ist – sonst sammeln sich nur Dateien.

## Nachtrag 30.10.: Empfänger fest auf den Inhaber

✅ live seit 30.10. (crm_core.py `ea99b023…`). Neu: Der Tagesabschluss geht nur noch an das
Unternehmen aus `inhaber_firma` in `config.json`. In den Einstellungen wird es nur angezeigt.

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm_core.py

# [Server]
cd /opt/crm && sha1sum crm_core.py /tmp/crm_core.py
#   00a93c63dd0f551b82bc4462d083a0803d5f9d29  crm_core.py       (live)
#   ea99b0239eeb5c51244618885578e0efa66f0805  /tmp/crm_core.py  (neu)
cp -p config.json /root/config.json.vor-inhaber && cp -p crm_core.py /root/crm_core.py.vor-inhaber
sudo -u crmapp python3 -c "import json; p='/opt/crm/config.json'; d=json.load(open(p)); d['inhaber_firma']='Digitale Konzepte e. K.'; json.dump(d, open(p,'w'), ensure_ascii=False, indent=2)"
grep inhaber_firma config.json
cp /tmp/crm_core.py /opt/crm/crm_core.py && chown crmapp:crmapp /opt/crm/crm_core.py && rm /tmp/crm_core.py
systemctl restart crm && sleep 3 && systemctl is-active crm
```

Rückweg: `cp /root/crm_core.py.vor-inhaber /opt/crm/crm_core.py && cp /root/config.json.vor-inhaber /opt/crm/config.json && systemctl restart crm`.

## Nachtrag 2 (30.10.): Tagesabschluss als Wissensobjekt statt Datei

Hochgeladene Dateien kann die Bewertung in ACOS nicht auflisten. Der Abschluss geht deshalb als
Wissensobjekt „Tagesabschluss JJJJ-MM-TT“ (kind report) in die Akte des Inhabers; erneutes
Abschließen am selben Tag schreibt dasselbe Objekt fort. Die Markdown-Kopie in
`<Inhaber>/Tagesabschluss/` der Nextcloud bleibt. Kein Journal-Eintrag mehr für die Übertragung.

```bash
# [Mac]
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm_core.py
# [Server]
cd /opt/crm && sha1sum crm_core.py /tmp/crm_core.py
#   ea99b0239eeb5c51244618885578e0efa66f0805  crm_core.py       (live)
#   22337ec237bedfb3466d64986f8e7e7a64280a4f  /tmp/crm_core.py  (neu)
cp -p crm_core.py /root/crm_core.py.vor-wissensobjekt
cp /tmp/crm_core.py /opt/crm/crm_core.py && chown crmapp:crmapp /opt/crm/crm_core.py && rm /tmp/crm_core.py
systemctl restart crm && sleep 3 && systemctl is-active crm
```

Rückweg: `cp /root/crm_core.py.vor-wissensobjekt /opt/crm/crm_core.py && systemctl restart crm`.

## Nachtrag 3 (30.10.): Maskierung durch das CRM, Bewertung zurück

Probe am 30.10.: Beim Lesen über ACOS kamen Namen aus dem CRM im Klartext an. ACOS maskiert nur
Namen, die es selbst kennt. Jetzt maskiert das CRM vor dem Senden selbst (Firmen und Personen
aus der eigenen Datenbank, dazu Mail, Telefon, IBAN und Namen mit Anrede). Die Bewertung
„Tagesbewertung JJJJ-MM-TT“ holt das CRM morgens (Timer 6:30) oder per „Bewertung abholen“
zurück, setzt die Namen wieder ein und zeigt sie am Tag und im Briefing.

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
scp CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/tagesabschluss.py \
    Migration-Postgres/migration_011_tagesabschluss_maskierung.sql root@46.225.13.130:/tmp/

# [Server]
cd /opt/crm && sha1sum crm_core.py crm_serve.py tagesabschluss.py
#   22337ec237bedfb3466d64986f8e7e7a64280a4f  crm_core.py   (live, Nachtrag 2)
#   dd7a02de43cde9b428393b60c2807cc8cf309f4a  crm_serve.py
#   24530fd5100442855f8ef568cf30c109d995dfe2  tagesabschluss.py
cd /tmp && sha1sum crm_core.py crm_serve.py tagesabschluss.py migration_011_tagesabschluss_maskierung.sql
#   8a2051a86a2ca5b93c980a34a56e8659be458a24  crm_core.py
#   190ce21079a3e68b5cbb76fbd8b9b4c11d262dbc  crm_serve.py
#   49f543f70476d6be27b40656028ec7f5248cbddd  tagesabschluss.py
#   2043f3b5827eb337da63624be7e310e6233f86ac  migration_011_tagesabschluss_maskierung.sql
sudo -u crmapp psql -d crm < /tmp/migration_011_tagesabschluss_maskierung.sql
mkdir -p /root/crm-code-vor-maskierung && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/tagesabschluss.py /root/crm-code-vor-maskierung/
cp /tmp/crm_core.py /tmp/crm_serve.py /tmp/tagesabschluss.py /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py
rm /tmp/crm_core.py /tmp/crm_serve.py /tmp/tagesabschluss.py /tmp/migration_011_tagesabschluss_maskierung.sql
systemctl restart crm && sleep 3 && systemctl is-active crm
```

Rückweg: `cp /root/crm-code-vor-maskierung/* /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py && systemctl restart crm`.
Die Migration ist additiv und darf bleiben.

Bekannte Grenze: Namen, die weder im CRM stehen noch mit Anrede im Journaltext vorkommen
(„Telefonat mit Meier“), erkennt die Maskierung nicht. Journaltexte deshalb mit Anrede oder
über verknüpfte Personen schreiben.

### Korrektur zu Nachtrag 3 (30.10., 16:40)

ACOS lehnt Markdown-Berichte über `am_acos_knowledge_save` ab. Der Abschluss geht jetzt per
`am_acos_artifact_save` als Bericht (kind report); erneutes Abschließen erzeugt eine neue Version.

```bash
# [Mac]
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm_core.py
# [Server]
cd /opt/crm && sha1sum crm_core.py /tmp/crm_core.py
#   8a2051a86a2ca5b93c980a34a56e8659be458a24  crm_core.py       (live)
#   2c570a877f278da24e2695bb9cf32d5279b21669  /tmp/crm_core.py  (neu)
cp /tmp/crm_core.py /opt/crm/crm_core.py && chown crmapp:crmapp /opt/crm/crm_core.py && rm /tmp/crm_core.py
systemctl restart crm && sleep 3 && systemctl is-active crm
```

## Kundenwissen (30.10.2026, Migration 012)

Neuer Reiter „Kundenwissen“ in der Firmenakte. Durchsucht nur die Unterlagen dieser Firma:
`<Kundenordner>/Besprechungen/`, `<Kundenordner>/ACOS/` und das Journal. Wortwurzel-Suche,
damit „Stundung“ auch „gestundet“ findet. Ohne Suchbegriff: Liste der Besprechungen (Datum aus
dem Dateinamen) und der ACOS-Unterlagen, Klick zeigt den erkannten Text. Abgleich stündlich im
selben Lauf wie die Recherche (`wissen_sync.py`), aber eigene Tabelle `kundenwissen` – in der
Recherche taucht nichts davon auf. Ordnername muss dem Firmennamen im CRM entsprechen
(Leerzeichen, Punkte, Groß/Klein egal). `Mail-Eingang/` und andere Ordner bleiben draußen.

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
scp CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/wissen_sync.py \
    Migration-Postgres/migration_012_kundenwissen.sql root@46.225.13.130:/tmp/

# [Server] Prüfen
cd /opt/crm && sha1sum crm_core.py crm_serve.py wissen_sync.py
#   2c570a877f278da24e2695bb9cf32d5279b21669  crm_core.py   (live)
#   190ce21079a3e68b5cbb76fbd8b9b4c11d262dbc  crm_serve.py
#   8d6b9c1b406b40ba8714ff5cd75f3051fa6ed7c2  wissen_sync.py
cd /tmp && sha1sum crm_core.py crm_serve.py wissen_sync.py migration_012_kundenwissen.sql
#   902c9ec3ca16df0141ceb581b27274c3432f9ec6  crm_core.py
#   65cb6ebec29a3d9d9c30e9eceede7611e0b48f11  crm_serve.py
#   6da5eb5ca0965a90b3bb73593590f73620e183c9  wissen_sync.py
#   6da1c6aa158497e7b303f4eb0d7b166ae7feb3d8  migration_012_kundenwissen.sql

# [Server] Sichern, Migration, einspielen
mkdir -p /root/crm-code-vor-kundenwissen && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/wissen_sync.py /root/crm-code-vor-kundenwissen/
sudo -u crmapp psql -d crm < /tmp/migration_012_kundenwissen.sql
cp /tmp/crm_core.py /tmp/crm_serve.py /tmp/wissen_sync.py /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py
rm /tmp/crm_core.py /tmp/crm_serve.py /tmp/wissen_sync.py /tmp/migration_012_kundenwissen.sql
systemctl restart crm && sleep 3 && systemctl is-active crm

# [Server] Ersten Abgleich gleich anstoßen statt bis zur vollen Stunde zu warten
cd /tmp && sudo -u crmapp python3 /opt/crm/wissen_sync.py hand 2>&1 | grep -i "kundenwissen\|beendet"
```

Rückweg: `cp /root/crm-code-vor-kundenwissen/* /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py && systemctl restart crm`.
Migration additiv, darf bleiben.

## Kundenwissen: ACOS-Dokumente als Verweis (03.11.2026, keine Migration)

Im Reiter „Kundenwissen“ der Firmenakte gibt es den neuen Block **„Dokumente in ACOS“**: alle
Dokumente (kind=document), die der ACOS-Abgleich für die Firma kennt, mit Titel, Datum und
Link „in ACOS ↗“. Kein Download, kein Inhalt im CRM – die Datei bleibt in ACOS. Die Suche im
Reiter findet die Dokumente über den Titel (auch per Wortwurzel, „gestundet“ → „Stundungsantrag“).
Ausgeblendet werden in ACOS entfernte Dokumente und alles, was kein Dokument ist. Der
ACOS-Abgleich vermerkt bei Dokumenten „Datei bleibt in ACOS – im Kundenwissen als Verweis“.

Link: Liefert ACOS einen eigenen Link, gilt der. Sonst `https://acos.alchimedus.pro/clients/{client_id}`
(Muster bestätigt am Mandanten M-10). Abweichend einstellbar in `config.json`:
`"acos": {"dokument_link": "…{client_id}…{id}…"}`.

✅ live seit 03.11.2026 (crm_core.py `8a8a89fc…`, acos_sync.py `a200faf7…`). Aufgesetzt auf den
Umbau-Stand (siehe nächster Abschnitt), ausgeliefert aus `~/crm-umbau`.

Getestet gegen `crm_test` mit Migrationen 002–023 und dem Live-Code: `test_kundenwissen_acos.py` 11/11 grün,
`smoke_test.py` 80 grün, 4 rot – dieselben 4 wie beim unveränderten Live-Code (der Smoke-Test kennt den
Umbau noch nicht), Oberfläche ohne JavaScript-Fehler.

```bash
# [Mac]
cd ~/crm-umbau
scp crm_core.py acos_sync.py root@46.225.13.130:/tmp/

# [Server] Prüfen
cd /opt/crm && sha1sum crm_core.py acos_sync.py
#   47185719f979ebfbcb48502f818626febf5b295e  crm_core.py   (live, Umbau 13)
#   9d4fd8e5eb1b439bcc3730070c3afe1a69c1d66a  acos_sync.py
cd /tmp && sha1sum crm_core.py acos_sync.py
#   8a8a89fc387ee243a8ab2e42e38d2eb5ac1c61f3  crm_core.py
#   a200faf795b32a26e83a3aee833edd722145812a  acos_sync.py

# [Server] Sichern, einspielen, neu starten
mkdir -p /root/crm-code-vor-acos-dokumente && cp -p /opt/crm/crm_core.py /opt/crm/acos_sync.py /root/crm-code-vor-acos-dokumente/
cp /tmp/crm_core.py /tmp/acos_sync.py /opt/crm/ && chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/acos_sync.py
rm /tmp/crm_core.py /tmp/acos_sync.py
systemctl restart crm && sleep 3 && systemctl is-active crm
```

Rückweg: `cp /root/crm-code-vor-acos-dokumente/* /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py && systemctl restart crm`.

## Repository auf Live-Stand gebracht (03.11.2026)

Bis heute fehlte im Repository der Umbau vom 31.10.: Er wurde in `~/crm-umbau` entwickelt
(Git-Klon mit dem Server als Gegenstelle) und von dort ausgeliefert. Das Repository hätte
ihn bei der nächsten Auslieferung überschrieben. Jetzt übernommen, abgeglichen per Prüfsumme
gegen `/opt/crm` am 03.11.2026 um 16:37:

- Umbau 1: Hinweis-Banner für die Testinstanz, Titel CRM · Digitale Konzepte
- Umbau 2/2a: Beziehung je Unternehmen (Mandant, Netzwerk, Lieferant, Eigenes Unternehmen) – Migration 013
- Umbau 3: Beteiligte (Netzwerk-Unternehmen je Mandant mit Rolle) – Migration 014
- Umbau 4: Verträge bei Lieferanten mit Kündigungstermin – Migration 015
- Umbau 5: Aufgaben ohne Projekt, Herkunft je Aufgabe – Migration 016
- Umbau 6: Sammelprojekte ohne Wert aufgelöst – Migration 017
- Umbau 7: Projektphasen (Anbahnung, Angebot raus, Läuft, Abgeschlossen, Verloren) – Migration 018
- Umbau 8: Honorarart, Honorar, Verlustgrund, Lexware-Nr. je Projekt – Migration 019
- Umbau 9: Mail-Review mit Liste und Detail, Status Offen/Später/Erledigt – Migration 020
- Umbau 10: Mail-Review erkennt Fristen, Zeeg-Terminbuchungen, mehrere Unternehmen – Migration 021
- Umbau 11/11a: Heute als Startseite, Google-Kalender per iCal nur lesend (`kalender.py`) – Migration 022
- Umbau 12: Neue Dateien in Kundenordnern als Journal-Eintrag Dokument – Migration 023
- Umbau 13: Recherche über alle Bereiche als eigener Menüpunkt
- Umbau 14: Mail-Abruf merkt sich das Postfach, Nachholen von Hand (`mail_poller.py --nachholen TAGE`)

Dateien: `CPX12-Postgres/` crm_core.py, crm_serve.py, mail_poller.py, wissen_sync.py, acos_sync.py,
kalender.py (neu); Dienste crm.service und crm-mailpoll.service auf den echten Pfad `/opt/crm`
zurückgestellt; neu im Repository crm-backup.service/.timer (Datenbank-Backup 22:30, Skript
`/usr/local/bin/crm-backup.sh`) und crm-umbau.service (Testinstanz, Port 8081, `crm_test`).
`Migration-Postgres/` migration_013 bis migration_023 (Namen angeglichen, Inhalt unverändert),
smoke_test.py an den Umbau angepasst (Aufgabe ohne Projekt erlaubt, Phasen statt alter Status).
config.json: Abrufintervall 5 Minuten wie auf dem Server.

Nicht übernommen: die alten Markdown-Skripte, die in `/opt/crm` noch liegen (`crm_server.py`,
`crm_add.py`, `task_cli.py` usw.). Der laufende Dienst nutzt sie nicht.

Getestet in der Sandbox gegen `crm_test` mit Migrationen 002–023: `smoke_test.py` 84/84 grün,
`test_kundenwissen_acos.py` 11/11 grün.

**Ab jetzt gilt:** Entwickelt und ausgeliefert wird aus `crm-code-upload`. `~/crm-umbau` ist Archiv.

## Backup-Skript ins Repository (03.11.2026)

`CPX12-Postgres/crm-backup.sh` ist die Kopie von `/usr/local/bin/crm-backup.sh` (sha1 `2523ce7f…`),
gestartet von `crm-backup.timer` täglich 22:30. Ablauf: `pg_dump` der Datenbank `crm`, Lesbarkeit
prüfen, mit GPG (AES256) verschlüsseln, in die Nextcloud laden – je Wochentag eine Datei, die sich
wöchentlich überschreibt, am Monatsersten zusätzlich eine Monatsdatei. Lokal unverschlüsselt
14 Tage unter `/var/backups/crm`.

Im Skript stehen keine Zugangsdaten. Die liegen nur auf dem Server und gehören nicht ins Repository:
- `/root/.crm-backup.pass` – Passphrase für die Verschlüsselung
- `/root/.crm-backup.netrc` – Nextcloud-Zugang

**Wichtig:** Ohne die Passphrase sind die Sicherungen in der Nextcloud wertlos. Fällt der Server
aus, ist sie mit ihm weg. Sie muss deshalb zusätzlich außerhalb des Servers liegen, z. B. im
Passwortmanager.

Ausrollen ist nicht nötig, das Skript läuft unverändert.

## 2026-11-16 – Unternehmen umbenennen (live 2026-11-16)

Stammdaten → Unternehmen → Bearbeiten: Das Feld „Firma“ ist jetzt änderbar. Vor dem Speichern
kommt eine Rückfrage mit altem und neuem Namen und dem Hinweis, den Kundenordner in der Nextcloud
von Hand mitzuziehen (wissen_sync und acos_sync finden ihn über den Namen). Ein Name, den schon ein
anderes Unternehmen trägt, wird abgelehnt (Hinweis: zusammenführen). Das Sammelprojekt
„<Name> – laufende Betreuung“ wird mitumbenannt, Audit-Log wie gewohnt. Keine Migration.

Dateien: `crm_core.py`, `crm_serve.py` (PUT /api/contacts gibt Fehler als 400 statt 500 zurück),
neu `Migration-Postgres/test_firma_umbenennen.py`.

Sandbox `crm_test`, Migrationen 002–024: `smoke_test.py` 84/84, `test_firma_umbenennen.py` 11/11,
Dialog per Playwright ohne JavaScript-Fehler.

Prüfsummen: vorher crm_core.py `ef604c8efb9dd9352067aad0019e379876e95dd1`, crm_serve.py
`26cc8d43877c1bad468d1739e90505d5060e5200`; nachher crm_core.py
`abff7a01e62dee3718ff7f4a59f262d7ee41e5ff` (Stand nach Punkt 4), crm_serve.py `4b60015a8a0782e66bd31a9061c8e0ea99fe2900` (Stand nach Punkt 4).

## 2026-11-16 – Suchfeld bekommt keinen Benutzernamen mehr (live 2026-11-16)

Beim Klick in die Unternehmensliste trug der Browser (Safari bzw. Passwort-Manager) den
Benutzernamen ins Suchfeld ein. Ursache: Die Seite enthält in den Einstellungen das Feld
„Bisheriges Passwort“ ohne zugehöriges Benutzerfeld. Der Browser nimmt dann das nächstbeste
Textfeld, die Suche. Abhilfe: verstecktes Benutzerfeld (`set-pw-user`, autocomplete=username)
bei „Passwort ändern“, alle Suchfelder mit `type=search`, `autocomplete=off` und Ignorier-Merkmalen
für 1Password, LastPass und Bitwarden (auch nachträglich erzeugte, über `focusin`). Felder mit
Vorschlagsliste (`list=`) bleiben unberührt. Datei: `crm_core.py`.

Klick auf eine Zeile in Unternehmen öffnet die Akte überall in der Zeile (Chromium: 24 von 24
Klickpunkten links, Mitte, rechts). In Safari noch am Live-System nachprüfen.

## 2026-11-16 – Mail-Review: Aktionen immer an derselben Stelle (live 2026-11-16)

Die Aktionsleiste unter jeder Mail hat jetzt feste Plätze: links „Nicht ins CRM“ und
„Zuordnen / ändern“, rechts „Später“ und „Übernehmen“. Kein Knopf verschwindet oder wandert mehr.
Passt eine Aktion nicht, ist sie ausgegraut, der Grund steht im Tooltip: Übernehmen bei
unbekanntem Absender, Zuordnen bei gesendeten Mails, Später bei schon Zurückgestelltem.
„Übernehmen“ führt immer den Vorschlag aus (zuordnen, Lead anlegen oder beim Newsletter
nicht ins CRM). Die bisher verstreuten Zuordnen-Links und -Knöpfe in den Blöcken darüber sind
entfallen. Die Zeile „Künftig gar nicht mehr zeigen“ steht immer da. Datei: `crm_core.py`.

Test: sechs Fälle (bekannt, Lead, Newsletter, unbekannt, gesendet, zurückgestellt) mit
fiktiven Daten, alle vier Knöpfe in jedem Fall auf denselben Positionen, keine JavaScript-Fehler.

## 2026-11-16 – Schnellauswahl in Unternehmen und Kontakte (live 2026-11-16)

Stammdaten → Unternehmen und → Kontakte bekommen über der Tabelle:
- **Sichten:** gespeicherte Filterkombinationen als Knöpfe, für alle Nutzer gemeinsam
  (neue Tabelle `gespeicherte_sichten`, **Migration 025**). „+ Sicht speichern“ fragt nach dem
  Namen, gleicher Name fragt nach Überschreiben, × löscht nach Rückfrage. Zwei Startsichten:
  „Aktive Mandanten“, „Lange kein Kontakt“.
- **Suchfeld** wie bisher, wirkt mit den Chips zusammen.
- **Filter-Chips mit Trefferzahl.** Unternehmen: Beziehung, Status, Branche, Ort (aus der
  Adresse, ohne PLZ), Letzter Kontakt (bis 30 / 31–90 / über 90 Tage / noch nie), Merkmale
  (In ACOS, Offene Aufgabe). Kontakte: Beziehung (des Unternehmens), Status, Kampagne,
  Unternehmen, Letzter Kontakt. In einer Gruppe „oder“, zwischen Gruppen „und“, Merkmale „und“.
  Lange Gruppen zeigen die 10 häufigsten Werte und „+ N weitere“.
- **A–Z-Leiste:** Unternehmen nach Name, Kontakte nach Nachname; Umlaute beim Grundbuchstaben,
  Ziffern unter #. Buchstaben ohne Treffer ausgegraut.
- **Trefferzahl** „x von y“ und „Alle Filter lösen“. Filter werden nicht gemerkt.
Die bisherigen Auswahllisten (Beziehung, Status, Kampagne) entfallen, die Chips ersetzen sie.

Dateien: `crm_core.py`, `crm_serve.py` (`GET/POST /api/sichten`, `DELETE /api/sichten/<id>`),
neu `Migration-Postgres/migration_025_sichten.sql` (sha1 `07cd351ee5593bdff54fa832308c7e6b8a220d9a`, idempotent),
neu `Migration-Postgres/test_schnellauswahl.py`.

Test: Sandbox `crm_test`, Migrationen 002–025 (025 zweimal eingespielt, ohne Fehler):
`smoke_test.py` 84/84, `test_firma_umbenennen.py` 11/11, `test_schnellauswahl.py` 19/19.
Browser mit 53 fiktiven Unternehmen und 50 Kontakten: Trefferzahlen auf den Chips stimmen mit
der Tabelle überein, A–Z, Sicht anwenden und speichern, Zeilenklick öffnet weiter die Akte,
Handy-Breite geprüft, keine JavaScript-Fehler.

**Live 2026-11-16:** Release laut `DEPLOY-026-release-2026-11-16.md` ausgeliefert. Prüfsummen auf
dem Server bestätigt, Migration 025 eingespielt, Dienst läuft, Ronald hat Unternehmen, Bearbeiten
und Mail-Review im Browser durchgeklickt. Sicherung unter `/root/crm-code-vor-release-1116/`.

## 2026-11-17 – Aufgabe als Auftrag an ACOS, Webseite am Unternehmen (live 2026-11-17)

- **Aufgabe → ACOS:** Im Aufgabenfenster bei einem mit ACOS verknüpften Unternehmen der Schalter
  „Von ACOS bearbeiten lassen“ (Artefakt, Thema ohne Namen, Hinweise, Prüfung des Kundenordners,
  fehlende Dateien gehen mit). „Speichern und übergeben“ legt `AUF-JJJJ-NNNN.json` in
  `/Arbeitsdateien/Aufträge/offen/` ab. Claude arbeitet den Auftrag am Mac ab
  (`AUFTRAEGE-ABARBEITEN.md`), Rückfrage oder Fehler als neue Datei in `ergebnis/`.
- **Rückweg** über den ACOS-Abgleich: Artefakt mit Auftrags-ID im Titel → `<Kunde>/ACOS/Wissen` →
  Kundenwissen, Auftrag „Ergebnis da“, Aufgabe „Bearbeitet“, Journal. Abschließen nur mit
  „Geprüft, Aufgabe abschließen“ (zweiter Journal-Eintrag), alternativ „Nachbessern lassen“.
- Der laufende Auftrag steuert den Aufgabenstatus (Statusfeld und Abhaken gesperrt), Etikett
  „ACOS“ in Aufgabenliste, Heute und Akte, Verlauf im ACOS-Bereich statt Einträgen in den Notizen.
- **Webseite am Unternehmen** (Akte → Stammdaten), geht mit dem Abgleich als `company.website` an ACOS.
- Menüwechsel lädt die Ansicht neu, wenn seither etwas geändert wurde oder sie älter als eine
  Minute ist (nicht bei offenem Formular).

Dateien: `crm_core.py`, `crm_serve.py`, `acos_sync.py`, neu `acos_auftraege.py`,
neu `Migration-Postgres/migration_026_acos_auftraege.sql`, neu `Migration-Postgres/migration_027_webseite_auftragsverlauf.sql`,
neu `Migration-Postgres/test_acos_auftraege.py`, `AUFTRAEGE-ABARBEITEN.md`,
`DEPLOY-027-acos-auftraege.md`, `DEPLOY-028-acos-aufgabenfenster.md`.

Test: Sandbox `crm_test`, Migrationen 002–027: `smoke_test.py` 84/84, `test_acos_auftraege.py` 43/43,
übrige Einzeltests grün, Browser ohne JavaScript-Fehler.

**Live 2026-11-17:** Migration 026 und 027 eingespielt, Prüfsummen bestätigt. Nachweis am
Testmandanten M-13: AUF-2026-0001 Fehler (Auftragsordner fehlte), AUF-2026-0002 Rückfrage
(Website-Profil fehlt), AUF-2026-0003 als Folgeauftrag beantwortet, Artefakt in ACOS, Rückweg
über den Abgleich durchgelaufen. Sicherungen unter `/root/crm-code-vor-auftraege/` und
`/root/crm-code-vor-aufgabenfenster/`.
Offen: „Bei ACOS nachsehen“ hat einmal keinen Abgleich ausgelöst (Lauf von Hand gestartet).
