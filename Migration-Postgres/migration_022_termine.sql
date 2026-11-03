-- Migration 022 (2026-10-31, Umbau Schritt 11): Termine aus dem Google-Kalender (nur lesend)
-- Quelle: geheime iCal-Adresse in secrets/kalender.env (KALENDER_ICS_URL=...), Abruf alle 15 Minuten.
-- Der Kalender wird nie veraendert. Zuordnung zu Unternehmen ueber Teilnehmer-Adressen oder Firmennamen im Titel;
-- eine Zuordnung von Hand (firma_manuell) bleibt bei jedem Abgleich erhalten, ebenso die Notiz zum Gespraech.
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migrations/022_termine.sql
BEGIN;
CREATE TABLE IF NOT EXISTS termin (
    id             serial PRIMARY KEY,
    schluessel     text NOT NULL UNIQUE,          -- UID + Beginn (bei Serien je Vorkommen)
    uid            text NOT NULL,
    beginn         timestamptz NOT NULL,
    ende           timestamptz,
    ganztag        boolean NOT NULL DEFAULT false,
    titel          text,
    ort            text,
    teilnehmer     text[] NOT NULL DEFAULT '{}',
    firma_id       integer REFERENCES firmen(id) ON DELETE SET NULL,
    person_id      integer REFERENCES personen(id) ON DELETE SET NULL,
    firma_manuell  boolean NOT NULL DEFAULT false,
    zuordnung      text,
    notiz_status   text NOT NULL DEFAULT 'offen' CHECK (notiz_status IN ('offen','gespeichert','keine')),
    aktivitaet_id  integer REFERENCES aktivitaeten(id) ON DELETE SET NULL,
    entfernt       boolean NOT NULL DEFAULT false,  -- im Kalender nicht mehr vorhanden
    aktualisiert_am timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_termin_beginn ON termin (beginn);
CREATE INDEX IF NOT EXISTS idx_termin_firma ON termin (firma_id);

CREATE TABLE IF NOT EXISTS kalender_lauf (
    id        serial PRIMARY KEY,
    zeitpunkt timestamptz NOT NULL DEFAULT now(),
    ok        boolean NOT NULL,
    anzahl    integer,
    meldung   text
);
COMMIT;
SELECT count(*) AS termine FROM termin;
