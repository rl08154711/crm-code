-- Migration 002 (2026-10-19): einheitliches Archiv + erweiterte Stammdaten
-- ========================================================================
-- Idempotent: kann gefahrlos mehrfach laufen (IF NOT EXISTS / WHERE ... IS NULL).
-- Ausfuehren auf dem Server:  sudo -u crmapp psql -d crm -f migration_002_archiv_stammdaten.sql
--
-- 1) Archiv: Statt den Status mit 'archiviert' zu ueberschreiben (Status ging
--    dabei verloren, Reaktivieren war nicht moeglich) bekommt jede Tabelle eine
--    eigene Spalte archiviert_am. NULL = aktiv. Der fachliche Status bleibt
--    erhalten, Reaktivieren setzt nur archiviert_am wieder auf NULL.
-- 2) Stammdaten: Zentrale Rufnummer bei Firmen; Mobilnummer, zweite Mail-Adresse
--    und LinkedIn-Profil bei Personen.

ALTER TABLE firmen   ADD COLUMN IF NOT EXISTS telefon_zentrale TEXT;
ALTER TABLE firmen   ADD COLUMN IF NOT EXISTS archiviert_am    TIMESTAMPTZ;

ALTER TABLE personen ADD COLUMN IF NOT EXISTS mobil            TEXT;
ALTER TABLE personen ADD COLUMN IF NOT EXISTS email2           TEXT;
ALTER TABLE personen ADD COLUMN IF NOT EXISTS linkedin         TEXT;
ALTER TABLE personen ADD COLUMN IF NOT EXISTS archiviert_am    TIMESTAMPTZ;

ALTER TABLE projekte ADD COLUMN IF NOT EXISTS archiviert_am    TIMESTAMPTZ;
ALTER TABLE tasks    ADD COLUMN IF NOT EXISTS archiviert_am    TIMESTAMPTZ;

-- Bisher archivierte Datensaetze uebernehmen. Der urspruengliche Status ist
-- nicht mehr bekannt, daher 'inaktiv' (existiert bei Firmen und Projekten).
UPDATE firmen   SET archiviert_am = updated_at, status = 'inaktiv'
 WHERE status = 'archiviert' AND archiviert_am IS NULL;
UPDATE projekte SET archiviert_am = updated_at, status = 'inaktiv'
 WHERE status = 'archiviert' AND archiviert_am IS NULL;

CREATE INDEX IF NOT EXISTS idx_firmen_archiv   ON firmen(archiviert_am);
CREATE INDEX IF NOT EXISTS idx_personen_archiv ON personen(archiviert_am);
CREATE INDEX IF NOT EXISTS idx_projekte_archiv ON projekte(archiviert_am);
CREATE INDEX IF NOT EXISTS idx_tasks_archiv    ON tasks(archiviert_am);
