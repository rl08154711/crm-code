-- Migration 014 (2026-10-31, Umbau Schritt 3): Beteiligte
-- Ein Netzwerk-Unternehmen (Bank, Steuerbuero ...) ist an einem Mandat beteiligt.
-- Setzt Migration 013 voraus. Ausfuehren als Dienstbenutzer:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -d <datenbank> -f migrations/014_beteiligung.sql
BEGIN;

CREATE TABLE IF NOT EXISTS beteiligung (
    id                serial PRIMARY KEY,
    netzwerk_firma_id integer NOT NULL REFERENCES firmen(id),
    mandant_firma_id  integer NOT NULL REFERENCES firmen(id),
    rolle             text    NOT NULL,
    person_id         integer REFERENCES personen(id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    archiviert_am     timestamptz,
    CONSTRAINT beteiligung_nicht_selbst CHECK (netzwerk_firma_id <> mandant_firma_id),
    CONSTRAINT beteiligung_eindeutig UNIQUE (netzwerk_firma_id, mandant_firma_id, rolle)
);
CREATE INDEX IF NOT EXISTS beteiligung_mandant_idx  ON beteiligung (mandant_firma_id);
CREATE INDEX IF NOT EXISTS beteiligung_netzwerk_idx ON beteiligung (netzwerk_firma_id);

COMMIT;

SELECT 'beteiligung angelegt' AS ergebnis, count(*) AS eintraege FROM beteiligung;
