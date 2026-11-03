#!/usr/bin/env bash
# CRM Postgres-Grundsetup auf CPX12 - 2026-09-11
# Einmalig als root ausfuehren (Konsole oder SSH). Idempotent: mehrfaches
# Ausfuehren schadet nicht (CREATE ROLE/DATABASE IF NOT EXISTS-Aequivalente).
#
# Legt an:
#   - Postgres-Server (nur 127.0.0.1, kein Netzwerkzugriff von aussen)
#   - DB-Rolle 'crmapp' mit Peer-Authentication ueber den gleichnamigen
#     OS-User (der bereits existiert, siehe setup_test_server.sh/crm.service) -
#     kein Passwort noetig, keine Secrets-Datei fuer die DB-Verbindung.
#   - Zwei Datenbanken: crm_test (Sandbox, jederzeit per
#     "DROP DATABASE crm_test" wegwerfbar) und crm (Produktiv, bleibt leer
#     bis der Cutover-Schritt in DEPLOY-Postgres.md ausgefuehrt wird).
#   - Schema aus schema.sql in BEIDEN Datenbanken.
set -euo pipefail

if ! id -u crmapp >/dev/null 2>&1; then
  echo "FEHLER: OS-User 'crmapp' existiert nicht - erst setup_test_server.sh ausfuehren." >&2
  exit 1
fi

echo "=== 1/4: Postgres installieren ==="
apt-get update -y
apt-get install -y postgresql python3-psycopg2

echo "=== 2/4: DB-Rolle 'crmapp' anlegen (Peer-Auth, kein Passwort) ==="
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='crmapp'" | grep -q 1 \
  || sudo -u postgres createuser crmapp

echo "=== 3/4: Datenbanken crm_test + crm anlegen ==="
for db in crm_test crm; do
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
    || sudo -u postgres createdb -O crmapp "$db"
done

echo "=== 4/4: Schema in beiden Datenbanken deployen ==="
SCHEMA_FILE="$(dirname "$0")/schema.sql"
if [ ! -f "$SCHEMA_FILE" ]; then
  echo "FEHLER: schema.sql nicht gefunden neben diesem Skript ($SCHEMA_FILE)." >&2
  exit 1
fi
for db in crm_test crm; do
  echo "--- $db ---"
  sudo -u crmapp psql -d "$db" -v ON_ERROR_STOP=1 -f "$SCHEMA_FILE"
done

echo ""
echo "=== Fertig ==="
echo "Peer-Auth-Test (sollte ohne Passwortabfrage eine leere Tabellenliste zeigen):"
sudo -u crmapp psql -d crm_test -c '\dt'
echo ""
echo "Naechster Schritt: neuen Code (crm_core.py, crm_serve.py, manage_users.py) nach"
echo "/opt/crm-pg-test hochladen und gegen crm_test testen - siehe DEPLOY-Postgres.md."
