# Release 17.11.2026 (5): Aufträge über ACOS statt Nextcloud – reine Serverlösung (Migration 028)

Fachlich: Das CRM legt den Auftrag als Wissensobjekt `crm_auftrag` in der ACOS-Kundenakte ab statt als Datei
in `/Arbeitsdateien/Aufträge`. Rückfragen kommen als `crm_rueckfrage` aus ACOS. Beide Arten landen nicht im
Kundenwissen. Die Abarbeitung übernimmt eine geplante Aufgabe in der Cloud – der Mac muss nicht laufen.
Oberfläche unverändert. Details: `AUFTRAEGE-ABARBEITEN.md`.

Getestet in der Sandbox (`crm_test`, Migrationen 002–028, ACOS als Attrappe): `test_acos_auftraege.py` 58/58,
`smoke_test.py` 84/84, übrige Einzeltests grün. Probe in ACOS: eigene Objektart wird angenommen,
organisationsweit gelistet und taucht nicht im Context Pack der Skills auf (Probeobjekt
„ACOS-Auftrag PROBE-0000“ bei M-13).

| Datei | vorher (live seit Release 030) | neu |
|---|---|---|
| acos_sync.py | 3b977b1589fdf38c3627eb9232c40f2e1e10e71f | 77b04b7cb3e1eca58a18baa5e20ee09852427b5e |
| acos_auftraege.py | a75127f673aac172f345e2b4e3b39849c6a26a6d | 1be9e4580be887c1de101be0664519f143330c22 |
| migration_028_auftrag_in_acos.sql | – | aabd721e37aae2180b690717ae4b543f446f4951 |

crm_core.py und crm_serve.py bleiben unverändert.

## Ausliefern (jede Zeile ein Schritt)

0 [Server] `cd /opt/crm && sha1sum acos_sync.py acos_auftraege.py crm_core.py`
  (erwartet 3b977b15…, a75127f6…, fe1ecbe9…)

1 [Mac] `cd ~/Documents/Claude/Projects/CRM/crm-code-upload && shasum CPX12-Postgres/acos_sync.py CPX12-Postgres/acos_auftraege.py Migration-Postgres/migration_028_auftrag_in_acos.sql && ssh root@46.225.13.130 "mkdir -p /tmp/crm-release-1117e" && scp CPX12-Postgres/acos_sync.py root@46.225.13.130:/tmp/crm-release-1117e/ && scp CPX12-Postgres/acos_auftraege.py root@46.225.13.130:/tmp/crm-release-1117e/ && scp Migration-Postgres/migration_028_auftrag_in_acos.sql root@46.225.13.130:/tmp/crm-release-1117e/ && echo "UPLOAD OK"`

2 [Server] `cd /tmp/crm-release-1117e && sha1sum * && chmod 644 * && mkdir -p /root/crm-code-vor-auftrag-acos && cp -p /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py /root/crm-code-vor-auftrag-acos/ && cd /tmp && sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d crm -f /tmp/crm-release-1117e/migration_028_auftrag_in_acos.sql`

3 [Server] `cp /tmp/crm-release-1117e/acos_sync.py /tmp/crm-release-1117e/acos_auftraege.py /opt/crm/ && chown crmapp:crmapp /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py && cd /opt/crm && sha1sum acos_sync.py acos_auftraege.py && systemctl restart crm && sleep 2 && systemctl status crm --no-pager | head -3`

4 [Server] `curl -s http://127.0.0.1:8080/healthz; journalctl -u crm -n 20 --no-pager | grep -iE "error|traceback" || echo "keine Fehler im Log"`

## Rückweg

`cp -p /root/crm-code-vor-auftrag-acos/*.py /opt/crm/ && chown crmapp:crmapp /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py && systemctl restart crm`
(Spalte `auftrag_objekt_id` stört den alten Code nicht.)

## Ins Repository (nach bestätigtem Live-Stand)

`cd ~/Documents/Claude/Projects/CRM/crm-code-upload && git add CPX12-Postgres/acos_sync.py CPX12-Postgres/acos_auftraege.py Migration-Postgres/migration_028_auftrag_in_acos.sql Migration-Postgres/test_acos_auftraege.py AUFTRAEGE-ABARBEITEN.md DEPLOY-031-auftrag-in-acos.md NAECHSTES-UPDATE.md && git commit -m "Aufträge über ACOS statt Nextcloud: reine Serverlösung (Migration 028)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01TH82hA4ccFXq1iNRepN1az" && git push`
