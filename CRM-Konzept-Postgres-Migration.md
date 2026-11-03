---
type: konzept
titel: CRM-Konzept-Postgres-Migration
stand: 2026-09-11
---

# Wechsel von Markdown-Vault zu PostgreSQL

## Ausgangslage

Das CRM läuft heute auf Markdown-Dateien (Obsidian-Vault) plus `tasks.json`, geparst
über handgestrickte Regex-Funktionen in `crm_server.py`. Das hat in der Vergangenheit
zu echten Datenkorruptionen geführt (Parser-Bug vom 21.08.2026, 10 betroffene Dateien,
siehe `CRM-Konzept-Unternehmen-Personen-Projekte-Dashboard.md`). Außerdem gibt es
inzwischen drei parallele Codepfade (`crm_server.py`, `CGI-Demo-AllInkl`,
`CPX12-Generalprobe`) ohne gemeinsame Quelle.

## Entscheidung (2026-09-11, aktualisiert nach Ronalds Korrektur vom selben Tag)

- Umstieg auf PostgreSQL als Datenhaltung, Schema siehe `Migration-Postgres/schema.sql`.
- Externes Editieren über Obsidian entfällt vollständig — das Dashboard im Browser
  ist die alleinige Oberfläche.
- Es soll **keine lokale Laufzeitumgebung mehr geben**. Es gibt nur noch EINE
  gehostete, browserbasierte Instanz. Der bisherige lokale Betrieb von
  `crm_server.py` auf dem Mac (via launchd) wird aufgegeben.
- Der bestehende Hetzner-Testserver **CPX12** (46.225.13.130) wird zur
  Produktivinstanz aufgewertet — kein separater neuer Server.
- Basis wird der Codepfad `CPX12-Generalprobe/` (hat bereits ein Login-/Session-System),
  nicht `crm_server.py`. `CGI-Demo-AllInkl` bleibt unverändert reine Vertriebsdemo.
- Mehrnutzer-Zugriff (mehrere Personen gleichzeitig schreibend) war der Hauptgrund,
  SQLite als leichtere Alternative zu verwerfen — SQLite verträgt sich schlecht mit
  mehreren gleichzeitigen Schreibern plus Hintergrund-Workern (IMAP-Intake,
  ACOS-Sync), Postgres ist dafür gebaut.
- Zusätzlicher Nutzen gegenüber der alten Lösung: eine `audit_log`-Tabelle
  protokolliert künftig, wer wann was geändert hat — das ersetzt die
  Nachvollziehbarkeit, die ein Git-Repository geboten hätte (hier nie vorhanden).
- **Kein Angebote/Rechnungen-Modul im Schema.** `CPX12-Generalprobe/crm_serve.py`
  hält bereits fest, dass Angebote bewusst nicht Teil dieses Zielsystems sind
  (Entscheidung vom 2026-07-25, siehe `angebote_feature_crm.md`). Die erste
  Schema-Fassung hatte das Feature fälschlich aus `crm_server.py` übernommen —
  von Ronald am 11.09. korrigiert.
- **Aufgaben hängen zwingend an einem Projekt.** `tasks.projekt_id` ist NOT NULL.
  Eine Aufgabe wird im Kontext ihres Projekts angezeigt und dort bearbeitet, aber
  nicht als eigenständiges, projektloses Objekt angelegt. `firma_id`/`contact_raw`
  fliegen aus der `tasks`-Tabelle heraus, die Firmenzuordnung kommt ausschließlich
  über das Projekt. Die bisherige "Opportunities"-Tabelle heißt deshalb im Schema
  jetzt `projekte` (deckt sowohl Verkaufschancen als auch interne/administrative
  Arbeit ab, analog zum bereits bestehenden Sammelkunden `Kontakte/Firmen/Intern.md`).

## Praktisches Problem: SSH aus der Cloud-Sandbox

Claude arbeitet in dieser Cowork-Sitzung aus einer Cloud-Sandbox, die kein SSH
(Port 22) nach außen aufbauen kann — feste Netzwerkgrenze, kein Einzelfall
(siehe `CRM-Konzept-Email-Serverloesung.md`). Für die eigentliche Postgres-Installation
und den Umbau auf CPX12 braucht es aber SSH-Zugriff auf den Server.

**Ronalds Entscheidung:** Claude Code wird lokal auf seinem Mac installiert. Das ist
dieselbe KI, läuft aber mit dem normalen Netzwerkzugriff des Mac — kein SSH-Block.
Vorteil zusätzlich zur reinen Technik: Client-Daten (Namen, Kontaktdaten) müssen für
die eigentliche Migration nie durch die Cloud-Sandbox laufen, sondern bleiben
zwischen Mac und eigenem Server — passt zum bestehenden DSGVO-Anspruch des Projekts
(siehe `DSGVO-Compliance-Audit.md`).

## Phasenplan

1. **Schema-Entwurf** (erledigt, 2026-09-11): `Migration-Postgres/schema.sql`,
   abgeleitet aus den bestehenden Frontmatter-Feldern und `tasks.json`. Noch ohne
   Produktivdaten — reine Struktur.
2. **Claude Code lokal installieren** (Ronald, nächster Schritt): normale
   Terminal-Installation auf dem Mac, danach direkter SSH-Zugriff auf CPX12 möglich.
3. **Postgres auf CPX12 aufsetzen**, Schema deployen, `CPX12-Generalprobe`-Code auf
   Datenbankzugriffe statt Dateizugriffe umstellen (ersetzt die
   `parse_md_field`/`update_md_field`-Logik komplett).
4. **Importskript** schreiben und in einer Sandbox-Kopie gegen die echten
   Markdown-/JSON-Daten testen, bevor irgendetwas produktiv umgestellt wird
   (gleiches Vorgehen wie bisher: Kopie → Test → erst dann übernehmen).
5. **Cutover**: Dashboard läuft browserbasiert über CPX12/Postgres. Die
   bestehenden Markdown-Dateien werden nicht gelöscht, sondern als Archiv/Backup
   aufbewahrt.

## Offene Punkte

- Login-Rollenmodell (wer darf was) noch nicht im Detail festgelegt — Basis ist
  `manage_users.py` aus `CPX12-Generalprobe`.
- Domain/HTTPS für den produktiven Zugriff: `crm-test.ubrl.de` war als Testdomain
  vorgesehen, muss ggf. auf eine produktive Domain umgestellt werden.
- Backup-Strategie ändert sich von der bisherigen Nextcloud-md-Sicherung zu
  regelmäßigen `pg_dump`-Backups des Servers — noch nicht eingerichtet.
- **Migration der projektlosen Alt-Tasks — GEKLÄRT (2026-09-11):**
  Analyse von `tasks.json` (29 Tasks): nur 3 Opportunity-Dateien existieren
  im ganzen System, alle für Donau Drive. Tasks hängen aber an 8 verschiedenen
  echten Firmen und 9 Freitext-Werten ohne jede Akte. Beschlossene Lösung:
  1) Firmen mit Tasks, aber ohne passende Opportunity (STAHL Holding GmbH,
     Nexxivon AG, Trufflepig IT-Forensics GmbH, Liscia Consulting GbR,
     Freiberger Steuerberatungsgesellschaft mbH, David Gagliardi) bekommen
     beim Import automatisch ein generisches Projekt, Arbeitstitel
     "<Firma> – laufende Betreuung".
  2) Von den 9 Freitext-Werten ohne Firmenakte (Intern / DK Marketing [3x],
     MGM, Denise, Hopfner/VR, Admin, ACN, Projektträger, Jehra, Offen) sind
     8 Einzelfälle bereits als "Erledigt" markiert — die wandern gesammelt in
     EIN Archiv-Projekt "Altvorgänge vor CRM-Umstellung" (kein firma_id nötig,
     `projekte.firma_id` ist nullable). Das schließt "Projektträger"/"GAGL ZIM
     Projekt" mit ein, obwohl das nach einem echten ZIM-Fördervorgang aussieht
     — Ronald hat sich bewusst für den einfachen Sammeltopf entschieden.
  3) "Intern / DK Marketing" bekommt ein eigenes Projekt "DK Marketing" unter
     der Firma "Intern" (Akte existiert bereits seit 21.08.2026), weil eine der
     drei Aufgaben (MKT-003, KI-Video-Template) noch offen ist und DK Marketing
     ohnehin ein laufendes Thema ist (siehe Ronalds persönliche Notiz
     areas/dk-marketing).
- **Wo genau Aufgaben künftig erstellt werden** (wenn nicht als eigenständiges
  Objekt unterhalb eines beliebigen Projekts), ist noch nicht im Detail
  festgelegt — Teil der Anwendungslogik in Phase 3, nicht mehr Teil des reinen
  Datenschemas.
- Verbleib des Angebote-Features (nur weiter auf dem Mac/`crm_server.py`? eigenes
  kleines Tool?) ist offen — nur klar, dass es nicht ins Postgres-Schema wandert.
