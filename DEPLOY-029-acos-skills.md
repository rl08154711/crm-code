# Release 17.11.2026 (3): Alle ACOS-Skills im Aufgabenfenster (keine Migration)

Fachlich:
- Im Aufgabenfenster stehen alle Skills, die ACOS gerade anbietet, statt nur der Mandatsstart-Analyse,
  jeweils mit kurzer Beschreibung.
- **Synchron:** Das CRM holt die Skill-Liste bei jedem ACOS-Abgleich (täglich 6:30 und bei
  „Bei ACOS nachsehen“) und speichert sie (`system_einstellungen.acos_skills`). Neue Skills erscheinen
  von selbst; entfallene sind nicht mehr wählbar, laufende Aufträge zeigen sie weiter an.
  Gibt es noch keine Liste, holt das CRM sie beim ersten Öffnen.
- **Voraussetzungen vorab:** Nach der Wahl des Skills fragt das CRM ACOS, was beim Mandanten für diesen
  Skill fehlt (z. B. „Website-Profil“), und zeigt es an. Übergeben geht trotzdem.
- **Abgleich sichtbar:** Bei laufendem Auftrag steht „Zuletzt in ACOS nachgesehen: 17.11. 14:05 – noch
  kein Ergebnis“ bzw. „Abgleich läuft gerade“. „Bei ACOS nachsehen“ wartet, bis der Lauf fertig ist,
  und aktualisiert dann die Anzeige.

Getestet in der Sandbox (`crm_test`, Migrationen 002–027, fiktive Daten, ACOS als Attrappe):
`smoke_test.py` 84/84, `test_acos_auftraege.py` 54/54 (11 neue Prüfungen für Skills,
Voraussetzungen und Abgleich-Stand), übrige Einzeltests grün, Browser ohne JavaScript-Fehler.

| Datei | vorher (live seit Release 028) | neu |
|---|---|---|
| crm_core.py | 0e8b91ad06717e298b5fa54e1be19d1d7a274e08 | 89ce2bb9bd816ae115fde78488463bd20fff9e96 |
| crm_serve.py | b27b43d05750a101dde6a8e196585ad5c2a47b95 | d29fe0720c34c90b5844e10c6a31b3365bcf72e4 |
| acos_sync.py | 7c991314a64fb67b6e0acd82442d95be1362bfd0 | 3b977b1589fdf38c3627eb9232c40f2e1e10e71f |
| acos_auftraege.py | b121045207cdc81d9e2a61512fb28fe7f5c08b6b | 5eb8cb921cc2cb83f3603b62fbbb48d793a04c12 |

## Ausliefern (jede Zeile ein Schritt)

0 [Server] Live-Stand, muss „vorher“ zeigen:
`cd /opt/crm && sha1sum crm_core.py crm_serve.py acos_sync.py acos_auftraege.py`

1 [Mac] Arbeitsordner, muss „neu“ zeigen:
`cd ~/Documents/Claude/Projects/CRM/crm-code-upload && shasum CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/acos_sync.py CPX12-Postgres/acos_auftraege.py`

2 [Mac] Hochladen:
`ssh root@46.225.13.130 "mkdir -p /tmp/crm-release-1117c" && scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm-release-1117c/ && scp CPX12-Postgres/crm_serve.py root@46.225.13.130:/tmp/crm-release-1117c/ && scp CPX12-Postgres/acos_sync.py root@46.225.13.130:/tmp/crm-release-1117c/ && scp CPX12-Postgres/acos_auftraege.py root@46.225.13.130:/tmp/crm-release-1117c/ && echo "UPLOAD OK"`

3 [Server] Ankunft, muss „neu“ zeigen:
`cd /tmp/crm-release-1117c && sha1sum * && chmod 644 *`

4 [Server] Sicherung:
`mkdir -p /root/crm-code-vor-skills && cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py /root/crm-code-vor-skills/ && ls -la /root/crm-code-vor-skills/`

5 [Server] Einspielen und neu starten:
`cp /tmp/crm-release-1117c/*.py /opt/crm/ && chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py && cd /opt/crm && sha1sum crm_core.py crm_serve.py acos_sync.py acos_auftraege.py && systemctl restart crm && sleep 2 && systemctl status crm --no-pager | head -5`

6 [Server] Nachweis, holt dabei gleich die Skill-Liste aus ACOS:
`curl -s http://127.0.0.1:8080/healthz; cd /opt/crm && sudo -u crmapp python3 -c "import acos_auftraege as a; print(a.skills_aus_acos()); print([x['titel'] for x in a.skills()])"; journalctl -u crm -n 20 --no-pager | grep -iE "error|traceback" || echo "keine Fehler im Log"`

## Rückweg

`cp -p /root/crm-code-vor-skills/*.py /opt/crm/ && chown crmapp:crmapp /opt/crm/*.py && systemctl restart crm`

## Ins Repository (nach bestätigtem Live-Stand)

`cd ~/Documents/Claude/Projects/CRM/crm-code-upload && git add CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/acos_sync.py CPX12-Postgres/acos_auftraege.py Migration-Postgres/test_acos_auftraege.py DEPLOY-029-acos-skills.md NAECHSTES-UPDATE.md && git status --short`

`git commit -m "Aufgabenfenster: alle ACOS-Skills, Liste synchron über den Abgleich, Voraussetzungen vorab, Abgleich-Stand sichtbar" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01TH82hA4ccFXq1iNRepN1az" && git push`
