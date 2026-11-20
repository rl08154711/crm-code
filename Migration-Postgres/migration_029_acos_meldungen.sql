-- Migration 029 (2026-11-20): ACOS-Auftraege automatisch - Meldungen im CRM
-- Rueckfragen, "Ergebnis liegt in ACOS" und "in der Nextcloud abgelegt" erscheinen als Meldung
-- (Heute, kurze Einblendung, Verlauf der Aufgabe). gesehen_am markiert, was schon angezeigt wurde.
-- Rein additiv und idempotent. Bestehende Verlaufseintraege gelten als gesehen.
BEGIN;
ALTER TABLE acos_auftrag_verlauf ADD COLUMN IF NOT EXISTS gesehen_am TIMESTAMPTZ;
UPDATE acos_auftrag_verlauf SET gesehen_am = zeit WHERE gesehen_am IS NULL;
CREATE INDEX IF NOT EXISTS acos_auftrag_verlauf_offen_idx ON acos_auftrag_verlauf (id) WHERE gesehen_am IS NULL;
COMMIT;
