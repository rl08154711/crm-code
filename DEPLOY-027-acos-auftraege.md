# Release 17.11.2026: Aufgabe als Auftrag an ACOS, Aktualisieren beim Menüwechsel (Migration 026)

Fachlich:
- Aufgabe eines Mandanten → Bereich „ACOS-Auftrag“ in der Aufgabe → Artefakttyp und Thema wählen →
  „Dateien prüfen und übergeben“. Das CRM zeigt Dateien des Kundenordners, die noch nicht in ACOS
  sind, sendet die angehakten mit und legt die Auftragsdatei `AUF-JJJJ-NNNN.json` unter
  `/Arbeitsdateien/Aufträge/offen/` ab. Aufgabe → „In Bearbeitung“.
- Claude arbeitet den Auftrag am Mac ab (`AUFTRAEGE-ABARBEITEN.md`).
- „Ergebnis jetzt abholen“ startet den ACOS-Abgleich: Artefakt → `<Kunde>/ACOS/Wissen` →
  Kundenwissen, Auftrag „bearbeitet“, Aufgabe „Bearbeitet“ mit Hinweis, Journal-Eintrag.
  Rückfragen von ACOS erscheinen in der Aufgabe. „Erledigt“ setzt nur Ronald (zweiter Journal-Eintrag).
- Neuer Aufgaben-Status „Bearbeitet“.
- Menüwechsel lädt die Ansicht neu, wenn seitdem etwas geändert wurde oder der Stand älter als eine
  Minute ist. Bei offenem Formular nicht, dann kurzer Hinweis.

Getestet in der Sandbox (`crm_test`, Migrationen 002–026, fiktive Daten): `smoke_test.py` 84/84,
`test_acos_auftraege.py` 32/32 (neu), `test_acos_verweis.py` 14/14, `test_acos_verweis_ablage.py` 14/14,
`test_kundenwissen_acos.py` 11/11, `test_firma_umbenennen.py` 11/11, `test_schnellauswahl.py` 19/19,
Oberfläche per Browser ohne JavaScript-Fehler.

| Datei | vorher (Repository = live laut Release 16.11.) | neu |
|---|---|---|
| crm_core.py | abff7a01e62dee3718ff7f4a59f262d7ee41e5ff | ff1fb2fdfce0f7a2617575a6ac56490378573ae2 |
| crm_serve.py | 4b60015a8a0782e66bd31a9061c8e0ea99fe2900 | 9ab748169bc42d7b35a9d3a7fb0a4b83a0734d72 |
| acos_sync.py | dc7f818974eb777d639ec915a050200eaa64c897 | 4980937835ce2c72ad3b1d685bf926a25cc27879 |
| acos_auftraege.py | – | 49a3ce711f4d54796ae376416c90c64ec7f1a5c9 |
| migration_026_acos_auftraege.sql | – | a9d6e27d9675b3bad45bc668a7abc73b17a5e389 |

## Vorher einmalig

In der Nextcloud (Weboberfläche) den Ordner `/Arbeitsdateien/Aufträge` anlegen. Die Unterordner
`offen` und `ergebnis` legt das CRM bzw. Claude selbst an. Anderer Pfad: `AUFTRAEGE_PFAD=…` in
`/opt/crm/secrets/wissen.env`.

## Ausliefern

```bash
# 0 [Server] Live-Stand – muss "vorher" zeigen, sonst ABBRECHEN
cd /opt/crm && sha1sum crm_core.py crm_serve.py acos_sync.py

# 1 [Mac] Arbeitsordner prüfen – muss "neu" zeigen, sonst ABBRECHEN
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
shasum CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/acos_sync.py \
       CPX12-Postgres/acos_auftraege.py Migration-Postgres/migration_026_acos_auftraege.sql

# 2 [Mac] Hochladen (je Datei ein scp)
ssh root@46.225.13.130 "mkdir -p /tmp/crm-release-1117"
scp CPX12-Postgres/crm_core.py root@46.225.13.130:/tmp/crm-release-1117/
scp CPX12-Postgres/crm_serve.py root@46.225.13.130:/tmp/crm-release-1117/
scp CPX12-Postgres/acos_sync.py root@46.225.13.130:/tmp/crm-release-1117/
scp CPX12-Postgres/acos_auftraege.py root@46.225.13.130:/tmp/crm-release-1117/
scp Migration-Postgres/migration_026_acos_auftraege.sql root@46.225.13.130:/tmp/crm-release-1117/

# 3 [Server] Ankunft prüfen – "neu", sonst ABBRECHEN
cd /tmp/crm-release-1117 && sha1sum * && chmod 644 *

# 4 [Server] Sicherung: Code und Datenbank
mkdir -p /root/crm-code-vor-auftraege
cp -p /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /root/crm-code-vor-auftraege/
cd /tmp && sudo -u crmapp pg_dump -d crm > /root/crm-code-vor-auftraege/crm-db.sql && ls -la /root/crm-code-vor-auftraege/

# 5 [Server] Migration 026 (legt nur die neue Tabelle acos_auftraege an, zeigt am Ende 0)
cd /tmp && sudo -u crmapp psql -v ON_ERROR_STOP=1 -P pager=off -d crm -f /tmp/crm-release-1117/migration_026_acos_auftraege.sql

# 6 [Server] Code einspielen, Dienst neu starten
cp /tmp/crm-release-1117/crm_core.py /tmp/crm-release-1117/crm_serve.py /tmp/crm-release-1117/acos_sync.py /tmp/crm-release-1117/acos_auftraege.py /opt/crm/
chown crmapp:crmapp /opt/crm/crm_core.py /opt/crm/crm_serve.py /opt/crm/acos_sync.py /opt/crm/acos_auftraege.py
cd /opt/crm && sha1sum crm_core.py crm_serve.py acos_sync.py acos_auftraege.py
systemctl restart crm
sleep 2; systemctl status crm --no-pager | head -5

# 7 [Server] Nachweis
curl -s http://127.0.0.1:8080/healthz
journalctl -u crm -n 20 --no-pager | grep -iE "error|traceback" || echo "keine Fehler im Log"
```

Der ACOS-Timer (`crm-acos`, 6:30) startet `acos_sync.py` selbst neu, kein Neustart nötig.

Danach im Browser: Aufgabe am Testmandanten (M-13) anlegen, öffnen → Bereich „ACOS-Auftrag“,
Thema ohne Namen eingeben, „Dateien prüfen und übergeben“ → in der Nextcloud liegt
`/Arbeitsdateien/Aufträge/offen/AUF-2026-0001.json`.

## Rückweg

```bash
cp -p /root/crm-code-vor-auftraege/crm_core.py /root/crm-code-vor-auftraege/crm_serve.py /root/crm-code-vor-auftraege/acos_sync.py /opt/crm/
systemctl restart crm
# acos_auftraege.py und die Tabelle acos_auftraege stören den alten Code nicht und können bleiben.
```

## Ins Repository (erst nach bestätigtem Live-Stand)

```bash
cd ~/Documents/Claude/Projects/CRM/crm-code-upload
git status --short
git add CPX12-Postgres/crm_core.py CPX12-Postgres/crm_serve.py CPX12-Postgres/acos_sync.py \
        CPX12-Postgres/acos_auftraege.py Migration-Postgres/migration_026_acos_auftraege.sql \
        Migration-Postgres/test_acos_auftraege.py DEPLOY-027-acos-auftraege.md AUFTRAEGE-ABARBEITEN.md NAECHSTES-UPDATE.md
git commit -F - <<'EOF'
Release 17.11.2026: Aufgabe als Auftrag an ACOS, Aktualisieren beim Menüwechsel (Migration 026)

- Aufgabe eines Mandanten als Auftrag an ACOS (Auftrags-ID AUF-JJJJ-NNNN, Auftragsdatei in der Nextcloud)
- Vorprüfung Kundenordner gegen ACOS, fehlende Dateien vorab senden
- Rückweg über den ACOS-Abgleich: Ablage im Kundenordner, Kundenwissen, Journal,
  Aufgabe automatisch "Bearbeitet", "Erledigt" setzt der Nutzer
- Rückfragen/Fehler von ACOS als Ergebnisdatei
- Menüwechsel lädt die Ansicht neu (nicht bei offenem Formular)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TH82hA4ccFXq1iNRepN1az
EOF
git push
```
