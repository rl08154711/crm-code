-- Migration 030 (2026-11-23): Pipeline-Stand je Tag fuer das Fokusband auf "Heute"
-- Summe und Zahl der offenen Projekte (Phasen anbahnung und angebot), ein Wert je Tag.
-- Geschrieben vom CRM, wenn "Heute" geladen wird (letzter Stand des Tages gilt).
-- Vorher gibt es keine Geschichte: Vergleich zur Vorwoche und Kurve fuellen sich ab dem Einspielen.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_030_pipeline_stand.sql
BEGIN;

CREATE TABLE IF NOT EXISTS pipeline_stand (
    tag         date PRIMARY KEY,
    summe       numeric(14,2) NOT NULL DEFAULT 0,
    anzahl      integer NOT NULL DEFAULT 0,
    ohne_wert   integer NOT NULL DEFAULT 0,
    erfasst_am  timestamptz NOT NULL DEFAULT now()
);

COMMIT;

SELECT 'pipeline_stand' AS tabelle, count(*) AS zeilen FROM pipeline_stand;
