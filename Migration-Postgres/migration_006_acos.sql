-- Migration 006 (2026-10-20): Vorbereitung Abgleich CRM -> ACOS (Schritt 1)
-- Konzept: "Konzept Abgleich CRM-ACOS" (Stand 20.10.2026).
--  * Schalter "In ACOS fuehren" am Unternehmen
--  * Verknuepfung CRM-Firma <-> ACOS-Mandant (Vorschlag, Bestaetigung, Ende)
--  * Liste der Artefakte (vorerst Wissensobjekte) je Unternehmen, mit
--    Verweis auf ACOS und auf die Ablage in der Nextcloud
-- Der Abgleich selbst kommt in einem spaeteren Schritt. Rein additiv und
-- idempotent; bestehende Daten werden nicht veraendert.

ALTER TABLE firmen ADD COLUMN IF NOT EXISTS acos_fuehren BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS acos_verknuepfung (
    firma_id         INTEGER PRIMARY KEY REFERENCES firmen(id) ON DELETE CASCADE,
    acos_client_id   TEXT,                          -- NULL, solange nur ein Vorschlag besteht
    acos_name        TEXT,                          -- Name des Mandanten in ACOS (Anzeige)
    zustand          TEXT NOT NULL DEFAULT 'offen'
                     CHECK (zustand IN ('offen', 'vorgeschlagen', 'bestaetigt', 'beendet')),
    vorschlaege      JSONB NOT NULL DEFAULT '[]',   -- Trefferliste beim Zuordnen: [{id, name, hinweis}]
    pruefwert        TEXT,                          -- Hash der zuletzt nach ACOS gesendeten Felder
    letzter_abgleich TIMESTAMPTZ,
    meldung          TEXT,                          -- letzter Hinweis/Fehler fuer die Anzeige
    bestaetigt_am    TIMESTAMPTZ,
    bestaetigt_von   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_acos_verkn_client
    ON acos_verknuepfung(acos_client_id) WHERE acos_client_id IS NOT NULL AND zustand = 'bestaetigt';

CREATE TABLE IF NOT EXISTS acos_artefakte (
    id                SERIAL PRIMARY KEY,
    firma_id          INTEGER NOT NULL REFERENCES firmen(id) ON DELETE CASCADE,
    quelle            TEXT NOT NULL DEFAULT 'wissen',   -- wissen; spaeter weitere Artefakt-Arten
    acos_id           TEXT NOT NULL,
    titel             TEXT NOT NULL DEFAULT '',
    art               TEXT,                             -- Typ/Skill laut ACOS, z. B. Liquiditaetsplanung
    acos_erstellt_am  TIMESTAMPTZ,
    acos_geaendert_am TIMESTAMPTZ,
    acos_projekt      TEXT,                             -- nur Anzeige
    acos_link         TEXT,
    nextcloud_pfad    TEXT,                             -- relativ zu Arbeitsdateien/Kunden
    status            TEXT NOT NULL DEFAULT 'neu'
                      CHECK (status IN ('neu', 'abgelegt', 'fehler', 'entfernt')),
    meldung           TEXT,
    erstmals_gesehen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    zuletzt_gesehen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    abgelegt_am       TIMESTAMPTZ,
    UNIQUE (quelle, acos_id)
);
CREATE INDEX IF NOT EXISTS idx_acos_artefakte_firma ON acos_artefakte(firma_id);
