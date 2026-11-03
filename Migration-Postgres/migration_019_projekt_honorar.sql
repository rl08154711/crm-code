-- Migration 019 (2026-10-31, Umbau Schritt 8): Honorar, Verlustgrund und Lexware-Referenz je Projekt
-- Festlegung Ronald 31.10.2026:
--   Honorarart: pauschal | zeit | laufend | gebuehr_provision | provision | offen (Details im Freitext "honorar")
--   Verlustgrund: preis | kein_bedarf | anderer_berater | keine_rueckmeldung | abgelehnt | insolvent (+ Freitext)
--   Lexware: Angebots-/Auftragsnummer als Freitext (Abgleich folgt in Bauabschnitt 8)
-- Bestehende Projekte bekommen Honorarart "offen"; nichts wird geraten.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/019_projekt_honorar.sql
BEGIN;

ALTER TABLE projekte ADD COLUMN IF NOT EXISTS honorarart    text NOT NULL DEFAULT 'offen';
ALTER TABLE projekte ADD COLUMN IF NOT EXISTS honorar       text;
ALTER TABLE projekte ADD COLUMN IF NOT EXISTS verlustgrund  text;
ALTER TABLE projekte ADD COLUMN IF NOT EXISTS verlust_notiz text;
ALTER TABLE projekte ADD COLUMN IF NOT EXISTS lexware_ref   text;

ALTER TABLE projekte DROP CONSTRAINT IF EXISTS projekte_honorarart_check;
ALTER TABLE projekte ADD CONSTRAINT projekte_honorarart_check
    CHECK (honorarart IN ('pauschal','zeit','laufend','gebuehr_provision','provision','offen'));
ALTER TABLE projekte DROP CONSTRAINT IF EXISTS projekte_verlustgrund_check;
ALTER TABLE projekte ADD CONSTRAINT projekte_verlustgrund_check
    CHECK (verlustgrund IS NULL OR verlustgrund IN ('preis','kein_bedarf','anderer_berater','keine_rueckmeldung','abgelehnt','insolvent'));

COMMIT;

SELECT status AS phase, count(*) AS projekte,
       count(*) FILTER (WHERE status = 'verloren' AND verlustgrund IS NULL) AS verlustgrund_nachtragen
FROM projekte WHERE archiviert_am IS NULL GROUP BY 1 ORDER BY 1;
