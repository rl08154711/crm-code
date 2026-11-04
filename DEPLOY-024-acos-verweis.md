# Update 024: ACOS-Dokumente „nur in ACOS“ statt „wartet auf Ablage“ (04.11.2026)

**Problem:** Seit dem 03.11.2026 (Variante 2) bleiben hochgeladene Dateien (`kind = document`) in ACOS.
Der Abgleich hat sie richtig nicht in die Nextcloud gelegt, ihren Status aber auf `neu` gelassen.
Die Oberfläche zeigt `neu` als „wartet auf Ablage“. Diese Dokumente blieben deshalb dauerhaft in diesem Zustand.

**Lösung:**

| Datei | Änderung |
|---|---|
| `Migration-Postgres/migration_024_acos_verweis.sql` | neuer Status `verweis`, bestehende Dokumente in `neu`/`fehler` werden einmalig umgestellt |
| `CPX12-Postgres/acos_sync.py` | Dokumente bekommen beim Abgleich `verweis` statt `neu` |
| `CPX12-Postgres/crm_core.py` | Etikett „nur in ACOS“ (blau) |
| `Migration-Postgres/test_acos_verweis.py` | neue Prüfung (13 Fälle, ACOS und Nextcloud als Attrappe) |

Unverändert: Berichte landen weiter als Markdown unter `Kunde/ACOS/Wissen`. Dateien, die das CRM selbst
an ACOS gesendet hat, bleiben „in Nextcloud“. Im Kundenwissen stehen die Dokumente wie bisher als Verweis.

**Sandbox-Test (frische `crm_test`, Migrationen 002–024):** smoke_test 84/84, test_acos_verweis 13/13,
test_kundenwissen_acos 11/11, Migration 024 zweimal hintereinander fehlerfrei, Oberfläche ohne JavaScript-Fehler.

## Prüfsummen (sha1)

| Datei | vorher (Repository = live seit 03.11.) | neu |
|---|---|---|
| `crm_core.py` | `8a8a89fc387ee243a8ab2e42e38d2eb5ac1c61f3` | `80bcf31d79b1aa4ea51663d41da4c09afc008054` |
| `acos_sync.py` | `a200faf795b32a26e83a3aee833edd722145812a` | `34cf6c8233b90b4d51380ff205d20d7e63870c50` |
| `migration_024_acos_verweis.sql` | – | `cc3efd3d085ea0f28537583220aa4406077288f5` |

## Ausrollen

```bash
# 1 [Server] Live-Stand prüfen – bei Abweichung von "vorher" ABBRECHEN und Bescheid geben
cd /opt/crm && sha1sum crm_core.py acos_sync.py

# 2 [Mac] Arbeitsordner prüfen – muss ebenfalls "vorher" zeigen, sonst ABBRECHEN
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/acos_sync.py

# 3 [Mac] Update auspacken (überschreibt die zwei Dateien, legt Migration, Test und Anleitung neu an)
unzip -o ~/Downloads/crm-update-024-acos-verweis.zip
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/acos_sync.py Migration-Postgres/migration_024_acos_verweis.sql

# 4 [Mac] Hochladen
ssh root@46.225.13.130 "mkdir -p /tmp/crm-update-024"
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm-update-024/
scp CPX12-Postgres/acos_sync.py root@46.225.13.130:/tmp/crm-update-024/
scp Migration-Postgres/migration_024_acos_verweis.sql root@46.225.13.130:/tmp/crm-update-024/

# 5 [Server] Ankunft prüfen – muss "neu" zeigen
cd /tmp/crm-update-024 && sha1sum *

# 6 [Server] Sicherung von Datenbank und Code
sudo -u crmapp pg_dump -Fc crm > /root/crm-vor-acos-verweis_$(date +%F_%H%M).dump
mkdir -p /root/crm-code-vor-acos-verweis && cp -p /opt/crm/crm_core.py /opt/crm/acos_sync.py /root/crm-code-vor-acos-verweis/

# 7 [Server] Migration – erwartet: BEGIN, ALTER TABLE, ALTER TABLE, UPDATE <Anzahl>, COMMIT
cd /tmp && sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d crm -f /tmp/crm-update-024/migration_024_acos_verweis.sql

# 8 [Server] Code einspielen, Dienst neu starten
cp /tmp/crm-update-024/crm_core.py /tmp/crm-update-024/acos_sync.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/acos_sync.py
cd /opt/crm && sha1sum crm_core.py acos_sync.py
systemctl restart crm
systemctl status crm --no-pager | head -5

# 9 [Server] Nachweis – keine Dokumente mehr auf "neu"
cd /tmp && sudo -u crmapp psql -P pager=off -d crm -c "SELECT art='document' AS dokument, status, count(*) FROM acos_artefakte GROUP BY 1,2 ORDER BY 1,2"
```

Danach im Browser eine Firma mit ACOS-Dokumenten öffnen → Reiter ACOS: Die Dokumente zeigen jetzt „nur in ACOS“.

## Rückweg

```bash
cp -p /root/crm-code-vor-acos-verweis/crm_core.py /root/crm-code-vor-acos-verweis/acos_sync.py /opt/crm/
cd /tmp && sudo -u crmapp psql -d crm -c "UPDATE acos_artefakte SET status='neu' WHERE status='verweis'"
systemctl restart crm
```

Die erweiterte Statusliste aus Migration 024 kann bleiben, sie stört den alten Code nicht.

## Ins Repository (erst nach bestätigtem Live-Stand)

```bash
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
git status --short
git add CPX12-Postgres/crm_core.py CPX12-Postgres/acos_sync.py Migration-Postgres/migration_024_acos_verweis.sql Migration-Postgres/test_acos_verweis.py DEPLOY-024-acos-verweis.md
git commit -m "ACOS-Dokumente als Verweis: Status 'nur in ACOS' statt 'wartet auf Ablage' (Migration 024)"
git push
```
