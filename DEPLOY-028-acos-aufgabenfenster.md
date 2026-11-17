# Release 17.11.2026 (2): ACOS im Aufgabenfenster, Webseite am Unternehmen (Migration 027)

Baut auf Release `DEPLOY-027-acos-auftraege.md` auf (live seit 17.11.2026).

Fachlich:
- **Ein Weg:** Im Aufgabenfenster bei einem mit ACOS verknüpften Unternehmen der Schalter
  „Von ACOS bearbeiten lassen“ – Artefakt, Thema, Hinweise und die Dateiprüfung stehen direkt im
  Fenster, „Speichern und übergeben“ erledigt alles in einem Schritt.
- **Der Auftrag steuert den Status:** Solange ein Auftrag läuft, ist das Statusfeld gesperrt
  (auch das Abhaken in Akte und Heute). Fortschritt: übergeben → bei ACOS → Ergebnis da → abgeschlossen.
- **Rückfrage im Fenster beantworten:** „Antwort an ACOS senden“ legt den Folgeauftrag selbst an.
- **Ergebnis:** Datei mit Link in den Kundenordner und nach ACOS, „Geprüft, Aufgabe abschließen“
  (einziger Weg zu Erledigt) oder „Nachbessern lassen“.
- **Verlauf statt Notizen:** Die automatischen Hinweise stehen im Verlauf des ACOS-Bereichs,
  die Notizen gehören allein dem Nutzer.
- **Etikett** „ACOS“, „ACOS: Rückfrage“ oder „ACOS: Ergebnis da“ in Aufgabenliste, Heute und Akte.
- **Webseite am Unternehmen** (Akte → Stammdaten). Der ACOS-Abgleich gibt sie an ACOS weiter.
- Fehlt der Auftragsordner in der Nextcloud, kommt ein verständlicher Satz statt „409 Conflict“.

Getestet in der Sandbox (`crm_test`, Migrationen 002–027, fiktive Daten): `smoke_test.py` 84/84,
`test_acos_auftraege.py` 43/43, `test_acos_verweis.py` 14/14, `test_acos_verweis_ablage.py` 14/14,
`test_kundenwissen_acos.py` 11/11, `test_firma_umbenennen.py` 11/11, `test_schnellauswahl.py` 19/19,
Oberfläche per Browser ohne JavaScript-Fehler.

| Datei | vorher (live seit Release 027) | neu |
|---|---|---|
| crm_core.py | ff1fb2fdfce0f7a2617575a6ac56490378573ae2 | 0e8b91ad06717e298b5fa54e1be19d1d7a274e08 |
| crm_serve.py | 9ab748169bc42d7b35a9d3a7fb0a4b83a0734d72 | b27b43d05750a101dde6a8e196585ad5c2a47b95 |
| acos_sync.py | 4980937835ce2c72ad3b1d685bf926a25cc27879 | 7c991314a64fb67b6e0acd82442d95be1362bfd0 |
| acos_auftraege.py | 49a3ce711f4d54796ae376416c90c64ec7f1a5c9 | b121045207cdc81d9e2a61512fb28fe7f5c08b6b |
| migration_027_webseite_auftragsverlauf.sql | – | 1904db019c79e04bb00aa21b406b2c74ce1eee25 |

Hinweis: Die Migration muss **vor** dem neuen Code laufen (der Code liest die Tabelle
`acos_auftrag_verlauf`). Beim nächsten scharfen Abgleich gehen eingetragene Webseiten an ACOS.

## Ausliefern

```bash
# 0 [Server] Live-Stand – muss "vorher" zeigen, sonst ABBRECHEN
cd /opt/crm && sha1sum crm_core.py crm_serve.py acos_sync.py acos_auftraege.py

# 1 [Mac] Arbeitsordner prüfen – muss "neu" zeigen, sonst ABBRECHEN
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/acos_sync.py \
       CPX12-Postgres/acos_auftraege.py Migration-Postgres/migration_027_webseite_auftragsverlauf.sql

# 2 [Mac] Hochladen (je Datei ein scp)
ssh root@46.225.13.130 "mkdir -p /tmp/crm-release-1117b"
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm-release-1117b/
scp CPX12-Postgres/crm_serve.py root@46.225.13.130:/tmp/crm-release-1117b/
scp CPX12-Postgres/acos_sync.py root@46.225.13.130:/tmp/crm-release-1117b/
scp CPX12-Postgres/acos_auftraege.py root@46.225.13.130:/tmp/crm-release-1117b/
scp Migration-Postgres/migration_027_webseite_auftragsverlauf.sql root@46.225.13.130:/tmp/crm-release-1117b/

# 3 [Server] Ankunft prüfen – "neu", sonst ABBRECHEN
cd /tmp/crm-release-1117b && sha1sum * && chmod 644 *

# 4 [Server] Sicherung: Code und Datenbank
mkdir -p /root/crm-code-vor-aufgabenfenster
cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py /root/crm-code-vor-aufgabenfenster/
cd /tmp && sudo -u crmapp pg_dump -d crm > /root/crm-code-vor-aufgabenfenster/crm-db.sql && ls -la /root/crm-code-vor-aufgabenfenster/

# 5 [Server] Migration 027 (neue Spalte webseite, neue Tabelle acos_auftrag_verlauf; zeigt am Ende 0 | <Anzahl Unternehmen>)
cd /tmp && sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d crm -f /tmp/crm-release-1117b/migration_027_webseite_auftragsverlauf.sql

# 6 [Server] Code einspielen, Dienst neu starten
cp /tmp/crm-release-1117b/crm_core.py /tmp/crm-release-1117b/crm_serve.py /tmp/crm-release-1117b/acos_sync.py /tmp/crm-release-1117b/acos_auftraege.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py
cd /opt/crm && sha1sum crm_core.py crm_serve.py acos_sync.py acos_auftraege.py
systemctl restart crm
sleep 2; systemctl status crm --no-pager | head -5

# 7 [Server] Nachweis
curl -s http://127.0.0.1:8080/healthz
journalctl -u crm -n 20 --no-pager | grep -iE "error|traceback" || echo "keine Fehler im Log"
```

## Rückweg

```bash
cp -p /root/crm-code-vor-aufgabenfenster/*.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py
systemctl restart crm
# Spalte webseite und Tabelle acos_auftrag_verlauf stören den alten Code nicht und können bleiben.
```

## Ins Repository (erst nach bestätigtem Live-Stand, zusammen mit Release 027)

```bash
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
git status --short
git add CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/acos_sync.py CPX12-Postgres/acos_auftraege.py \
        Migration-Postgres/migration_026_acos_auftraege.sql Migration-Postgres/migration_027_webseite_auftragsverlauf.sql \
        Migration-Postgres/test_acos_auftraege.py DEPLOY-027-acos-auftraege.md DEPLOY-028-acos-aufgabenfenster.md \
        AUFTRAEGE-ABARBEITEN.md NAECHSTES-UPDATE.md
git commit -F - <<'EOF'
Release 17.11.2026: Aufgabe als Auftrag an ACOS, Webseite am Unternehmen (Migrationen 026, 027)

- Aufgabe eines Mandanten als Auftrag an ACOS (Auftrags-ID AUF-JJJJ-NNNN, Auftragsdatei in der Nextcloud)
- Aufgabenfenster: "Von ACOS bearbeiten lassen", Dateiprüfung, Rückfrage beantworten,
  "Geprüft, Aufgabe abschließen", Nachbessern, Verlauf statt Notizen
- Der laufende Auftrag steuert den Aufgabenstatus; Etikett ACOS in Liste, Heute und Akte
- Rückweg über den ACOS-Abgleich: Ablage im Kundenordner, Kundenwissen, Journal
- Webseite am Unternehmen, geht mit dem Abgleich an ACOS
- Menüwechsel lädt die Ansicht neu (nicht bei offenem Formular)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TH82hA4ccFXq1iNRepN1az
EOF
git push
```
