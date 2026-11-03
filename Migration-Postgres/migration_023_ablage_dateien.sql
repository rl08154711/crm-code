-- Migration 023 (2026-10-31, Umbau Schritt 12): Neue Dateien im Kundenordner als Journal-Eintrag "Dokument"
-- Der Wissens-Abgleich (stuendlich) merkt sich jede Datei in den Kundenordnern ueber ihre Nextcloud-Datei-ID.
-- Beim ersten Lauf wird nur der Bestand erfasst (kein Journal). Danach ergibt jede neue Datei einen Eintrag,
-- gesammelt je Unternehmen und Lauf. Verschobene oder umbenannte Dateien behalten ihre ID und zaehlen nicht als neu.
-- Ausgenommen: Unterordner ACOS (kommt aus ACOS), Mail-Eingang (kommt aus dem Mail-Review), ausgeblendete Ordner.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/023_ablage_dateien.sql
BEGIN;
CREATE TABLE IF NOT EXISTS ablage_datei (
    datei_id       text PRIMARY KEY,               -- oc:fileid der Nextcloud
    pfad           text NOT NULL,
    firma_id       integer REFERENCES firmen(id) ON DELETE SET NULL,
    groesse        bigint,
    geaendert_am   timestamptz,
    erstmals_am    timestamptz NOT NULL DEFAULT now(),
    zuletzt_am     timestamptz NOT NULL DEFAULT now(),
    aktivitaet_id  integer REFERENCES aktivitaeten(id) ON DELETE SET NULL,
    entfernt       boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_ablage_datei_firma ON ablage_datei (firma_id);
COMMIT;
SELECT count(*) AS dateien_erfasst FROM ablage_datei;
