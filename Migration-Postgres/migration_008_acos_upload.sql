-- Migration 008 (2026-10-24): Dokumente aus dem Kundenordner an ACOS senden
-- Der Server laedt eine Datei aus /Arbeitsdateien/Kunden/<Firma>/ direkt in die
-- Kundenakte in ACOS (ohne Claude). Hier steht nur, was wann gesendet wurde.
-- Rein additiv und idempotent.

CREATE TABLE IF NOT EXISTS acos_uploads (
    id               SERIAL PRIMARY KEY,
    firma_id         INTEGER NOT NULL REFERENCES firmen(id) ON DELETE CASCADE,
    pfad             TEXT NOT NULL,                  -- relativ zum Kundenordner, z. B. Unterlagen/Bilanz 2025.pdf
    groesse          BIGINT,
    etag             TEXT,                           -- Stand der Datei beim Senden
    acos_client_id   TEXT NOT NULL,
    acos_file_id     TEXT,
    acos_document_id TEXT,
    status           TEXT NOT NULL DEFAULT 'gesendet' CHECK (status IN ('gesendet', 'fehler')),
    meldung          TEXT,
    gesendet_am      TIMESTAMPTZ NOT NULL DEFAULT now(),
    gesendet_von     TEXT
);
CREATE INDEX IF NOT EXISTS idx_acos_uploads_firma ON acos_uploads(firma_id, pfad);
