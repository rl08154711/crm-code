-- Migration 015 (2026-10-31, Umbau Schritt 4): Vertraege bei Lieferanten
-- Rechnungen bleiben in Lexware Office; hier steht nur, was fuer Kuendigung
-- und Nachbestellung gebraucht wird. Ausfuehren als Dienstbenutzer:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -d <datenbank> -f migrations/015_vertrag.sql
BEGIN;

CREATE TABLE IF NOT EXISTS vertrag (
    id               serial PRIMARY KEY,
    firma_id         integer NOT NULL REFERENCES firmen(id),
    bezeichnung      text    NOT NULL,
    kundennummer     text,
    kosten           text,
    laufzeit         text,
    kuendigungsfrist text,
    kuendbar_bis     date,
    notiz            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    archiviert_am    timestamptz
);
CREATE INDEX IF NOT EXISTS vertrag_firma_idx ON vertrag (firma_id);

COMMIT;

SELECT 'vertrag angelegt' AS ergebnis, count(*) AS eintraege FROM vertrag;
