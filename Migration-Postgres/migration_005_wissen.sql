-- Migration 005 (2026-10-19): Wissens-DB (DK-Wissen aus Nextcloud)
-- Dokumente aus den Vault-Ordnern Fachwissen und Vorlagen, als Text fuer die
-- Volltextsuche (deutsch). Die Dateien selbst bleiben in Nextcloud, hier liegt
-- nur der erkannte Text. Rein additiv und idempotent.

CREATE TABLE IF NOT EXISTS wissen_dokumente (
    id              SERIAL PRIMARY KEY,
    pfad            TEXT NOT NULL UNIQUE,          -- relativ zum Vault, z. B. Fachwissen/Sanierung/StaRUG.pdf
    name            TEXT NOT NULL,
    ordner          TEXT NOT NULL,                 -- Unterordner ohne Dateiname
    typ             TEXT NOT NULL,                 -- md, pdf, bild, docx, text, sonst
    groesse         BIGINT,
    etag            TEXT,
    geaendert_am    TIMESTAMPTZ,
    inhalt          TEXT NOT NULL DEFAULT '',
    ocr             BOOLEAN NOT NULL DEFAULT false,
    namens_treffer  JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'ok',    -- ok, fehler, zu_gross
    fehler          TEXT,
    abgeglichen_am  TIMESTAMPTZ NOT NULL DEFAULT now(),
    suchtext        tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('german', coalesce(name, '')), 'A') ||
                        setweight(to_tsvector('german', coalesce(inhalt, '')), 'B')) STORED
);
CREATE INDEX IF NOT EXISTS idx_wissen_suchtext ON wissen_dokumente USING GIN (suchtext);

CREATE TABLE IF NOT EXISTS wissen_laeufe (
    id              SERIAL PRIMARY KEY,
    start           TIMESTAMPTZ NOT NULL DEFAULT now(),
    ende            TIMESTAMPTZ,
    neu             INTEGER NOT NULL DEFAULT 0,
    geaendert       INTEGER NOT NULL DEFAULT 0,
    geloescht       INTEGER NOT NULL DEFAULT 0,
    fehler          INTEGER NOT NULL DEFAULT 0,
    offen           INTEGER NOT NULL DEFAULT 0,    -- in diesem Lauf nicht mehr geschafft, kommt im naechsten
    meldung         TEXT,
    ausgeloest_von  TEXT
);
