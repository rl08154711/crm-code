---
type: dokumentation
title: CRM-System-Dokumentation
stand: 2026-07-07
---

# CRM-System-Dokumentation

Diese Dokumentation beschreibt den aktuellen, technischen Ist-Zustand des CRM (nicht die ursprüngliche Konzeptidee aus `Obsidian-CRM-mit-DSGVO.md`). Stand: 07.07.2026, Datenbestand 19 Firmen, 23 Personen, 2 aktive Opportunities, 24 Tasks (3 offen, 21 erledigt).

---

## 1. Wo liegen die Daten

**Speicherort:** Lokal auf deinem Rechner, im Ordner `/Users/rl/Documents/Claude/Projects/CRM/` – ein Obsidian-Vault aus einzelnen Markdown-Dateien. Keine Cloud, kein externer Server, kein Git-Repository.

Struktur:

| Ordner/Datei | Inhalt |
|---|---|
| `Kontakte/Firmen/` | 19 Firmenprofile (1 Datei pro Firma, Markdown mit YAML-Frontmatter: Status, Branche, Quelle, last_contact) |
| `Kontakte/Personen/` | 23 Ansprechpartner (verlinkt per `firma:` Feld auf die Firmendatei) |
| `Kontakte/_Backup_pre_migration/` | Alte Kontaktdateien vor der Firmen/Personen-Trennung, unverändert aufbewahrt |
| `Opportunities/` | Verkaufschancen, verlinkt auf Kontakt |
| `Opportunities/_Archiv/` | Abgeschlossene/verworfene Opportunities |
| `Aktivitäten/` | Seit 09.08.2026 für den Sichtbarkeits-Sync (Abschnitt 5) befüllt, pro Mandant/Monitoring-Woche eine Datei; ansonsten weiterhin kaum genutzt |
| `Projekte/` | Angelegt, aktuell leer (keine laufenden Projekte erfasst) |
| `Datenbank/consent-register.md`, `dsgvo-log.md` | DSGVO-Register – Struktur vorhanden, aber nicht befüllt |
| `Dashboard/` | Drei manuell zu pflegende Übersichtsdateien (Pipeline, Wochenplanung, KPIs) – aktuell leere Templates |
| `tasks.json` | Die eigentliche Aufgaben-Datenbank (24 Tasks), JSON statt Markdown |
| `Dashboard.html` | Generierte, interaktive Übersichtsseite (siehe Abschnitt 3), inkl. Aktivitäten-Log-Drawer je Firma |

Sensible Daten (E-Mail, Telefon) liegen **direkt in den Markdown-Dateien**, nicht ausgelagert – die in den Konzeptdokumenten empfohlene Trennung über Bitwarden/1Password ist nicht umgesetzt.

---

## 2. Welche Prozesse sind relevant

**Lead-/Kontakt-Erfassung:** Neue Firma → Datei in `Kontakte/Firmen/`, zugehörige Person → Datei in `Kontakte/Personen/` mit Link zurück zur Firma.

**Opportunity-Tracking:** Pro Verkaufschance eine Datei in `Opportunities/`, Status (`aktiv`, `won`, `lost`, ...), Wert, Wahrscheinlichkeit, nächste Aktion, Deadline im Frontmatter.

**Task-Tracking:** Alle Aufgaben zentral in `tasks.json` (nicht als Markdown) – mit Kategorie (Kundenakquise, Projektmanagement, Administrativ, Follow-up), Priorität (automatisch aus Deadline berechnet), Status, Abhängigkeiten (`blockedBy`/`blocks`).

**Tägliches Morgen-Briefing (08:00 Uhr):** Ein Scheduled Task (`crm-task-briefing-midday`) ist eingerichtet, um Dashboard.html zu regenerieren und einen Report zu kritischen/überfälligen Tasks auszugeben – **ist aktuell deaktiviert** (`enabled: false`), letzter Lauf 03.07.2026. Das entspricht der Projektvorgabe "Tracking zyklisch 8:00 Uhr", läuft aber gerade nicht automatisch.

**DSGVO-Prozess:** Consent-Register und DSGVO-Log als Struktur angelegt (Erfassung, Auskunft/Löschung, Löschungen, monatliche Überprüfung), aber inhaltlich leer – für keinen der 19 Kontakte ist bislang ein Konsent-Eintrag vorhanden.

**Aktivitäten-Log:** Der ursprünglich vorgesehene Weg (eigene Markdown-Dateien im Ordner `Aktivitäten/`) war lange ungenutzt und wird seit 09.08.2026 für den Sichtbarkeits-Sync bespielt (siehe Abschnitt 5). Für alles andere gibt es seit 07.07.2026 zusätzlich ein Log direkt im Dashboard (`crm_server.py`): In den Tabs **Kontakte** und **Pipeline** öffnet ein Klick auf eine Zeile einen Log-Drawer, in dem freie Text-Einträge mit Datum erfasst werden können.
- **Schlüssel ist die Firma** – Kontakt- und Pipeline-Einträge derselben Firma landen im selben Log, unabhängig davon, aus welchem Tab sie angelegt wurden.
- Jeder Eintrag trägt ein **Quell-Tag**, das erkennen lässt, woher er stammt: „👤 Kontakt" oder „📈 Pipeline". Bei Pipeline-Einträgen wird zusätzlich der **Name der Opportunity** angezeigt (z. B. „📈 Pipeline · DonauDrive interims management"), da eine Firma mehrere parallele Pipelines/Opportunities haben kann.
- **Wichtige Einschränkung:** Die Einträge werden im `localStorage` des Browsers gespeichert, **nicht** als Markdown-Datei im Vault. Sie sind also nicht Teil des Backups, nicht geräteübergreifend verfügbar und gehen verloren, wenn der Browser-Speicher geleert wird oder ein anderer Browser/Rechner verwendet wird. Die neuen `Aktivitäten/`-Dateien aus dem Sichtbarkeits-Sync haben dieses Problem nicht (echte, gesicherte Markdown-Dateien) – erscheinen aber (Stand 09.08.2026) noch **nicht** im Dashboard/Log-Drawer, da dieser bislang nur `localStorage` liest.

---

## 3. Wie erfolgt die Bearbeitung

Es gibt drei Wege, Daten zu ändern:

1. **CRM-Dashboard im Browser (`crm_server.py`)** – lokaler Webserver unter `http://localhost:8765`. Läuft als macOS-Hintergrunddienst (`launchd`, definiert in `com.digitalkonzepte.crm.plist`, `RunAtLoad` + `KeepAlive` = startet automatisch beim Anmelden und bleibt aktiv). Bietet Tabs für Aufgaben, Kontakte, Pipeline mit Bearbeiten-Modals, die direkt in die Markdown-Dateien bzw. `tasks.json` zurückschreiben (REST-API, u. a. `PUT /api/opportunities/...`). Beim Anlegen einer Aufgabe stehen im Ansprechpartner-Feld alle Ansprechpartner der ausgewählten Firma zur Auswahl (nicht mehr nur der erste). Das ist der primäre Weg für Tagesgeschäft.

2. **Kommandozeilen-Skripte:**
   - `crm_add.py "Freitext"` – erkennt automatisch, ob Kontakt/Opportunity/Task gemeint ist, und legt die passende Datei/den Eintrag an.
   - `task_cli.py` – Status ändern, Tasks anlegen/auflisten (`status`, `complete`, `add`, `list`, `show`, `report`).
   - `task_report.py` – erzeugt Text-Briefings (abgelegt unter `reports/`).
   - `validate_tasks.py` – prüft `tasks.json` auf Duplikate, ungültige Status/Prioritäten, unplausible Deadlines und schreibt die Metadaten neu.
   - `generate_dashboard.py` – baut `Dashboard.html` aus den aktuellen Markdown-/JSON-Daten neu (wird auch vom 08:00-Uhr-Job aufgerufen).
   - `migrate_contacts.py` – Einmal-Migrationsskript (bereits ausgeführt), das die alte flache Kontaktstruktur in `Firmen/`+`Personen/` aufgeteilt und die Originale nach `_Backup_pre_migration/` kopiert hat.

3. **Direkte Markdown-Bearbeitung** in Obsidian oder einem Texteditor – jederzeit möglich, da es sich um reine Textdateien handelt, wird aber vom Server nicht "live" erkannt (Neuladen nötig).

Server-Steuerung: Start über `start_crm.sh` bzw. automatisch per `launchd`; im Dashboard selbst gibt es Buttons zum Neustarten/Stoppen des Servers.

---

## 4. Wie ist das Backup-Konzept

**Ist-Zustand: automatisiertes Backup vorbereitet, Aktivierung durch dich noch ausstehend.** Seit 07.07.2026 liegen im CRM-Ordner:
- `backup_to_nextcloud.sh` – erstellt ein `tar.gz`-Archiv des gesamten CRM-Ordners und lädt es per WebDAV in einen dedizierten Nextcloud-Account hoch, der ausschließlich für das CRM-Backup existiert (Benutzer `Backup`, Zielverzeichnis = Hauptverzeichnis dieses Accounts). Ältere Archive werden automatisch gelöscht (Aufbewahrung: 30 Tage). Läuft/protokolliert nach `nextcloud-backup.log`.
- `com.digitalkonzepte.crm-nextcloud-backup.plist` – launchd-Job, der das Skript wöchentlich Montag 07:00 Uhr startet (nach demselben Muster wie `com.digitalkonzepte.crm.plist` für den Server).
- Zugangsdaten (Nextcloud-App-Passwort) sind bewusst **nicht** im Skript hinterlegt, sondern werden aus dem macOS-Schlüsselbund gelesen (Service `nextcloud-crm-backup`) – kein Klartext-Passwort auf der Platte.
- Auf Wunsch unverschlüsselt übertragen (Transportverschlüsselung via HTTPS reicht laut Entscheidung vom 07.07.2026; keine zusätzliche Archivverschlüsselung).
- `NC_BASE_URL` (`https://nx89264.your-storageshare.de`) und `NC_USER` (`Backup`) sind seit 07.07.2026 im Skript eingetragen; Basis-URL und Zugangsdaten wurden per `curl`-Testabfrage gegen die WebDAV-Schnittstelle verifiziert (200/207 OK).

**Damit das Backup tatsächlich läuft, fehlt nur noch ein Schritt:**
1. Testlauf (`bash backup_to_nextcloud.sh`), Ergebnis in `nextcloud-backup.log` prüfen; danach die `.plist` nach `~/Library/LaunchAgents/` kopieren und mit `launchctl load` aktivieren.

*(App-Passwort im Schlüsselbund ist laut Testlauf bereits hinterlegt.)*

**Weiterhin offen (aus dem ursprünglichen Soll-Konzept):**
- `tasks.json` als einzige Aufgaben-Quelle ist im Backup-Archiv enthalten (mitgesichert), hat aber weiterhin keine eigene Versionierung innerhalb eines Laufs.
- Betriebssystem-Verschlüsselung (FileVault) als Grundschutz – Status nicht geprüft.
- Der DSGVO-Compliance-Audit hatte Backup-Sicherheit als Risiko "Mittel" bewertet – mit aktiviertem Nextcloud-Backup sinkt dieses Risiko, sobald die drei Schritte oben durchgeführt sind.

---

## 5. Sichtbarkeits-Sync (ACOS)

**Was:** Für Mandanten, die auch in der ACOS/Alchimedus-Instanz (externes SEO-/Marketing-Monitoring) geführt werden, lassen sich Sichtbarkeitsdaten (SEO-Rankings, Backlinks, KI-Sichtbarkeit) und die daraus resultierenden nächsten Schritte ins CRM übernehmen – **auch wenn beim Kunden kein beauftragtes SEO-/Marketing-Mandat läuft.** Es ist dann ein informeller Datensatz, der aber Einfluss auf die Kundenakquise (und damit ggf. Liquidität) des Mandanten haben kann. Eingeführt am 09.08.2026, erstmals umgesetzt für Fahrschule Donau Drive GmbH.

**Wo landet was:**

| ACOS-Konzept | Ziel im CRM | Verhalten |
|---|---|---|
| Aktuelle Lage (neuester Pulse-Bericht) + Knowledge Feed (Rankings, Backlinks, KI-Sichtbarkeit) | Abschnitt `## Sichtbarkeit` in der Firmenakte (`Kontakte/Firmen/<Firma>.md`) | Wird bei jedem Sync überschrieben – zeigt immer nur den aktuellsten Stand |
| Wöchentlicher Pulse-Bericht (Verlauf) | Eine Datei pro Woche in `Aktivitäten/`, `art: sichtbarkeit-monitoring`, verlinkt auf die Firma (und ggf. eine passende Opportunity) | Wird nicht überschrieben – baut die Historie auf |
| Offene „next_steps" aus dem Pulse-Bericht | Tasks in `tasks.json`, Präfix **`SICHT-`**, Kategorie `Follow-up` | importance 3 → Priorität „Hoch", importance 2 → „Mittel", importance 1 → „Niedrig" |
| Wichtigster offener Punkt | `next_action` im Frontmatter der Firmenakte | Manuell beim Sync aktualisiert |

**Vorbereitung für weitere Mandanten:** `Templates/_template_kontakt.md` und die Firma-Erzeugung in `crm_add.py` (`create_contact`) enthalten seit 09.08.2026 standardmäßig einen leeren `## Sichtbarkeit`-Platzhalter – jede neu angelegte Firma hat die Sektion also schon vorbereitet.

**Wichtige Einschränkungen (Stand 09.08.2026):**
- Der Sync läuft **nicht automatisch**. ACOS ist für dieses CRM nur über die von Claude genutzten MCP-Werkzeuge erreichbar, nicht über eine lokal hinterlegte API-Anbindung – der Abgleich muss also weiterhin pro Session von Claude angestoßen werden.
- Die neuen `Aktivitäten/`-Dateien werden vom Dashboard (`crm_server.py`) noch nicht gelesen/angezeigt (siehe Abschnitt 2) – sie sind aktuell reine Ablage, keine sichtbare Historie im Dashboard.
- Der `SICHT-`-Präfix ist neu und (bewusst) nicht Teil der automatischen ID-Vergabe in `crm_add.py` (`next_task_id` generiert weiterhin nur `PROJ-…`); SICHT-Tasks werden bislang von Hand/durch Claude vergeben.

---

## Zusammenfassung: Was läuft automatisch, was manuell

| Prozess | Automatisiert? |
|---|---|
| Dashboard-Generierung | Ja, aber nur wenn der 08:00-Job aktiviert ist (aktuell: nein) |
| Task-Prioritäten aus Deadline | Ja (`crm_add.py`, `priority_from_deadline`) |
| Server-Start beim Systemstart | Ja (`launchd`) |
| DSGVO-Löschfristen (>12 Monate inaktiv) | Nein, nur als Checkliste dokumentiert |
| Backup | Vorbereitet (wöchentlich, Nextcloud), Aktivierung durch dich noch offen |
| Consent-Register-Pflege | Nein, aktuell nicht befüllt |
| Sichtbarkeits-Sync (ACOS → CRM) | Nein, aktuell manuell durch Claude pro Session (keine lokale API-Anbindung) |

---

## 6. Änderungshistorie

| Datum | Änderung |
|---|---|
| 09.08.2026 | **Sichtbarkeits-Sync (ACOS) eingeführt:** Neuer Abschnitt `## Sichtbarkeit` in Firmenakten (aktueller Stand), wöchentliche Aktivitäten-Dateien für die Pulse-Historie, Tasks mit Präfix `SICHT-` für offene next_steps. Erstmals umgesetzt für Fahrschule Donau Drive GmbH (Firmenakte bereinigt/ergänzt, 5 Aktivitäten-Dateien für 10.07.–07.08.2026, 3 Tasks SICHT-001 bis SICHT-003). `Templates/_template_kontakt.md` und `crm_add.py` um `## Sichtbarkeit`-Platzhalter für künftige Mandanten ergänzt. |
| 07.07.2026 | **Ansprechpartner-Auswahl bei Aufgaben korrigiert:** Dropdown zeigte bisher nur den ersten Ansprechpartner einer Firma; jetzt sind alle hinterlegten Ansprechpartner auswählbar (`crm_server.py`, `contacts_json` liefert nun die vollständige Liste, `updatePersonSelect()` baut das Dropdown daraus auf). |
| 07.07.2026 | **Aktivitäten-Log auf Pipeline-Tab erweitert:** Der bisher nur im Kontakte-Tab nutzbare Log-Drawer funktioniert jetzt auch im Pipeline-Tab. Schlüssel bleibt die Firma (gemeinsames Log über beide Tabs). Jeder Eintrag erhält ein Quell-Tag (👤 Kontakt / 📈 Pipeline). |
| 07.07.2026 | **Pipeline-Name im Log ergänzt:** Da eine Firma mehrere parallele Opportunities haben kann, wird bei Pipeline-Einträgen zusätzlich der Name der jeweiligen Opportunity im Tag angezeigt (z. B. „📈 Pipeline · DonauDrive interims management"). |
| 07.07.2026 | **Automatisiertes Nextcloud-Backup entwickelt:** `backup_to_nextcloud.sh` + `com.digitalkonzepte.crm-nextcloud-backup.plist` angelegt (wöchentlich Montag 07:00 Uhr, WebDAV-Upload, 30 Tage Aufbewahrung, Zugangsdaten im macOS-Schlüsselbund). |
| 07.07.2026 | **Backup-Zielpfad korrigiert:** Erster Testlauf schlug mit HTTP 404 fehl, weil `NC_BASE_URL` fälschlich noch den Freigabe-Link-Pfad `/f/31452` enthielt und zusätzlich ein nicht vorhandener Unterordner `Backup` adressiert wurde. Per `curl`-Diagnose (PROPFIND) verifiziert: Account `Backup` ist dediziert fürs CRM-Backup, Ziel ist dessen Hauptverzeichnis. `NC_BASE_URL` bereinigt, `NC_REMOTE_DIR` auf leer (Hauptverzeichnis) gesetzt, Skriptlogik für leeren Zielpfad angepasst. |
