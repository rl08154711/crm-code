# Update 025: ACOS-Dokument wird „in Nextcloud“, sobald die Datei im Kundenordner liegt (04.11.2026)

**Ziel (Variante A):** Ein Dokument mit dem Etikett „nur in ACOS“ springt von selbst auf „in Nextcloud“,
sobald eine gleichnamige Datei im Kundenordner derselben Firma liegt. Der Ordner-Link 📁 führt dann zur Datei.
Das Original lädt Ronald wie bisher selbst aus ACOS herunter und legt es in den Kundenordner.

**Regeln:**
- Gleicher Dateiname, Groß- und Kleinschreibung egal, Unterordner egal (z. B. `Kunde/Planung/…`).
- Hat der ACOS-Titel keine Endung, zählt der Dateiname ohne Endung.
- Nur Dateien derselben Firma. Gelöschte Dateien zählen nicht, der Unterordner `ACOS` auch nicht.
- Andere Version, anderer Name: z. B. `v2` ≠ `v3`, das Dokument bleibt „nur in ACOS“.
- Die Prüfung läuft stündlich mit dem Wissens-Abgleich und zusätzlich beim ACOS-Abgleich um 6:30.
- Wird die Datei später aus dem Kundenordner entfernt, bleibt das Etikett „in Nextcloud“.

| Datei | Änderung |
|---|---|
| `CPX12-Postgres/crm_core.py` | neue Funktion `acos_verweise_mit_ablage()` |
| `CPX12-Postgres/wissen_sync.py` | ruft sie stündlich nach dem Erfassen der Kundenordner auf |
| `CPX12-Postgres/acos_sync.py` | ruft sie beim ACOS-Abgleich je Firma auf |
| `Migration-Postgres/test_acos_verweis_ablage.py` | neue Prüfung (14 Fälle) |
| `Migration-Postgres/test_acos_verweis.py` | um den Fall „Datei liegt schon im Ordner“ ergänzt (14 Fälle) |

Keine Datenbank-Migration.

**Sandbox-Test (frische `crm_test`, Migrationen 002–024):** smoke_test 84/84, test_acos_verweis_ablage 14/14,
test_acos_verweis 14/14, test_kundenwissen_acos 11/11, Oberfläche ohne JavaScript-Fehler.

## Prüfsummen (sha1)

| Datei | vorher (live seit Update 024) | neu |
|---|---|---|
| `crm_core.py` | `80bcf31d79b1aa4ea51663d41da4c09afc008054` | `ef604c8efb9dd9352067aad0019e379876e95dd1` |
| `acos_sync.py` | `34cf6c8233b90b4d51380ff205d20d7e63870c50` | `dc7f818974eb777d639ec915a050200eaa64c897` |
| `wissen_sync.py` | `325776e28f7ec104e173beaea660fe2fddfe4dd4` | `70321fd1345eee5867a410601da7c8eb1e23f1be` |

## Ausrollen

```bash
# 1 [Server] Live-Stand prüfen – muss "vorher" zeigen, sonst ABBRECHEN
cd /opt/crm && sha1sum crm_core.py acos_sync.py wissen_sync.py

# 2 [Mac] Arbeitsordner prüfen – ebenfalls "vorher", sonst ABBRECHEN
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/acos_sync.py CPX12-Postgres/wissen_sync.py

# 3 [Mac] Auspacken und prüfen – muss "neu" zeigen
unzip -o ~/Downloads/crm-update-025-acos-verweis-ablage.zip
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/acos_sync.py CPX12-Postgres/wissen_sync.py

# 4 [Mac] Hochladen
ssh root@46.225.13.130 "mkdir -p /tmp/crm-update-025"
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm-update-025/
scp CPX12-Postgres/acos_sync.py root@46.225.13.130:/tmp/crm-update-025/
scp CPX12-Postgres/wissen_sync.py root@46.225.13.130:/tmp/crm-update-025/

# 5 [Server] Ankunft prüfen – "neu"
cd /tmp/crm-update-025 && sha1sum *

# 6 [Server] Sicherung des Codes
mkdir -p /root/crm-code-vor-acos-verweis-ablage
cp -p /opt/crm/crm_core.py /opt/crm/acos_sync.py /opt/crm/wissen_sync.py /root/crm-code-vor-acos-verweis-ablage/

# 7 [Server] Einspielen, Dienst neu starten
cp /tmp/crm-update-025/*.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/acos_sync.py /opt/crm/wissen_sync.py
cd /opt/crm && sha1sum crm_core.py acos_sync.py wissen_sync.py
systemctl restart crm
systemctl status crm --no-pager | head -5

# 8 [Server] Wissens-Abgleich einmal sofort laufen lassen statt auf die volle Stunde zu warten
systemctl start crm-wissen.service
journalctl -u crm-wissen.service -n 20 --no-pager | grep -iE "acos_verweise|fehl" || echo "keine Auffälligkeiten"

# 9 [Server] Nachweis – Dokumente nach Status
cd /tmp && sudo -u crmapp psql -P pager=off -d crm -c "SELECT status, count(*) FROM acos_artefakte WHERE art='document' GROUP BY 1 ORDER BY 1"
```

Zum Ausprobieren: Ein Dokument mit „nur in ACOS“ über ↗ in ACOS herunterladen, unter genau diesem Namen in den
Kundenordner legen und nach dem nächsten stündlichen Lauf (oder Schritt 8) den ACOS-Reiter neu öffnen.

## Rückweg

```bash
cp -p /root/crm-code-vor-acos-verweis-ablage/*.py /opt/crm/
systemctl restart crm
# bei Bedarf umgestellte Dokumente zurücksetzen (nur die, die nicht vom CRM selbst an ACOS gesendet wurden):
cd /tmp && sudo -u crmapp psql -d crm -c "UPDATE acos_artefakte a SET status='verweis', nextcloud_pfad=NULL WHERE art='document' AND status='abgelegt' AND NOT EXISTS (SELECT 1 FROM acos_uploads u WHERE u.firma_id=a.firma_id AND u.acos_document_id=a.acos_id)"
```

## Ins Repository (erst nach bestätigtem Live-Stand)

```bash
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
git status --short
git add CPX12-Postgres/crm_core.py CPX12-Postgres/acos_sync.py CPX12-Postgres/wissen_sync.py Migration-Postgres/test_acos_verweis.py Migration-Postgres/test_acos_verweis_ablage.py DEPLOY-025-acos-verweis-ablage.md
git commit -m "ACOS-Dokumente: 'in Nextcloud', sobald gleichnamige Datei im Kundenordner liegt (Variante A)"
git push
```
