-- Migration 020 (2026-10-31, Umbau Schritt 9): Mail-Review mit Status und gesendeten Mails
-- Status: pending (offen) | spaeter | erledigt (uebernommen) | weg (nicht ins CRM)
-- Erledigte und verworfene Eintraege bleiben 30 Tage sichtbar (Rueckgaengig), dann raeumt der Poller sie weg.
-- richtung: ein (Posteingang) | aus (Gesendet); an = Empfaenger bei gesendeten Mails.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/020_mail_review_status.sql
BEGIN;

ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS richtung    text NOT NULL DEFAULT 'ein';
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS an          text;
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS ordner      text;
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS newsletter  boolean NOT NULL DEFAULT false;
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS erledigt_am timestamptz;
ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS ergebnis    jsonb;

UPDATE mail_review_queue SET status = 'pending' WHERE status NOT IN ('pending','spaeter','erledigt','weg');

ALTER TABLE mail_review_queue DROP CONSTRAINT IF EXISTS mail_review_status_check;
ALTER TABLE mail_review_queue ADD CONSTRAINT mail_review_status_check
    CHECK (status IN ('pending','spaeter','erledigt','weg'));
ALTER TABLE mail_review_queue DROP CONSTRAINT IF EXISTS mail_review_richtung_check;
ALTER TABLE mail_review_queue ADD CONSTRAINT mail_review_richtung_check
    CHECK (richtung IN ('ein','aus'));
CREATE INDEX IF NOT EXISTS idx_mail_review_status ON mail_review_queue (status);

COMMIT;

SELECT status, richtung, count(*) AS anzahl FROM mail_review_queue GROUP BY 1, 2 ORDER BY 1, 2;
