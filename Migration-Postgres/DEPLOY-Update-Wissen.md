# Ausrollen: Wissens-DB (DK-Wissen) und Kompaktansicht-Knopf

Stand 2026-10-19. Baut auf „Teil 2“ auf (live seit 19.10.2026, Commit 086e963).

**Was neu ist**
- Reiter „📚 Wissen“: Volltextsuche über `Fachwissen` und `Vorlagen` aus dem Vault
  DK-Wissen (Nextcloud). Treffer mit Textauszug, Öffnen der Datei, Link in Nextcloud.
- Stündlicher Abgleich (systemd-Timer `crm-wissen.timer`) plus Knopf „Jetzt abgleichen“.
- Texterkennung für gescannte PDFs und Screenshots (deutsch + englisch).
- Namensprüfung: Dokumente, in denen Firmen- oder Personennamen aus dem CRM vorkommen,
  werden mit ⚠ markiert (bleiben suchbar).
- Handy: Knopf „📱 Kompaktansicht“ in der Vollansicht, Kopfzeile bricht um.

**Neu/geändert:** `crm_core.py`, `crm_serve.py`, neu `wissen_sync.py`, `crm-wissen.service`,
`crm-wissen.timer`. **Datenbank:** Migration 005 (zwei neue Tabellen, rein additiv).
**Pakete:** `poppler-utils`, `tesseract-ocr`, `tesseract-ocr-deu`.

Server: `root@46.225.13.130`. `[Mac]` = Terminal auf dem Mac, `[Server]` = nach
`ssh root@46.225.13.130`. Befehle einzeln einfügen, möglichst per Kopieren.

### 0 – Ausgangsstand prüfen

```bash
# [Server]
cd /opt/crm && sha1sum crm_core.py crm_serve.py
```
Erwartet:
```
2ce9021166e6db71a4065d0dc69d945098a51826  crm_core.py
b0ddaff7c413be9200e69b526eb75c17a0af3996  crm_serve.py
```

### 1 – Pakete für Texterkennung

```bash
# [Server]
apt update && apt install -y poppler-utils tesseract-ocr tesseract-ocr-deu
tesseract --list-langs
```
In der Liste muss `deu` stehen.

### 2 – Hochladen

```bash
# [Mac]
cd ~/Documents/Claude/Projects/CRM/crm-code
git branch --show-current          # feature/naechstes-update
ssh root@46.225.13.130 "mkdir -p /tmp/crm-update"
scp CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/wissen_sync.py CPX12-Postgres/crm-wissen.service CPX12-Postgres/crm-wissen.timer Migration-Postgres/migration_005_wissen.sql root@46.225.13.130:/tmp/crm-update/
```

```bash
# [Server]
chmod 644 /tmp/crm-update/*
cd /tmp/crm-update && sha1sum crm_core.py crm_serve.py wissen_sync.py
```
Erwartet:
```
874f7873a5a6d446af0936fa52509daa7027605f  crm_core.py
4de760c82a82db950f8e1e94795b52a3210738f9  crm_serve.py
8d6b9c1b406b40ba8714ff5cd75f3051fa6ed7c2  wissen_sync.py
```

### 3 – Probelauf, Sicherung, Migration

```bash
# [Server]
sudo -u crmapp psql -d crm_test -f /tmp/crm-update/migration_005_wissen.sql
sudo -u crmapp pg_dump -Fc crm > /root/crm-vor-wissen_$(date +%F_%H%M).dump
mkdir -p /root/crm-code-vor-wissen && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /root/crm-code-vor-wissen/
sudo -u crmapp psql -d crm -f /tmp/crm-update/migration_005_wissen.sql
```
Bei beiden Migrationen: zweimal `CREATE TABLE`, einmal `CREATE INDEX`, kein `ERROR`.

### 4 – Code und Dienste einspielen

```bash
# [Server]
cp /tmp/crm-update/crm_core.py /tmp/crm-update/crm_serve.py /tmp/crm-update/wissen_sync.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/wissen_sync.py
cp /tmp/crm-update/crm-wissen.service /tmp/crm-update/crm-wissen.timer /etc/systemd/system/
systemctl daemon-reload
cd /opt/crm && sha1sum crm_core.py crm_serve.py wissen_sync.py
```
Die Prüfsummen müssen jetzt den neuen Werten aus Schritt 2 entsprechen.

### 5 – Zugang zu Nextcloud hinterlegen

Das App-Passwort von `wissen-sync` wird verdeckt abgefragt und landet nicht in der
Befehlshistorie:

```bash
# [Server]
install -m 600 -o crmapp -g crmapp /dev/null /opt/crm/secrets/wissen.env
read -s -p "App-Passwort wissen-sync: " PW; echo
printf 'WEBDAV_URL=https://nx89264.your-storageshare.de/remote.php/dav/files/wissen-sync/DK-Wissen/\nWEBDAV_USER=wissen-sync\nWEBDAV_PASSWORD=%s\nNEXTCLOUD_WEB=https://nx89264.your-storageshare.de/apps/files/files?dir=/DK-Wissen\n' "$PW" > /opt/crm/secrets/wissen.env; unset PW
ls -l /opt/crm/secrets/wissen.env
```
Erwartet: `-rw------- 1 crmapp crmapp`.

### 6 – Erster Abgleich von Hand

```bash
# [Server]
sudo -u crmapp python3 /opt/crm/wissen_sync.py erstlauf
```
Am Ende steht `Abgleich beendet: {'neu': …} ok`. Bei vielen Scans kann der erste Lauf
einige Minuten dauern; was nicht fertig wird, steht unter `offen` und kommt im nächsten Lauf.

### 7 – Neu starten, Timer einschalten

```bash
# [Server]
systemctl restart crm crm-mailpoll
systemctl enable --now crm-wissen.timer
systemctl list-timers crm-wissen.timer --no-pager
systemctl status crm --no-pager
```

Im Browser (`Cmd + Shift + R`): Reiter „📚 Wissen“, Suche ausprobieren, eine Datei öffnen.

Aufräumen: `rm -r /tmp/crm-update`

## Rückweg

```bash
# [Server]
systemctl disable --now crm-wissen.timer
cp /root/crm-code-vor-wissen/* /opt/crm/ && chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py
systemctl restart crm crm-mailpoll
```
Die neuen Tabellen stören den alten Code nicht.
