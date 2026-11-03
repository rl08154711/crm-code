#!/bin/bash
# Setzt die Demo-Daten (Kontakte, Opportunities, Tasks) auf den Pristine-Stand zurück.
# Läuft automatisch per Timer (crm-demo-reset.timer), kann aber auch jederzeit
# manuell ausgeführt werden:  bash /opt/crm-demo/reset_demo.sh
set -euo pipefail

LIVE=/opt/crm-demo
SEED=/opt/crm-demo-seed
LOG="$LIVE/reset.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $1" >> "$LOG"; }

if [ ! -d "$SEED" ]; then
  log "FEHLER: Seed-Verzeichnis $SEED fehlt – Reset abgebrochen."
  exit 1
fi

# --delete sorgt dafür, dass auch neu angelegte/gelöschte Demo-Einträge
# wieder auf den Ausgangsstand zurückgesetzt werden.
rsync -a --delete "$SEED/Kontakte/" "$LIVE/Kontakte/"
rsync -a --delete "$SEED/Opportunities/" "$LIVE/Opportunities/"
cp -f "$SEED/tasks.json" "$LIVE/tasks.json"

log "OK: Demo-Daten zurückgesetzt."
