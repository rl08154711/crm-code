-- Migration 003 (2026-10-19): Mail-Review mit unbekannten Absendern
-- ==================================================================
-- Idempotent. Ausfuehren: sudo -u crmapp psql -d crm -f migration_003_mail_review.sql
--
-- 1) Anzeigename des Absenders ("Max Mustermann <max@firma.de>") wird mit
--    gespeichert, damit beim Anlegen einer Person der Name vorbefuellt ist.
-- 2) Ignorierliste: Absender oder ganze Domains, deren Mails nicht mehr im
--    Mail-Review landen (z.B. Newsletter). art = 'adresse' | 'domain'.

ALTER TABLE mail_review_queue ADD COLUMN IF NOT EXISTS von_name TEXT;

CREATE TABLE IF NOT EXISTS mail_ignoriert (
    muster       TEXT PRIMARY KEY,          -- 'max@firma.de' oder 'firma.de'
    art          TEXT NOT NULL,             -- 'adresse' | 'domain'
    angelegt_am  TIMESTAMPTZ NOT NULL DEFAULT now()
);
