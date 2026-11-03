-- Migration 017 (2026-10-31, Umbau Schritt 6): Sammelprojekte "<Firma> – laufende Betreuung" aufloesen
-- Seit Migration 016 brauchen Aufgaben kein Projekt mehr. Die alten Sammelprojekte
-- waren nur ein Behelf und stehen faelschlich als aktive Projekte in Liste und Briefing.
-- Aufgeloest werden nur Sammelprojekte OHNE Wert. Solche mit Wert bleiben unangetastet
-- und erscheinen am Ende im Bericht (vermutlich echte Mandate -> umbenennen).
-- Geloescht wird nichts: Aufgaben und Journal-Eintraege bleiben beim Unternehmen,
-- das Projekt kommt ins Archiv. Setzt Migration 016 voraus.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/017_sammelprojekte_aufloesen.sql
BEGIN;

CREATE TEMP TABLE sammel ON COMMIT DROP AS
SELECT p.id, p.firma_id, p.name, p.next_action
FROM projekte p
WHERE p.name LIKE '% – laufende %' AND p.archiviert_am IS NULL AND p.value IS NULL;

-- 1. Aufgaben: Unternehmen sichern, Projekt loesen
UPDATE tasks t SET firma_id = COALESCE(t.firma_id, s.firma_id), projekt_id = NULL, updated_at = now()
FROM sammel s WHERE t.projekt_id = s.id;

-- 2. Journal: bleibt beim Unternehmen
UPDATE aktivitaeten a SET firma_id = COALESCE(a.firma_id, s.firma_id), projekt_id = NULL
FROM sammel s WHERE a.projekt_id = s.id;

-- 3. Naechster Schritt wandert zum Unternehmen, falls dort noch keiner steht
UPDATE firmen f SET next_action = s.next_action, updated_at = now()
FROM sammel s
WHERE f.id = s.firma_id AND coalesce(trim(s.next_action), '') <> '' AND coalesce(trim(f.next_action), '') = '';

-- 4. Sammelprojekt ins Archiv, mit Protokolleintrag
INSERT INTO audit_log (tabelle, datensatz_id, aktion, alt_werte, neu_werte)
SELECT 'projekte', s.id, 'archiv', jsonb_build_object('name', s.name, 'next_action', s.next_action),
       jsonb_build_object('grund', 'Migration 017: Sammelprojekt aufgeloest')
FROM sammel s;
UPDATE projekte p SET archiviert_am = now(), updated_at = now() FROM sammel s WHERE p.id = s.id;

-- Bericht
SELECT 'aufgeloest' AS ergebnis, s.name, f.next_action AS naechster_schritt_unternehmen
FROM sammel s JOIN firmen f ON f.id = s.firma_id
UNION ALL
SELECT 'NICHT aufgeloest (hat einen Wert)', p.name, p.value::text
FROM projekte p WHERE p.name LIKE '% – laufende %' AND p.archiviert_am IS NULL
ORDER BY 1, 2;

COMMIT;
