-- Migration 013 (2026-10-31, Umbau Schritt 2): Art der Beziehung je Unternehmen
-- Additiv: bestehender Code laeuft unveraendert weiter.
-- Ausfuehren als Dienstbenutzer, damit die Spalten ihm gehoeren:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -d <datenbank> -f migrations/013_beziehung.sql
BEGIN;

ALTER TABLE firmen ADD COLUMN IF NOT EXISTS art text NOT NULL DEFAULT 'mandant';
ALTER TABLE firmen ADD COLUMN IF NOT EXISTS funktion text;
ALTER TABLE firmen DROP CONSTRAINT IF EXISTS firmen_art_check;
ALTER TABLE firmen ADD CONSTRAINT firmen_art_check
  CHECK (art IN ('mandant', 'netzwerk', 'lieferant', 'intern'));

-- Erstbelegung aus dem bisherigen Status (nur Zeilen, die noch auf dem Standard stehen)
UPDATE firmen SET art = CASE
    WHEN status ~* '(^|,)\s*intern\s*(,|$)'                     THEN 'intern'
    WHEN status ~* '(^|,)\s*(netzwerk|partner)\s*(,|$)'         THEN 'netzwerk'
    WHEN status ~* '(^|,)\s*(dienstleister|lieferant)\s*(,|$)'  THEN 'lieferant'
    ELSE 'mandant' END
WHERE art = 'mandant';

COMMIT;

SELECT art, count(*) AS anzahl FROM firmen WHERE archiviert_am IS NULL GROUP BY art ORDER BY art;
