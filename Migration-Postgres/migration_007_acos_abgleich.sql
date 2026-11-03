-- Migration 007 (2026-10-20): Abgleich CRM -> ACOS (Schritt 3, Trockenlauf)
-- * acos_verknuepfung.anlegen: Du hast "Neu in ACOS anlegen" bestaetigt; der
--   Mandant wird beim ersten scharfen Lauf angelegt und bekommt dann seine ID.
-- * acos_laeufe: Protokoll je Lauf mit Bericht (was gesendet/abgelegt wurde
--   bzw. im Trockenlauf: was gesendet/abgelegt wuerde).
-- Rein additiv und idempotent.

ALTER TABLE acos_verknuepfung ADD COLUMN IF NOT EXISTS anlegen BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS acos_laeufe (
    id              SERIAL PRIMARY KEY,
    start           TIMESTAMPTZ NOT NULL DEFAULT now(),
    ende            TIMESTAMPTZ,
    modus           TEXT NOT NULL DEFAULT 'trocken',   -- trocken | scharf
    ausgeloest_von  TEXT,
    ok              BOOLEAN,
    meldung         TEXT,
    zahlen          JSONB NOT NULL DEFAULT '{}',       -- {vorschlaege, gesendet, archiviert, wissen_neu, abgelegt, fehler}
    bericht         JSONB NOT NULL DEFAULT '[]'        -- [{firma, aktion, text}]
);
