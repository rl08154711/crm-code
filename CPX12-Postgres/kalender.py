"""
kalender.py - Termine aus dem Google-Kalender (Umbau Schritt 11, 2026-10-31)
=========================================================================
Liest die geheime iCal-Adresse (secrets/kalender.env, KALENDER_ICS_URL) und
schreibt die Termine der naechsten Wochen in die Tabelle termin. Nur lesend:
Der Kalender selbst wird nie veraendert. Stdlib only (urllib, zoneinfo).
Aufgerufen vom Mail-Poller alle 15 Minuten und ueber den Knopf auf "Heute".
"""
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    BERLIN = ZoneInfo("Europe/Berlin")
except Exception:                                    # pragma: no cover
    ZoneInfo, BERLIN = None, timezone(timedelta(hours=1))

FENSTER_ZURUECK = 7      # Tage
FENSTER_VOR = 35         # Tage
_WT = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


# Zeitzonen-Namen aus Outlook/Exchange-Einladungen -> IANA
_WINDOWS_TZ = {"W. Europe Standard Time": "Europe/Berlin", "Central Europe Standard Time": "Europe/Budapest",
               "Central European Standard Time": "Europe/Warsaw", "Romance Standard Time": "Europe/Paris",
               "GMT Standard Time": "Europe/London", "Greenwich Standard Time": "Atlantic/Reykjavik",
               "UTC": "UTC", "Coordinated Universal Time": "UTC", "E. Europe Standard Time": "Europe/Chisinau",
               "FLE Standard Time": "Europe/Kiev", "GTB Standard Time": "Europe/Bucharest",
               "Eastern Standard Time": "America/New_York", "Pacific Standard Time": "America/Los_Angeles",
               "Central Standard Time": "America/Chicago", "Russian Standard Time": "Europe/Moscow"}


class KalenderFehler(Exception):
    pass


# ── iCal lesen ────────────────────────────────────────────────────────────────
def _entfalten(text):
    zeilen = []
    for z in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if z[:1] in (" ", "\t") and zeilen:
            zeilen[-1] += z[1:]
        elif z:
            zeilen.append(z)
    return zeilen


def _eigenschaft(zeile):
    """'DTSTART;TZID=Europe/Berlin:2026...' -> ('DTSTART', {'TZID': ...}, '2026...')"""
    in_q, pos = False, -1
    for i, ch in enumerate(zeile):
        if ch == '"':
            in_q = not in_q
        elif ch == ":" and not in_q:
            pos = i
            break
    if pos < 0:
        return None, {}, ""
    kopf, wert = zeile[:pos], zeile[pos + 1:]
    teile = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', kopf)
    params = {}
    for p in teile[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return teile[0].upper(), params, wert


def _text(v):
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


def _zeit(wert, params):
    """-> (datetime mit Zeitzone oder date, ganztag)"""
    wert = wert.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", wert):
        return date(int(wert[:4]), int(wert[4:6]), int(wert[6:8])), True
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", wert)
    if not m:
        raise ValueError(wert)
    dt = datetime(*[int(x) for x in m.groups()[:5]], int(m.group(6) or 0))
    if m.group(7) == "Z":
        return dt.replace(tzinfo=timezone.utc), False
    tz = BERLIN
    tzid = (params.get("TZID") or "").strip()
    tzid = _WINDOWS_TZ.get(tzid, tzid)
    if tzid and ZoneInfo:
        try:
            tz = ZoneInfo(tzid)
        except Exception:
            tz = BERLIN
    return dt.replace(tzinfo=tz), False


def ereignisse(ics_text):
    """Liste der VEVENTs als dict (roh, Serien noch nicht aufgeloest)."""
    out, cur = [], None
    for z in _entfalten(ics_text):
        name, params, wert = _eigenschaft(z)
        if name == "BEGIN" and wert.upper() == "VEVENT":
            cur = {"exdate": [], "teilnehmer": []}
        elif name == "END" and wert.upper() == "VEVENT":
            if cur is not None and cur.get("uid") and cur.get("start"):
                out.append(cur)
            cur = None
        elif cur is None or not name:
            continue
        elif name == "UID":
            cur["uid"] = wert.strip()
        elif name == "SUMMARY":
            cur["titel"] = _text(wert)
        elif name == "LOCATION":
            cur["ort"] = _text(wert)
        elif name == "STATUS":
            cur["status"] = wert.strip().upper()
        elif name in ("DTSTART", "DTEND", "RECURRENCE-ID"):
            try:
                cur[{"DTSTART": "start", "DTEND": "ende", "RECURRENCE-ID": "rid"}[name]] = _zeit(wert, params)
            except ValueError:
                pass
        elif name == "DURATION":
            m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", wert.strip())
            if m:
                w, d, h, mi, s = (int(x or 0) for x in m.groups())
                cur["dauer"] = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
        elif name == "RRULE":
            cur["rrule"] = dict(p.split("=", 1) for p in wert.strip().split(";") if "=" in p)
        elif name == "EXDATE":
            for v in wert.split(","):
                try:
                    cur["exdate"].append(_zeit(v, params)[0])
                except ValueError:
                    pass
        elif name in ("ATTENDEE", "ORGANIZER"):
            m = re.search(r"mailto:([^\s;]+)", wert, re.I)
            if m:
                cur["teilnehmer"].append(m.group(1).strip().lower())
    return out


def _als_dt(x):
    return datetime(x.year, x.month, x.day, tzinfo=BERLIN) if not isinstance(x, datetime) else x


def _schluessel_zeit(x):
    return x.isoformat() if not isinstance(x, datetime) else x.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _monatstage(jahr, monat, rr, lokal):
    """Tage eines Monats fuer FREQ=MONTHLY (BYMONTHDAY oder BYDAY mit Ordnungszahl, z. B. 1MO, -1FR)."""
    import calendar
    letzter = calendar.monthrange(jahr, monat)[1]
    tage = []
    for t in [x for x in rr.get("BYMONTHDAY", "").split(",") if x.strip()]:
        try:
            n = int(t)
        except ValueError:
            continue
        d = n if n > 0 else letzter + 1 + n
        if 1 <= d <= letzter:
            tage.append(d)
    for t in [x for x in rr.get("BYDAY", "").split(",") if x.strip()]:
        m = re.fullmatch(r"([+-]?\d{0,2})(MO|TU|WE|TH|FR|SA|SU)", t.strip())
        if not m:
            continue
        wt = _WT[m.group(2)]
        alle = [d for d in range(1, letzter + 1) if date(jahr, monat, d).weekday() == wt]
        if m.group(1) in ("", "+"):
            tage += alle
        else:
            n = int(m.group(1))
            if -len(alle) <= n <= len(alle) and n != 0:
                tage.append(alle[n - 1] if n > 0 else alle[n])
    if not tage:
        tage = [lokal.day] if lokal.day <= letzter else []
    return sorted(set(tage))


def _vorkommen(ev, von, bis):
    """Beginnzeiten einer (Serien-)Veranstaltung im Fenster [von, bis)."""
    start = ev["start"][0]
    rr = ev.get("rrule")
    if not rr:
        return [start]
    freq = rr.get("FREQ", "").upper()
    try:
        intervall = max(1, int(rr.get("INTERVAL", "1") or 1))
    except ValueError:
        intervall = 1
    anzahl = int(rr["COUNT"]) if rr.get("COUNT", "").isdigit() else None
    until = None
    if rr.get("UNTIL"):
        try:
            until = _als_dt(_zeit(rr["UNTIL"], {})[0])
        except ValueError:
            until = None
    tage = [_WT[t[-2:]] for t in rr.get("BYDAY", "").split(",") if t[-2:] in _WT]
    lokal = start.astimezone(BERLIN) if isinstance(start, datetime) else start
    ex = {_schluessel_zeit(e) for e in ev["exdate"]}
    lokal_tag = lokal.date() if isinstance(lokal, datetime) else lokal
    # Ohne COUNT direkt kurz vor das Fenster springen (alte Serien seit Jahren)
    i = 0
    if anzahl is None:
        abstand = (von.date() - lokal_tag).days
        if abstand > 0:
            einheit = {"DAILY": 1, "WEEKLY": 7}.get(freq)
            if einheit:
                i = max(0, abstand // (einheit * intervall) - 1)
            elif freq == "MONTHLY":
                i = max(0, ((von.year - lokal_tag.year) * 12 + von.month - lokal_tag.month) // intervall - 1)
            elif freq == "YEARLY":
                i = max(0, (von.year - lokal_tag.year) // intervall - 1)
    erg, n, schritte = [], 0, 0
    while schritte < 3000:
        schritte += 1
        if freq == "DAILY":
            kandidaten = [lokal + timedelta(days=i * intervall)]
            if tage:
                kandidaten = [k for k in kandidaten if k.weekday() in tage]
        elif freq == "WEEKLY":
            woche = lokal - timedelta(days=lokal.weekday()) + timedelta(weeks=i * intervall)
            kandidaten = sorted(woche + timedelta(days=t) for t in (tage or [lokal.weekday()]))
            kandidaten = [k for k in kandidaten if k >= lokal]
        elif freq == "MONTHLY":
            mon = lokal.month - 1 + i * intervall
            j, m = lokal.year + mon // 12, mon % 12 + 1
            kandidaten = []
            for d in _monatstage(j, m, rr, lokal):
                try:
                    k = lokal.replace(year=j, month=m, day=d)
                except ValueError:
                    continue
                if k >= lokal:
                    kandidaten.append(k)
        elif freq == "YEARLY":
            try:
                kandidaten = [lokal.replace(year=lokal.year + i * intervall)]
            except ValueError:
                kandidaten = []
        else:
            return [start]
        i += 1
        stop = False
        for k in kandidaten:
            n += 1
            if anzahl is not None and n > anzahl:
                stop = True
                break
            if until and _als_dt(k) > until:
                stop = True
                break
            if _als_dt(k) >= bis:
                stop = True
                break
            if _als_dt(k) >= von - timedelta(days=1) and _schluessel_zeit(k) not in ex:
                erg.append(k)
        if stop:
            break
    return erg


def termine_aus_ics(ics_text, heute=None):
    """Aufgeloeste Termine im Fenster als Liste von dicts."""
    heute = heute or datetime.now(BERLIN).date()
    von = datetime(heute.year, heute.month, heute.day, tzinfo=BERLIN) - timedelta(days=FENSTER_ZURUECK)
    bis = datetime(heute.year, heute.month, heute.day, tzinfo=BERLIN) + timedelta(days=FENSTER_VOR)
    evs = ereignisse(ics_text)
    ersatz = {(e["uid"], _schluessel_zeit(e["rid"][0])): e for e in evs if e.get("rid")}
    out = []
    for e in evs:
        if e.get("rid"):
            continue
        for b in _vorkommen(e, von, bis):
            quelle = ersatz.get((e["uid"], _schluessel_zeit(b)), e)
            beginn = quelle["start"][0] if quelle is not e else b
            if quelle.get("status") == "CANCELLED" or e.get("status") == "CANCELLED":
                continue
            ganztag = not isinstance(beginn, datetime)
            if quelle.get("ende"):
                dauer = _als_dt(quelle["ende"][0]) - _als_dt(quelle["start"][0])
            else:
                dauer = quelle.get("dauer") or (timedelta(days=1) if ganztag else timedelta(0))
            b_dt = _als_dt(beginn)
            if not (von <= b_dt + dauer and b_dt < bis):
                continue
            out.append({
                "schluessel": f'{e["uid"]}|{_schluessel_zeit(b)}',
                "uid": e["uid"], "beginn": b_dt, "ende": b_dt + dauer, "ganztag": ganztag,
                "titel": quelle.get("titel") or e.get("titel") or "(ohne Titel)",
                "ort": quelle.get("ort") or e.get("ort") or "",
                "teilnehmer": sorted(set(quelle.get("teilnehmer") or e.get("teilnehmer") or [])),
            })
    return out


# ── Abgleich mit der Datenbank ────────────────────────────────────────────────
def _url():
    import crm_core as core
    datei = core.BASE_DIR / "secrets" / "kalender.env"
    if not datei.exists():
        return ""
    for z in datei.read_text(encoding="utf-8").splitlines():
        k, _, v = z.strip().partition("=")
        if k.strip() == "KALENDER_ICS_URL":
            return v.strip()
    return ""


def eingerichtet():
    return bool(_url())


def _zuordnen(t, eigene):
    """(firma_id, person_id, grund) ueber Teilnehmer, sonst Firmenname im Titel."""
    import crm_core as core
    for a in t["teilnehmer"]:
        if a in eigene:
            continue
        m = core.match_contact_for_email(a)
        if m and m.get("firma"):
            f = core._q1("SELECT id FROM firmen WHERE lower(name)=lower(%s)", (m["firma"],))
            if f:
                p = core._q1("SELECT id FROM personen WHERE firma_id=%s AND lower(email)=lower(%s) LIMIT 1", (f["id"], a))
                return f["id"], (p["id"] if p else None), f"Teilnehmer {a}"
    treffer = core.weitere_firmen("", [], [t["titel"]])
    if treffer:
        f = core._q1("SELECT id FROM firmen WHERE name=%s", (treffer[0]["firma"],))
        if f:
            return f["id"], None, "Name im Titel"
    return None, None, None


def abgleich(ics_text=None):
    """Kalender lesen und Tabelle termin aktualisieren. Liefert {ok, anzahl, meldung}."""
    import crm_core as core
    try:
        if ics_text is None:
            url = _url()
            if not url:
                return {"ok": False, "anzahl": 0, "meldung": "Keine Kalender-Adresse hinterlegt"}
            if url.lower().startswith("webcal://"):
                url = "https://" + url[9:]
            if not url.lower().startswith("https://"):
                raise KalenderFehler("Die Kalender-Adresse muss mit https:// beginnen")
            req = urllib.request.Request(url, headers={"User-Agent": "CRM-Digitale-Konzepte/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    ics_text = r.read(20 * 1024 * 1024).decode("utf-8", errors="replace")
            except Exception as e:
                raise KalenderFehler(f"Kalender nicht erreichbar ({e.__class__.__name__})")
        if "BEGIN:VCALENDAR" not in ics_text[:2000]:
            raise KalenderFehler("Antwort ist kein Kalender im iCal-Format")
        termine = termine_aus_ics(ics_text)
        eigene = {a.strip().lower() for a in (core.load_secrets().get("IMAP_USER", ""),
                                              *core.load_secrets().get("MAIL_EIGENE_ADRESSEN", "").split(",")) if "@" in a}
        gesehen = []
        for t in termine:
            alt = core._q1("SELECT id, firma_manuell FROM termin WHERE schluessel=%s", (t["schluessel"],))
            if alt and alt["firma_manuell"]:
                core._x("""UPDATE termin SET beginn=%s, ende=%s, ganztag=%s, titel=%s, ort=%s, teilnehmer=%s,
                           entfernt=false, aktualisiert_am=now() WHERE id=%s""",
                        (t["beginn"], t["ende"], t["ganztag"], t["titel"], t["ort"], t["teilnehmer"], alt["id"]))
            else:
                fid, pid, grund = _zuordnen(t, eigene)
                core._x("""INSERT INTO termin (schluessel, uid, beginn, ende, ganztag, titel, ort, teilnehmer, firma_id, person_id, zuordnung)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (schluessel) DO UPDATE SET beginn=EXCLUDED.beginn, ende=EXCLUDED.ende,
                             ganztag=EXCLUDED.ganztag, titel=EXCLUDED.titel, ort=EXCLUDED.ort, teilnehmer=EXCLUDED.teilnehmer,
                             firma_id=EXCLUDED.firma_id, person_id=EXCLUDED.person_id, zuordnung=EXCLUDED.zuordnung,
                             entfernt=false, aktualisiert_am=now()""",
                        (t["schluessel"], t["uid"], t["beginn"], t["ende"], t["ganztag"], t["titel"], t["ort"],
                         t["teilnehmer"], fid, pid, grund))
            gesehen.append(t["schluessel"])
        heute = datetime.now(BERLIN).date()
        von = datetime(heute.year, heute.month, heute.day, tzinfo=BERLIN) - timedelta(days=FENSTER_ZURUECK)
        core._x("""UPDATE termin SET entfernt=true, aktualisiert_am=now()
                   WHERE beginn >= %s AND NOT entfernt AND NOT (schluessel = ANY(%s))""", (von, gesehen or [""]))
        core._x("INSERT INTO kalender_lauf (ok, anzahl, meldung) VALUES (true, %s, NULL)", (len(termine),))
        core._x("DELETE FROM kalender_lauf WHERE zeitpunkt < now() - interval '7 days'")
        return {"ok": True, "anzahl": len(termine), "meldung": ""}
    except (KalenderFehler, ValueError) as e:
        try:
            core._x("INSERT INTO kalender_lauf (ok, anzahl, meldung) VALUES (false, 0, %s)", (str(e)[:300],))
        except Exception:
            pass
        return {"ok": False, "anzahl": 0, "meldung": str(e)}
