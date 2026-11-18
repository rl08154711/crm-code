-- Migration 028 (2026-11-17): Auftraege an ACOS als Wissensobjekt in der Kundenakte (Variante A).
-- Das CRM legt den Auftrag nicht mehr als Datei in der Nextcloud ab, sondern in ACOS
-- (kind 'crm_auftrag'); hier steht die ID dieses Objekts. Bestehende Auftraege bleiben unveraendert.
-- Idempotent:
--   sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d <datenbank> -f migration_028_auftrag_in_acos.sql

ALTER TABLE acos_auftraege ADD COLUMN IF NOT EXISTS auftrag_objekt_id TEXT;

SELECT count(*) AS auftraege, count(auftrag_objekt_id) AS in_acos FROM acos_auftraege;
