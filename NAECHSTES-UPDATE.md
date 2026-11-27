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

## 2026-11-17 – Alle ACOS-Skills im Aufgabenfenster (live 2026-11-17, Release 029)

Skill-Liste kommt aus ACOS und wird bei jedem ACOS-Abgleich aktualisiert (`system_einstellungen.acos_skills`),
Voraussetzungen des Skills werden vorab in ACOS geprüft, „Zuletzt in ACOS nachgesehen“ im Fenster.
Siehe `DEPLOY-029-acos-skills.md`. Sandbox: `test_acos_auftraege.py` 54/54, `smoke_test.py` 84/84.

Nachtrag (Release 030, keine Migration): Status eines übergebenen Auftrags heißt „wartet auf Bearbeitung“,
Fortschrittsschritt „in Bearbeitung“. Abarbeitung der Aufträge am Mac jetzt als geplante Aufgabe
„ACOS-Aufträge aus dem CRM abarbeiten“ (stündlich 7:35–17:35, Rückfrage bei kostenpflichtiger Recherche).
crm_core.py `fe1ecbe9eaca1c010c82ee07519359d69d9c023b`, acos_auftraege.py `a75127f673aac172f345e2b4e3b39849c6a26a6d`.

## 2026-11-17 – Aufträge über ACOS statt Nextcloud, reine Serverlösung (Release 031, Migration 028)

Das CRM legt den Auftrag als Wissensobjekt `crm_auftrag` in der ACOS-Kundenakte an, Rückfragen kommen als
`crm_rueckfrage`. Beide gehen nicht ins Kundenwissen. Abarbeitung durch eine geplante Aufgabe in der Cloud,
der Mac muss nicht laufen; der Ordner `/Arbeitsdateien/Aufträge` wird nicht mehr gebraucht.
Siehe `DEPLOY-031-auftrag-in-acos.md`, `AUFTRAEGE-ABARBEITEN.md`. Sandbox: `test_acos_auftraege.py` 58/58, `smoke_test.py` 84/84.

**Live 2026-11-17, Nachweis 18.11.2026:** Migration 028 eingespielt, Übergabe über ACOS und Abarbeitung durch die
geplante Aufgabe „ACOS-Aufträge abarbeiten (Server)“ von Ronald getestet. Die geplante Aufgabe am Mac ist abgeschaltet.
Sicherung unter `/root/crm-code-vor-auftrag-acos/`.

## 2026-11-20 – Oberfläche „Heute“ und Stammdaten: Feinschliff (keine Migration, live 2026-11-20)

Vorlage: `CRM Heute - Feinschliff.dc.html` aus Claude Design (Nummern A1–A4, H2–H8, S1–S8 wie dort).
Farben und Dichte bleiben, Akzentfarbe aus den Einstellungen gilt weiter.

| Nr. | Was sich ändert |
|---|---|
| A1 | Titel und Navigation in einer Leiste. Rechts: Recherche-Suchfeld (Taste „/“), Stand mit Aktualisieren, Nutzermenü (Kürzel) mit Einstellungen und Abmelden. Neustart, „In neuem Tab öffnen“ und Stoppen nur für Admins im Nutzermenü; `/api/server/restart` und `/api/server/shutdown` antworten Nicht-Admins mit 403. Admin = Rolle `admin`; gibt es keinen Admin, gilt wie bei den Systemeinstellungen jeder Nutzer als Admin. Alle übrigen Bereiche unter „Mehr“. |
| A2 | Keine Emojis in Navigation, Kartenköpfen, Überschriften, Archiv und Dialogtiteln. |
| A3 | Eine Badge-Sprache: getönt statt weißer Schrift auf voller Farbe, großer Anfangsbuchstabe. |
| A4 | Letzter Kontakt relativ („vor 8 Tagen“) mit Ampelpunkt (≤ 30 / ≤ 90 / > 90 Tage), Datum als Tooltip. |
| H2 | Lagezeile als klickbare Zahlen: überfällig (rot, vorn), Aufgaben heute, Termine offen mit nächstem, Mails zuordnen. |
| H3 | „＋ Aufgabe“ blau rechts außen; Journal und Unternehmen als Nebenaktionen. |
| H4 | Briefing unter der Begrüßung: Hinweise nebeneinander, Firmennamen als Link zur Akte, Projektfristen und Ruhende in einer Fußzeile. „Fällig“ und „Überfällig“ entfallen dort. Auf/zu wird weiter gemerkt. |
| H5 | Zu erledigen: Zahl je Gruppe, Überfällige mit rotem Rand und „seit 4 Tagen“, „Alle auf heute“, je Aufgabe „→ Morgen“ (nutzt das vorhandene Aufgaben-Update), größere Klickfläche der Checkbox, „Diese Woche“ eingeklappt. |
| H6 | Mail-Review-Karte: Betreff eigene Zeile, Vorschlag als Etiketten, „Übernehmen“ nur bei eindeutigen Mails blau, sonst „Prüfen“, „Später“ als Textlink, Zeit relativ. |
| H7 | Tagesbilanz als eine Karte: links Erledigtes und Journal mit Uhrzeit, rechts Tageszahlen und Tagesabschluss; Resümee und Briefing nach dem Abschluss aufklappbar. |
| H8 | Handy `/m`: Aufgaben abhaken (44 px), nächster Termin oben, Kachel „Mails offen“. |
| S1 | Kennzahlen sind Filter (Alle, Mandanten, Leads, Netzwerk); Überschrift „Unternehmen“. |
| S2 | Filter in einer Zeile: Ausklapper je Gruppe, aktive Filter als Chip mit ×, Sichten im Ausklapper, A–Z und Sortierung (Name / Letzter Kontakt) in der Zählzeile. Filterlogik und gespeicherte Sichten unverändert. |
| S3 | Tabelle mit A3/A4, fehlender nächster Schritt als „festlegen“ (öffnet die Akte mit dem Eingabefeld), Branche ausgeblendet bei offener Akte. |
| S4 | Akte angedockt ab 1100 px Breite: kein Abdunkler, Liste bleibt klickbar, aktive Zeile markiert, ↑/↓ wechselt, Esc schließt. Faktenzeile unter dem Titel, „Aufgabe“ als Hauptaktion. |
| S5 | Akte-Übersicht: offene Aufgaben (überfällig rot), letzte Aktivitäten, Ansprechpartner, Beteiligte, Verträge, Stammdaten als eingeklappte Zeile. |
| S6 | „Personen“ statt „Kontakte“, als Reiter direkt neben „Unternehmen“ (interner Schlüssel `persons` bleibt, Favoriten und Sichten gültig). Dubletten als Hinweiszeile nur bei Verdacht. Auf dem Handy heißt der Bereich weiter „Kontakte“. |
| S7 | Personenliste: Erreichbarkeit als drei Symbolknöpfe (Telefon, Mail, LinkedIn; blass, wenn leer), Kampagne als Etikett am Namen, Sortierung nach Nachname. „＋ Person“ fragt nach dem Unternehmen und öffnet dessen Akte. |
| S8 | Handy „Kontakte“: Anruf-Knopf je Karte, Kontaktstufe, nächster Schritt hervorgehoben, feste Aktionen Zentrale/Notiz/Karte (Notiz geht ins Journal), Personen mit Knöpfen, Umschalter Unternehmen/Personen. |

Getestet gegen `crm_test` mit Migrationen 002–028 und fiktiven Testdaten: `smoke_test.py` 84/84,
`test_acos_auftraege.py` 58/58, `test_acos_verweis.py` 14/14, `test_acos_verweis_ablage.py` 14/14,
`test_kundenwissen_acos.py` 11/11, `test_firma_umbenennen.py` 11/11, `test_schnellauswahl.py` 19/19,
neu `test_oberflaeche_feinschliff.py` 21/21 (u. a. Restart/Stop als Nicht-Admin abgelehnt, Verschieben,
Abhaken). Browser 1280 und 390 px: 29 Klickprüfungen grün (Zeilenklick an 24 Punkten, ↑/↓, Esc,
Filter, Sortierung, /m abhaken), keine JavaScript-Fehler.

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
scp CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py root@46.225.13.130:/tmp/

# [Server] Prüfen
cd /opt/crm && sha1sum crm_core.py crm_serve.py
#   fe1ecbe9eaca1c010c82ee07519359d69d9c023b  crm_core.py   (live, 18.11.)
#   d29fe0720c34c90b5844e10c6a31b3365bcf72e4  crm_serve.py
cd /tmp && sha1sum crm_core.py crm_serve.py
#   73e15005bc13e064a137c79caf6b5d409de48869  crm_core.py
#   6c19f8979e740b6d8c74ea9fc54919c230354642  crm_serve.py

# [Server] Rollen ansehen (wer ist Admin?)
sudo -u crmapp psql -d crm -c "SELECT username, rolle, aktiv FROM users ORDER BY username"

# [Server] Sichern, einspielen, neu starten
mkdir -p /root/crm-code-vor-feinschliff && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /root/crm-code-vor-feinschliff/
cp /tmp/crm_core.py /tmp/crm_serve.py /opt/crm/ && chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py
rm /tmp/crm_core.py /tmp/crm_serve.py
systemctl restart crm && sleep 3 && systemctl is-active crm
```

Rückweg: `cp /root/crm-code-vor-feinschliff/* /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py && systemctl restart crm`.

## 2026-11-20 – ACOS-Aufträge automatisch: Takt, Meldungen, Übergabe beim Anlegen (Migration 029, live 2026-11-20)

Anlass: Der Weg Aufgabe → ACOS → Ergebnis war zeitlich nicht schlüssig. Rückfragen kamen erst mit dem Abgleich um 6:30 Uhr
oder nach „Bei ACOS nachsehen“.

| Punkt | Was sich ändert |
|---|---|
| 1 | Akte → „＋ Aufgabe“: Ist das Unternehmen mit ACOS verknüpft, gibt es „Von ACOS bearbeiten lassen“ mit Skill, Thema (ohne Namen), Hinweisen, Voraussetzungen und Vorprüfung des Kundenordners. Der Knopf heißt dann „Anlegen und an ACOS übergeben“. Klappt die Übergabe nicht, bleibt die Aufgabe angelegt und lässt sich im Aufgabenfenster erneut übergeben. Im Dialog „＋ Aufgabe“ auf Heute gab es die Box schon. |
| 2 | `crm-acos.timer` läuft jede Minute und ruft `acos_sync.py takt` auf. Das prüft, ob etwas fällig ist. **Auftragsprüfung:** nur wenn ein Auftrag bei ACOS liegt (Status „übergeben“) und nur für diese Mandanten. Takt in den Einstellungen: 2/5/10/15/30 Minuten oder aus, Standard 5. **Voller Abgleich:** täglich zur eingestellten Uhrzeit (Standard 06:30) oder stündlich. Schnelle Prüfungen werden zwei Tage aufbewahrt und erscheinen nicht in der Liste der Abgleiche. Dort steht stattdessen „Zuletzt geprüft“. |
| 3 | „Bei ACOS nachsehen“ entfällt. Das Aufgabenfenster zeigt „Das CRM prüft automatisch alle N Minuten“. Neue Verlaufsart `in_acos` („Ergebnis liegt in ACOS“) im selben Lauf vor „In der Nextcloud abgelegt“. Rückfrage, Ergebnis in ACOS und „abgelegt“ erscheinen als Meldung oben in „Im Blick“ und einmal je Sitzung als Einblendung unten rechts. Die Seite fragt `/api/acos/meldungen` jede Minute ab (nur Datenbank, kein ACOS-Abruf). Gesehen: Klick auf „Gesehen“ oder Öffnen der Aufgabe. |

Migration 029: Spalte `acos_auftrag_verlauf.gesehen_am`. Bestehende Einträge gelten als gesehen.

Getestet gegen `crm_test` mit Migrationen 002–029 und fiktiven Daten:

| Prüfung | Ergebnis |
|---|---|
| `smoke_test.py` | grün |
| `test_acos_auftraege.py` | 61/61 (+3: Verlauf in_acos vor bearbeitet, Meldungen, Takt-Text) |
| neu `test_acos_automatik.py` | 33/33 (Einstellungen, Fälligkeit, takt(), Meldungen, Aufräumen) |
| `test_acos_verweis.py` | 14/14 |
| `test_acos_verweis_ablage.py` | 14/14 |
| `test_kundenwissen_acos.py` | 11/11 |
| `test_firma_umbenennen.py` | 11/11 |
| `test_schnellauswahl.py` | 19/19 |
| `test_oberflaeche_feinschliff.py` | 21/21 |
| Browser | 29 Klickprüfungen grün, ACOS-Ablauf durchgeklickt, keine JavaScript-Fehler |

Prüfsummen neu:

| Datei | sha1 |
|---|---|
| crm_core.py | 4795d8be335b6ae29f170b6f40a4ec802968ac1d |
| crm_serve.py | e86d8bf14fc77d0f115fcd278d64acabf064ef04 |
| acos_sync.py | e3aaa985ecf8b96684c8e5b4f60b704ec08ba4fd |
| acos_auftraege.py | d3c0d175b1fc17f684dadd7c5583af220c8c8910 |
| crm-acos.timer | ff00a16763d9e36b3472acf544253de44eac57c9 |
| crm-acos.service | 33a80b4bfe27c639077def850e6d0fd7a7bcee51 |
| migration_029_acos_meldungen.sql | 1ea3c2a5c66325482fe90dbb2f8eb610a323f07a |

Live vorher (Stand 20.11.):

| Datei | sha1 |
|---|---|
| crm_core.py | 73e15005… |
| crm_serve.py | 6c19f897… |
| acos_sync.py | 77b04b7c… |
| acos_auftraege.py | 1be9e458… |

Sicherung: `/root/crm-code-vor-acos-takt/`.
Rückweg: Dateien von dort zurückkopieren, `daemon-reload`, `systemctl restart crm crm-acos.timer`. Die Spalte aus 029 stört den alten Code nicht.

Danach: In der geplanten Aufgabe „ACOS-Aufträge abarbeiten (Server)“ den Schlusssatz „Bei ACOS nachsehen“ ersetzen.

**Live 2026-11-20:** Migration 029 eingespielt, Timer im Minutentakt läuft fehlerfrei, Prüfsummen bestätigt.

## 2026-11-23 – Einstellungen kompakter (keine Migration, nur crm_core.py, live 2026-11-23)

ACOS-Abgleich, Tagesabschluss an ACOS und Ignorierte Absender stehen nebeneinander statt über die volle Breite; „Aufgaben und KI“
steht unter „Passwort ändern“, damit oben drei Spalten aufgehen. Ignorierte Absender: Liste eingeklappt („Liste anzeigen (N)“),
Hinzufügen bleibt sichtbar. ACOS-Karte: kürzere Texte, Abgleichberichte eingeklappt. Schmale Fenster und Handy: untereinander wie bisher.
Sandbox: alle Tests grün (smoke, 61, 33, 14, 14, 11, 11, 19, 21), keine JavaScript-Fehler.
crm_core.py: live vorher 4795d8be335b6ae29f170b6f40a4ec802968ac1d, neu 23f126dfb77888aea711dbf338a6eb7afc03d77f.
Sicherung: /root/crm-code-vor-einstellungen/. Rückweg: Datei zurückkopieren, chown, systemctl restart crm.

## 2026-11-23 – Fokusband auf „Heute“ mit ACOS-Streifen (Migration 030, live 2026-11-23)

Unter der Begrüßung ein Band:
- **Tagesring:** heute erledigt / (erledigt + überfällig + heute fällig).
- **Der eine Schritt heute:** älteste überfällige Aufgabe zuerst, dann die heute fälligen nach Projektwert, dann die Woche; Aufgaben, die bei ACOS liegen, zählen nicht. Bis zu 5 Vorschläge, „Nächster Vorschlag ›“ blättert. Dazu Firma, nächster Termin mit dieser Firma (14 Tage), Projektwert, Grund. Knöpfe Öffnen und Erledigt.
- **Pipeline offen:** Summe der Projekte in Anbahnung und Angebot (Läuft zählt nicht), Abstand zur Vorwoche, Kurve über 8 Wochen. Klick öffnet Projekte. Der Tageswert wird beim Laden von „Heute“ in `pipeline_stand` geschrieben (Migration 030); Vergleich und Kurve füllen sich ab dem Einspielen.
- **ACOS-Streifen** unter dem Band, nur solange ein Auftrag offen ist (übergeben, Rückfrage, abgelegt, Fehler): Rückfrage mit Frage und „Beantworten“, abgelegt mit „Prüfen“, in Arbeit mit „seit …“. Aktualisiert sich jede Minute (`/api/heute/acos-streifen`, nur Datenbank). Die ACOS-Meldungen stehen nicht mehr in „Im Blick“; die Einblendung unten rechts bleibt.

Sandbox (crm_test, Migrationen 002–030, fiktive Daten): smoke grün, neu `test_fokusband.py` 22/22, übrige Tests unverändert grün
(61, 33, 14, 14, 11, 11, 19, 21), Browser 29/29 Klickprüfungen, Fokusband durchgeklickt, keine JavaScript-Fehler.

| Datei | live vorher | neu |
|---|---|---|
| crm_core.py | 23f126df… | 2121e938d442a074996210dd5fa2a78baf86a3ac |
| crm_serve.py | e86d8bf1… | 519325659d90cd7b2f0c4c5b68bbf42f51e6a795 |
| migration_030_pipeline_stand.sql | – | 3a6e22d58c27cfa991d4d8409fcf747c0f39c947 |

Sicherung: `/root/crm-code-vor-fokusband/`. Rückweg: beide Dateien zurück, chown, `systemctl restart crm`; die Tabelle aus 030 stört den alten Code nicht.

**Live 2026-11-23:** Migration 030 eingespielt, Code eingespielt, von Ronald bestätigt.

## 2026-11-25 – Geplant: ACOS-Abgleich erkennt Archivierung und direkt hochgeladene Dateien (umgesetzt im Release „ACOS führt“, s. unten)

Anlass: Mandant M-15, 24./25.11.2026. Eine Gesprächsunterlage wurde aus dem Chat direkt in ACOS abgelegt, nicht über den CRM-Auftrag.

1. **Archivierte Wissensobjekte:** Der Abgleich hat einen Bericht (`kind: report`, Quelle `ai:saveback`) als .md unter `ACOS/Wissen` abgelegt. Danach wurde der Bericht in ACOS archiviert und durch eine neue Fassung ersetzt. Die alte .md bleibt in der Nextcloud stehen und wird nicht als überholt erkannt.
   Gewünscht: Der Abgleich prüft, ob bereits abgelegte Wissensobjekte in ACOS archiviert sind, und kennzeichnet die Datei (z. B. Umbenennen mit Präfix `ARCHIVIERT_` oder Verschieben nach `ACOS/Wissen/archiviert/`; nichts löschen). Neue Versionen desselben Objekts ebenfalls nachziehen.
2. **Direkt in ACOS hochgeladene Dateien:** Dokumente (`kind: document`, Quelle `mcp`) ohne Nextcloud-Herkunft in der Beschreibung zeigt das CRM nur als „nur in ACOS“; sie kommen nicht in den Kundenordner.
   Gewünscht: Diese Dateien beim Abgleich in den Kundenordner holen (z. B. `ACOS/Dokumente/`), ohne bestehende Dateien zu überschreiben, und danach als vorhanden erkennen, damit kein Duplikat zurück nach ACOS geht.

Zu klären vor dem Bau: Ablageort im Kundenordner, ob Archiviertes umbenannt oder verschoben wird, ob die ACOS-Schnittstelle archivierte Objekte und den Dateiinhalt liefert. Fachlich freigegeben von Ronald am 25.11.2026.

## 2026-11-25 – Geplant: ACOS-Auftrag zurückziehen, Doppelklick-Schutz, Altlasten 0009/0012/0014 (umgesetzt im Release „ACOS führt“, s. unten)

Anlass: Auf „Heute“ stehen drei Rückfragen (AUF-2026-0009, -0012, -0014), die fachlich überholt sind. 0012/0014 gehören zu M-15:
die Gesprächsunterlage ist inzwischen direkt in ACOS entstanden. 0009 gehört zum Test-Mandanten (seit 18.11. offen).
In ACOS liegen die drei Rückfragen unbeantwortet vor; ACOS selbst kennt dafür keinen Status.

1. **Sofortbereinigung (mit dem Release, per SQL auf dem Server):** 0009, 0012, 0014 auf `erledigt` setzen, Verlauf
   „Auftrag zurückgezogen (überholt)“, Meldungen als gesehen. In ACOS nichts löschen.
2. **„Auftrag zurückziehen“** im Aufgabenfenster und im ACOS-Streifen auf „Heute“ für Aufträge in „übergeben“, „Rückfrage“
   und „Fehler“: Auftrag wird abgeschlossen (Verlauf „zurückgezogen“, Journal), die Aufgabe ist danach wieder frei
   (bisher sperrt ein offener Auftrag den Aufgabenstatus, Ausweg war nur Beantworten → Folgeauftrag).
   Zu klären: eigener Status `zurueckgezogen` (Migration, CHECK erweitern) oder `erledigt` mit Verlaufsart; ob im
   ACOS-Auftragsobjekt ein Vermerk landen soll, damit die geplante Aufgabe ihn sicher überspringt (Lesen genügt heute:
   eine vorhandene Rückfrage zählt dort schon als erledigt).
3. **Doppelklick-Schutz beim Übergeben:** Am 23.11. entstanden 0012 und 0013 im Abstand von 2 Sekunden; alle Kundendateien
   liegen dadurch doppelt in der ACOS-Akte von M-15. Gewünscht: Knopf sofort sperren und serverseitig ablehnen, wenn für
   dieselbe Aufgabe in den letzten 60 Sekunden schon ein Auftrag angelegt wurde. Die doppelten Dateien räumt Ronald in ACOS auf.

Zum Nachsehen dabei: Die Rückfrage zu 0013, auf die mit „A)“ geantwortet wurde (→ 0014), ist in ACOS nicht mehr vorhanden;
0012/0014 wurden erst am 25.11. 12:21 bearbeitet statt am 23.11. abends. Ursache offen (Läufe der geplanten Aufgabe prüfen).
Fachlich freigegeben von Ronald am 25.11.2026.

**Härtung (Vorgabe Ronald, 25.11.2026): ACOS führt.** Was in ACOS gelöscht oder archiviert ist, darf im CRM nicht stehen bleiben –
weder als offener Auftrag noch als Rückfrage, Meldung, Kundenwissen-Eintrag oder Verweis. Der Abgleich gleicht dafür
Aufträge, Rückfragen und Wissensobjekte aktiv gegen ACOS ab (nicht nur „neu dazu“). Betrifft auch den Abschnitt
„ACOS-Abgleich erkennt Archivierung“ oben. Nextcloud-Kopien (entschieden 25.11.2026): nicht löschen, sondern nach
`<Kunde>/ACOS/Wissen/archiviert/` verschieben; die Regel „Nextcloud nur lesen oder neu anlegen“ bekommt dafür diese eine Ausnahme.

**Rückfrage beantworten als Auswahl (Wunsch Ronald, 25.11.2026):** Statt Freitext eine Option je Antwort (Radio, eine Wahl),
unter der gewählten Option ein Ergänzungsfeld (optional), dazu immer „Andere Antwort“ mit Pflicht-Freitext.
Quelle der Optionen: neues Feld `data.optionen` [{"key": "A", "text": "…"}] im ACOS-Objekt `crm_rueckfrage` (Prompt der geplanten
Aufgabe anpassen); für alte Rückfragen Erkennung von „A) … B) …“ im Fragetext. An ACOS geht der volle Text, nicht nur „A)“:
„Antwort auf Rückfrage <ID> (‚<Frage>‘): A) <Optionstext>. Ergänzung: …“ – damit die Antwort auch ohne die alte Rückfrage
zuzuordnen ist (Fall 0013/0014). Knopf „Auftrag zurückziehen“ steht in derselben Maske.

## 2026-11-25 – Release „ACOS führt“: Zurückziehen, Auswahl-Antwort, Doppelklick-Schutz, Archivierung (Migration 031, live 2026-11-25)

| Punkt | Umsetzung |
|---|---|
| Zurückziehen | Knopf „Auftrag zurückziehen“ im Aufgabenfenster (übergeben, Rückfrage; bei Fehler „Auftrag beenden“) und × im ACOS-Streifen auf „Heute“, jeweils mit Rückfrage. Status `zurueckgezogen` (Migration 031), Aufgabe wieder „Offen“ und frei, Verlauf und Journal. In ACOS wird nichts gelöscht: liegt der Auftrag noch unbearbeitet dort, legt das CRM ein Objekt „Zurückgezogen <ID>“ (Art crm_rueckfrage, status zurueckgezogen) an – die geplante Aufgabe überspringt jeden Auftrag mit so einem Objekt. |
| Doppelklick | Speichern im Aufgabenfenster und „Anlegen“ in der Akte sperren sich bis zur Antwort (auch Doppel-Enter). Serverseitig je Aufgabe nur eine Übergabe gleichzeitig; eine spätere zweite scheitert an „liegt noch bei ACOS“. (Die 60-Sekunden-Regel aus der Planung ist damit nicht nötig.) |
| Antwort als Auswahl | Rückfrage mit Optionen: je Option ein Auswahlknopf, unter der gewählten ein Ergänzungsfeld, dazu „Andere Antwort“ (Text Pflicht). Optionen aus `data.optionen` des ACOS-Objekts (Spalte `rueckfrage_optionen`), sonst aus „A) … B) …“ im Fragetext. An ACOS geht der volle Wortlaut mit der Frage: „Antwort auf die Rückfrage zu <ID> (Frage: „…“): B) <Optionstext>. Ergänzung: …“. |
| ACOS führt: Aufträge | Bei jedem Abgleich (auch der Minutentakt): Auftragsobjekt in ACOS gelöscht/archiviert → Auftrag im CRM beendet, Aufgabe frei, Meldung „Auftrag beendet“. Rückfrage-Objekt in ACOS gelöscht → Auftrag zurück auf „übergeben“, ACOS bearbeitet neu. Ergebnis in ACOS gelöscht → Link am Auftrag entfernt, Hinweis. Bei Lesefehlern oder abgeschnittenen Listen ändert sich nichts. |
| ACOS führt: Wissen | In ACOS gelöschte/archivierte Wissensobjekte verschwinden aus der ACOS-Liste am Unternehmen und aus dem Kundenwissen; die Kopie in der Nextcloud wird nach `<Kunde>/ACOS/Wissen/archiviert/` verschoben (nie gelöscht, nie überschrieben, nur unter ACOS/Wissen und ACOS/Dokumente). Neue Fassung eines Objekts in ACOS (geändert > 1 Min.): alte Kopie nach archiviert, neue Kopie abgelegt, Auftrag zeigt auf die neue. `wissen_sync` übergeht `archiviert/`. |
| Direkt hochgeladene Dokumente | ACOS liefert kein Original, nur Text (am_acos_file_read). Lesbares kommt als Textauszug nach `<Kunde>/ACOS/Dokumente/<Datum> <Titel>.md` (im Kundenwissen suchbar), Hinweis „Textauszug in der Nextcloud, Original in ACOS“. Ohne lesbaren Text (z. B. Bilder) bleibt der Verweis mit Hinweis „Kein Text lesbar“. Der Ordner ACOS/ wird nie zurück nach ACOS gesendet. |

Altlasten 0009/0012/0014: nach dem Einspielen von Ronald per „Auftrag zurückziehen“ zu beenden (kein SQL nötig).
Danach: Prompt der geplanten Aufgabe „ACOS-Aufträge abarbeiten (Server)“ um `data.optionen` ergänzen.

Sandbox (crm_test, Migrationen 002–031, fiktive Daten): neu `test_acos_fuehrt.py` 43/43; smoke grün, 61, 33, 22, 14, 14, 11, 11, 19, 21;
Browser 29/29, Auswahl-Antwort und Zurückziehen im Streifen durchgeklickt, keine JavaScript-Fehler.

| Datei | live vorher | neu |
|---|---|---|
| crm_core.py | 2121e938… | 81cf51cc7992a3a196b9bb932a9f8ea66189788f |
| crm_serve.py | 51932565… | a00cb0797153948ff50f871201e0de2b3f733bd3 |
| acos_sync.py | e3aaa985… | 0eaed82161c1a33be443785ead55f1047d320634 |
| acos_auftraege.py | d3c0d175… | 439608ded6195b23cd3722c510cc5e067e6a70f6 |
| wissen_sync.py | 70321fd1… | 01b5c4b949ab369e26313547a6cbe4eb65f79efb |
| migration_031_acos_fuehrt.sql | – | ea0378b3c5497f3438a2238372cfab4245c41757 |

Sicherung: `/root/crm-code-vor-acos-fuehrt/`. Rückweg: Dateien zurück, chown, `systemctl restart crm`; Migration 031 stört den alten Code nicht
(der alte Code kennt `zurueckgezogen` nicht, zeigt solche Aufträge aber nur als beendet).

**Nachbesserung 25.11.2026 (nach dem Einspielen):** Das × im Streifen zog den jüngsten Auftrag der Aufgabe zurück, nicht den der Zeile.
PROJ-066 trägt 0012 und 0014 (Doppelklick-Altfall), PROJ-054 einen alten Fehler (0001) neben einem erledigten Auftrag – dort kam
„kein Auftrag, der sich zurückziehen lässt“. Jetzt: Zurückziehen mit Auftrags-ID (genau dieser Auftrag), Aufgabe wird nur frei, wenn
kein anderer Auftrag an ihr läuft. Minutentakt prüft auch Unternehmen mit offener Rückfrage oder Fehler (Härtung greift dann in Minuten
statt erst um 6:30). `test_acos_fuehrt.py` 49/49, alle übrigen grün.

| Datei | live (Release 25.11.) | neu |
|---|---|---|
| crm_core.py | 81cf51cc… | eca1f0b000ede19335a6833d01bd3c13dedbab0d |
| crm_serve.py | a00cb079… | 11368269fbbf71a6da2f4dcbcc37b672b6860bb5 |
| acos_sync.py | 0eaed821… | 723b9b6b892b0e241c2df1f804a556de38e1bde1 |
| acos_auftraege.py | 439608de… | 4338fbe8bc486df12e23947f6fef75df28376bc9 |

**Nachbesserung 2 (25.11.2026):** 0009 hängt an PROJ-056, die Aufgabe ist gelöscht („Aufgabe nicht gefunden“). Jetzt: Zurückziehen mit
Auftrags-ID geht auch ohne Aufgabe; „Aufgabe löschen“ zieht laufende Aufträge vorher zurück; verwaiste Aufträge beendet der Abgleich
selbst. `test_acos_fuehrt.py` 53/53, alle übrigen grün. crm_core.py eca1f0b0… → 5f5d6def9806598610bf7c9ba52a072745ac2abc,
acos_auftraege.py 4338fbe8… → 4690eb800453b175f8de838d6668d526ca9b9f57.

**Live 2026-11-25:** Migration 031 und beide Nachbesserungen eingespielt (crm_core 5f5d6def…, acos_auftraege 4690eb80…,
acos_sync 723b9b6b…, crm_serve 11368269…, wissen_sync 01b5c4b9…). 0009, 0012, 0014 hingen an gelöschten Aufgaben und wurden
vom Abgleich beendet, 0001 von Hand zurückgezogen. Von Ronald bestätigt.

Geplant (klein): Scheitert das × im ACOS-Streifen, den Streifen trotzdem neu laden, damit keine schon beendeten Aufträge stehen bleiben. → umgesetzt 26.11.2026, s. unten.

## 2026-11-26 – Geplant: geplante Aufgabe „ACOS-Aufträge abarbeiten (Server)“ anpassen (offen, noch nicht umgesetzt)

1. Rückfrage mit getrennten Antwortmöglichkeiten: `data.optionen` = [{"key": "A", "text": "…"}] zusätzlich zum Fragetext, damit die
   Auswahlmaske im CRM nicht auf die Texterkennung „A) … B) …“ angewiesen ist.
2. Vermerk „Zurückgezogen <Auftrags-ID>“ (Art crm_rueckfrage, status zurueckgezogen) ausdrücklich als erledigt nennen
   (greift heute schon über Regel 2a, soll aber eindeutig im Prompt stehen).
Rest des Prompts unverändert. Änderung erst mit Ronalds OK zum Release. Fachlich vorgemerkt von Ronald am 26.11.2026.

## 2026-11-26 – Fokusband: Kundenwert statt Gesamt-Pipeline (nur crm_core.py, live 2026-11-26)

Festlegung Ronald 26.11.2026: Rechts im Band steht der Wert des Kunden aus dem „einen Schritt“ (wechselt mit „Nächster Vorschlag“):
groß der **Umsatz der letzten 12 Monate**, klein die **offene Pipeline** des Kunden. Quelle (entschieden): Projektwerte, weil das CRM keine
Rechnungen kennt (die liegen in Lexware Office) – Umsatz = laufende Projekte + in den letzten 12 Monaten abgeschlossene (`updated_at`),
Pipeline = Anbahnung + Angebot; Projekte ohne Wert werden genannt. Klick öffnet die Akte. Ohne Kunden im Fokus bleibt die Gesamt-Pipeline
mit Verlauf. Dazu: × im ACOS-Streifen lädt den Streifen auch bei Fehler neu.
Sandbox: `test_fokusband.py` 27/27 (+5), alle übrigen grün, Browser ohne JavaScript-Fehler.
crm_core.py live 5f5d6def… → 3e0f5995da1cca7ba36ecf5b7deee102f1606bfc. Sicherung `/root/crm-code-vor-kundenwert/`.

## Termin: Lexware Office anbinden – Januar 2027, nicht früher (Festlegung Ronald 26.11.2026)

Dann echte Rechnungen statt Projektwerten für den Kundenwert im Fokusband (Umsatz 12 Monate). Bis dahin bleibt die Quelle „Projektwerte“.
Vorher keinen Bau und keine Vorarbeit beginnen.

Umfang (Ergänzung Ronald 26.11.2026): nicht nur Rechnungen lesen, sondern **Kundenstammdaten zwischen Lexware Office, CRM und ACOS
synchron halten** – ein Sync-Prozess, den Claude baut. Vor dem Bau im Januar zu klären:
- Führendes System je Feldgruppe (z. B. Rechnungsadresse/Steuerdaten → Lexware, Ansprechpartner/Status → CRM, Analysen → ACOS).
- Gemeinsamer Schlüssel (Lexware-Kontaktnummer am Unternehmen im CRM, wie heute die ACOS-Verknüpfung).
- Richtung und Takt je Feld, Umgang mit Konflikten (beide Seiten geändert), was nie automatisch überschrieben wird.
- Neue Kunden: wo angelegt, wie verknüpft; Archivieren/Löschen nach dem Muster „ACOS führt“.
- Datenschutz: Stammdaten laufen Server ↔ Server, nicht über Claude.

Festlegungen Ronald 26.11.2026 zum Lexware-Sync:
- Führende Systeme wie vorgeschlagen: Rechnungsadresse/Steuerdaten → Lexware, Ansprechpartner/Status → CRM, Analysen → ACOS.
- **Schlüssel ist die Lexware-Kundennummer.** Im CRM ein Identifikator `<Lexware-KNr>_<ACOS-Mandant>_<ACOS-Projekt>`
  (z. B. `10023_M-10_P-14`). Unternehmen ↔ Lexware-Kunde ↔ ACOS-Mandant über die ersten beiden Teile, Projekt über den dritten.
- **CRM-Projekte und ACOS-Projekte synchronisieren sich automatisch** (neu im Umfang).
- Übrige Punkte (Richtung/Takt/Konflikte, neue Kunden, Archivieren nach „ACOS führt“, Server ↔ Server) wie oben: ok.
Geklärt 26.11.2026: Leads ohne Lexware-Kundennummer bekommen einen Platzhalter bis zur Kundennummer. Wer nicht in ACOS geführt wird,
braucht keine ACOS-Teile – leer oder Dummy. Ändert sich eine Zuordnung (Kundennummer vergeben, in ACOS aufgenommen, Projekt angelegt),
aktualisiert der Sync die Kennung.

## 2026-11-27 – ACOS führt: Kopie umbenennen statt verschieben (keine Migration, acos_sync.py + wissen_sync.py, live 2026-11-27)

Befund live 27.11.2026: „Kopie nicht archiviert … (HTTPError)“. Ursache: Die Nextcloud lehnt das Verschieben nach `ACOS/Wissen/archiviert/`
mit **403** ab, weil der CRM-Nutzer an der Freigabe bewusst kein Löschrecht hat (Rechte der Kopie `SGNVW`, kein D). Damit konnte die
Archivierung aus Release 031 nie gelingen. Umbenennen im selben Ordner braucht nur N.
- Archivieren = Umbenennen im selben Ordner mit Vorsatz `ARCHIVIERT_` (bei Namensgleichheit `ARCHIVIERT_<Name> (2).md`). Nie löschen,
  nie überschreiben, kein Ordner `archiviert/` mehr. Alte Kopien unter `archiviert/` gelten weiter als archiviert.
- Kundenwissen (`wissen_sync.py`) übergeht Dateien mit Vorsatz `ARCHIVIERT_` wie bisher den Ordner `archiviert/`.
- Fehlermeldungen nennen den HTTP-Code („HTTP 403“ statt „HTTPError“). Scheitert das Archivieren, steht das einmal als Fehler im Lauf und
  in `meldung` („bitte in der Nextcloud von Hand archivieren“); danach kein neuer Versuch bei jedem Lauf.
Sandbox (crm_test, Migrationen 002–031, fiktive Daten): smoke grün, `test_acos_fuehrt.py` 57/57 (+4, Attrappe verhält sich wie die
Nextcloud ohne Löschrecht), übrige ACOS-Tests grün (61, 33, 14, 14, 11). Gegenprobe: alter Code scheitert am neuen Test.

| Datei | live erwartet (Repo-Stand vorher) | neu |
|---|---|---|
| acos_sync.py | 723b9b6b892b0e241c2df1f804a556de38e1bde1 | 7d64af8e5ae7d6c432f394b4bb6953c8cebfc96e |
| wissen_sync.py | 01b5c4b949ab369e26313547a6cbe4eb65f79efb | c9602d5ab2a649d8ed2e9f4eeff289677c6baef3 |

Sicherung: `/root/crm-code-vor-archiv-umbenennen/`. Rückweg: beide Dateien zurück, chown; Timer laden die Skripte selbst neu.

**Live 2026-11-27:** Prüfsummen bestätigt, Dienst neu gestartet, Abgleich von Hand: Kopie zu M-15 umbenannt, von Ronald bestätigt.
