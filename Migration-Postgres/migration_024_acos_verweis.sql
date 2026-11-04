-- Migration 024 (2026-11-04): ACOS-Dokumente als Verweis statt "wartet auf Ablage"
-- Seit 03.11.2026 (Variante 2) bleiben hochgeladene Dateien (art = document) in ACOS und werden
-- nicht in die Nextcloud abgelegt. Der Abgleich liess ihren Status aber auf 'neu' stehen, die
-- Oberflaeche zeigte deshalb dauerhaft "wartet auf Ablage". Neuer Status 'verweis' = nur in ACOS.
-- Bestehende Dokumente in 'neu'/'fehler' werden einmalig umgestellt. Dokumente, die das CRM selbst
-- aus dem Kundenordner gesendet hat, stehen bereits auf 'abgelegt' und bleiben unveraendert.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_024_acos_verweis.sql
BEGIN;
ALTER TABLE acos_artefakte DROP CONSTRAINT IF EXISTS acos_artefakte_status_check;
ALTER TABLE acos_artefakte ADD CONSTRAINT acos_artefakte_status_check
    CHECK (status IN ('neu', 'abgelegt', 'fehler', 'entfernt', 'verweis'));
UPDATE acos_artefakte
   SET status = 'verweis', meldung = 'Datei bleibt in ACOS – im Kundenwissen als Verweis'
 WHERE art = 'document' AND status IN ('neu', 'fehler');
COMMIT;
