# CRM – Digitale Konzepte e. K.

Quellcode des eigenentwickelten CRM-Systems. Betrieb auf einem Hetzner-Server (CPX12),
Datenhaltung in PostgreSQL, Bedienung ausschließlich über den Browser.

---

## Wichtig: Was hier nicht hineingehört

Dieses Repository enthält **nur Code und Konzepte**. Niemals hinein gehören:

- **Zugangsdaten** – IMAP-Passwörter, API-Schlüssel, Datenbank-Passwörter.
  Sie liegen in `secrets/mail.env` auf dem jeweiligen Server und sind per
  `.gitignore` ausgeschlossen. Vorlage: `mail.env.example`.
- **Mandantendaten** – Kontakte, Projekte, Aktivitäten, Aufgaben, Angebote.
  Diese liegen in der Postgres-Datenbank beziehungsweise in der alten
  Markdown-Ablage im übergeordneten Ordner, außerhalb dieses Repositorys.

Die erfundenen Beispielfirmen unter `Demo-Deployment/vault/` sind Testdaten
für die Vorführung und keine echten Mandanten.

Vor jedem `git add .` lohnt ein Blick auf `git status`. Was einmal committet und
hochgeladen wurde, lässt sich nachträglich kaum noch sauber aus der Historie entfernen.

---

## Aufbau

| Ordner | Inhalt |
|---|---|
| `CPX12-Postgres/` | **Live.** Der Code, der auf dem CPX12 unter `/opt/crm` läuft: `crm_core.py`, `crm_serve.py`, `mail_poller.py`, `kalender.py`, `wissen_sync.py`, `acos_sync.py`, `tagesabschluss.py`, `manage_users.py`, systemd-Units, Caddy-Konfiguration. Stand: Umbau 14 plus Kundenwissen mit ACOS-Dokumenten (03.11.2026). |
| `CPX12-Generalprobe/` | Alter Markdown-Stand. Wird nur noch von der Vorführ-Instanz gebraucht, siehe unten. |
| `Migration-Postgres/` | Schema, Migrationen 002–023 (`migration_NNN_<thema>.sql`, in Nummernfolge einspielen), Importskript, Einrichtungs- und Testskripte (`smoke_test.py`, `test_kundenwissen_acos.py`). |
| `Demo-Deployment/` | Vorführ-Server mit automatischem Zurücksetzen, mit erfundenen Beispieldaten. Läuft noch auf dem Markdown-Code. |
| `archiv/` | Dokumente, die den alten Markdown-Aufbau beschreiben. Inhaltlich noch brauchbar, aber nicht mehr der aktuelle Stand. |
| `setup_test_server.sh` | Grundeinrichtung des Servers. Wird von `Migration-Postgres/setup_postgres.sh` vorausgesetzt. |

---

## Einrichtung auf einem Server

1. Repository klonen.
2. `mail.env.example` nach `secrets/mail.env` kopieren und ausfüllen.
3. `config.json` prüfen – sie enthält keine Geheimnisse, verweist aber auf
   `secrets/mail.env` und auf die Umgebungsvariable für den LLM-Schlüssel.
4. Datenbank nach `Migration-Postgres/DEPLOY-Postgres.md` einrichten.

---

## Arbeitsweise

Es wird **nichts direkt am Live-Server geändert**. Änderungen entstehen in einer
Sandbox-Kopie, werden dort getestet (`py_compile`, isolierte Tests) und erst danach
ausgerollt.

Am Ende jeder Arbeitssitzung committen und hochladen – sonst ist die Rücksicherung
irgendwann Monate alt und der Server längst weiter.

Ausgeliefert wird derzeit per `scp` mit Prüfsummenvergleich; die Schritte stehen je Änderung in
`NAECHSTES-UPDATE.md`. Später soll sich der Server seinen Stand per `git pull` holen
(`DEPLOY-Git-CPX12.md`). Dieses Repository ist die einzige Quelle für den Code – der frühere
Arbeitsordner `~/crm-umbau` ist seit 03.11.2026 Archiv.

---

## Anleitungen

- `DEPLOY-Git-CPX12.md` – Deploy Key einrichten, Repository auf den Server
  klonen, Auslieferung per `git pull`
- `Migration-Postgres/DEPLOY-Postgres.md` – Umstieg der Datenhaltung auf
  PostgreSQL, Schritt für Schritt

## Konzeptdokumente

- `CRM-Konzept-Postgres-Migration.md` – Umstellung von Markdown auf PostgreSQL
- `CRM-Konzept-ACOS-Anbindung.md` – Verknüpfung mit der Beratungsplattform ACOS
- `CRM-Konzept-Email-Serverloesung.md` – Mailanbindung und Serverbetrieb
- `CRM-Konzept-Unternehmen-Personen-Projekte-Dashboard.md` – Datenmodell und Oberfläche

Im `archiv/` liegen die Systemdokumentation und die Datenschutzbetrachtung zum
Markdown-Aufbau. Beide stammen aus der Zeit vor der Postgres-Entscheidung – die
Datenschutzbetrachtung gehört nach der Umstellung neu gemacht.

---

## Offen: Vorführ-Instanz

Die Demo unter `Demo-Deployment/` läuft auf `crm_server.py`, also auf dem alten
Markdown-Code, und soll später als zweite Instanz neben dem Produktivsystem auf
dem CPX12 laufen. Solange sie auf dem alten Code läuft, muss dieser gepflegt
werden – und `CPX12-Generalprobe/` bleibt im Repository.

Geplant ist deshalb, auch die Demo auf Postgres zu holen: eigene Datenbank
`crm_demo`, eigene Postgres-Rolle ohne Zugriff auf die Produktivdaten, und der
Reset läuft über `import_data.py` gegen den Seed-Ordner statt über das
Zurückkopieren von Dateien. Danach gibt es nur noch einen Codestand, und die
Demo zeigt automatisch die aktuelle Fassung.

Zu beachten bei der Umsetzung: Es gibt zwei Caddy-Konfigurationen im
Repository, die beide beanspruchen, *die* Caddyfile zu sein. Auf dem Server
gibt es nur eine – sie müssen zu einer Datei mit zwei Blöcken zusammengeführt
werden.

Reihenfolge: erst der Produktivumzug, dann die Demo, dann kann
`CPX12-Generalprobe/` weg.

## Historie

Der erste Commit (`8ace15c`) enthielt zusätzlich die ursprüngliche lokale
Markdown-Fassung, das Angebotsmodul und eine zweite Vorführ-Variante als CGI.
Alles davon ist über die Historie weiterhin erreichbar, aber nicht mehr Teil
des aktuellen Stands.
