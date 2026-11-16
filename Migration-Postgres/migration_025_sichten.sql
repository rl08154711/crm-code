-- Migration 025 (2026-11-16): Gespeicherte Sichten fuer die Schnellauswahl
-- in Stammdaten -> Unternehmen und Kontakte. Eine Sicht ist eine benannte
-- Filterkombination (Chips + Suchtext) und gilt fuer alle Nutzer des CRM.
-- Idempotent:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_025_sichten.sql

CREATE TABLE IF NOT EXISTS gespeicherte_sichten (
    id            SERIAL PRIMARY KEY,
    bereich       TEXT NOT NULL CHECK (bereich IN ('firmen', 'personen')),
    name          TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 60),
    filter        JSONB NOT NULL DEFAULT '{}'::jsonb,
    position      INTEGER NOT NULL DEFAULT 100,
    angelegt_von  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    angelegt_am   TIMESTAMPTZ NOT NULL DEFAULT now(),
    geaendert_am  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS gespeicherte_sichten_name_uq
    ON gespeicherte_sichten (bereich, lower(name));

-- Zwei Startsichten, damit die Leiste nicht leer ist (loeschbar wie jede andere)
INSERT INTO gespeicherte_sichten (bereich, name, filter, position) VALUES
  ('firmen', 'Aktive Mandanten',   '{"chips": {"art": ["mandant"], "st": ["kunde", "aktiv"]}, "q": ""}', 10),
  ('firmen', 'Lange kein Kontakt', '{"chips": {"art": ["mandant"], "kt": ["r"]}, "q": ""}', 20)
ON CONFLICT DO NOTHING;

SELECT bereich, name FROM gespeicherte_sichten ORDER BY bereich, position, lower(name);
