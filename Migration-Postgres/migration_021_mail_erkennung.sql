-- Migration 021 (2026-10-31, Umbau Schritt 10): Erkennung im Mail-Review
-- lead:   aus einer Terminbuchung (Zeeg) erkannter Interessent {quelle, name, email, firma, termin, ort, info}
-- firmen: weitere Unternehmen, die die Mail betreffen [{firma, grund}] (Aufteilen)
-- Aufgabenvorschlaege aus Fristen ("bis Freitag") stehen in task_suggestion.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/021_mail_erkennung.sql
BEGIN;
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS lead   jsonb;
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS firmen jsonb;
COMMIT;
SELECT count(*) AS eintraege_im_review FROM mail_review_queue;
