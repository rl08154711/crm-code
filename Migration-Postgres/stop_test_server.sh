#!/usr/bin/env bash
# CRM Postgres - Testserver auf Port 8091 wieder stoppen (2026-09-14)
# Als root ausfuehren.
set -euo pipefail

pkill -f "CRM_PORT=8091" 2>/dev/null && echo "Testserver-Prozess gestoppt." || echo "Kein laufender Testserver-Prozess gefunden."
