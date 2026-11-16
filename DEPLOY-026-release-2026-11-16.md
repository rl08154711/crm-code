# Release 16.11.2026: Umbenennen, Suchfeld, Mail-Review, Schnellauswahl (Migration 025)

Inhalt siehe `NAECHSTES-UPDATE.md`. Freigabe durch Ronald am 16.11.2026, Live-Prüfsummen vorher bestätigt.

| Datei | vorher (live) | neu |
|---|---|---|
| crm_core.py | ef604c8efb9dd9352067aad0019e379876e95dd1 | abff7a01e62dee3718ff7f4a59f262d7ee41e5ff |
| crm_serve.py | 26cc8d43877c1bad468d1739e90505d5060e5200 | 4b60015a8a0782e66bd31a9061c8e0ea99fe2900 |
| migration_025_sichten.sql | – | 07cd351ee5593bdff54fa832308c7e6b8a220d9a |

## Ausliefern

```bash
# 1 [Mac] Arbeitsordner prüfen – muss "neu" zeigen, sonst ABBRECHEN
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py Migration-Postgres/migration_025_sichten.sql

# 2 [Mac] Hochladen (je Datei ein scp)
ssh root@46.225.13.130 "mkdir -p /tmp/crm-release-1116"
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm-release-1116/
scp CPX12-Postgres/crm_serve.py root@46.225.13.130:/tmp/crm-release-1116/
scp Migration-Postgres/migration_025_sichten.sql root@46.225.13.130:/tmp/crm-release-1116/

# 3 [Server] Ankunft prüfen – "neu", sonst ABBRECHEN
cd /tmp/crm-release-1116 && sha1sum * && chmod 644 *

# 4 [Server] Sicherung: Code und Datenbank
mkdir -p /root/crm-code-vor-release-1116
cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /root/crm-code-vor-release-1116/
cd /tmp && sudo -u crmapp pg_dump -d crm > /root/crm-code-vor-release-1116/crm-db.sql && ls -la /root/crm-code-vor-release-1116/

# 5 [Server] Migration 025 (legt nur die neue Tabelle für Sichten an, zeigt am Ende 2 Startsichten)
cd /tmp && sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d crm -f /tmp/crm-release-1116/migration_025_sichten.sql

# 6 [Server] Code einspielen, Dienst neu starten
cp /tmp/crm-release-1116/crm_core.py /tmp/crm-release-1116/crm_serve.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py
cd /opt/crm && sha1sum crm_core.py crm_serve.py
systemctl restart crm
sleep 2; systemctl status crm --no-pager | head -5

# 7 [Server] Nachweis
curl -s http://127.0.0.1:8080/healthz
journalctl -u crm -n 20 --no-pager | grep -iE "error|traceback" || echo "keine Fehler im Log"
```

Danach im Browser: Stammdaten → Unternehmen (Sichten, Chips, A–Z), eine Mail im Mail-Review,
Bearbeiten eines Unternehmens (Feld „Firma“ änderbar), Klick in eine Zeile ohne Benutzernamen im Suchfeld.

## Rückweg

```bash
cp -p /root/crm-code-vor-release-1116/crm_core.py /root/crm-code-vor-release-1116/crm_serve.py /opt/crm/
systemctl restart crm
# Die Tabelle gespeicherte_sichten stört den alten Code nicht und kann stehen bleiben.
```

## Ins Repository (erst nach bestätigtem Live-Stand)

```bash
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
git status --short
git add CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py Migration-Postgres/migration_025_sichten.sql \
        Migration-Postgres/test_firma_umbenennen.py Migration-Postgres/test_schnellauswahl.py \
        NAECHSTES-UPDATE.md DEPLOY-026-release-2026-11-16.md
git commit -m "Release 16.11.2026: Unternehmen umbenennen, Suchfeld ohne Autofill, Mail-Review mit festen Aktionen, Schnellauswahl mit Sichten (Migration 025)"
git push
```
