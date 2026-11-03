-- Migration 018 (2026-10-31, Umbau Schritt 7): Projektphasen statt Projektstatus
-- Fuenf Phasen: anbahnung, angebot, laeuft, abgeschlossen, verloren.
-- Zuordnung nach Ronalds Festlegung vom 31.10.2026:
--   lead -> anbahnung | aktiv, won (Mandat erteilt), pausiert, kunde -> laeuft
--   inaktiv -> abgeschlossen | lost -> verloren
-- WICHTIG: zusammen mit dem passenden Code einspielen (der Code kennt nur noch die Phasen).
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/018_projektphasen.sql
BEGIN;

SELECT coalesce(status, '(leer)') AS status_vorher, count(*) AS anzahl
FROM projekte WHERE archiviert_am IS NULL GROUP BY 1 ORDER BY 1;

UPDATE projekte SET status = CASE lower(trim(split_part(coalesce(status, ''), ',', 1)))
    WHEN 'lead'          THEN 'anbahnung'
    WHEN 'anbahnung'     THEN 'anbahnung'
    WHEN 'angebot'       THEN 'angebot'
    WHEN 'inaktiv'       THEN 'abgeschlossen'
    WHEN 'abgeschlossen' THEN 'abgeschlossen'
    WHEN 'lost'          THEN 'verloren'
    WHEN 'verloren'      THEN 'verloren'
    ELSE 'laeuft' END;

ALTER TABLE projekte ALTER COLUMN status SET DEFAULT 'anbahnung';
ALTER TABLE projekte DROP CONSTRAINT IF EXISTS projekte_phase_check;
ALTER TABLE projekte ADD CONSTRAINT projekte_phase_check
  CHECK (status IN ('anbahnung', 'angebot', 'laeuft', 'abgeschlossen', 'verloren'));

-- Persoenlicher Projektfilter: auf die offenen Phasen setzen
UPDATE benutzer_einstellungen
SET werte = jsonb_set(werte, '{projekt_status}', '["anbahnung","angebot","laeuft"]'::jsonb)
WHERE werte ? 'projekt_status';

COMMIT;

SELECT status AS phase_nachher, count(*) AS anzahl
FROM projekte WHERE archiviert_am IS NULL GROUP BY 1 ORDER BY 1;
