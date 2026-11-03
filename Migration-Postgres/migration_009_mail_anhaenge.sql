-- Migration 009 (2026-10-26): Anhaenge aus dem Mail-Eingang
-- Der Mail-Abruf legt Anhaenge vorlaeufig geschuetzt auf dem Server ab
-- (secrets/mail-anhaenge, nur crmapp). Hier steht je Anhang, was es ist und wo
-- die vorlaeufige Kopie liegt. Beim Uebernehmen im Mail-Review kommen die
-- angehakten Dateien in den Kundenordner (Mail-Eingang/<Datum> <Betreff>/),
-- auf Wunsch weiter nach ACOS; danach wird die vorlaeufige Kopie geloescht.
-- Rein additiv und idempotent.

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
