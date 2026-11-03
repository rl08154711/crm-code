---
type: status
title: E-Mail-Anbindung – Umsetzungsstand
stand: 2026-08-04
bezug: CRM-Konzept-Email-Serverloesung.md, Abschnitt 1 + 2.3
---

# Was heute gebaut wurde

Umgesetzt ist Stufe 1 aus dem Konzept (Abschnitt 1.8): jede eingehende Mail wird zugeordnet und bewertet, landet aber **immer nur als Vorschlag** in einer Review-Ansicht – nichts wird automatisch als Aktivität oder Aufgabe übernommen, bevor du das im Dashboard bestätigst.

**Im Einzelnen:**

- **Kontakt-Zuordnung** (Konzept 1.4): exakter Treffer auf die E-Mail-Adresse einer Person → sonst Domain-Treffer auf eine bestehende Firma → sonst kein Treffer, Mail bleibt trotzdem in der Warteschlange.
- **LLM-Bewertung** (Konzept 1.5): Kategorie (Anfrage/Lead, Rückmeldung zu Angebot, Terminanfrage, Reklamation/Support, Sonstiges/Spam), Kurzzusammenfassung, optionaler Aufgaben-Vorschlag. Läuft über Claude (dein bestehender AVV), wie besprochen.
- **Review-Ansicht im Dashboard**: neuer Tab „✉️ Mail-Review" – zeigt Absender, Zuordnung, Kategorie, Zusammenfassung, Aufgaben-Vorschlag. Zwei Buttons: „Übernehmen" (legt Aktivitäts-Eintrag bei der Firma an, plus Aufgabe falls vorgeschlagen) oder „Verwerfen".
- **Dateibasiertes Aktivitäten-Log** (Konzept 1.6): war bisher nur im Browser-localStorage gespeichert – also weder Teil des Backups noch geräteübergreifend. Das war laut Konzept unabhängig von der Mail-Anbindung schon ein Datenverlust-Risiko und ist jetzt mit erledigt: liegt jetzt dateibasiert unter `Aktivitäten/<Firma>.json`, landet damit auch im normalen Nextcloud-Backup.
- **Idempotenz** (Konzept 1.6): dieselbe Mail erzeugt bei einem erneuten Poll-Durchlauf keinen zweiten Vorschlag/keine zweite Aufgabe (Prüfung über Message-ID).
- **Konfigurationsschicht** (Konzept 2.3): `config.json` regelt LLM-Modell, Poll-Intervall, ob die Mail-Anbindung überhaupt aktiv ist (`mail.enabled`) – ohne Code-Änderung.
- **IMAP-Poller** (Konzept 1.2/1.3): eigenständiges Skript `mail_poller.py`, läuft als eigener systemd-Service unabhängig vom Dashboard. Bewusst so gebaut, dass es genau die Schnittstelle (`POST /api/mail-intake`) aufruft, die im Konzept auch für eine spätere n8n-Ablösung vorgesehen ist – falls ihr später auf n8n wechselt, ändert sich an `crm_core.py` nichts.

Alles lokal mit synthetischen Test-Mails durchgetestet (exakter Treffer, Domain-Treffer, kein Treffer, Duplikat-Erkennung, Übernehmen, Verwerfen) – lief fehlerfrei durch.

---

# Was noch fehlt, bevor es live geht

**Zwingend von dir:** IMAP-Zugangsdaten und der Anthropic API-Key. Liegt bereits eine Vorlage lokal bereit unter `CRM/CPX12-Generalprobe/secrets/mail.env.example` – bitte kopieren nach `mail.env` (gleicher Ordner) und ausfüllen:

- `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD` (E-Mail-Adresse, Host meist `imap.<anbieter>.de`, Port 993, Passwort bzw. App-Passwort)
- `ANTHROPIC_API_KEY`

Die Datei bitte nicht in den Chat einfügen – ich lese sie danach direkt über die Geräteanbindung.

**Danach von mir:**

1. `mail_poller.py`, `crm-mailpoll.service` mit auf den Server hochladen (liegt jetzt mit im `CPX12-Generalprobe`-Ordner)
2. `config.json` mit hochladen, darin `mail.enabled` auf `true` setzen
3. `systemctl enable --now crm-mailpoll` auf dem Server
4. Ersten echten Poll-Durchlauf beobachten (Logs: `journalctl -u crm-mailpoll -f`), bevor es unbeaufsichtigt läuft

Das state ich aktiv an, sobald `mail.env` befüllt ist – sag einfach Bescheid.

---

# Was aus dem Konzept bewusst NICHT Teil dieser Runde war

Du hattest dich für „E-Mail-Anbindung zuerst" entschieden – das ist jetzt fertig. Aus Abschnitt 2/4 des Konzepts noch offen, falls du als Nächstes dort weitermachen willst:

- App-seitiger Login (aktuell nur Caddy Basic-Auth – für den Pilotbetrieb ausreichend, aber nicht dasselbe wie die im Konzept beschriebene Nutzerverwaltung in der Konfigurationsschicht)
- Wiedervorlage-Automatik (Konzept 4: "kein Kontakt seit X Tagen" etc.)
- Kleines KPI-Dashboard (4 Kacheln, Konzept 4.1)
- n8n-Variante / RegioAI-Evaluierung (falls ihr das später statt des jetzigen Python-Pollers wollt)
- Backup-Erfolgsmeldung (der deaktivierte 08:00-Job aus dem Konzept)

Sag Bescheid, was davon als Nächstes dran soll.
