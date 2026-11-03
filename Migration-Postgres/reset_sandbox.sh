#!/usr/bin/env bash
# CRM Postgres - Sandbox-Reset (2026-09-12)
# Setzt crm_test + crm komplett zurueck und raeumt Sandbox-Verzeichnisse weg.
# Ruehrt NICHT an /opt/crm (die laufende Produktivinstanz auf altem Markdown-
# Code) - die bleibt unberuehrt weiterlaufen. Als root ausfuehren.
#
# Aufruf: bash reset_sandbox.sh /pfad/zu/schema.sql
set -euo pipefail

SCHEMA_FILE="${1:-/opt/crm-migration/schema.sql}"
if [ ! -f "$SCHEMA_FILE" ]; then
  echo "FEHLER: schema.sql nicht gefunden unter $SCHEMA_FILE" >&2
  echo "Aufruf: bash reset_sandbox.sh /pfad/zu/schema.sql" >&2
  exit 1
fi

echo "=== 1/5: Testserver-Prozess (Port 8091) beenden, falls aktiv ==="
pkill -f "CRM_PORT=8091" 2>/dev/null || true
pkill -f "crm-pg-test/crm_serve.py" 2>/dev/null || true

echo "=== 2/5: Sandbox-Importverzeichnis entfernen ==="
rm -rf /opt/crm-import

echo "=== 3/5: Datenbanken crm_test + crm sauber neu anlegen ==="
sudo -u postgres dropdb --if-exists crm_test
sudo -u postgres dropdb --if-exists crm
sudo -u postgres createdb -O crmapp crm_test
sudo -u postgres createdb -O crmapp crm

echo "=== 4/5: Schema in beide deployen ==="
sudo -u crmapp psql -d crm_test -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE"
sudo -u crmapp psql -d crm      -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE"

echo "=== 5/5: Kontrolle ==="
echo "--- crm_test ---"
sudo -u crmapp psql -d crm_test -c '\dt'
echo "--- crm ---"
sudo -u crmapp psql -d crm -c '\dt'

echo ""
echo "=== Fertig - beide Datenbanken leer, Schema deployt ==="
echo "Naechster Schritt: /opt/crm-pg-test per FileZilla frisch mit CPX12-Postgres/ befuellen,"
echo "dann 'md5sum /opt/crm-pg-test/crm_core.py' pruefen."
