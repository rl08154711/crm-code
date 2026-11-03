#!/usr/bin/env bash
# CRM Postgres - Testserver auf Port 8091 gegen crm_test starten (2026-09-14)
# Als root ausfuehren. Startet crm_serve.py im Hintergrund als crmapp,
# prueft danach /healthz. Login-Nutzer NICHT Teil dieses Skripts (Passwort
# gehoert nicht in ein Skript/Chat - das bitte weiterhin interaktiv per
# manage_users.py setzen, siehe Ausgabe am Ende).
set -euo pipefail

CRM_PG_DIR="${1:-/opt/crm-pg-test}"
PORT=8091
LOG="/tmp/crm-test.log"

if [ ! -f "$CRM_PG_DIR/crm_serve.py" ]; then
  echo "FEHLER: $CRM_PG_DIR/crm_serve.py nicht gefunden." >&2
  echo "Aufruf: bash start_test_server.sh [/pfad/zu/crm-pg-test]" >&2
  exit 1
fi

if curl -s -o /dev/null "http://127.0.0.1:${PORT}/healthz"; then
  echo "Es laeuft bereits ein Server auf Port ${PORT} - stoppe ihn zuerst mit stop_test_server.sh."
  exit 1
fi

echo "=== Starte Testserver ($CRM_PG_DIR, Port $PORT, DB crm_test) ==="
sudo -u crmapp env CRM_PORT="$PORT" CRM_DB_NAME=crm_test CRM_COOKIE_SECURE=0 \
  nohup python3 "$CRM_PG_DIR/crm_serve.py" > "$LOG" 2>&1 &
disown

sleep 1
if curl -s "http://127.0.0.1:${PORT}/healthz" | grep -q '"ok": true'; then
  echo "OK: Server laeuft, /healthz antwortet."
else
  echo "FEHLER: /healthz antwortet nicht wie erwartet - Log-Ausgabe:"
  cat "$LOG"
  exit 1
fi

echo ""
echo "Naechster Schritt (einmalig, interaktiv - Passwort wird abgefragt, nicht hier eintragen):"
echo "  cd $CRM_PG_DIR"
echo "  sudo -u crmapp env CRM_DB_NAME=crm_test python3 manage_users.py add smoketest"
