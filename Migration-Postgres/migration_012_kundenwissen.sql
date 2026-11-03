-- Migration 012 (2026-10-30): Kundenwissen
--
-- Volltextsuche je Kunde, getrennt von der allgemeinen WissensDB (Recherche).
-- Quelle sind die Kundenordner der Nextcloud (Arbeitsdateien/Kunden/<Firma>),
-- und dort nur zwei Unterordner:
--   ACOS/           Artefakte aus ACOS (legt der ACOS-Abgleich ab)
--   Besprechungen/  Besprechungsnotizen und Transkripte, Dateiname mit Datum vorne
-- Dazu kommt das Journal der Firma (Volltextindex auf aktivitaeten).
-- Gesucht wird nur in der Akte der jeweiligen Firma; in der allgemeinen
-- Recherche taucht nichts davon auf, und es gibt keinen Weg zu Claude.
--
-- Rein additiv und idempotent.

CREATE TABLE IF NOT EXISTS kundenwissen (
    id              SERIAL PRIMARY KEY,
    firma_id        INTEGER NOT NULL REFERENCES firmen(id) ON DELETE CASCADE,
    pfad            TEXT NOT NULL UNIQUE,          -- relativ zu den Kundenordnern, z. B. Muster GmbH/Besprechungen/2026-10-28 Bank.txt
    quelle          TEXT NOT NULL,                 -- acos | besprechung
    name            TEXT NOT NULL,                 -- Dateiname
    titel           TEXT NOT NULL DEFAULT '',      -- Dateiname ohne Datum und Endung
    datum           DATE,                          -- aus dem Dateinamen, sonst Aenderungsdatum
    typ             TEXT NOT NULL,                 -- md, text, pdf, docx, bild, sonst
    groesse         BIGINT,
    etag            TEXT,
    geaendert_am    TIMESTAMPTZ,
    inhalt          TEXT NOT NULL DEFAULT '',
    ocr             BOOLEAN NOT NULL DEFAULT false,
    status          TEXT NOT NULL DEFAULT 'ok',    -- ok, fehler, zu_gross
    fehler          TEXT,
    abgeglichen_am  TIMESTAMPTZ NOT NULL DEFAULT now(),
    suchtext        tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('german', coalesce(titel, '')), 'A') ||
                        setweight(to_tsvector('german', coalesce(inhalt, '')), 'B')) STORED
);
CREATE INDEX IF NOT EXISTS idx_kundenwissen_firma    ON kundenwissen (firma_id, quelle, datum DESC);
CREATE INDEX IF NOT EXISTS idx_kundenwissen_suchtext ON kundenwissen USING GIN (suchtext);

-- Journal durchsuchbar machen (deutsche Wortstaemme: "Stundung" findet "gestundet")
CREATE INDEX IF NOT EXISTS idx_aktivitaeten_suchtext ON aktivitaeten
    USING GIN (to_tsvector('german', coalesce(titel, '') || ' ' || coalesce(notiz, '')));

-- Kennzahlen des Kundenwissen-Teils je Abgleichlauf
ALTER TABLE wissen_laeufe ADD COLUMN IF NOT EXISTS kunden JSONB;
