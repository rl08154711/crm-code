-- Migration 011 (2026-10-30): Tagesabschluss maskiert an ACOS
--
-- Probe am 30.10.: ACOS maskiert nur Namen, die es selbst kennt. Ansprechpartner
-- und Firmen, die nur im CRM stehen, kamen beim Lesen im Klartext an. Deshalb
-- maskiert jetzt das CRM selbst, bevor der Abschluss nach ACOS geht.
--
-- acos_objekt_id: Wissensobjekt "Tagesabschluss JJJJ-MM-TT" in ACOS (wird beim
--                 erneuten Abschliessen fortgeschrieben)
-- ps_zuordnung:   Platzhalter -> Klartext fuer Mail, Telefon, IBAN dieses Abschlusses
--                 (FIRMA_n und PERSON_n loest das CRM direkt ueber die IDs auf)
-- bewertung_acos_id: Wissensobjekt "Tagesbewertung JJJJ-MM-TT", aus dem die
--                 Bewertung (mit wieder eingesetzten Namen) in "bewertung" steht
--
-- Rein additiv und idempotent.

ALTER TABLE tagesabschluss ADD COLUMN IF NOT EXISTS acos_objekt_id    TEXT;
ALTER TABLE tagesabschluss ADD COLUMN IF NOT EXISTS ps_zuordnung      JSONB NOT NULL DEFAULT '{}';
ALTER TABLE tagesabschluss ADD COLUMN IF NOT EXISTS bewertung_acos_id TEXT;
