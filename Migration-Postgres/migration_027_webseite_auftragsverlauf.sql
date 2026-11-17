-- Migration 027 (2026-11-17):
--  1. Webseite am Unternehmen. Der ACOS-Abgleich gibt sie als company.website an ACOS weiter
--     (Pflicht-Input Website-Profil der Mandatsstart-Analyse).
--  2. Verlauf der ACOS-Auftraege je Aufgabe. Die automatischen Hinweise stehen dort statt in den
--     Notizen der Aufgabe (die bleiben allein dem Nutzer).
-- Idempotent:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_027_webseite_auftragsverlauf.sql

ALTER TABLE firmen ADD COLUMN IF NOT EXISTS webseite TEXT;

CREATE TABLE IF NOT EXISTS acos_auftrag_verlauf (
    id           SERIAL PRIMARY KEY,
    task_id      TEXT NOT NULL,
    auftrags_id  TEXT,
    zeit         TIMESTAMPTZ NOT NULL DEFAULT now(),
    art          TEXT NOT NULL,          -- uebergeben, rueckfrage, bearbeitet, erledigt, fehler
    text         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS acos_auftrag_verlauf_task_idx ON acos_auftrag_verlauf (task_id, id);

SELECT count(*) FILTER (WHERE webseite IS NOT NULL) AS mit_webseite, count(*) AS unternehmen FROM firmen;
