#!/usr/bin/env bash
# CRM Test-Server Setup (CPX12 Generalprobe) - 2026-07-25
# Einmal komplett in die Server-Konsole einfuegen und ausfuehren (als root).
set -euo pipefail

echo "=== 1/6: System aktualisieren ==="
apt-get update -y
apt-get upgrade -y

echo "=== 2/6: Basis-Pakete installieren ==="
apt-get install -y python3 python3-pip python3-venv git curl ufw \
    debian-keyring debian-archive-keyring apt-transport-https

echo "=== 3/6: Caddy-Repository einrichten ==="
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list

echo "=== 4/6: Caddy installieren ==="
apt-get update -y
apt-get install -y caddy

echo "=== 5/6: Dedizierten Systembenutzer fuers CRM anlegen (kein root-Betrieb) ==="
if ! id -u crmapp >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin crmapp
fi
mkdir -p /opt/crm
chown crmapp:crmapp /opt/crm

echo "=== 6/6: Firewall-Grundschutz ==="
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo ""
echo "=== Setup abgeschlossen ==="
echo "Naechster Schritt: crm_core.py & Co per FileZilla als root nach /opt/crm hochladen."
echo "Python-Version zur Kontrolle:"
python3 --version
echo "Caddy-Version zur Kontrolle:"
caddy version
