-- Migration 031 (2026-11-25): ACOS führt – Auftrag zurückziehen, Rückfrage mit Auswahl
--   * acos_auftraege.status: neuer Wert 'zurueckgezogen' (von Hand im CRM oder weil der Auftrag in ACOS
--     gelöscht/archiviert wurde). Die Aufgabe ist danach wieder frei.
--   * acos_auftraege.rueckfrage_optionen: Antwortmöglichkeiten der Rückfrage [{"key":"A","text":"…"}]
--     aus dem ACOS-Objekt crm_rueckfrage (data.optionen) oder aus dem Fragetext erkannt.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_031_acos_fuehrt.sql
BEGIN;

ALTER TABLE acos_auftraege DROP CONSTRAINT IF EXISTS acos_auftraege_status_check;
ALTER TABLE acos_auftraege ADD CONSTRAINT acos_auftraege_status_check
    CHECK (status IN ('uebergeben', 'rueckfrage', 'bearbeitet', 'erledigt', 'fehler', 'ersetzt', 'zurueckgezogen'));
ALTER TABLE acos_auftraege ADD COLUMN IF NOT EXISTS rueckfrage_optionen JSONB;
ALTER TABLE acos_auftraege ADD COLUMN IF NOT EXISTS zurueckgezogen_am TIMESTAMPTZ;

COMMIT;

SELECT status, count(*) FROM acos_auftraege GROUP BY status ORDER BY status;
