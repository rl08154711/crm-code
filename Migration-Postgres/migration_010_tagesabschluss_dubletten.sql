-- Migration 010 (2026-10-30): Tagesabschluss und Dublettenpruefung
--
-- tagesabschluss: je Kalendertag ein Abschluss mit Resuemee (was war) und
-- Briefing (was kommt am naechsten Arbeitstag). Entsteht per Knopf
-- "Tag abschliessen" oder nachts automatisch (tagesabschluss.py).
-- Optional geht beides als Markdown-Datei in den eigenen ACOS-Mandanten
-- (Einstellungen > Tagesabschluss an ACOS); die Bewertung entsteht dort und
-- kommt mit dem ACOS-Abgleich als Wissensobjekt zurueck.
--
-- dubletten_ignoriert: Paare, die du ausdruecklich als "keine Dublette"
-- markiert hast, damit sie nicht wieder auftauchen.
--
-- personen.zusammengefuehrt_in: beim Zusammenfuehren wird der zweite
-- Datensatz nicht geloescht, sondern archiviert und hier auf den
-- behaltenen verwiesen. So bleibt der Weg zurueck offen.
--
-- Idempotent: mehrfaches Ausfuehren schadet nicht.

CREATE TABLE IF NOT EXISTS tagesabschluss (
    datum            DATE PRIMARY KEY,
    erstellt_am      TIMESTAMPTZ NOT NULL DEFAULT now(),
    erstellt_von     TEXT NOT NULL,                  -- Benutzername oder 'automatik'
    resuemee         JSONB NOT NULL DEFAULT '{}',
    briefing         JSONB NOT NULL DEFAULT '{}',    -- fuer briefing->>'fuer' (naechster Arbeitstag)
    notiz            TEXT,                           -- eigene Zeile beim Abschliessen, optional
    bewertung        TEXT,
    bewertung_status TEXT NOT NULL DEFAULT 'aus',    -- aus / gesendet / fehler
    bewertung_am     TIMESTAMPTZ,                    -- wann an ACOS gesendet
    acos_meldung     TEXT                            -- Dateiname bzw. Fehlertext der Uebertragung
);
ALTER TABLE tagesabschluss ADD COLUMN IF NOT EXISTS acos_meldung TEXT;

CREATE TABLE IF NOT EXISTS dubletten_ignoriert (
    person_a     INTEGER NOT NULL REFERENCES personen(id) ON DELETE CASCADE,
    person_b     INTEGER NOT NULL REFERENCES personen(id) ON DELETE CASCADE,
    markiert_am  TIMESTAMPTZ NOT NULL DEFAULT now(),
    markiert_von TEXT,
    PRIMARY KEY (person_a, person_b),
    CHECK (person_a < person_b)
);

ALTER TABLE personen ADD COLUMN IF NOT EXISTS zusammengefuehrt_in INTEGER REFERENCES personen(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_personen_email_lower  ON personen (lower(email));
CREATE INDEX IF NOT EXISTS idx_personen_email2_lower ON personen (lower(email2));
CREATE INDEX IF NOT EXISTS idx_aktivitaeten_datum    ON aktivitaeten (datum);
CREATE INDEX IF NOT EXISTS idx_tasks_completed       ON tasks (completed_at);
