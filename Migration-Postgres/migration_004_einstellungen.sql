-- Migration 004 (2026-10-19): Einstellungen
-- Persoenliche Einstellungen pro Benutzer (Startansicht, Projektfilter, Farbe)
-- und systemweite Einstellungen (Mail-Abruf, KI-Schalter, Auto-Archiv).
-- Rein additiv und idempotent.

CREATE TABLE IF NOT EXISTS benutzer_einstellungen (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    werte         JSONB NOT NULL DEFAULT '{}',
    geaendert_am  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_einstellungen (
    schluessel     TEXT PRIMARY KEY,
    wert           JSONB NOT NULL,
    geaendert_am   TIMESTAMPTZ NOT NULL DEFAULT now(),
    geaendert_von  INTEGER REFERENCES users(id) ON DELETE SET NULL
);
