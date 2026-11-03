# CRM-Demo extern bereitstellen – Schritt-für-Schritt

Ziel: `https://demo.digitalkonzepte.biz` zeigt das CRM-Dashboard mit Demodaten, geschützt per Passwort, läuft dauerhaft ohne dass dein Mac an sein muss, und setzt sich alle 4 Stunden automatisch zurück, falls Interessenten Daten verändern.

Voraussetzung: du hast Zugriff auf digitalkonzepte.biz (DNS-Einträge setzen können) und legst selbst einen Server an.

---

## 1. Server anlegen

- [Hetzner Cloud Console](https://console.hetzner.cloud) → neues Projekt → neuer Server
- Image: **Ubuntu 24.04**
- Typ: **CX22** reicht völlig (2 vCPU, 4 GB RAM, ~5 €/Monat) – für die Demo braucht es keine GPU/KI-Server
- SSH-Key hinterlegen (nicht Passwort-Login verwenden)
- Nach dem Anlegen: Server-IP notieren (z. B. `123.45.67.89`)

## 2. DNS einrichten

Bei deinem Domain-Verwalter (dort wo digitalkonzepte.biz liegt) einen Eintrag anlegen:

```
Typ: A
Name: demo
Wert: <Server-IP>
TTL: 300
```

Kurz warten bis `demo.digitalkonzepte.biz` auf die neue IP zeigt (prüfen mit `dig demo.digitalkonzepte.biz` oder `nslookup demo.digitalkonzepte.biz`).

## 3. Auf dem Server: Firewall + Basis-Setup

Per SSH verbinden:

```bash
ssh root@<Server-IP>
```

Firewall (nur SSH, HTTP, HTTPS erlauben):

```bash
apt update && apt install -y ufw
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

Dedizierten, unprivilegierten Nutzer für die Demo anlegen (Prozess läuft nicht als root):

```bash
adduser --system --group --home /opt/crm-demo crmdemo
mkdir -p /opt/crm-demo /opt/crm-demo-seed
chown -R crmdemo:crmdemo /opt/crm-demo /opt/crm-demo-seed
```

Python3 prüfen (bei Ubuntu 24.04 vorinstalliert):

```bash
python3 --version
```

## 4. Dateien hochladen

Von deinem Mac aus, im Ordner `Demo-Deployment/vault` (Terminal, **nicht** auf dem Server):

```bash
cd /Users/rl/Documents/Claude/Projects/CRM/Demo-Deployment
scp -r vault/* root@<Server-IP>:/opt/crm-demo/
```

Auf dem Server: einmal als "Pristine-Kopie" für den automatischen Reset sichern und Rechte setzen:

```bash
cp -r /opt/crm-demo/. /opt/crm-demo-seed/
chown -R crmdemo:crmdemo /opt/crm-demo /opt/crm-demo-seed
```

## 5. CRM-Server als Dienst einrichten

Von deinem Mac die systemd-Dateien hochladen:

```bash
scp systemd/crm-demo.service systemd/crm-demo-reset.service systemd/crm-demo-reset.timer root@<Server-IP>:/etc/systemd/system/
scp reset_demo.sh root@<Server-IP>:/opt/crm-demo/reset_demo.sh
```

Auf dem Server:

```bash
chmod +x /opt/crm-demo/reset_demo.sh
chown crmdemo:crmdemo /opt/crm-demo/reset_demo.sh
systemctl daemon-reload
systemctl enable --now crm-demo.service
systemctl enable --now crm-demo-reset.timer
```

Prüfen ob der Server läuft:

```bash
systemctl status crm-demo.service
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8765/   # sollte 200 zeigen
```

## 6. Caddy installieren (Reverse Proxy + automatisches HTTPS + Passwort)

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

Passwort-Hash für den Demo-Zugang erzeugen (ersetze `DEIN-DEMO-PASSWORT`):

```bash
caddy hash-password --plaintext 'DEIN-DEMO-PASSWORT'
```

Den ausgegebenen Hash kopieren. Dann von deinem Mac die `Caddyfile` hochladen:

```bash
scp Caddyfile root@<Server-IP>:/etc/caddy/Caddyfile
```

Auf dem Server den Platzhalter-Hash in `/etc/caddy/Caddyfile` durch den echten Hash ersetzen (z. B. mit `nano /etc/caddy/Caddyfile`), dann:

```bash
systemctl reload caddy
```

## 7. Testen

Im Browser: `https://demo.digitalkonzepte.biz` öffnen. Login-Abfrage erscheint (Benutzername `demo`, das Passwort aus Schritt 6). Danach sollte das CRM-Dashboard mit den 8 Demo-Firmen, 8 Opportunities und 14 Aufgaben erscheinen.

## 8. Was passiert automatisch

- **Dienst-Ausfall:** `Restart=always` im systemd-Service startet `crm_server.py` bei einem Absturz sofort neu.
- **Server-Neustart:** Der Dienst startet automatisch mit (`enable`).
- **Demo-Reset:** Alle 4 Stunden (0/4/8/12/16/20 Uhr) werden Kontakte, Opportunities und Tasks auf den Ausgangsstand zurückgesetzt – manuell auch jederzeit möglich mit `sudo -u crmdemo /opt/crm-demo/reset_demo.sh`.

## Troubleshooting

| Problem | Prüfen mit |
|---|---|
| Seite lädt nicht | `systemctl status caddy`, `journalctl -u caddy -n 50` |
| Dashboard zeigt Fehler | `journalctl -u crm-demo.service -n 50` |
| Zertifikat wird nicht ausgestellt | DNS-Eintrag korrekt? `dig demo.digitalkonzepte.biz`; Ports 80/443 offen? `ufw status` |
| Reset läuft nicht | `systemctl list-timers \| grep crm-demo`, `cat /opt/crm-demo/reset.log` |

## Laufende Kosten

Nur der Server selbst (~5 €/Monat, Hetzner CX22). Caddy und die Zertifikate sind kostenlos. Den Server einfach löschen, sobald die Demo-Phase vorbei ist.
