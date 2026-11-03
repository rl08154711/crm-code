#!/bin/bash
set -euo pipefail
ZIEL=/var/backups/crm
DATEI="$ZIEL/crm-$(date +%F_%H%M).dump"
NC="https://nx89264.your-storageshare.de/remote.php/dav/files/Backup/Backup/CRM"
# 1. Sichern und pruefen
sudo -u postgres pg_dump -Fc crm > "$DATEI"
chmod 600 "$DATEI"
pg_restore --list "$DATEI" > /dev/null
# 2. Verschluesseln und in die Nextcloud laden
gpg --batch --yes --pinentry-mode loopback --passphrase-file /root/.crm-backup.pass \
    --symmetric --cipher-algo AES256 -o "$DATEI.gpg" "$DATEI"
curl -s --netrc-file /root/.crm-backup.netrc -X MKCOL "$NC" > /dev/null || true
curl -sf --netrc-file /root/.crm-backup.netrc -T "$DATEI.gpg" "$NC/crm-$(LC_ALL=C date +%a).dump.gpg"
if [ "$(date +%d)" = "01" ]; then
  curl -sf --netrc-file /root/.crm-backup.netrc -T "$DATEI.gpg" "$NC/crm-$(date +%Y-%m).dump.gpg"
fi
rm -f "$DATEI.gpg"
# 3. Lokal 14 Tage aufheben
find "$ZIEL" -name 'crm-*.dump' -mtime +14 -delete
echo "Backup ok: $DATEI"
