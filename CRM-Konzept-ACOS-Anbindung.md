# CRM-Konzept: Anbindung an ACOS

Stand: 21.09.2026
Status: Entwurf abgestimmt, noch nicht umgesetzt
Voraussetzung: Postgres-Migration des CRM (siehe CRM-Konzept-Postgres-Migration.md)

---

## 1. Worum es geht

Das CRM (Postgres, CPX12) und ACOS (Alchimedus Consulting OS) halten beide Daten zu
denselben Unternehmen. ACOS trägt die inhaltliche Beratungsarbeit – Recherche, Analysen,
Berichte, Fragebögen, Wochenberichte. Das CRM trägt die kaufmännisch-organisatorische Seite –
Akquise, Aufgaben, Aktivitäten, Mailverkehr, und zusätzlich Kontakte, die ACOS gar nicht kennt
(Netzwerk, Dienstleister).

Ziel ist **keine Datenmigration und keine Doppelhaltung**, sondern eine Verknüpfung:
Im CRM soll sichtbar sein, *dass* und *worum es* bei einem ACOS-Objekt geht – der Inhalt
selbst bleibt in ACOS.

### Entscheidungen

| Frage | Entscheidung |
|---|---|
| Datenhaltung | Keine Inhalte spiegeln. Nur Bezeichnung, eine Zeile Zusammenfassung, Link. |
| Umfang | Gilt für Kunden, Leads und archivierte Akten gleichermaßen. |
| Netzwerk/Dienstleister | Bleiben rein im CRM, ACOS-Felder bleiben leer. |
| Kontakt-Sync | In beide Richtungen, aber **auf Befehl**, nicht automatisch. |
| Konfigurierbarkeit | Pro ACOS-Objekttyp einstellbar, ob und wie er im CRM erscheint. |

---

## 2. Befunde: Was ACOS liefert

Geprüft am 21.09.2026 über die ACOS-Schnittstelle und die Weboberfläche,
am Beispiel des Mandanten "Fahrschule Donau Drive GmbH".

### 2.1 Objekttypen (`kind`)

Vorgefunden wurden: `report`, `notes`, `measure`, `collaboration_frame`,
`questionnaire_response`, `website_profile`, `sistrix_backlinks`, `sistrix_rankings`,
`sistrix_ai_visibility`, `sistrix_keyword_tracking`.

**Diese Liste ist nicht abschließend und wird wachsen.** Das Datenmodell darf sie
deshalb nicht fest verdrahten – `kind` ist ein freies Textfeld, kein Aufzählungstyp.

### 2.2 Felder je Objekt

Die Objektliste liefert: `id`, `kind`, `title`, `source`, `version`, `client_id`,
`project_id`, `updated_at`. Beim Einzelabruf zusätzlich den Inhalt, die Beziehungen
zu anderen Objekten (`edges`, z. B. `derived_from`) und die Versionsanzahl.
Bei Dokumenten mit Markdown-Inhalt gibt es außerdem eine Prüfsumme (`content_hash`)
und eine Kapitelgliederung.

**Es gibt kein Feld mit einer Kurzbeschreibung.** Die eine Zeile Zusammenfassung
muss beim Abgleich erzeugt werden (siehe Abschnitt 4).

### 2.3 Wochenberichte (Pulse)

Pro Mandant existieren fortlaufende Berichte mit `headline`, Zusammenfassung,
Konfidenzwert (1–3) und den Abschnitten Veränderungen, Risiken, Chancen,
nächste Schritte. Zeiträume: `weekly`, `monthly`, `quarterly`.

Die `headline` ist bereits eine fertige Ein-Zeilen-Zusammenfassung und muss
nicht erst erzeugt werden.

> **Wichtige Einschränkung:** Leads sind laut ACOS aus dem Pulse-Feed ausgenommen,
> bis sie gewonnen sind. Für Leads gibt es also in der Regel keinen Wochenbericht.
> Die Anzeige im CRM muss das abfangen und darf nicht ins Leere laufen.

---

## 3. Adressmuster der ACOS-Oberfläche

Basisadresse: `https://acos.alchimedus.pro`

Am 21.09.2026 durch Aufruf verifiziert:

| Ziel | Muster | Status |
|---|---|---|
| Kundenakte | `/clients/{client_id}` | funktioniert |
| Projekt | `/projects/{project_id}` | funktioniert |
| Dokument/Bericht | `/artifacts/{object_id}` | funktioniert bei `kind = report` |
| Fragebogen-Verlauf | `/clients/{client_id}/assessments` | Link vorhanden |
| Fragebogen-Auswertung | `/projects/{project_id}/assessments/{assessment_id}/auswertung` | eigene ID, s. u. |

Die IDs sind identisch mit denen der Schnittstelle – `client_id`, `project_id` und
die Objekt-ID lassen sich also direkt in Adressen einsetzen. Der Parameter `?from=...`
dient nur der Zurück-Navigation und ist nicht erforderlich.

### Zwei Einschränkungen

**Nicht jeder Objekttyp hat eine eigene Seite.** Der Aufruf von `/artifacts/{id}`
mit der ID eines Sistrix-Datenobjekts liefert „404 – Artefakt nicht gefunden".
Die Route bedient offenbar nur Dokumente mit Markdown-Inhalt. Für alle anderen
Typen ist die Kundenakte das nächstbeste Ziel.

**Fragebogen-Auswertungen haben eine eigene ID-Welt.** Die Auswertungs-ID in der
Adresse ist nicht die ID des Wissensobjekts vom Typ `questionnaire_response`.
Eine Zuordnung ist über die Schnittstelle derzeit nicht erkennbar; als Ziel dient
deshalb `/clients/{client_id}/assessments`.

---

## 4. Wie die Daten ins CRM kommen

Ein direkter Programmzugriff auf ACOS (API mit Zugangsschlüssel) ist **nicht bestätigt** –
Alchimedus hat dazu bislang keine Auskunft gegeben. Der Entwurf setzt deshalb bewusst
nicht darauf, sondern nutzt den Weg, der heute funktioniert.

### Ablauf

1. Eine KI-Sitzung mit ACOS-Zugang (Cowork oder lokales Claude Code) liest für jede
   verknüpfte Firma die Objektliste und den neuesten Wochenbericht.
2. Für jedes Objekt, das neu ist oder dessen `version` bzw. `content_hash` sich
   geändert hat, wird der Inhalt einmal gelesen und daraus **eine Zeile** formuliert.
   Unveränderte Objekte werden übersprungen – das hält den Abgleich billig.
3. Die Sitzung schickt das Ergebnis per HTTPS an das CRM.

Punkt 3 funktioniert aus jeder Umgebung heraus, weil der CPX12 öffentlich erreichbar ist –
anders als SSH, das aus der Cowork-Sandbox heraus nicht zur Verfügung steht.

### Auslösung

- **Auf Zuruf:** „Aktualisiere den ACOS-Abgleich für Firma X" bzw. für alle verknüpften Firmen.
- **Später optional geplant:** eine wiederkehrende Aufgabe, die das täglich ohne Zutun erledigt.

### Endpunkt im CRM

```
POST /api/acos-sync
Authorization: Bearer <Token aus secrets/>
Content-Type: application/json

{
  "acos_client_id": "c99a704e-...",
  "objekte": [
    {
      "acos_object_id": "53234475-...",
      "kind": "report",
      "bezeichnung": "BAFA-Bericht Liquiditätsmanagement (Entwurf)",
      "zusammenfassung": "Entwurf des Förderberichts mit Liquiditätsanalyse und Maßnahmenkatalog.",
      "acos_project_id": "e94e74ee-...",
      "version": 1,
      "content_hash": "sha256:7b01e8...",
      "acos_updated_at": "2026-09-11T14:57:52Z"
    }
  ],
  "pulse": {
    "acos_report_id": "e1ed3fc6-...",
    "zeitraum": "weekly",
    "headline": "KI-Sichtbarkeit springt auf 27 % ...",
    "zusammenfassung": "...",
    "konfidenz": 3,
    "generiert_am": "2026-09-18T22:06:28Z",
    "abschnitte": { "veraenderungen": "...", "risiken": "...", "chancen": "...", "naechste_schritte": "..." }
  }
}
```

Der Endpunkt schreibt per Upsert, ist also beliebig oft wiederholbar.
Er speichert **alles**, was ankommt – auch Typen, die noch nicht konfiguriert sind.
Die Konfiguration steuert nur die Anzeige, nicht die Speicherung.

### Gegenrichtung: Kontakt nach ACOS

Gleiches Muster, umgekehrt: Eine KI-Sitzung legt den Mandanten in ACOS an
(das dortige Anlegen ist namensgleich-idempotent, ein vorhandener Mandant wird
zurückgegeben statt doppelt angelegt) und meldet die erhaltene ID per
`POST /api/acos-link` an das CRM zurück, wo sie in `acos_client_id` landet.

---

## 5. Datenmodell

```sql
-- Verknüpfung. Nullable: Netzwerk- und Dienstleisterkontakte bleiben leer.
ALTER TABLE firmen   ADD COLUMN acos_client_id UUID;
ALTER TABLE personen ADD COLUMN acos_client_id UUID;

CREATE INDEX idx_firmen_acos   ON firmen(acos_client_id);
CREATE INDEX idx_personen_acos ON personen(acos_client_id);


-- Gespiegelte Objektliste: nur Metadaten, keine Inhalte.
CREATE TABLE acos_objekte (
    id               SERIAL PRIMARY KEY,
    acos_object_id   UUID NOT NULL UNIQUE,
    acos_client_id   UUID NOT NULL,
    firma_id         INTEGER REFERENCES firmen(id) ON DELETE CASCADE,
    person_id        INTEGER REFERENCES personen(id) ON DELETE CASCADE,
    kind             TEXT NOT NULL,            -- bewusst frei, kein ENUM
    bezeichnung      TEXT NOT NULL,
    zusammenfassung  TEXT,                     -- die eine Zeile
    acos_project_id  UUID,
    version          INTEGER,
    content_hash     TEXT,
    acos_updated_at  TIMESTAMPTZ,
    synced_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_acos_objekte_firma ON acos_objekte(firma_id);
CREATE INDEX idx_acos_objekte_kind  ON acos_objekte(kind);


-- Wochenberichte. Angezeigt wird der jeweils neueste, Historie bleibt erhalten.
CREATE TABLE acos_pulse (
    id               SERIAL PRIMARY KEY,
    acos_report_id   UUID NOT NULL UNIQUE,
    acos_client_id   UUID NOT NULL,
    firma_id         INTEGER REFERENCES firmen(id) ON DELETE CASCADE,
    zeitraum         TEXT,
    headline         TEXT NOT NULL,
    zusammenfassung  TEXT,
    konfidenz        INTEGER,
    generiert_am     TIMESTAMPTZ,
    abschnitte       JSONB,                    -- Veränderungen/Risiken/Chancen/nächste Schritte
    synced_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_acos_pulse_firma ON acos_pulse(firma_id, generiert_am DESC);


-- Typ-Konfiguration: was erscheint wo, und wohin verlinkt es.
CREATE TABLE acos_typen (
    kind            TEXT PRIMARY KEY,
    anzeigename     TEXT NOT NULL,
    aktiv           BOOLEAN NOT NULL DEFAULT false,
    link_muster     TEXT,
    zuerst_gesehen  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Startwerte für `acos_typen`

```sql
INSERT INTO acos_typen (kind, anzeigename, aktiv, link_muster) VALUES
  ('report',                 'Bericht',              true,  '/artifacts/{object_id}'),
  ('questionnaire_response', 'Fragebogen',           true,  '/clients/{client_id}/assessments'),
  ('notes',                  'Notizen',              true,  '/clients/{client_id}'),
  ('collaboration_frame',    'Ziel & Zusammenarbeit',true,  '/clients/{client_id}'),
  ('measure',                'Maßnahme',             true,  '/clients/{client_id}'),
  ('website_profile',        'Webprofil',            false, '/clients/{client_id}'),
  ('sistrix_rankings',       'SEO-Rankings',         false, '/clients/{client_id}'),
  ('sistrix_backlinks',      'Backlinks',            false, '/clients/{client_id}'),
  ('sistrix_ai_visibility',  'KI-Sichtbarkeit',      false, '/clients/{client_id}'),
  ('sistrix_keyword_tracking','Keyword-Tracking',    false, '/clients/{client_id}');
```

Die Sistrix-Typen stehen bewusst auf `aktiv = false`: Für Insolvenz- und
Fördermittelmandate sind sie ohne Belang und würden die Akte nur zumüllen.
Bei Marketingmandaten lassen sie sich einschalten.

### Unbekannte Typen

Trifft der Abgleich auf einen `kind`-Wert, der noch nicht in `acos_typen` steht,
legt er ihn automatisch an – mit `aktiv = false` und `link_muster` auf
`/clients/{client_id}`. Das Objekt wird gespeichert, erscheint aber noch nicht.
Im CRM sollte dafür ein dezenter Hinweis auftauchen, etwa
„ACOS liefert 3 neue Objekttypen, noch nicht konfiguriert".

So geht nichts verloren, und nichts erscheint ungefragt.

### Basisadresse

`https://acos.alchimedus.pro` gehört in die vorhandene Konfiguration (`config.json`),
nicht fest in den Code. Ist sie leer, zeigt das CRM statt eines Links die Objekt-ID
mit Kopier-Knopf.

---

## 6. Anzeige im CRM

In der Firmenakte, unterhalb der Stammdaten, ein Abschnitt „ACOS":

**Oben der Lagebericht.** Headline und Zusammenfassung des neuesten Wochenberichts,
dazu Datum und Konfidenz. Fehlt er – etwa bei einem Lead –, steht dort
„Noch kein ACOS-Wochenbericht" statt einer leeren Fläche.

**Darunter die Objektliste.** Je Zeile: Anzeigename des Typs, Bezeichnung,
die eine Zeile Zusammenfassung, Datum, Link. Nur Typen mit `aktiv = true`.
Sortiert nach `acos_updated_at` absteigend.

**Ohne Verknüpfung** erscheint der ganze Abschnitt nicht, sondern nur ein
unaufdringlicher Knopf „Mit ACOS verknüpfen".

Der Link wird aus Basisadresse und `link_muster` zusammengesetzt, mit
`{object_id}`, `{client_id}` und `{project_id}` als Platzhaltern.

---

## 7. Bewusst offen

- **Direkter API-Zugang zu ACOS.** Ungeklärt. Sobald Alchimedus dazu etwas sagt,
  lässt sich der Abgleich ohne KI-Sitzung dazwischen betreiben – am Datenmodell
  ändert das nichts, nur an Schritt 1 und 2 des Ablaufs.
- **Fragebogen-Auswertungen** verlinken vorerst auf die Übersicht statt auf die
  einzelne Auswertung, weil die Zuordnung der IDs nicht erkennbar ist.
- **Personen-Ebene.** ACOS führt Mandanten flach; eine Akte kann eine Firma oder
  eine Einzelperson sein. Mehrere Ansprechpartner unter einem Mandanten kennt ACOS
  nicht. Deshalb `acos_client_id` an beiden Tabellen, aber keine Zuordnung
  einzelner CRM-Personen zu einer ACOS-Firmenakte.
- **Einstellungen je Nutzer.** Vorerst nur organisationsweite Konfiguration.
  Falls später nötig, als zweite Ebene obendrauf, die die globale nur einschränkt.
- **Archivierte Mandanten.** ACOS kennt sichtbar nur `lead` und `active`.
  Ob es einen Archivstatus gibt, ist offen – für die Verknüpfung spielt es keine Rolle.

---

## 8. Reihenfolge der Umsetzung

1. Spalten `acos_client_id` ergänzen, Tabellen anlegen, Startwerte einspielen.
2. Endpunkte `POST /api/acos-sync` und `POST /api/acos-link` in `crm_serve.py`,
   Token in `secrets/`.
3. Anzeige in der Firmenakte.
4. Verknüpfung der bestehenden Mandate von Hand (es sind derzeit sechs).
5. Ersten Abgleich auf Zuruf laufen lassen und prüfen.
6. Erst danach über eine wiederkehrende Aufgabe nachdenken.

Wie im Projekt üblich: nichts direkt am Live-Server ändern, sondern erst in der
Sandbox testen. Es gibt kein Git, also keine Rücksicherung über einen Commit.
