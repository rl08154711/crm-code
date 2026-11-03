---
type: konzept
title: CRM-Konzept – E-Mail-Anbindung & Serverlösung
stand: 2026-07-23
---

# Konzept: E-Mail-Anbindung & Serverlösung

Die beiden letzten offenen Themen vor der finalen Lösung hängen enger zusammen, als es auf den ersten Blick wirkt: Ein Postfach zuverlässig abzurufen, Mails zu bewerten und daraus Aufgaben zu erzeugen, braucht einen Prozess, der dauerhaft läuft – nicht nur, wenn gerade jemand das Dashboard im Browser aufruft. Genau diese Voraussetzung schafft erst der Schritt von der lokalen Instanz zur allgemeinen Serverlösung. Wir behandeln beide Themen deshalb als ein zusammenhängendes Vorhaben und schlagen eine Reihenfolge vor, mit der wir schnell zu etwas Nutzbarem kommen, ohne uns zu verzetteln.

Ausgangslage: Aktuell existieren zwei parallele Codepfade – `crm_server.py` (lokal, macOS, `launchd`, Port 8765) und `crm_core.py`/`crm_cgi.py` (Vertriebsdemo auf All-Inkl-Shared-Hosting, CGI-basiert). Beide sind reines Python-Stdlib ohne Framework, Datenhaltung ist ein Markdown-Vault. Für das Produkt ist bereits entschieden: Instanz pro Kunde, Managed-LLM-API statt Self-Hosting, Design-Anpassungen nur über eine Konfigurationsschicht statt über Code-Zugriff der KI.

---

## 1. E-Mail-Anbindung (Inbound)

### 1.1 Zielbild

Ein IMAP-Postfach (zunächst eines, z. B. info@digitalkonzepte.biz) wird periodisch abgerufen. Neue Mails werden automatisch bewertet, so weit möglich einem bestehenden Kontakt/einer Firma zugeordnet, und daraus werden – nach klaren Regeln – Aufgaben und Aktivitätseinträge erzeugt. Nicht zuordenbare oder unklare Mails landen in einer Review-Warteschlange statt irgendwo automatisch "verbucht" zu werden.

### 1.2 Warum das einen dauerhaften Prozess braucht

Der CGI-Codepfad (`crm_cgi.py`) startet für jede Anfrage einen neuen Prozess und eignet sich damit nicht für einen Postfach-Poller, der im Hintergrund alle paar Minuten prüft, ob neue Mail da ist. Lokal funktioniert das heute nur, weil `crm_server.py` über `launchd` dauerhaft läuft. Für eine produktive Lösung heißt das: Der E-Mail-Poller braucht entweder denselben dauerhaft laufenden Prozess wie der Dashboard-Server (als zusätzlicher Thread) oder einen eigenen Hintergrund-Service daneben – beides setzt die unter Punkt 2 beschriebene Serverarchitektur voraus, nicht das CGI-Modell.

### 1.3 Architektur (Datenfluss)

Postfach (IMAP) → Poller (alle 5–15 Min.) → neue Mails einlesen → pro Mail: Zuordnung zu Kontakt/Firma → Bewertung durch die LLM-API (Kategorie, Zusammenfassung, Aufgaben-Vorschlag) → je nach Kategorie: automatische Aktivität + Aufgaben-Vorschlag ODER Ablage in Review-Warteschlange → sichtbar im Dashboard.

Technisch reicht Python-Stdlib (`imaplib`, `email`) – das passt zur bestehenden Low-Dependency-Philosophie des Codes und braucht keine neue Abhängigkeit außer ggf. einem IMAP-Client-Wrapper.

**Ergänzung (2026-07-25, strategische Überlegung):** Statt eines komplett selbst geschriebenen Python-Pollers schlagen wir vor, die Orchestrierung über n8n abzubilden – das erfüllt die Anforderung aus 1.2 (dauerhafter Prozess) automatisch, da n8n selbst dauerhaft läuft. Ablauf: n8n-IMAP-Trigger (neue Mail) → HTTP-Request-Knoten an die LLM-API (RegioAI oder Claude/GPT, je nach Konfiguration aus 2.3) → HTTP-Request-Knoten an einen neuen Endpoint in `crm_core.py` (z. B. `POST /api/mail-intake`), der die Fachlogik übernimmt: Kontakt-Zuordnung (1.4), Aktivitäts-/Aufgaben-Erzeugung (1.6). Die Fachlogik bleibt damit zentral in Python, n8n ist reine Orchestrierung/Glue-Code, keine Duplizierung von Geschäftslogik. Vorteil: weniger Python-Code zu pflegen, und der Ablauf ist als visueller Workflow nachvollziehbar – auch für Ronald einsehbar, ohne Code lesen zu müssen.

### 1.4 Zuordnung zu Kontakten

Reihenfolge der Zuordnungsversuche:

1. Exakter Treffer auf das Feld `email` in `Kontakte/Personen/*.md`.
2. Kein Personen-Treffer, aber die Domain der Absenderadresse taucht in einer bestehenden Firma auf (z. B. weitere Person derselben Firma) → Zuordnung zur Firma, Hinweis "neue Person, nicht im CRM".
3. Kein Treffer → Mail geht in die Review-Warteschlange, keine automatische Zuordnung. Das ist bewusst konservativ: eine falsch zugeordnete Mail (z. B. bei einer Person, die die Firma gewechselt hat) ist teurer als eine, die kurz manuell bestätigt werden muss.

### 1.5 KI-Bewertung – was heißt "bewerten"?

Für jede Mail schlagen wir eine Klassifikation in wenige feste Kategorien vor: Anfrage/Lead, Rückmeldung zu einem laufenden Angebot, Terminanfrage, Reklamation/Support, Sonstiges/Spam. Zusätzlich erzeugt die LLM-API eine Kurzzusammenfassung (2–3 Sätze) und – wo sinnvoll – einen Aufgaben-Vorschlag mit Frist (z. B. "Rückmeldung zu AN-1063 erhalten → Follow-up-Call vorschlagen, Frist 3 Tage").

Wichtig, analog zur bereits getroffenen Design-Entscheidung ("keine Schreibrechte der KI auf Code, nur auf Konfiguration"): Auch hier sollte die KI in der ersten Ausbaustufe keine Aufgaben *automatisch anlegen*, sondern nur *vorschlagen*. Erst wenn sich das über einige Wochen bewährt hat, ist eine automatische Aufgaben-Erstellung für eindeutige Fälle (z. B. "Terminbestätigung") sinnvoll nachrüstbar. Das verhindert, dass ein Fehlklassifikat sofort operative Aufgaben erzeugt, die dann unbemerkt liegen bleiben.

### 1.6 Datenmodell-Erweiterung

Die bestehende Doku weist selbst darauf hin, dass das aktuelle Aktivitäten-Log im Dashboard nur im Browser-`localStorage` liegt – nicht Teil des Backups, nicht geräteübergreifend. Für die E-Mail-Anbindung braucht es zwingend eine dateibasierte Ablage, sonst gehen die aus Mails erzeugten Einträge beim nächsten Backup verloren. Vorschlag: Aktivitäten künftig als echte Markdown-Dateien (wie ursprünglich im Ordner `Aktivitäten/` vorgesehen, aber bislang ungenutzt) oder als strukturierter Log-Block direkt in der jeweiligen Kontakt-/Firmendatei – in jedem Fall dateibasiert, damit Nextcloud-Backup und Instanz-Wiederherstellung greifen. Zusätzlich braucht `tasks.json` ein Feld wie `quelle_mail_id`, damit dieselbe Mail bei einem erneuten Poll-Durchlauf nicht zwei Mal eine Aufgabe erzeugt.

### 1.7 Datenschutz und Zugangsdaten

Mailinhalte gehen zur Bewertung an die Managed-LLM-API – das ist eine Weiterverarbeitung personenbezogener Daten Dritter (Absender, Erwähnte Personen) und gehört in den bestehenden AVV mit dem LLM-Anbieter, nicht als Nebenaspekt. IMAP-Zugangsdaten dürfen nicht im Code oder Klartext liegen; lokal nutzt das Backup-Skript dafür den macOS-Schlüsselbund, das gibt es auf einem Linux-Server nicht – dort brauchen wir stattdessen eine Secrets-Verwaltung über Umgebungsvariablen oder ein einfaches Secrets-File mit restriktiven Dateirechten, passend zur Config-Schicht aus Abschnitt 2. Rohe Mailkopien sollten eine Aufbewahrungsfrist bekommen (z. B. 90 Tage), danach nur die daraus erzeugte Aktivitätsnotiz behalten – das reduziert die Menge an sensiblen Rohdaten, die im Vault liegen.

### 1.8 Rollout in Stufen

Stufe 1 (MVP): Ein Postfach, Zuordnung zu Kontakten, Bewertung + Zusammenfassung, alles landet als Vorschlag in einer Review-Ansicht – noch keine automatische Aufgaben-Erstellung. Stufe 2: Automatische Aktivitäts-Einträge für eindeutig zugeordnete Mails, Aufgaben-Vorschlag weiterhin mit einem Klick zu bestätigen. Stufe 3 (optional, nach Bewährung): Automatische Aufgaben-Erstellung für klar definierte, risikoarme Fälle (z. B. Terminbestätigungen), alles andere bleibt Vorschlag.

---

## 2. Von der lokalen Lösung zur allgemeinen Serverlösung

### 2.1 Zielbild (bereits entschieden, 2026-07-09)

Instanz pro Kunde (eigener Server/Container + eigenes Vault, kein Multi-Tenant), Managed-LLM-API statt Self-Hosting auf dem Hetzner-GPU-Server, Design-Anpassungen der KI nur über eine Konfigurationsschicht. Das vorliegende Konzept baut auf diesen drei Leitplanken auf und macht sie konkret.

### 2.2 Risiko im Ist-Zustand

Zwei parallele Codepfade (`crm_server.py` lokal, `crm_core.py`/`crm_cgi.py` als Demo) bedeuten: Jede neue Funktion – zuletzt die Angebote/Docx-Funktion – muss potenziell zweimal gepflegt werden, oder gerät bei einem der beiden Pfade in Vergessenheit. Das ist auf Dauer eine Fehlerquelle, gerade wenn jetzt noch ein dritter Pfad (Produktivserver) dazukommt.

### 2.3 Zielarchitektur pro Kundeninstanz

`crm_core.py` wird die einzige Quelle der Business-Logik (Parsing, CRUD, Dashboard-Rendering, Angebote) – das ist durch die Demo-Portierung bereits vorbereitet, muss aber vervollständigt werden (aktuell sind z. B. neuere Angebote-Änderungen nur in `crm_server.py` eingeflossen). Als Transport-Schicht empfehlen wir für den Produktivbetrieb einen dauerhaft laufenden Prozess wie lokal `crm_server.py`, aber unter `systemd` statt `launchd` – das ist Linux-Standard, robuster bei Absturz (automatischer Neustart) und schafft die Grundlage für den E-Mail-Poller aus Abschnitt 1. Reverse Proxy und TLS übernimmt Caddy, wofür mit dem `Caddyfile` im `Demo-Deployment`-Ordner bereits eine Vorlage existiert.

Die Konfigurationsschicht (JSON/YAML) pro Instanz enthält: Design-Parameter (Farben, Spalten, Layout-Varianten), LLM-Provider und API-Key, Mail-Konto-Zugangsdaten (verweisend auf die Secrets-Verwaltung aus 1.7), Backup-Ziel. Die KI-Dialogschicht bekommt Schreibzugriff nur auf diese Konfiguration, nicht auf den Python-Quellcode – damit bleibt das Risiko einer kaputten Kundeninstanz durch einen KI-Fehler beherrschbar, ohne dass wir zwingend Git-Versionierung mit Rollback pro Instanz aufbauen müssen.

Die Datenhaltung bleibt das Markdown-Vault, aber jede Kundeninstanz bekommt ihr eigenes Verzeichnis – kein gemeinsames Datenbankschema mehrerer Kunden. **Entscheidung (2026-07-23): kein Docker.** Wir betreiben die Instanzen direkt in einer Serverumgebung auf Hetzner (ein VPS, mehrere systemd-Services) statt containerisiert – jede Kundeninstanz bekommt einen eigenen systemd-Service, einen eigenen Port und ein eigenes Vault-Verzeichnis auf demselben Server. Das ist einfacher zu debuggen (direkter Dateizugriff, kein Container-Layer dazwischen) und passt zur bisherigen Betriebsweise (`crm_server.py` läuft ja auch heute schon als "nackter" Python-Prozess, nur eben unter `launchd` statt `systemd`). Die Isolation zwischen Kunden erfolgt über Unix-Rechte (eigener Systembenutzer pro Instanz) statt über Container-Grenzen.

Backup läuft nach demselben Muster wie das bestehende Nextcloud-Skript, aber mit konfigurierbarem Ziel pro Instanz statt fest auf Ronalds Account verdrahtet. Monitoring kann schlank bleiben: ein Healthcheck-Endpoint plus automatischer Neustart über systemd reicht, ist aber notwendig – der aktuell seit Wochen deaktivierte 08:00-Uhr-Job zeigt, wie leicht ein Hintergrundprozess unbemerkt stehen bleibt, und das darf bei einem produktiven Mail-Poller nicht passieren.

### 2.4 LLM-Provider modular: RegioAI als möglicher zweiter Anbieter (Prüfung angestoßen 2026-07-24)

Ronald liegt ein Angebot von RegioAI (regio-ai.eu) vor – deutlich günstiger als offizielle Preislisten. RegioAI betreibt eine eigene Plattform (MYREGIO.AI) mit Open-Source-LLMs auf eigener Hardware (Kubernetes/Proxmox, geshared genutzte nVidia-Karten) in deutschen Rechenzentren (Bayern), Abrechnung über Grundgebühr + Token-Nutzung, DSGVO-/EU-AI-Act-Positionierung, ISO 9001/27001. Aus unserer Sicht ist das **kein Selbsthosting-Fall**, sondern ein weiterer Managed-API-Anbieter – RegioAI betreibt die Infrastruktur, wir sprechen nur ihre API an. Das passt direkt in die bereits 2026-07-09 beschlossene austauschbare LLM-Schicht (siehe 2.1) und würde die Leitplanke "kein Self-Hosting auf eigener GPU-Hardware" nicht verletzen.

Möglicher Zuschnitt: LLM-Provider ist Teil der Konfigurationsschicht (siehe oben) und damit pro Kundeninstanz wählbar – z. B. RegioAI für kostensensible Kunden oder wenn "100 % Server in Deutschland" ein Verkaufsargument ist, Claude/GPT für Fälle, die höhere Modellqualität brauchen. Denkbar ist sogar eine Aufteilung nach Aufgabentyp innerhalb einer Instanz: Die in Abschnitt 1 beschriebenen Aufgaben (Mail-Kategorisierung, Kurzzusammenfassung, Aufgaben-Vorschlag) sind eng umrissen und strukturiert – dafür könnte ein güns­tigeres Open-Source-Modell über RegioAI ausreichen, auch wenn die absolute Modellqualität unter der von Claude/GPT liegt.

**Offen, bevor wir das einplanen:** genaue API-Schnittstelle (eigenes Format oder OpenAI-kompatibel – dazu keine öffentliche Angabe gefunden), Preis-/Vertragsdetails (Grundgebühr, Token-Preis, Mindestlaufzeit), AVV-Konditionen für die Verarbeitung von Mail-/Kontaktdaten. RegioAI bietet 100 € Testguthaben – geeignet, um die Modellqualität für unsere konkreten Anwendungsfälle risikoarm zu testen, bevor eine Festlegung erfolgt.

### 2.5 Skalierungsmodell: n8n + gestaffelte Server-Größe (strategische Überlegung, 2026-07-25, noch nicht final entschieden)

Ronald denkt strategisch in Richtung bis zu 5 parallele, getrennte Kundeninstanzen, orchestriert über n8n, mit einem RegioAI-Einstiegspaket für ca. 100 €/Monat als kleinstem Baustein. Ziel ist ein Modell, das sich je nach Kundennachfrage erweitern lässt, ohne bei jedem neuen Kunden neu zu planen.

**n8n-Betrieb:** Eine einzige n8n-Installation reicht für alle Kundeninstanzen – n8n muss nicht pro Kunde separat laufen. Jeder Kunde bekommt innerhalb derselben Installation einen eigenen, isolierten Workflow (eigene IMAP-Zugangsdaten, eigener HTTP-Aufruf an die jeweilige CRM-Instanz). Das ist ausreichend Trennung, weil n8n hier als interne Automatisierungsschicht bei uns läuft, nicht als kundenzugängliches System. Empfehlung: selbst gehostet auf demselben Hetzner-Server (Node-Prozess unter systemd, kein Docker – passt zur Linie aus 2.3) statt n8n Cloud, damit Mailinhalte nicht zusätzlich über die Infrastruktur eines weiteren Drittanbieters laufen (n8n Cloud wäre ein zusätzlicher AVV-Partner).

**Gestaffelte Server-Größe** (Hetzner-Server lässt sich ohne Neuaufsetzen hochskalieren, siehe Checkliste):
- 1 Kunde (Pilot): CX23 (2 vCPU/4 GB) reicht – 1 CRM-Instanz + n8n + Caddy.
- 2–5 Kunden: eher CX33 oder CX43 (4–8 vCPU/8–16 GB) – n8n braucht als Node-Prozess ca. 150–300 MB RAM im Leerlauf, dazu kommt pro CRM-Instanz (Python) noch mal ca. 30–50 MB. Wenn absehbar ist, dass kurzfristig mehr als ein Kunde dazukommt, lohnt sich der direkte Start mit CX33 statt eines Upgrades mit kurzem Neustart mittendrin.
- Mehr als 5 Kunden bzw. spürbar höheres Mailaufkommen: an der Stelle prüfen, ob ein zweiter Hetzner-Server sinnvoller ist als ein einzelner großer (weiterhin Instanz-pro-Kunde, kein Multi-Tenant) – Entscheidung anhand der tatsächlichen Auslastung, nicht vorab.

**Offener Punkt, der das Skaliermodell konkret durchrechenbar macht:** Das RegioAI-Einstiegspaket (ca. 100 €/Monat) ist vermutlich eine Grundgebühr mit einem bestimmten Token-Kontingent (siehe 2.4) – ob dieses Kontingent 5 parallele Instanzen an Mailvolumen abdeckt oder ab Kunde 3–4 die nutzungsabhängige Abrechnung stärker greift, wissen wir erst mit den konkreten Vertragsdetails. Das ist der wichtigste fehlende Baustein, um das Skaliermodell verlässlich vorzurechnen.

### 2.6 Migrationsschritte

1. `crm_core.py` als einzige Quelle der Business-Logik fertigstellen (alle seit der Portierung entstandenen Änderungen aus `crm_server.py` nachziehen). **Entscheidung (2026-07-25): Angebote-Feature bleibt außen vor** – Ronald löst Angebote/Proposals separat, nicht als Teil des Basissetups. Das Feature bleibt unangetastet in Ronalds lokalem `crm_server.py` (macOS), wird aber nicht mit in `crm_core.py`/den Produktivserver übernommen.
2. Persistenten Server-Entrypoint für Linux bauen (systemd statt CGI) und probeweise auf Hetzner betreiben – das ersetzt die reine CGI-Nutzung nicht für die Vertriebsdemo, ergänzt sie aber um einen produktionsfähigen Pfad.
3. Konfigurationsschicht einführen (Design/LLM/Mail/Backup als externe Config statt Code).
4. n8n installieren und den Mail-Intake-Workflow für den ersten Kunden bauen (Abschnitt 1 und 2.5) – inkl. neuem `POST /api/mail-intake`-Endpoint in `crm_core.py`.
4a. Login/Auth-Layer einbauen (siehe 4.1) – Pflicht vor Live-Gang, nicht optional. Start mit einem Nutzer pro Instanz, Struktur aber erweiterbar auf mehrere Nutzer angelegt.
4b. Kontakte-Archivierung analog zum bestehenden Opportunities-/Angebote-Muster ergänzen (`Kontakte/_Archiv/`), Wiedervorlage-Automatik in die bestehende Task-Kategorie „Follow-up" integrieren statt eigenes System, kleines KPI-Dashboard (4 Kennzahlen, siehe 4.1) bauen.
5. Pilotkunde auf Hetzner live schalten – **Entscheidung (2026-07-23): manuelles Setup**, keine automatisierte Provisionierung für den ersten Kunden. Wir legen Systembenutzer, Vault-Verzeichnis, systemd-Service, Caddy-Eintrag und Config von Hand an und dokumentieren die Schritte als Checkliste. Backup und Monitoring im Echtbetrieb verifizieren, bevor der nächste Kunde folgt.
6. Automatisierte Instanz-Provisionierung (Skript aus Template statt manueller Schritte) erst als späterer Ausbauschritt, sobald mehr als ein oder zwei Kunden laufen und sich die manuellen Schritte wiederholen – dann lohnt sich die Automatisierung, vorher ist sie verfrühter Aufwand.

---

## 3. Entscheidungen und nächste Schritte

**Entschieden (2026-07-23):**
- Postfach und Zugangsdaten für den Abruf werden von Ronald bereitgestellt (siehe „Nächster Schritt" unten).
- Keine Container-Lösung – Betrieb direkt in einer Serverumgebung auf Hetzner, ein systemd-Service pro Kundeninstanz auf demselben VPS.
- Für den ersten Pilotkunden manuelles Setup, keine automatisierte Provisionierung.

**In Prüfung, noch nicht final entschieden (2026-07-25):**
- Skalierungsmodell mit n8n als zentraler Orchestrierung für bis zu 5 Kundeninstanzen und RegioAI-Einstiegspaket (ca. 100 €/Monat) als strategische Überlegung von Ronald – Architekturvorschlag dazu in Abschnitt 1.3 und 2.5, aber noch keine Bestellung/Festlegung.

**Noch offen:**
- Soll die Aufgaben-Erstellung aus Mails anfangs mit Freigabe laufen (Stufe 1/2 aus Abschnitt 1.8), oder ist ein schnellerer, direkterer Automatisierungsgrad wichtiger, auch mit höherem Korrekturaufwand? Unser Vorschlag bleibt Stufe 1 (nur Vorschlag, keine Auto-Erstellung) für den Start.
- RegioAI-Vertragsdetails (Token-/Request-Kontingent im Einstiegspaket, API-Schnittstelle, AVV) – ohne diese Zahlen lässt sich das Skaliermodell aus 2.5 nicht verlässlich durchrechnen.

**Nächster Schritt:** Sobald die IMAP-Zugangsdaten vorliegen, brauchen wir konkret: E-Mail-Adresse, IMAP-Host und Port (meist `imap.<anbieter>.de`, Port 993/SSL), Passwort bzw. App-Passwort. Zur Sicherheit legen wir diese Zugangsdaten nicht im Chat-Verlauf dauerhaft ab, sondern direkt in eine lokale Konfigurationsdatei mit eingeschränkten Zugriffsrechten – dieselbe Struktur, die später auch auf dem Hetzner-Server als Secrets-Datei dient (siehe 1.7).

---

## 4. Feature-Einschätzung: was fehlt noch aus unserer Sicht (2026-07-25)

Auf Ronalds Nachfrage, welche wichtigen Features vor dem produktiven Basissetup noch fehlen. Einschätzung basiert auf dem Ist-Zustand (`CRM-System-Dokumentation.md`, `DSGVO-Compliance-Audit.md`) und dem ursprünglichen Soll-Konzept (`CRM-Transformationsvorgabe.md`).

**Vor dem ersten Live-Kunden praktisch Pflicht:**

Login/Zugriffsschutz für die Produktivinstanz fehlt komplett – `crm_server.py` läuft lokal nur auf `localhost` ohne Auth, die All-Inkl-Demo hat nur einfaches HTTP-Basic-Auth über `.htaccess`. Sobald eine Kundeninstanz über Caddy aus dem Internet erreichbar ist, braucht sie einen echten Login, nicht nur TLS. Das gehört in die Migrationsschritte (Abschnitt 2.6) mit aufgenommen, ist dort aber noch nicht explizit enthalten.

Das Aktivitäten-Log liegt aktuell nur im Browser-`localStorage` (siehe 1.6) – das ist schon unabhängig von der E-Mail-Anbindung ein echtes Datenverlust-Risiko im laufenden Betrieb, nicht nur ein "Nice-to-have" für später.

Das DSGVO-Consent-Register und der DSGVO-Log sind laut Doku als Struktur angelegt, aber für keinen der bisherigen Kontakte tatsächlich befüllt – für Ronalds eigene Nutzung bisher folgenlos, aber sobald das Produkt an Kunden geht, die selbst wieder personenbezogene Daten Dritter verarbeiten, wird aus der Lücke ein echtes Compliance-Risiko, kein internes Aufräumthema mehr.

Das wöchentliche Backup ist vorbereitet, aber der 08:00-Job war laut Doku deaktiviert – für den Produktivbetrieb braucht es nicht nur ein laufendes Backup, sondern auch eine Erfolgs-/Fehlerbenachrichtigung, damit ein stillstehendes Backup auffällt, bevor es gebraucht wird.

**Kurz danach sehr wertvoll (eigentlicher CRM-Nutzen):**

Eine Wiedervorlage-/Follow-up-Automatik fehlt komplett – im ursprünglichen Soll-Konzept explizit gefordert ("kein Kontakt seit 3 Tagen → Follow-up", "Opportunity seit 30 Tagen in Verhandlung → entscheiden"), bisher aber nirgends umgesetzt. Das ist vermutlich das Feature mit dem größten Alltagsnutzen, und es lässt sich gut mit der E-Mail-Anbindung kombinieren (z. B. "Mail erhalten, aber seit 5 Tagen nicht beantwortet").

Ein echtes KPI-/Reporting-Dashboard fehlt – `Dashboard/03_KPIs.md` ist ein leeres Template, es gibt keine berechnete Conversion-Rate, keinen Pipelinewert nach Stufe, keine durchschnittliche Sales-Cycle-Dauer. Für ein Produkt, das du an Kunden verkaufen willst, ist das auch ein Verkaufsargument ("auf einen Blick sehen, wie die Pipeline steht").

Kontakte/Opportunities werden aktuell direkt gelöscht (`crm_delete.py`), ohne Papierkorb/Wiederherstellung – für den Eigengebrauch bisher unkritisch, aber sobald Kunden selbst mit dem System arbeiten, erhöht ein Soft-Delete die Fehlertoleranz spürbar.

**Später sinnvoll, aber nicht dringend:**

Kalender-Integration (Google/Outlook) für Termine, eine Volltextsuche über den gesamten Vault, und die Frage, ob eine Kundeninstanz mehrere Nutzer/Logins braucht (mehrere Vertriebler bei einem Kunden) – das wäre gut, jetzt zu klären, weil es das Auth-Design aus dem ersten Punkt oben direkt beeinflusst.

**Eine Rückfrage dazu:** Braucht eine typische Kundeninstanz nur einen Login (ein Nutzer pro Firma), oder sollten wir von Anfang an mit mehreren Nutzern pro Instanz planen? Das entscheidet, wie aufwendig die Login-Lösung von Anfang an werden muss.

### 4.1 Ronalds Rückmeldung und Entscheidungen (2026-07-25, Nachmittag)

**Login:** bestätigt als Pflicht, kommt in die Migrationsschritte (siehe 2.6, dort ergänzt). Zur genauen Ausgestaltung (Einzel- vs. Mehrbenutzer) hat Ronald sich nicht konkret festgelegt. Unser Vorschlag als Startpunkt: pro Instanz zunächst **ein** Login (ein Nutzer-/Passwort-Satz in der Konfigurationsschicht, siehe 2.3), aber die Auth-Struktur von Anfang an so anlegen (z. B. Nutzerliste statt einzelnem Passwort-Feld), dass sich später ohne Umbau weitere Nutzer pro Instanz ergänzen lassen, falls ein Kunde mit mehreren Vertrieblern das braucht. Bitte kurz bestätigen oder korrigieren, bevor wir das umsetzen.

**Löschen/Archivieren – entschieden:** Kein separates Papierkorb-System nötig. Stattdessen wird das bereits bestehende Archiv-Muster (gibt es schon für Opportunities: `Opportunities/_Archiv/`, und für Angebote: `Angebote/_Archiv/`) auf Kontakte ausgeweitet – ein gelöschter Kontakt wandert nach `Kontakte/_Archiv/` statt sofort unwiderruflich zu verschwinden, bleibt aber wiederherstellbar. Echtes, endgültiges Löschen bleibt daneben als bewusste, separate Aktion für tatsächliche DSGVO-Löschanfragen bestehen (nutzt die schon vorhandene `log_dsgvo_deletion()`-Funktion in `crm_server.py`, die den Vorgang im DSGVO-Log protokolliert) – Archivieren ist der neue Standardfall, echtes Löschen die bewusste Ausnahme.

**Aufgaben und Wiedervorlage – entschieden, verschmelzen:** Kein eigenes Wiedervorlage-System neben den bestehenden Aufgaben. Praktischer Vorteil: Die bestehende Task-Struktur in `tasks.json` hat bereits eine Kategorie **„Follow-up"** (neben Kundenakquise, Projektmanagement, Administrativ) – die in Abschnitt 1.8 geplante Wiedervorlage-Automatik (kein Kontakt seit X Tagen, Mail seit Y Tagen unbeantwortet, Opportunity seit Z Tagen ohne Fortschritt) erzeugt künftig automatisch Einträge in genau dieser Kategorie, statt eine parallele Liste zu führen. Ronald bevorzugt den Begriff "Wiedervorlage" gegenüber "Follow-up" – wird beim Umbau als Anzeigename im Dashboard verwendet, auch wenn intern ggf. weiter `Follow-up` als Kategoriewert steht (oder wir benennen die Kategorie direkt um – das entscheiden wir beim Bauen, hat keine strategische Bedeutung).

**KPI-Dashboard – entschieden, Umfang bewusst klein halten:** Ronald möchte ein Overview-Dashboard mit wenigen, aussagekräftigen Kennzahlen statt eines umfangreichen Reportings. Unser Vorschlag für die erste Version (kann später erweitert werden): Pipelinewert nach Status (aktiv/gewonnen/verloren), Anzahl offener Wiedervorlagen (davon überfällig), Conversion-Rate Lead → Won, durchschnittliche Sales-Cycle-Dauer der gewonnenen Opportunities. Vier Kacheln, keine vollständige BI-Lösung.
