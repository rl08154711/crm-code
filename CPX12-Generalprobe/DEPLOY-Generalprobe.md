---
type: anleitung
title: CRM – Deployment auf den Hetzner-Testserver (Generalprobe)
stand: 2026-08-03
server: 46.225.13.130 (Hetzner CPX12, Wegwerf-Server für die Generalprobe)
---

# Was in diesem Paket steckt

- `opt-crm/` – kompletter Inhalt für `/opt/crm` auf dem Server (Business-Logik + Kontakt-Testdaten)
- `crm.service` – systemd-Unit, macht den Server dauerhaft laufend (Neustart bei Absturz)
- `Caddyfile` – Reverse Proxy mit HTTPS über `crm-test.ubrl.de` (echtes Let's-Encrypt-Zertifikat, sobald der DNS-A-Record steht) – Login läuft jetzt über die App selbst, nicht mehr über Caddy Basic-Auth
- `manage_users.py` – legt den Login-Nutzer für die App direkt auf dem Server an (siehe Schritt 4)
- `setup_test_server.sh` – einmaliges Grundsetup (Pakete, Caddy-Repo, `crmapp`-Nutzer, Firewall)

Ich habe beim Durchgehen zwei Lücken gefunden und direkt behoben, bevor das Paket auf den Server geht:

1. **Restart-/Stop-Buttons im Dashboard** riefen `/api/server/restart` und `/api/server/shutdown` auf – die gab es in `crm_serve.py` (systemd-Variante) noch gar nicht, das hätte im Betrieb einen 404-Fehler gegeben. Jetzt nachgerüstet und lokal getestet: Restart läuft sauber durch (Prozess bleibt unter derselben PID am Leben, systemd merkt nichts davon), Stop beendet den Dienst sauber. Wichtig zu wissen: Ein "Stop"-Klick startet sich **nicht** von selbst neu (`Restart=on-failure` greift nur bei Abstürzen, nicht bei einem sauberen Stop) – danach muss auf dem Server `systemctl start crm` ausgeführt werden. Das ist so gewollt (echtes Stoppen), aber gut zu wissen, falls der Button aus Versehen gedrückt wird.
2. Der "⧉ Open"-Button öffnete hartcodiert `localhost:8765` (Rest eines alten macOS-Testaufbaus) – das hätte auf dem Server nie funktioniert. Jetzt öffnet er die aktuelle Adresse, egal wo das Dashboard läuft.

Beide Dateien (`crm_core.py`, `crm_serve.py`) habe ich danach mit `python3 -m py_compile` geprüft und den Server lokal hochgefahren – Dashboard, `/api/tasks`, Restart und Stop laufen alle wie erwartet.

---

# Schritt für Schritt auf dem Server

### 1. Erstes Grundsetup (einmalig, als root über die Hetzner-Konsole oder SSH)

Inhalt von `setup_test_server.sh` in die Konsole einfügen und ausführen. Das installiert Python, Caddy, legt den Nutzer `crmapp` an und öffnet die Firewall für 22/80/443.

### 2. Dateien hochladen

Mit FileZilla (oder `scp`) auf den Server:

- kompletten Inhalt von `opt-crm/` nach `/opt/crm/` auf dem Server
- `crm.service` nach `/etc/systemd/system/crm.service`
- `Caddyfile` nach `/etc/caddy/Caddyfile`

Danach Besitzrechte setzen, damit der unprivilegierte `crmapp`-Nutzer (kein Login, kein root) darauf zugreifen kann:

```
chown -R crmapp:crmapp /opt/crm
```

### 3. Dienste starten

```
systemctl daemon-reload
systemctl enable --now crm
systemctl restart caddy
systemctl status crm
```

`systemctl status crm` sollte "active (running)" zeigen. Falls nicht: `journalctl -u crm -n 50` gibt die Fehlermeldung aus.

### 4. Login-Nutzer anlegen (einmalig, auf dem Server)

Der Basic-Auth-Login aus dem alten Caddyfile ist entfallen – die App hat jetzt eine eigene Login-Seite (Konzept 2.6, Punkt 4a). Das Passwort dafür bitte direkt auf dem Server per SSH setzen, nicht über den Chat – **wichtig: als `crmapp`, nicht als `root`** (sonst gehört die neu angelegte Datei root, und der Dienst – der als `crmapp` läuft – kann sie danach nicht mehr lesen):

```
cd /opt/crm
sudo -u crmapp python3 manage_users.py add ronald
```

Fragt zweimal nach dem Passwort (nichts wird beim Tippen angezeigt), speichert nur einen PBKDF2-Hash in `secrets/users.json` und testet den Login direkt gegen – kein Neustart nötig. Falls du es doch als `root` ausgeführt hast, meldet das Skript das jetzt explizit und nennt den Befehl zum Nachbessern (`chown -R crmapp:crmapp secrets`).

### 5. Aufrufen

Im Browser: `https://crm-test.ubrl.de` (siehe Caddyfile – setzt voraus, dass der A-Record `crm-test` → `46.225.13.130` bei ubrl.de bereits gesetzt und propagiert ist, siehe Hinweis oben). Caddy holt sich dafür automatisch ein echtes Let's-Encrypt-Zertifikat, keine Zertifikatswarnung mehr. Dann Login mit dem gerade angelegten Nutzer.

Im Dashboard sollte die Testfirma "STAHL Holding GmbH" mit Ansprechpartner "Ruprecht Bauer" auftauchen – das bestätigt, dass Kontaktdaten korrekt eingelesen werden.

### 6. Was die Generalprobe zeigen soll

- Dashboard lädt über HTTPS mit echtem Zertifikat (keine Browser-Warnung) und eigener Login-Seite
- Nach Logout bzw. abgelaufener Session (12h) landet man automatisch wieder auf der Login-Seite
- Kontakte/Aufgaben/Pipeline werden angezeigt
- Neuanlage/Bearbeitung eines Kontakts oder einer Aufgabe funktioniert und bleibt nach Reload erhalten
- Restart-Button: Seite lädt nach ein paar Sekunden neu, Dashboard bleibt erreichbar, Login-Session bleibt erhalten (Cookie überlebt den Neustart)
- Server übersteht einen Reboot des Servers (`reboot` in der Konsole, nach ca. 30 Sek. `https://crm-test.ubrl.de` erneut aufrufen – sollte ohne manuellen Eingriff wieder laufen, da `systemctl enable` den Autostart aktiviert)

Sobald das alles durchläuft, wiederholen wir denselben Ablauf 1:1 auf dem echten netcup-Produktivserver (siehe Checkliste, Punkt 2) – nur mit dem dortigen Domainnamen statt `crm-test.ubrl.de`.
