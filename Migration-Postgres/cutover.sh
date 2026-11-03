#!/usr/bin/env bash
# CRM Postgres - Produktiv-Cutover (Fassung 2026-09-25, Auslieferung per Git)
#
# Als root ausfuehren, NACHDEM der Smoke-Test gegen crm_test erfolgreich war
# und der Import gegen crm_test die erwarteten Zahlen zeigt.
#
# Macht in dieser Reihenfolge:
#   1) Live-Daten aus /opt/crm nach /opt/crm-import einfrieren
#   2) Die laufenden Dienstdateien sichern (Rollback-Anker)
#   3) Echten Import gegen die Produktiv-DB 'crm' (fragt interaktiv 'ja' ab)
#   4) Dienste auf den Git-Klon umschalten
#   5) crm.service + crm-mailpoll.service neu starten
#
# Der Code selbst wird nicht mehr kopiert - er liegt im Klon unter
# /opt/crm-repo und wird dort per 'git pull' aktuell gehalten.
#
# Legt KEINEN Login-Nutzer an (Passwort gehoert nicht in ein Skript) - das
# bitte direkt danach von Hand machen, Befehl steht am Skriptende.
set -euo pipefail

CRM_LIVE_DIR=/opt/crm
CRM_REPO_DIR=/opt/crm-repo
CRM_CODE_DIR="$CRM_REPO_DIR/CPX12-Postgres"
CRM_MIGRATION_DIR="$CRM_REPO_DIR/Migration-Postgres"
CRM_IMPORT_DIR=/opt/crm-import

for d in "$CRM_LIVE_DIR" "$CRM_CODE_DIR" "$CRM_MIGRATION_DIR"; do
  if [ ! -d "$d" ]; then
    echo "FEHLER: $d nicht gefunden - Ablauf siehe DEPLOY-Postgres.md." >&2
    exit 1
  fi
done

echo "=== 1/5: Live-Daten einfrieren ==="
rm -rf "$CRM_IMPORT_DIR/Kontakte" "$CRM_IMPORT_DIR/Opportunities" "$CRM_IMPORT_DIR/tasks.json" "$CRM_IMPORT_DIR/Aktivitäten"
mkdir -p "$CRM_IMPORT_DIR"
cp -r "$CRM_LIVE_DIR/Kontakte" "$CRM_IMPORT_DIR/"
cp -r "$CRM_LIVE_DIR/Opportunities" "$CRM_IMPORT_DIR/"
cp "$CRM_LIVE_DIR/tasks.json" "$CRM_IMPORT_DIR/"
cp -r "$CRM_LIVE_DIR/Aktivitäten" "$CRM_IMPORT_DIR/" 2>/dev/null || true

echo "=== 2/5: Dienstdateien sichern (Rollback-Anker) ==="
BACKUP_DIR="/opt/crm-pre-postgres-backup-$(date +%Y%m%d-%H%M)"
mkdir -p "$BACKUP_DIR"
cp /etc/systemd/system/crm.service "$BACKUP_DIR/" 2>/dev/null || true
cp /etc/systemd/system/crm-mailpoll.service "$BACKUP_DIR/" 2>/dev/null || true
echo "Backup liegt in: $BACKUP_DIR"
echo "(Der alte Code braucht keine Sicherung - er liegt unveraendert in $CRM_LIVE_DIR"
echo " und zusaetzlich im Repository unter CPX12-Generalprobe/.)"

echo "=== 3/5: Echter Import gegen die Produktiv-DB 'crm' ==="
sudo -u crmapp env CRM_DB_NAME=crm python3 "$CRM_MIGRATION_DIR/import_data.py" \
  --root "$CRM_IMPORT_DIR" --live

echo "=== 4/5: Dienste auf den Git-Klon umschalten ==="
cp "$CRM_CODE_DIR/crm.service" /etc/systemd/system/
cp "$CRM_CODE_DIR/crm-mailpoll.service" /etc/systemd/system/
systemctl daemon-reload

echo "=== 5/5: Dienste neu starten ==="
systemctl restart crm crm-mailpoll
sleep 1
systemctl status crm --no-pager

echo ""
echo "=== Cutover fertig ==="
echo "WICHTIG - jetzt noch von Hand (Passwort gehoert nicht ins Skript):"
echo "  cd $CRM_CODE_DIR && sudo -u crmapp python3 manage_users.py add ronald"
echo ""
echo "Rollback falls noetig:"
echo "  cp $BACKUP_DIR/*.service /etc/systemd/system/"
echo "  systemctl daemon-reload && systemctl restart crm crm-mailpoll"
