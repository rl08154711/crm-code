---
type: konzept
title: CRM-Konzept – Unternehmen/Personen/Kampagne, Projekt-Zusammenführung, Tages-Dashboard
stand: 2026-08-21
status: Vorschlag, noch nicht umgesetzt
---

# CRM-Konzept: Unternehmen/Personen/Kampagne, Projekt, Tages-Dashboard

Ich habe mir dafür `crm_server.py`, `crm_add.py`, `tasks.json` und die bestehenden Vorlagen genau angeschaut, bevor ich etwas vorschlage – die drei Punkte hängen technisch enger zusammen, als sie auf den ersten Blick wirken, deshalb erst der Reihe nach die Konzepte, danach eine gemeinsame Reihenfolge.

---

## 1. Unternehmen + Personen-Tab mit Kampagne

**Ist-Zustand:** Der Tab "👥 Kontakte" zeigt heute 19 Firmenzeilen. Alle 23 Personen stecken als Unterzeilen in der jeweiligen Firmenzeile – es gibt keine eigene Liste aller Personen, also auch keine Möglichkeit, quer über alle Firmen zu filtern oder zu sehen "wer bekommt gerade welche Kampagne".

**Vorschlag:**

- Der Tab wird umbenannt in "🏢 Unternehmen". Technisch bleibt darunter alles beim Alten – Ordner `Kontakte/Firmen/`, API-Route `/api/contacts` bleiben, wie sie sind. Wir ändern nur, was du siehst, nicht die Bauteile darunter. Das ist eine bewusste Entscheidung: `crm_server.py` ist eine einzelne, 128 KB große Datei ohne Versionskontrolle, und die Bezeichnung nach außen ist unabhängig vom internen Namen.
- Direkt daneben ein neuer Tab "👤 Personen" – eine flache Tabelle, eine Zeile pro Person. Spalten: Name, Unternehmen (klickbar, öffnet die Firma), Kampagne, Status, letzter Kontakt, E-Mail/Telefon, Bearbeiten.
- Neues Feld pro Person: `kampagne` im Frontmatter der Personen-Datei, z. B. `kampagne: Weihnachtsaktion 2026`. Kommt ins bestehende Bearbeiten-Fenster für Ansprechpartner dazu – dasselbe Fenster, das heute schon Name, Titel, Abteilung, E-Mail und Telefon bearbeitet. Technisch der kleinste Teil der ganzen Sache.
- Filter über der Tabelle: Dropdown "Kampagne", gefüllt mit allen Werten, die irgendwo bereits eingetragen sind, plus "Alle". Genau das Prinzip, das beim Angebote-Tab schon läuft – dort lernt `_stammdaten.json` neue Zahlungsbedingungen und Artikel automatisch dazu. Bei Kampagnen brauchen wir nicht mal eine eigene Datei dafür, die Werte stehen ja schon in den Personen-Dateien.
- Aktivitäten je Kampagne: Hier würde ich bewusst **nicht** den bestehenden Log-Drawer aus dem Kontakte/Pipeline-Tab kopieren. Der speichert nämlich nur im Browser-`localStorage` – geht bei Cache-Löschung verloren, ist nicht Teil des Backups, funktioniert nicht geräteübergreifend. Steht so auch als bekannte Schwäche in der System-Doku. Für eine Kampagne, bei der du über Wochen nachhalten willst, wer wann wie reagiert hat, ist das zu wackelig.

  Stattdessen: dasselbe Muster, das für den Sichtbarkeits-Sync (ACOS) schon eingeführt wurde – echte Markdown-Dateien im vorhandenen `Aktivitäten/`-Ordner, eine Datei pro Kontaktpunkt, mit Frontmatter `person`, `firma`, `kampagne`, `datum`, `art`. Klick auf eine Personen-Zeile öffnet einen Drawer wie gewohnt, nur dass die Einträge jetzt aus echten, gesicherten Dateien kommen statt aus dem Browser-Speicher. Nebeneffekt: Der `Aktivitäten`-Ordner, der bisher nur vom ACOS-Sync bespielt wird und im Dashboard noch gar nicht angezeigt wird, bekommt damit endlich eine sichtbare zweite Verwendung.

**Aufwand:** mittel. Der größte Brocken ist die neue Tabelle samt Filter und einer neuen Route `/api/persons` (flach über alle Firmen); das Umstellen der Aktivitäten auf Dateien statt Browser-Speicher ist der Teil mit den meisten neuen Codezeilen.

**Offene Frage an dich:** Sollen Kampagnen frei eintippbar bleiben, wie ein Tag, oder soll es eine feste Liste geben, die nur du pflegst? Ich würde zu frei tippbar raten – das wächst mit, ohne dass du irgendwo eine Liste warten musst, genau wie bei den Angeboten.

---

## 2. Aufgaben und Pipeline zusammenführen

**Ist-Zustand:** Zwei getrennte Systeme. Aufgaben liegen in `tasks.json`, ohne Wert-Feld, mit Kategorie (Kundenakquise/Projektmanagement/Administrativ/Follow-up) und einem losen Textfeld `contact`. Pipeline-Opportunities liegen als einzelne Markdown-Dateien in `Opportunities/`, mit Status (lead/aktiv/won/lost), `value`, `probability` und einem Textfeld `kontakt`. Beide Felder tragen schon denselben Firmennamen als Text – eine Verknüpfung existiert also faktisch, nur nicht als feste ID.

Interessanter Fund dabei: Es gibt bereits einen Ordner `Projekte/` und eine fertige Vorlage `_template_projekt.md` mit Budget, Meilensteinen und Rechnungsstellung – offenbar mal angelegt und nie bespielt. Das passt gut zu deiner Idee, Pipeline zu Projekt zu machen.

**Vorschlag, in vier Bausteinen:**

**a) Wert-Feld bei jeder Aufgabe.** `tasks.json` bekommt ein neues Feld `value` (Freitext wie bei den Opportunities, z. B. "1.500 €", darf leer bleiben, wenn kein direkter Geldbezug besteht). Ergänzung im bestehenden Aufgaben-Bearbeiten-Fenster. Damit lässt sich später eine Summe bilden, so wie die Pipeline-Kachel heute schon den Gesamtwert aller Opportunities zeigt.

**b) Pipeline wird zu Projekt.** Der Tab "📈 Pipeline" heißt künftig "📁 Projekt". Zwei Wege, wie tief wir das technisch machen:

- *Weg A, empfohlen:* Die Dateien in `Opportunities/` bleiben liegen, wie sie sind – alle bestehenden Wikilinks aus den Firmenakten zeigen darauf, die würden sonst brechen. Wir ändern nur Anzeigename und Status-Wortlaut (statt lead/aktiv/won/lost z. B. Angebahnt/Aktiv/Gewonnen/Verloren). Inhaltlich bleibt es dieselbe Sache – eine Verkaufschance, die zum Auftrag wird –, nur mit dem Namen, den du willst.
- *Weg B, größerer Umbau:* echte Migration in die vorbereitete `Projekte/`-Struktur mit Budget/Meilensteinen/Rechnungsstellung. Dafür müsste jede bestehende Opportunity inhaltlich nachgepflegt werden – Meilensteine gibt es aktuell schlicht nicht. Sinnvoll, aber ein eigenes Vorhaben.

Ich würde mit Weg A starten und erst zu Weg B wechseln, wenn dir im Alltag Budget und Meilensteine tatsächlich fehlen.

**c) Aufgaben hängen an ihrem Projekt.** Statt zwei getrennter Tabellen eine gemeinsame Ansicht: Jedes Projekt zeigt seine zugehörigen Aufgaben als Unterzeilen, aufklappbar – dasselbe Muster, das die Firmenzeilen im Unternehmen-Tab heute schon für ihre Ansprechpartner nutzen. Die Verknüpfung läuft über den Firmennamen, den beide Seiten bereits als Feld führen. Es braucht also keine neue ID, nur den Code, der beide Listen zusammenführt.

**d) Interne Aufgaben auf Kunde "Intern".** Wir legen einen echten Firmen-Datensatz `Kontakte/Firmen/Intern.md` an (Status z. B. "intern", kein Akquise-Fall). Jede Aufgabe ohne externen Kunden – Buchhaltung, Website-Pflege, was auch immer – bekommt `contact: Intern` statt eines leeren Feldes. Bestehende Aufgaben ohne Kundenbezug werden einmalig per Skript umgestellt. Vorteil: Aufgaben ohne Kunde verschwinden nicht mehr als Sonderfall im Code, sondern laufen als eigenes Projekt "Intern" ganz normal mit.

**Wichtiger Hinweis vorweg:** Für diesen Umbau lohnt sich ein Sicherheitsnetz, bevor wir anfangen. Es gibt laut System-Doku kein Git-Repository, und das automatische Nextcloud-Backup ist vorbereitet, aber noch nicht aktiviert – ein einziger Schritt fehlt (`backup_to_nextcloud.sh` testen, `.plist` laden). Vor Baustein c) und d) würde ich das entweder aktivieren oder wenigstens eine Kopie des CRM-Ordners ziehen, weil dort echte Live-Daten verschoben werden.

**Aufwand:** a) und d) sind klein und risikoarm. b) Weg A ist überschaubar. c) ist der aufwendigste Teil, weil er zwei bislang getrennte Tabellen im Dashboard tatsächlich zusammenführt.

---

## 3. Tages-Dashboard "Was ist heute zu erledigen"

Bevor ich den Vorschlag mache, eine technische Einschränkung, die ich offen ansprechen muss: `crm_server.py` läuft bei dir lokal auf dem Mac, als eigener Hintergrunddienst, unabhängig von diesem Chat hier. ACOS/Alchimedus erreiche ich ausschließlich über die Werkzeuge, die in einer laufenden Claude-Sitzung bereitstehen – nicht über eine offene Programmierschnittstelle, die dein CRM-Programm selbst jederzeit anfragen könnte. Eine "live" Verbindung, bei der sich das Dashboard eigenständig frische ACOS-Daten holt, ist mit dem aktuellen Aufbau also nicht möglich. Es sei denn, Alchimedus bietet eine offizielle externe API mit eigenem Zugangsschlüssel an, die dein Mac direkt ansprechen dürfte – das weiß ich nicht, das müsstest du dort erfragen.

Was dagegen schon heute in Ansätzen funktioniert, siehe Donau Drive: Ich hole ACOS-Daten pro Sitzung und schreibe sie ins CRM – als `next_action`-Feld in der Firmenakte, als Aufgaben mit dem Präfix SICHT-. Das Dashboard braucht dafür gar keine eigene ACOS-Anbindung. Es muss nur diese bereits abgelegten Signale zusammen mit deinen eigenen fälligen Aufgaben anzeigen. Die "Verbindung zu ACOS" wäre dann kein technisches Kabel, sondern ein Rhythmus: Ich ziehe morgens frisch, das Dashboard zeigt, was daraus im CRM liegt.

**Vorschlag für das Panel:**

- Neuer, erster Tab "☀️ Heute" – löst die Aufgaben-Ansicht als Startbildschirm ab, oder steht davor, wie du magst.
- Drei Quellen fließen zusammen:
  1. Eigene fällige und überfällige Aufgaben – im Code schon fast fertig vorhanden (`overdue`, `today_t` in `build_dashboard()`), müssen nur als eigenes Panel statt nur als Alarmbanner oben erscheinen.
  2. `next_action`-Felder aus Firmenakten, für die noch keine passende Aufgabe existiert – Abgleich per Text und Firma gegen `tasks.json`.
  3. Offene Punkte aus dem letzten ACOS-Pulse-Bericht, die ich beim morgendlichen Durchlauf ablege, aber noch nicht in eine Aufgabe verwandelt habe.
- Jede Zeile zeigt, worum es geht, welche Firma betroffen ist, und woher der Hinweis kommt (👤 eigene Aufgabe, 🏢 Firmennotiz, 📡 ACOS). Dazu zwei Aktionen: "Löschen" – kein Handlungsbedarf, verschwindet aus der Liste, braucht eine kleine Merkliste, damit derselbe Hinweis nicht am nächsten Tag wieder auftaucht – und "In Aufgabe umwandeln" – übernimmt Text und Firma 1:1 als neue Zeile in `tasks.json`. Danach taucht der Punkt nicht mehr als Vorschlag auf, sondern läuft als echte Aufgabe weiter.
- Der morgendliche Ablauf aus deiner Projektvorgabe (8:00 Uhr) bekommt damit eine sichtbare Heimat: Ich ziehe frische ACOS-Stände für alle CRM-Firmen, die auch bei ACOS geführt werden, aktualisiere die Firmenakten und lege SICHT-Aufgaben an. Das Ergebnis landet automatisch im Heute-Panel, ohne dass ich dir das zusätzlich schreiben muss.

**Aufwand:** mittel bis hoch. Der eigentlich neue Teil ist der Abgleich "was ist schon Aufgabe, was ist nur Signal" und die Merkliste für gelöschte Vorschläge. Der ACOS-Teil selbst ist kein neuer Code – nur ein bestehender Handgriff, der jetzt jeden Morgen läuft statt nur bei Bedarf.

**Offene Frage an dich:** Reicht dir "einmal täglich durch mich aktualisiert" für ACOS, oder brauchst du wirklich häufigere oder sogar live Stände? Davon hängt ab, ob die Frage nach einer externen API oben überhaupt relevant wird.

---

## Empfohlene Reihenfolge

Zwei der drei Punkte fassen Live-Daten an, in einem System ohne aktive Versionierung. Deshalb würde ich so vorgehen:

1. Backup aktivieren – ein seit Wochen vorbereiteter, einzelner Schritt.
2. Baustein 1: Personen-Tab mit Kampagne. Geringstes Risiko, sofort sichtbarer Nutzen, keine Migration bestehender Daten nötig.
3. Baustein 2a + 2d: Wert-Feld und Kunde "Intern". Auch risikoarm, reine Ergänzung.
4. Baustein 2b/2c (Pipeline → Projekt, Zusammenführung mit Aufgaben) und Baustein 3 (Heute-Panel). Die zwei größten Umbauten – am besten nacheinander, nicht gleichzeitig.

Sag mir, ob das so passt, ob eine andere Reihenfolge sinnvoller ist, oder ob du bei den offenen Fragen (Kampagnen frei oder feste Liste, Weg A oder B bei Projekt, tägliche oder häufigere ACOS-Aktualisierung) schon eine Richtung hast – dann fange ich mit der Umsetzung an.
