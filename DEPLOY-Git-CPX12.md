---
type: anleitung
title: CRM – Auslieferung per Git auf den CPX12
stand: 2026-11-03
---

# Auslieferung per Git statt per Dateikopie

> **Stand 03.11.2026:** Das Repository heißt jetzt `crm-code` (privat, ein
> Erst-Commit ohne alte Historie). Der frühere Name `crm` gilt nicht mehr.
> Der Server liefert bis zur Umstellung weiter per `scp` aus; dieses Dokument
> beschreibt den Weg, sobald der Server auf Git wechselt. Das Repository
> enthält keine Demo-Mandanten und keine Zugangsdaten. Die Demo-Daten
> (`Demo-Deployment/vault/Kontakte`, `Opportunities`, `tasks.json`) liegen
> nur lokal.

Bisher wurde Code per `scp` auf den Server geschoben. Das hat drei Nachteile:
Man sieht hinterher nicht, was tatsächlich draufliegt, eine Rücksicherung gibt
es nicht, und die Dateirechte muss man jedes Mal von Hand nachziehen – daran
ist das Postgres-Setup schon einmal hängengeblieben.

Mit dem Repository `github.com/rl08154711/crm-code` wird daraus: Der Server holt
sich den Stand selbst, und `git status` sagt jederzeit, ob jemand direkt am
Live-System herumgeschraubt hat.

---

## Warum ein Deploy Key

Das Repository ist privat, der Server muss sich also ausweisen. Dafür gibt es
bei GitHub den **Deploy Key**: ein Schlüssel, der nur für dieses eine
Repository gilt – nicht für das ganze Konto, wie es ein Zugriffstoken täte.

Der Haken bei **„Allow write access" bleibt leer.** Der Server soll holen
dürfen, nicht schieben. Selbst wenn jemand den Schlüssel vom Server stiehlt,
kann er damit nichts verändern.

---

## Aufteilung auf dem Server

| Pfad | Inhalt |
|---|---|
| `/opt/crm-repo` | Klon des Repositorys. Der Code, der künftig läuft. |
| `/opt/crm` | Die bisherige Installation: alter Code, die Markdown-Altdaten, `secrets/`. Bleibt als Rückfallposition liegen. |

Die Dienste zeigen nach der Umstellung auf `/opt/crm-repo/CPX12-Postgres/`.
Die Unit-Dateien im Repository geben bis dahin den Live-Stand wieder und zeigen auf
`/opt/crm` (abgeglichen 03.11.2026). Bei der Umstellung in `crm.service`,
`crm-mailpoll.service` und den Timer-Diensten `WorkingDirectory` und `ExecStart` auf
`/opt/crm-repo/CPX12-Postgres/` ändern und `systemctl daemon-reload` ausführen.
Bewusst kein Symlink von `/opt/crm` dorthin: Ein `systemctl status crm` soll
ohne Umweg zeigen, welche Datei tatsächlich läuft.

---

## Einmalige Einrichtung

### 1. Vorab auf dem Server prüfen

```
id crmapp                      # existiert der Dienst-Nutzer?
getent passwd crmapp           # hat er ein Home-Verzeichnis?
ssh -T git@github.com          # kommt der Server ueberhaupt zu GitHub durch?
```

Bei `ssh -T` ist die Antwort „Permission denied (publickey)" an dieser Stelle
das erwartete Ergebnis – sie beweist, dass die Verbindung steht. Kommt
stattdessen eine Zeitüberschreitung, ist Port 22 nach außen dicht; dann in
`~/.ssh/config` zusätzlich `Hostname ssh.github.com` und `Port 443` setzen,
das bietet GitHub eigens dafür an.

Hat `crmapp` kein Home-Verzeichnis oder keine Login-Shell, gehören Schlüssel
und Klon stattdessen root, und nach jedem `git pull` folgt ein
`chown -R crmapp:crmapp /opt/crm-repo`. Sauberer ist die Variante unten.

### 2. Schlüsselpaar erzeugen

```
sudo -u crmapp ssh-keygen -t ed25519 -f /home/crmapp/.ssh/github_deploy -N "" -C "cpx12-deploy"
sudo -u crmapp cat /home/crmapp/.ssh/github_deploy.pub
```

Die ausgegebene Zeile wird gleich gebraucht. Der private Teil
(`github_deploy` ohne `.pub`) bleibt auf dem Server und wird nirgendwo
eingefügt – auch nicht in einen Chat.

### 3. Schlüssel bei GitHub eintragen

Auf `github.com/rl08154711/crm-code` → **Settings** → **Deploy keys** →
**Add deploy key**. Titel etwa „CPX12", in das große Feld die eben
ausgegebene Zeile. **Allow write access bleibt aus.** Speichern.

### 4. SSH-Konfiguration

```
sudo -u crmapp tee -a /home/crmapp/.ssh/config >/dev/null <<'EOF'
Host github.com
  IdentityFile /home/crmapp/.ssh/github_deploy
  IdentitiesOnly yes
EOF
sudo -u crmapp chmod 600 /home/crmapp/.ssh/config
```

Probe:

```
sudo -u crmapp ssh -T git@github.com
```

Erwartet: „Hi rl08154711/crm-code! You've successfully authenticated, but GitHub
does not provide shell access." Das ist der Erfolgsfall.

### 5. Klonen

```
mkdir -p /opt/crm-repo && chown crmapp:crmapp /opt/crm-repo
sudo -u crmapp git clone git@github.com:rl08154711/crm-code.git /opt/crm-repo
```

### 6. Zugangsdaten einmalig ablegen

`secrets/mail.env` ist bewusst nicht im Repository. Einmal anlegen:

```
sudo -u crmapp mkdir -p /opt/crm-repo/CPX12-Postgres/secrets
sudo -u crmapp cp /opt/crm/secrets/mail.env /opt/crm-repo/CPX12-Postgres/secrets/
sudo -u crmapp chmod 600 /opt/crm-repo/CPX12-Postgres/secrets/mail.env
```

Weil Git die Datei ignoriert, überlebt sie jeden künftigen `git pull`
unangetastet. Genau dafür war die Trennung gedacht.

---

## Auslieferung im Alltag

Nach jeder Änderung, die auf dem Mac committet und hochgeladen wurde:

```
sudo -u crmapp git -C /opt/crm-repo pull
systemctl restart crm crm-mailpoll
systemctl status crm --no-pager
```

Das war es. Keine Dateikopien, keine Rechte-Korrekturen.

---

## Was Git auf dem Server sichtbar macht

```
sudo -u crmapp git -C /opt/crm-repo status
```

Meldet „nothing to commit, working tree clean", läuft exakt der Stand, der
auch im Repository steht. Werden Dateien als geändert angezeigt, hat jemand
direkt am Server gearbeitet – und du siehst mit
`git -C /opt/crm-repo diff` genau was.

Vorher war das eine Vermutung, jetzt ist es eine Auskunft.

---

## Zurück auf einen früheren Stand

```
sudo -u crmapp git -C /opt/crm-repo log --oneline | head
sudo -u crmapp git -C /opt/crm-repo checkout <commit>
systemctl restart crm
```

Zurück auf aktuell: `git -C /opt/crm-repo checkout main`.

Die Altinstallation unter `/opt/crm` bleibt daneben liegen, solange die
Umstellung nicht über Wochen stabil gelaufen ist.
