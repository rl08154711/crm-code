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
