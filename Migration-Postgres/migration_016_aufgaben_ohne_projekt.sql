-- Migration 016 (2026-10-31, Umbau Schritt 5 / Bauabschnitt 4): Aufgaben ohne Projekt
-- Eine Aufgabe haengt kuenftig an einem Unternehmen, optional an einem Projekt,
-- oder an gar nichts (eigene Aufgabe). Dazu merkt sie sich ihre Herkunft.
-- Bestehende Aufgaben behalten ihr Projekt; firma_id wird aus dem Projekt gefuellt.
-- WICHTIG: vor dem Deploy des passenden Codes ausfuehren (der Code liest tasks.firma_id).
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -d <datenbank> -f migrations/016_aufgaben_ohne_projekt.sql
BEGIN;

ALTER TABLE tasks ALTER COLUMN projekt_id DROP NOT NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS firma_id integer REFERENCES firmen(id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS herkunft text NOT NULL DEFAULT 'manuell';
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_herkunft_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_herkunft_check
  CHECK (herkunft IN ('manuell', 'mail', 'termin', 'journal', 'heute'));
CREATE INDEX IF NOT EXISTS tasks_firma_idx ON tasks (firma_id);

UPDATE tasks t SET firma_id = p.firma_id
  FROM projekte p WHERE p.id = t.projekt_id AND t.firma_id IS NULL;
UPDATE tasks SET herkunft = 'mail' WHERE quelle_mail_id IS NOT NULL AND herkunft = 'manuell';

COMMIT;

SELECT count(*) AS aufgaben,
       count(*) FILTER (WHERE firma_id IS NOT NULL) AS mit_unternehmen,
       count(*) FILTER (WHERE herkunft = 'mail')    AS aus_mail
FROM tasks;
SELECT p.id, p.name, count(t.id) AS aufgaben
FROM projekte p LEFT JOIN tasks t ON t.projekt_id = p.id
WHERE p.name LIKE '% – laufende %' AND p.archiviert_am IS NULL
GROUP BY p.id, p.name ORDER BY p.name;
