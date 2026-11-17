-- Migration 026 (2026-11-17): Aufgabe als Auftrag an ACOS.
-- Zu einer Aufgabe eines Mandanten gibt es einen oder mehrere Auftraege (AUF-JJJJ-NNNN).
-- Das CRM legt die Auftragsdatei in der Nextcloud ab, Claude arbeitet sie am Mac ueber
-- ACOS ab; das Ergebnis (Artefakt mit der Auftrags-ID im Titel) findet das CRM beim
-- ACOS-Abgleich wieder. Neue Aufgaben-Status "Bearbeitet" braucht keine Migration
-- (tasks.status ist freier Text).
-- Idempotent:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_026_acos_auftraege.sql

CREATE TABLE IF NOT EXISTS acos_auftraege (
    id                SERIAL PRIMARY KEY,
    auftrags_id       TEXT NOT NULL UNIQUE,                 -- AUF-2026-0007, ohne Namen
    task_id           TEXT NOT NULL,                        -- tasks.task_id (PROJ-nnn)
    firma_id          INTEGER NOT NULL REFERENCES firmen(id) ON DELETE CASCADE,
    acos_client_id    TEXT NOT NULL,                        -- ACOS-Mandant (aus acos_verknuepfung)
    artefakttyp       TEXT NOT NULL,                        -- Slug der ACOS-Artefaktvorlage
    thema             TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'uebergeben'
                      CHECK (status IN ('uebergeben', 'rueckfrage', 'bearbeitet', 'erledigt', 'fehler', 'ersetzt')),
    rueckfrage        TEXT,
    meldung           TEXT,
    acos_artefakt_id  TEXT,
    acos_link         TEXT,
    nextcloud_pfad    TEXT,                                 -- Kopie des Artefakts im Kundenordner
    auftragsdatei     TEXT,                                 -- Pfad der Auftragsdatei in der Nextcloud
    ersetzt_durch     TEXT,
    angelegt_von      TEXT,
    angelegt_am       TIMESTAMPTZ NOT NULL DEFAULT now(),
    uebergeben_am     TIMESTAMPTZ,
    bearbeitet_am     TIMESTAMPTZ,
    erledigt_am       TIMESTAMPTZ,
    geaendert_am      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS acos_auftraege_task_idx  ON acos_auftraege (task_id);
CREATE INDEX IF NOT EXISTS acos_auftraege_firma_idx ON acos_auftraege (firma_id, status);

SELECT count(*) AS auftraege FROM acos_auftraege;
