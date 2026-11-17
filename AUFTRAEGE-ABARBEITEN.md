# ACOS-Aufträge aus dem CRM abarbeiten (Anleitung für Claude am Mac)

Seit Migration 026 kann im CRM eine Aufgabe eines Mandanten als Auftrag an ACOS übergeben werden.
Das CRM legt dafür eine Auftragsdatei in der Nextcloud ab. Ronald sagt am Mac
„arbeite die offenen ACOS-Aufträge ab“, dann gilt dieser Ablauf.

## Wo die Dateien liegen

Nextcloud `/Arbeitsdateien/Aufträge` (am Mac über den Nextcloud-Client synchronisiert):

| Ordner | Wer schreibt | Inhalt |
|---|---|---|
| `offen/AUF-JJJJ-NNNN.json` | CRM | der Auftrag (nur anlegen, nie ändern) |
| `ergebnis/AUF-JJJJ-NNNN.json` | Claude | nur bei Rückfrage oder Fehler, als **neue** Datei |

Auftragsdatei (Beispiel, fiktiv):

```json
{
  "auftrags_id": "AUF-2026-0007",
  "erstellt_am": "2026-11-17T10:15:00+01:00",
  "acos_client_id": "<ID des ACOS-Mandanten>",
  "artefakttyp": "mandatsstart-analyse",
  "artefakttyp_titel": "Mandatsstart-Analyse",
  "thema": "Wettbewerbsumfeld im regionalen Markt",
  "hinweise": "",
  "anweisung": "…"
}
```

Die Datei enthält keinen Mandantennamen. Ein Folgeauftrag (Antwort auf eine Rückfrage oder
Nachbesserung) trägt zusätzlich `"ersetzt": "<alte Auftrags-ID>"`; die Antwort steht dann in `hinweise`. Erledigt ist ein Auftrag, wenn es in ACOS ein Artefakt mit
seiner Auftrags-ID im Titel gibt oder unter `ergebnis/` eine Datei mit seiner ID liegt.

## Ablauf je Auftrag

1. Offene Aufträge finden: alle Dateien in `offen/`, zu denen es weder ein ACOS-Artefakt mit der ID im
   Titel (`am_acos_knowledge_list` mit `client_id`) noch eine Datei in `ergebnis/` gibt.
2. Skill **mandantenfiles** anwenden, `datenschutz: "stealth"`, Mandant nur über `acos_client_id`.
   Fehlende Unterlagen zieht das CRM bei der Übergabe selbst nach; trotzdem kurz prüfen.
3. Vorlage laden (`am_acos_artifact_specs_get`, Slug aus `artefakttyp`), Voraussetzungen prüfen
   (Mandatsstart-Analyse braucht Stammdaten und das Website-Profil).
4. Artefakt erstellen und mit `am_acos_artifact_save` speichern:
   - `slug` = `artefakttyp`, `client_id` = `acos_client_id`
   - Titel **mit Auftrags-ID in eckigen Klammern**, ohne Mandantennamen, z. B.
     `Mandatsstart-Analyse [AUF-2026-0007]`
   - Thema und Hinweise aus der Auftragsdatei berücksichtigen, Platzhalter (PERSON_…) unverändert lassen.
5. Fehlt etwas Wesentliches oder ist das Thema unklar: **kein** Artefakt speichern, sondern
   `ergebnis/AUF-JJJJ-NNNN.json` neu anlegen:
   `{"auftrags_id": "AUF-2026-0007", "status": "rueckfrage", "text": "Welche Region ist gemeint?"}`
   Bei einem technischen Problem `"status": "fehler"`.
6. Nichts überschreiben, nichts löschen – weder in der Nextcloud noch in ACOS.

## Was danach im CRM passiert

Ronald klickt in der Aufgabe auf „Bei ACOS nachsehen“ (oder der Abgleich um 6:30 läuft):
Das CRM legt das Artefakt unter `<Kunde>/ACOS/Wissen` ab (von dort ins Kundenwissen, stündlich),
setzt den Auftrag auf „Ergebnis da“, die Aufgabe auf „Bearbeitet“, schreibt Verlauf und Journal.
Abschließen nur Ronald mit „Geprüft, Aufgabe abschließen“.
