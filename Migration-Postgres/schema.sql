-- CRM Postgres-Schema — Stand 2026-10-19 (inkl. Migration 002 Archiv/Stammdaten, 003 Mail-Review, 004 Einstellungen und 005 Wissen, 006 ACOS-Vorbereitung, 007 ACOS-Abgleich, 008 ACOS-Upload, 009 Mail-Anhänge) (Phase 3: Umsetzung crm_core.py/
-- crm_serve.py gegen Postgres, siehe CRM-Konzept-Postgres-Migration.md).
-- Ersetzt die Markdown/JSON-Ablage. Feldnamen leiten sich aus den bestehenden
-- Frontmatter-Feldern und tasks.json ab.
--
-- Änderungen ggü. der ersten Fassung:
-- 1) Angebote/Rechnungen komplett entfernt. Grund: crm_serve.py (CPX12-Generalprobe,
--    die Basis der neuen Instanz) enthält den Kommentar "bewusst OHNE Angebote-Feature
--    (Entscheidung 2026-07-25: Angebote bleibt separat)". Das Feature existiert nur
--    noch im alten crm_server.py (Mac), nicht mehr im Zielsystem.
-- 2) Tasks hängen jetzt zwingend an einem Projekt (vormals "Opportunities", im UI
--    bereits seit 21.08.2026 als "Projekt" beschriftet). Kein freies contact_raw/
--    firma_id an der Aufgabe mehr — die Firmenzuordnung kommt ausschließlich über
--    das Projekt. Konsequenz für die Migration: die bisherigen freien Alt-Werte ohne
--    echte Firmenakte (z.B. "Intern", "Admin", "ACN", "MGM") brauchen je ein eigenes
--    Sammel-Projekt, bevor ihre Tasks importiert werden können — siehe offene Punkte
--    in CRM-Konzept-Postgres-Migration.md.
-- 3) Bei der Umsetzung von crm_core.py gegen dieses Schema (2026-09-11) ergänzt,
--    weil beim Entwurf übersehen: personen.titel/abteilung (Personen-Tab nutzte
--    diese Felder bereits), projekte.beschreibung (bisherige Freitext-
--    "Zusammenfassung"), tasks.quelle_mail_id (Mail-Intake-Idempotenz), sowie die
--    Tabellen mail_review_queue und heute_dismissed (beide bisher dateibasiert -
--    ausgerechnet die Mehrschreiber-Faelle, die der Umstieg auf Postgres lösen soll).

CREATE TABLE firmen (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,          -- bisher Dateiname in Kontakte/Firmen/
    status          TEXT,
    branch          TEXT,
    source          TEXT,
    address         TEXT,
    kundennr        INTEGER UNIQUE,
    next_action     TEXT,
    last_contact    DATE,
    dsgvo_consent   BOOLEAN,
    dsgvo_added     DATE,
    beziehung_notiz TEXT,                          -- Fließtext "## Beziehung" aus der Firmenakte
    telefon_zentrale TEXT,                         -- Migration 002 (2026-10-19)
    archiviert_am   TIMESTAMPTZ,                   -- Migration 002: NULL = aktiv
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE personen (
    id              SERIAL PRIMARY KEY,
    firma_id        INTEGER REFERENCES firmen(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    titel           TEXT,                           -- fehlte im ersten Entwurf, aber im Personen-Tab
    abteilung       TEXT,                           -- des Dashboards bereits genutzt - am 2026-09-11
                                                      -- bei der Umsetzung ergaenzt (siehe
                                                      -- CRM-Konzept-Postgres-Migration.md).
    email           TEXT,
    telefon         TEXT,
    mobil           TEXT,                           -- Migration 002 (2026-10-19)
    email2          TEXT,                           -- Migration 002
    linkedin        TEXT,                           -- Migration 002
    archiviert_am   TIMESTAMPTZ,                    -- Migration 002: NULL = aktiv
    status          TEXT,
    source          TEXT,
    kampagne        TEXT,
    hinzugefuegt    DATE,
    last_contact    DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_personen_firma ON personen(firma_id);

-- Projekte (vormals "Opportunities"/Pipeline). Zentrale Klammer: jede Aufgabe
-- hängt an genau einem Projekt (siehe tasks.projekt_id, NOT NULL). Deckt sowohl
-- Verkaufschancen (status lead/aktiv/won/lost) als auch interne/administrative
-- Arbeit ab (z.B. ein Sammel-Projekt "Intern" analog zur bestehenden
-- Kontakte/Firmen/Intern.md).
CREATE TABLE projekte (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,                  -- bisher Dateiname, z.B. "DonauDrive Liquidität"
    firma_id        INTEGER REFERENCES firmen(id) ON DELETE SET NULL,
    person_id       INTEGER REFERENCES personen(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'lead',    -- lead/aktiv/won/lost, Anzeige-Label separat im UI
    value           NUMERIC(12,2),
    probability     INTEGER,
    next_action     TEXT,
    deadline        DATE,
    beschreibung    TEXT,                            -- bisher Fließtext "## Zusammenfassung" der
                                                       -- Opportunity-Datei - im ersten Entwurf
                                                       -- uebersehen, am 2026-09-11 ergaenzt.
    archiviert_am   TIMESTAMPTZ,                     -- Migration 002: NULL = aktiv
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_projekte_firma ON projekte(firma_id);

-- Aufgaben sind Instanzen UNTERHALB eines Projekts: projekt_id ist Pflicht.
-- Anzeige/Bearbeitung erfolgt im Kontext des Projekts; eine Aufgabe ohne
-- Projekt kann in diesem Schema gar nicht existieren (DB erzwingt es).
CREATE TABLE tasks (
    id              SERIAL PRIMARY KEY,
    task_id         TEXT NOT NULL UNIQUE,            -- bisherige lesbare ID: PROJ-001, SICHT-001 etc.
    projekt_id      INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    category        TEXT,
    priority        TEXT,
    status          TEXT NOT NULL DEFAULT 'Offen',
    value           NUMERIC(12,2),
    deadline        DATE,
    assigned_to     TEXT,
    notes           TEXT,
    tags            TEXT[] DEFAULT '{}',
    blocked_by      TEXT[] DEFAULT '{}',             -- referenziert andere task_id-Werte
    blocks          TEXT[] DEFAULT '{}',
    quelle_mail_id  TEXT,                             -- Idempotenz-Schluessel fuer aus Mails erzeugte
                                                        -- Aufgaben (Konzept 1.6) - im ersten Entwurf
                                                        -- uebersehen, am 2026-09-11 bei der Umsetzung
                                                        -- ergaenzt (siehe CRM-Konzept-Postgres-Migration.md).
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
    , archiviert_am TIMESTAMPTZ                     -- Migration 002: NULL = aktiv
);
CREATE INDEX idx_tasks_projekt ON tasks(projekt_id);
CREATE INDEX idx_tasks_status ON tasks(status);

-- Aktivitäten: EIN Tabellentyp für alle "art"-Varianten (Gespräch, Kampagne,
-- Sichtbarkeits-Monitoring, künftig E-Mail-Intake). Art-spezifische Zusatzfelder
-- liegen in payload (JSONB) statt für jede Art eine eigene Tabelle zu bauen.
CREATE TABLE aktivitaeten (
    id              SERIAL PRIMARY KEY,
    firma_id        INTEGER REFERENCES firmen(id) ON DELETE CASCADE,
    person_id       INTEGER REFERENCES personen(id) ON DELETE SET NULL,
    projekt_id      INTEGER REFERENCES projekte(id) ON DELETE SET NULL,
    art             TEXT NOT NULL,                   -- z.B. kampagne, sichtbarkeit-monitoring, meeting, email
    datum           DATE NOT NULL,
    dauer_minuten   INTEGER DEFAULT 0,
    quelle          TEXT,
    pulse_id        UUID,                            -- ACOS-Referenz, NULL bei manuellen Einträgen
    titel           TEXT,
    notiz           TEXT,
    payload         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_aktivitaeten_firma ON aktivitaeten(firma_id);
CREATE INDEX idx_aktivitaeten_art ON aktivitaeten(art);

-- Mehrnutzer-Login. Ansatz aus CPX12-Generalprobe/manage_users.py übernehmen
-- (PBKDF2-Hash), nicht neu erfinden.
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    rolle           TEXT NOT NULL DEFAULT 'mitarbeiter',
    aktiv           BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login      TIMESTAMPTZ
);

-- Nachvollziehbarkeit, WER WANN WAS geändert hat — Konsequenz aus den zwei
-- bereits aufgetretenen stillen Datenkorruptionen im alten Regex-Parser.
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    tabelle         TEXT NOT NULL,
    datensatz_id    INTEGER NOT NULL,
    aktion          TEXT NOT NULL,                   -- insert/update/delete
    alt_werte       JSONB,
    neu_werte       JSONB,
    zeitpunkt       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_tabelle ON audit_log(tabelle, datensatz_id);

-- Mail-Review-Warteschlange (Konzept 1.5/1.8 Stufe 1) - bisher dateibasiert unter
-- Mail-Review/*.json. Am 2026-09-11 bei der Postgres-Umsetzung mit aufgenommen:
-- genau die Mehrschreiber-Situation (Dashboard + mail_poller.py als Hintergrund-
-- prozess schreiben gleichzeitig), die ueberhaupt der Grund fuer den Umstieg auf
-- Postgres war, siehe CRM-Konzept-Postgres-Migration.md.
CREATE TABLE mail_review_queue (
    id              TEXT PRIMARY KEY,                -- bisherige item_id (sha1-Kurzhash)
    message_id      TEXT,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    von             TEXT,
    betreff         TEXT,
    datum           DATE,
    body_excerpt    TEXT,
    match           JSONB,
    category        TEXT,
    summary         TEXT,
    task_suggestion JSONB,
    llm_error       TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    von_name        TEXT                              -- Migration 003 (2026-10-19)
);

-- Ignorierliste fuer den Mail-Review (Migration 003, 2026-10-19)
CREATE TABLE mail_ignoriert (
    muster       TEXT PRIMARY KEY,          -- 'max@firma.de' oder 'firma.de'
    art          TEXT NOT NULL,             -- 'adresse' | 'domain'
    angelegt_am  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "Heute"-Panel: weggeklickte next_action-Signale (Konzept, 2026-08-21), bisher
-- dateibasiert unter heute_dismissed.json. Aus demselben Grund wie oben mit
-- aufgenommen (Dashboard schreibt hier schreibend, kuenftig potenziell aus
-- mehreren Browser-Sessions gleichzeitig).
CREATE TABLE heute_dismissed (
    key             TEXT PRIMARY KEY,                -- heute_candidate_key(firma, text)
    dismissed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Einstellungen (Migration 004, 2026-10-19)
CREATE TABLE benutzer_einstellungen (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    werte         JSONB NOT NULL DEFAULT '{}',
    geaendert_am  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE system_einstellungen (
    schluessel     TEXT PRIMARY KEY,
    wert           JSONB NOT NULL,
    geaendert_am   TIMESTAMPTZ NOT NULL DEFAULT now(),
    geaendert_von  INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Wissens-DB (Migration 005, 2026-10-19)
CREATE TABLE wissen_dokumente (
    id              SERIAL PRIMARY KEY,
    pfad            TEXT NOT NULL UNIQUE,          -- relativ zum Vault, z. B. Fachwissen/Sanierung/StaRUG.pdf
    name            TEXT NOT NULL,
    ordner          TEXT NOT NULL,                 -- Unterordner ohne Dateiname
    typ             TEXT NOT NULL,                 -- md, pdf, bild, docx, text, sonst
    groesse         BIGINT,
    etag            TEXT,
    geaendert_am    TIMESTAMPTZ,
    inhalt          TEXT NOT NULL DEFAULT '',
    ocr             BOOLEAN NOT NULL DEFAULT false,
    namens_treffer  JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'ok',    -- ok, fehler, zu_gross
    fehler          TEXT,
    abgeglichen_am  TIMESTAMPTZ NOT NULL DEFAULT now(),
    suchtext        tsvector GENERATED ALWAYS AS (
                        setweight(to_tsvector('german', coalesce(name, '')), 'A') ||
                        setweight(to_tsvector('german', coalesce(inhalt, '')), 'B')) STORED
);
CREATE INDEX idx_wissen_suchtext ON wissen_dokumente USING GIN (suchtext);

CREATE TABLE wissen_laeufe (
    id              SERIAL PRIMARY KEY,
    start           TIMESTAMPTZ NOT NULL DEFAULT now(),
    ende            TIMESTAMPTZ,
    neu             INTEGER NOT NULL DEFAULT 0,
    geaendert       INTEGER NOT NULL DEFAULT 0,
    geloescht       INTEGER NOT NULL DEFAULT 0,
    fehler          INTEGER NOT NULL DEFAULT 0,
    offen           INTEGER NOT NULL DEFAULT 0,    -- in diesem Lauf nicht mehr geschafft, kommt im naechsten
    meldung         TEXT,
    ausgeloest_von  TEXT
);

-- Abgleich mit ACOS, Schritt 1 (Migration 006, 2026-10-20)
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

-- Abgleich mit ACOS, Schritt 3 (Migration 007, 2026-10-20)
ALTER TABLE acos_verknuepfung ADD COLUMN IF NOT EXISTS anlegen BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS acos_laeufe (
    id              SERIAL PRIMARY KEY,
    start           TIMESTAMPTZ NOT NULL DEFAULT now(),
    ende            TIMESTAMPTZ,
    modus           TEXT NOT NULL DEFAULT 'trocken',   -- trocken | scharf
    ausgeloest_von  TEXT,
    ok              BOOLEAN,
    meldung         TEXT,
    zahlen          JSONB NOT NULL DEFAULT '{}',       -- {vorschlaege, gesendet, archiviert, wissen_neu, abgelegt, fehler}
    bericht         JSONB NOT NULL DEFAULT '[]'        -- [{firma, aktion, text}]
);

-- Dokumente an ACOS senden (Migration 008, 2026-10-24)
CREATE TABLE IF NOT EXISTS acos_uploads (
    id               SERIAL PRIMARY KEY,
    firma_id         INTEGER NOT NULL REFERENCES firmen(id) ON DELETE CASCADE,
    pfad             TEXT NOT NULL,                  -- relativ zum Kundenordner, z. B. Unterlagen/Bilanz 2025.pdf
    groesse          BIGINT,
    etag             TEXT,                           -- Stand der Datei beim Senden
    acos_client_id   TEXT NOT NULL,
    acos_file_id     TEXT,
    acos_document_id TEXT,
    status           TEXT NOT NULL DEFAULT 'gesendet' CHECK (status IN ('gesendet', 'fehler')),
    meldung          TEXT,
    gesendet_am      TIMESTAMPTZ NOT NULL DEFAULT now(),
    gesendet_von     TEXT
);
CREATE INDEX IF NOT EXISTS idx_acos_uploads_firma ON acos_uploads(firma_id, pfad);

-- Anhaenge aus dem Mail-Eingang (Migration 009, 2026-10-26)
CREATE TABLE IF NOT EXISTS mail_anhaenge (
    id          SERIAL PRIMARY KEY,
    mail_id     TEXT NOT NULL REFERENCES mail_review_queue(id) ON DELETE CASCADE,
    dateiname   TEXT NOT NULL,
    mime        TEXT,
    groesse     BIGINT,
    datei       TEXT,                 -- relativ zu secrets/mail-anhaenge; NULL = nicht gespeichert
    hinweis     TEXT,                 -- z. B. "groesser als 25 MB"
    angelegt_am TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mail_anhaenge_mail ON mail_anhaenge(mail_id);
