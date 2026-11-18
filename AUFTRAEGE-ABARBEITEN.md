# ACOS-Aufträge aus dem CRM abarbeiten (Anleitung für Claude)

Seit 17.11.2026 (Variante A, Migration 028) laufen Aufträge vollständig über ACOS, ohne Mac und
ohne Nextcloud-Ordner. Die geplante Aufgabe „ACOS-Aufträge abarbeiten (Server)“ arbeitet sie
stündlich ab; von Hand: „arbeite die offenen ACOS-Aufträge ab“.

## Wo die Aufträge liegen

In der ACOS-Kundenakte des Mandanten als Wissensobjekte:

| Art (`kind`) | Titel | Wer legt an | Inhalt (`data`) |
|---|---|---|---|
| `crm_auftrag` | `ACOS-Auftrag AUF-JJJJ-NNNN` | CRM | auftrags_id, acos_client_id, artefakttyp, artefakttyp_titel, thema, hinweise, ggf. ersetzt |
| `crm_rueckfrage` | `Rückfrage AUF-JJJJ-NNNN` | Claude | auftrags_id, status (`rueckfrage` oder `fehler`), text |

Beide Arten sind Betriebsobjekte: Das CRM legt sie nicht als Kundenwissen in der Nextcloud ab, und sie
erscheinen nicht im Kontext der Skills. Sie enthalten keine Namen.

## Offen ist ein Auftrag, wenn

- es kein Artefakt beim Mandanten gibt, dessen Titel die Auftrags-ID enthält,
- es kein `crm_rueckfrage`-Objekt mit der Auftrags-ID gibt und
- kein anderer Auftrag `"ersetzt": "<diese ID>"` trägt.

Offene Aufträge findet `am_acos_knowledge_list` mit `kind: "crm_auftrag"` ohne Mandant (organisationsweit).

## Ablauf je Auftrag

1. Skill **mandantenfiles**, jeder ACOS-Aufruf mit `datenschutz: "stealth"`, Mandant nur über die Nummer.
2. Skill-Vorgabe (`am_acos_artifact_specs_get`, slug = `artefakttyp`) und `am_acos_context_pack` laden.
3. Rückfrage statt Artefakt, wenn ein Pflicht-Input fehlt, das Thema unklar ist oder kostenpflichtige
   Recherchen nötig wären, die die Hinweise nicht ausdrücklich freigeben. Rückfragen als Entweder-oder
   mit vorgegebenen Antworten formulieren, nicht als Ja-Nein-Frage.
4. Sonst Artefakt nach der Vorgabe, nur aus ACOS-Daten, gespeichert mit `am_acos_artifact_save`,
   Titel `<Kurztitel> [AUF-JJJJ-NNNN]` ohne Namen.
5. Nichts überschreiben, archivieren oder löschen.

## Im CRM danach

„Bei ACOS nachsehen“ (oder der Abgleich um 6:30): Ergebnis → `<Kunde>/ACOS/Wissen`, Kundenwissen,
Aufgabe „Bearbeitet“, Verlauf, Journal. Rückfrage → steht in der Aufgabe, Antwort legt den Folgeauftrag an.
Abschließen nur Ronald mit „Geprüft, Aufgabe abschließen“.
