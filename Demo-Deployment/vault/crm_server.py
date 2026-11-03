#!/usr/bin/env python3
# Starten mit: python3 crm_server.py
"""
crm_server.py – CRM Local Web Server
======================================
Startet einen lokalen Server auf http://localhost:8765
Stellt REST-API für das CRM-Dashboard bereit (Lesen + Schreiben).

Starten:  python crm_server.py
Öffnen:   http://localhost:8765
Stoppen:  STRG+C
"""

import json
import re
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, date
from urllib.parse import urlparse, parse_qs, unquote

BASE_DIR     = Path(__file__).parent
CONTACTS_DIR = BASE_DIR / "Kontakte"          # Legacy-Pfad (Backup)
FIRMEN_DIR   = BASE_DIR / "Kontakte" / "Firmen"
PERS_DIR     = BASE_DIR / "Kontakte" / "Personen"
OPPS_DIR     = BASE_DIR / "Opportunities"
TASKS_FILE   = BASE_DIR / "tasks.json"
TODAY = date.today().isoformat()
NOW = lambda: datetime.now().isoformat(timespec="seconds") + "Z"

# ──────────────────────────────────────────────────────────────────────────────
# DATA HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("-"):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def parse_md_field(text, field):
    m = re.search(rf"\*\*{field}:\*\*\s*(.+)", text)
    return m.group(1).strip() if m else ""

def parse_all_ansprechpartner(text):
    """Alle ## Ansprechpartner-Blöcke aus einer Kontakt-MD-Datei extrahieren."""
    blocks = re.split(r"(?=## Ansprechpartner)", text)
    results = []
    for block in blocks:
        if "## Ansprechpartner" not in block:
            continue
        name  = re.search(r"\*\*Name:\*\*\s*(.+)", block)
        email = re.search(r"\*\*E-Mail:\*\*\s*(.+)", block)
        phone = re.search(r"\*\*Telefon:\*\*\s*(.+)", block)
        added = re.search(r"\*\*Hinzugefügt:\*\*\s*(.+)", block)
        entry = {
            "name":  name.group(1).strip()  if name  else "",
            "email": email.group(1).strip() if email else "",
            "phone": phone.group(1).strip() if phone else "",
            "added": added.group(1).strip() if added else "",
        }
        if entry["name"]:
            results.append(entry)
    return results

def update_md_field(text, field, value):
    """Ersetzt **Field:** Wert in MD-Text."""
    pattern = rf"(\*\*{re.escape(field)}:\*\*\s*)(.+)"
    replacement = rf"\g<1>{value}"
    new_text = re.sub(pattern, replacement, text)
    if new_text == text and value:
        # Feld nicht gefunden – ans Ende von Grunddaten anfügen
        pass
    return new_text

def update_frontmatter_field(text, key, value):
    """Ersetzt key: value NUR im YAML-Frontmatter (zwischen den --- Trennern)."""
    fm_match = re.match(r"^(---\s*\n)(.*?)(\n---)", text, re.DOTALL)
    if not fm_match:
        return text
    pre, fm_block, post_sep = fm_match.group(1), fm_match.group(2), fm_match.group(3)
    rest = text[fm_match.end():]
    pattern = rf"(^{re.escape(key)}:[ \t]*)(.*)$"
    replacement = rf"\g<1>{value}"
    new_fm = re.sub(pattern, replacement, fm_block, flags=re.MULTILINE)
    if new_fm == fm_block:  # Key nicht gefunden → ans Ende des Frontmatters anhängen
        new_fm = fm_block + f"\n{key}: {value}"
    return pre + new_fm + post_sep + rest

def load_tasks():
    if not TASKS_FILE.exists():
        return []
    with open(TASKS_FILE, encoding="utf-8") as f:
        return json.load(f).get("tasks", [])

def save_tasks(tasks):
    if TASKS_FILE.exists():
        with open(TASKS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"version": "1.0", "schema": {}}
    data["tasks"] = tasks
    data["lastUpdated"] = NOW()
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "Erledigt")
    data["metadata"] = {"totalTasks": total, "completedTasks": done, "openTasks": total - done}
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_contacts():
    """Lädt Firmen aus Firmen/ und verknüpfte Personen aus Personen/."""
    contacts = []
    if not FIRMEN_DIR.exists():
        return contacts

    # Personen-Index aufbauen: firma_name (lower) → [person_dict]
    person_index: dict = {}
    if PERS_DIR.exists():
        for pf in sorted(PERS_DIR.glob("*.md")):
            pt = pf.read_text(encoding="utf-8")
            pfm = parse_frontmatter(pt)
            firma_link = pfm.get("firma", "").replace("[[", "").replace("]]", "").strip()
            if not firma_link:
                continue
            p = {
                "id":         pf.stem,
                "name":       parse_md_field(pt, "Name") or pf.stem,
                "email":      pfm.get("email", "") or parse_md_field(pt, "E-Mail"),
                "phone":      pfm.get("tel", "")   or parse_md_field(pt, "Telefon"),
                "titel":      parse_md_field(pt, "Titel"),
                "abteilung":  parse_md_field(pt, "Abteilung"),
                "added":      pfm.get("hinzugefuegt", ""),
            }
            person_index.setdefault(firma_link.lower(), []).append(p)

    for ff in sorted(FIRMEN_DIR.glob("*.md")):
        text = ff.read_text(encoding="utf-8")
        fm   = parse_frontmatter(text)
        firma = parse_md_field(text, "Firma") or fm.get("Firma", "") or ff.stem
        persons = person_index.get(firma.lower(), [])
        primary = persons[0] if persons else {}
        contacts.append({
            "id":                  ff.stem,
            "file":                ff.name,
            "firma":               firma,
            "ansprechpartner":     primary.get("name", ""),
            "ansprechpartner_list": persons,
            "email":               primary.get("email", ""),
            "phone":               primary.get("phone", ""),
            "status":              fm.get("status", "lead"),
            "last_contact":        fm.get("last_contact", ""),
            "next_action":         fm.get("next_action", ""),
            "source":              fm.get("source", "") or parse_md_field(text, "Quelle"),
            "branch":              fm.get("branch", "") or parse_md_field(text, "Branche"),
            "address":             fm.get("address", "") or parse_md_field(text, "Adresse"),
            "notes":               "",
        })
    return contacts

def load_opportunities():
    opps = []
    if not OPPS_DIR.exists():
        return opps
    for f in sorted(OPPS_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        summary_m = re.search(r"## Zusammenfassung\s*\n(.+?)(?=\n##|\Z)", text, re.DOTALL)
        summary = summary_m.group(1).strip().replace("\n", " ")[:120] if summary_m else ""
        opps.append({
            "id": f.stem,
            "file": f.name,
            "title": f.stem,
            "kontakt": fm.get("kontakt", "").replace("[[", "").replace("]]", ""),
            "status": fm.get("status", "aktiv"),
            "value": fm.get("value", "") or parse_md_field(text, "Umsatz"),
            "probability": fm.get("probability", "") or parse_md_field(text, "Wahrscheinlichkeit"),
            "next_action": fm.get("next_action", ""),
            "deadline": fm.get("deadline", ""),
            "created": fm.get("created", ""),
            "ansprechpartner": fm.get("ansprechpartner", ""),
            "summary": summary,
        })
    return opps

def days_until(date_str):
    if not date_str:
        return None
    try:
        return (date.fromisoformat(date_str) - date.today()).days
    except:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# PARSER JS (raw string – backslashes and braces are literal, no f-string issues)
# ──────────────────────────────────────────────────────────────────────────────
PARSE_JS = r"""
function toggleParser() {
  const body = document.getElementById('parse-body');
  const arrow = document.getElementById('parse-arrow');
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  arrow.textContent = open ? '▾' : '▸';
}

function parseContactText() {
  const raw = document.getElementById('c-paste').value.trim();
  if (!raw) return;
  const lines = raw.split(/\n/).map(l => l.trim()).filter(Boolean);
  const full  = raw;

  // Email
  const emailM = full.match(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/);
  const email  = emailM ? emailM[0] : '';

  // Telefon (DE/AT/CH)
  const telM = full.match(/(\+49[\s\-/]?[\d\s\-/]{7,}|0049[\s\-/]?[\d\s\-/]{7,}|\+4[13][\s\-/]?[\d\s\-/]{7,}|0[\d]{3,5}[\s\/\-]?[\d\s\-/]{4,10})/);
  const tel  = telM ? telM[0].replace(/\s+/g,' ').trim() : '';

  // Website
  const webM = full.match(/(?:https?:\/\/|www\.)([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})/i);

  // Firma (enthält GmbH / AG / UG etc.)
  let firma = '';
  const firmaPatterns = [
    /([A-ZÄÖÜ][^\n,·|]+(?:GmbH|AG|UG|KG|GbR|Ltd|SE|Inc|e\.V\.|eG|OHG|Co\.|KGaA)(?:\s+&\s+\w+\.?)?)/,
    /(?:Firma|Unternehmen|Company|Arbeitgeber)[:\s]+([^\n]+)/i,
  ];
  for (const p of firmaPatterns) {
    const m = full.match(p);
    if (m) { firma = m[1].trim(); break; }
  }
  // Fallback: Zeile mit Großbuchstaben die kein Name/Email/Tel ist
  if (!firma) {
    for (const l of lines) {
      if (l.includes('@') || l.match(/^\+?[\d\s\-\/(){}]{6,}$/)) continue;
      if (l.match(/^(https?|www)/i)) continue;
      if (l.match(/^(Dr\.|Prof\.|Dipl\.|Ing\.|M\.Sc|B\.Sc)/i)) continue;
      if (l.match(/[A-ZÄÖÜ][a-zäöüß]+ [A-ZÄÖÜ][a-zäöüß]+/) && !firma) continue;
      if (l.match(/[A-ZÄÖÜ]/) && l.length > 4) { firma = l; break; }
    }
  }

  // Name (Vor- + Nachname, optional Titel)
  let name = '';
  const nameRe = /^(?:(?:Dr\.|Prof\.|Dipl\.-?Ing\.|M\.Sc\.?|B\.Sc\.?|Mag\.|Ing\.)\s+)?([A-ZÄÖÜ][a-zäöüß\-]+ [A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+)?)/;
  for (const l of lines) {
    if (l.includes('@') || l.match(/^\+?[\d\s\-\/()]{6,}$/) || l.match(/^(https?|www)/i)) continue;
    const m = l.match(nameRe);
    if (m) { name = m[0].trim(); break; }
  }

  // Felder setzen
  const filled = [];
  if (email) { document.getElementById('c-email').value = email; filled.push('E-Mail'); }
  if (tel)   { document.getElementById('c-tel').value   = tel;   filled.push('Tel'); }
  if (firma) { document.getElementById('c-firma').value = firma; filled.push('Firma'); }
  if (name)  { document.getElementById('c-name').value  = name;  filled.push('Name'); }

  // Feedback
  const result = document.getElementById('parse-result');
  if (filled.length > 0) {
    result.style.color = 'var(--green)';
    result.textContent = '✓ Erkannt: ' + filled.join(', ');
  } else {
    result.style.color = 'var(--red)';
    result.textContent = 'Nichts erkannt – Felder manuell füllen.';
  }

  // Gefüllte Felder kurz grün markieren
  ['c-firma','c-name','c-email','c-tel'].forEach(id => {
    const el = document.getElementById(id);
    if (el.value) {
      el.style.borderColor = 'var(--green)';
      setTimeout(() => el.style.borderColor = '', 2500);
    }
  });
}
"""

# ──────────────────────────────────────────────────────────────────────────────
# HTML GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def badge(text, color):
    return f'<span class="badge" style="background:{color}">{text}</span>'

STATUS_COLORS = {
    "offen": "#f59e0b", "in bearbeitung": "#3b82f6", "blockiert": "#ef4444",
    "erledigt": "#22c55e", "verschoben": "#8b5cf6",
    "aktiv": "#3b82f6", "lead": "#f59e0b", "kunde": "#22c55e",
    "interessent": "#a78bfa", "inaktiv": "#9ca3af", "won": "#22c55e", "lost": "#ef4444",
}
PRIO_COLORS = {"kritisch": "#ef4444", "hoch": "#f97316", "mittel": "#f59e0b", "niedrig": "#22c55e"}

def status_badge(s):
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return " ".join(badge(p, STATUS_COLORS.get(p.lower(), "#6b7280")) for p in parts) if parts else ""

def prio_badge(p):
    return badge(p, PRIO_COLORS.get(p.lower(), "#6b7280"))

def deadline_cell(dl):
    if not dl:
        return '<span style="color:#9ca3af">–</span>'
    days = days_until(dl)
    try:
        label = date.fromisoformat(dl).strftime("%d.%m.")
    except:
        return dl
    if days is None: return label
    if days < 0:  return f'<span style="color:#ef4444;font-weight:600">⚠ {label} ({abs(days)}d)</span>'
    if days == 0: return f'<span style="color:#ef4444;font-weight:600">🔥 Heute</span>'
    if days <= 3: return f'<span style="color:#f97316">{label} ({days}d)</span>'
    if days <= 7: return f'<span style="color:#f59e0b">{label}</span>'
    return f'<span style="color:#6b7280">{label}</span>'

def build_dashboard():
    tasks = load_tasks()
    contacts = load_contacts()
    opps = load_opportunities()

    active_tasks = [t for t in tasks if t["status"] not in ("Erledigt",)]
    overdue = [t for t in active_tasks if t.get("deadline") and (days_until(t["deadline"]) or 0) < 0]
    today_t  = [t for t in active_tasks if t.get("deadline") and days_until(t["deadline"]) == 0]
    done_count = sum(1 for t in tasks if t["status"] == "Erledigt")

    alert_html = ""
    if overdue:
        items = "".join(f"<li>{t['taskId']}: {t['title']}</li>" for t in overdue)
        alert_html += f'<div class="alert alert-red">⚠️ {len(overdue)} überfällige Tasks:<ul>{items}</ul></div>'
    if today_t:
        items = "".join(f"<li>{t['taskId']}: {t['title']}</li>" for t in today_t)
        alert_html += f'<div class="alert alert-yellow">🔥 Heute fällig:<ul>{items}</ul></div>'

    # ── TASKS TABLE ──
    task_rows = ""
    for t in sorted(active_tasks, key=lambda x: (x.get("deadline") or "9999", x["priority"])):
        tid = t["taskId"]
        contact = t.get('contact','')
        contact_cell = f'<a class="contact-link" href="#" onclick="openContactByName(\'{contact.replace(chr(39), chr(92)+chr(39))}\')">{contact}</a>' if contact else '<span style="color:#9ca3af">–</span>'
        task_rows += f"""<tr>
          <td><span class="task-id">{tid}</span></td>
          <td>{t['title']}</td>
          <td>{contact_cell}</td>
          <td>{prio_badge(t['priority'])}</td>
          <td>{status_badge(t['status'])}</td>
          <td>{deadline_cell(t.get('deadline',''))}</td>
          <td><button class="btn-edit" onclick="editTask('{tid}')">✏️</button></td>
        </tr>"""
    if not task_rows:
        task_rows = '<tr><td colspan="7" style="text-align:center;color:#6b7280">Keine offenen Tasks 🎉</td></tr>'

    # ── CONTACTS TABLE (grouped by firma) ──
    leads_n = sum(1 for c in contacts if any(s in c["status"].lower() for s in ("lead","interessent")))
    kunden_n = sum(1 for c in contacts if "kunde" in c["status"].lower())
    firma_groups: dict = {}
    for c in contacts:
        firma_groups.setdefault(c["firma"], []).append(c)
    contact_rows = ""
    for gi, (firma, grp) in enumerate(sorted(firma_groups.items())):
        c = grp[0]
        cid = c["id"].replace("'", "\\'")
        persons = c.get("ansprechpartner_list", [])
        person_lines = "".join(
            f'<br><small style="color:var(--text2)">👤 {p["name"]}'
            + (f' · <a href="mailto:{p["email"]}" style="color:var(--text2)">{p["email"]}</a>' if p.get("email") else "")
            + (f' · {p["phone"]}' if p.get("phone") else "")
            + (f' <span style="font-size:.7em;color:#9ca3af">(+{p["added"]})</span>' if p.get("added") else "")
            + f' <button class="btn-edit" style="font-size:.7rem;padding:1px 3px" onclick="event.stopPropagation();editPerson(\'{c["id"].replace(chr(39), chr(92)+chr(39))}\',\'{p["id"].replace(chr(39), chr(92)+chr(39))}\')" title="Ansprechpartner bearbeiten">✏️</button>'
            + "</small>"
            for p in persons
        )
        firma_esc = c['firma'].replace("'", "\\'").replace('"', '&quot;')
        addr_line = f'<br><small style="color:var(--text2)">📍 {c["address"]}</small>' if c.get("address") else ""
        contact_rows += f"""<tr data-firma="{firma_esc}">
          <td><strong>{c['firma']}</strong>{addr_line}{person_lines}</td>
          <td>{status_badge(c['status'])}</td>
          <td>{c.get('branch','') or '<span style="color:#9ca3af">–</span>'}</td>
          <td>{c.get('last_contact','') or '<span style="color:#9ca3af">–</span>'}</td>
          <td>{c.get('source','') or '<span style="color:#9ca3af">–</span>'}</td>
          <td><button class="btn-edit" onclick="editContact('{cid}')">✏️</button></td>
        </tr>"""
    if not contact_rows:
        contact_rows = '<tr><td colspan="6" style="text-align:center;color:#6b7280">Keine Kontakte</td></tr>'

    # ── PIPELINE TABLE ──
    total_value = sum(int(re.sub(r"[^\d]","",o.get("value","") or "") or 0) for o in opps)
    aktiv_n = sum(1 for o in opps if o["status"].lower() == "aktiv")
    value_display = f'{total_value:,}'.replace(",",".") + " €" if total_value else "–"
    opp_rows = ""
    for o in sorted(opps, key=lambda x: ({"aktiv":0,"kunde":1,"won":2,"lost":3}.get(x["status"].lower(),9), x.get("deadline") or "9999")):
        oid = o["id"].replace("'","\\'")
        summ = f'<br><small style="color:#9ca3af">{o["summary"]}</small>' if o["summary"] else ""
        kontakt = o.get('kontakt','')
        kontakt_cell = f'<a class="contact-link" href="#" onclick="event.stopPropagation();openContactByName(\'{kontakt.replace(chr(39), chr(92)+chr(39))}\')">{kontakt}</a>' if kontakt else '<span style="color:#9ca3af">–</span>'
        kontakt_esc = kontakt.replace("'", "\\'").replace('"', '&quot;')
        title_esc = o['title'].replace("'", "\\'").replace('"', '&quot;')
        opp_rows += f"""<tr data-firma="{kontakt_esc}" data-title="{title_esc}">
          <td><strong>{o['title']}</strong>{summ}</td>
          <td>{kontakt_cell}</td>
          <td>{status_badge(o['status'])}</td>
          <td>{o.get('value','') or '<span style="color:#9ca3af">–</span>'}</td>
          <td>{o.get('probability','') or '<span style="color:#9ca3af">–</span>'}</td>
          <td>{o.get('next_action','') or '<span style="color:#9ca3af">–</span>'}</td>
          <td>{deadline_cell(o.get('deadline',''))}</td>
          <td><button class="btn-edit" onclick="event.stopPropagation();editOpp('{oid}')">✏️</button></td>
        </tr>"""
    if not opp_rows:
        opp_rows = '<tr><td colspan="8" style="text-align:center;color:#6b7280">Keine Opportunities</td></tr>'

    generated = datetime.now().strftime("%d.%m.%Y %H:%M")
    contacts_json = json.dumps([{"id": c["id"], "firma": c["firma"], "ansprechpartner": c.get("ansprechpartner",""), "ansprechpartner_list": [p.get("name","") for p in c.get("ansprechpartner_list", []) if p.get("name")]} for c in contacts], ensure_ascii=False)
    tasks_json    = json.dumps([{"taskId": t["taskId"], "title": t["title"], "status": t["status"], "contact": t.get("contact",""), "ansprechpartner": t.get("ansprechpartner","")} for t in tasks], ensure_ascii=False)
    opps_json     = json.dumps([{"id": o["id"], "title": o["title"], "status": o["status"], "kontakt": o.get("kontakt",""), "ansprechpartner": o.get("ansprechpartner","")} for o in opps], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>CRM Dashboard</title>
<style>
:root {{
  --bg:#f8fafc; --surface:#fff; --surface2:#f1f5f9;
  --text:#0f172a; --text2:#64748b; --border:#e2e8f0;
  --accent:#4f46e5; --accent2:#4338ca; --red:#ef4444; --green:#22c55e;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}}
.header{{background:var(--surface);border-bottom:1px solid var(--border);padding:.9rem 1.5rem;display:flex;align-items:center;justify-content:space-between}}
.header h1{{font-size:1.15rem;font-weight:700;color:var(--accent2)}}
.header-meta{{font-size:.75rem;color:var(--text2)}}
.header-meta a{{color:var(--accent);text-decoration:none}}
.tabs{{display:flex;background:var(--surface);border-bottom:1px solid var(--border);padding:0 1.5rem;overflow-x:auto}}
.tab{{padding:.7rem 1.2rem;cursor:pointer;font-size:.875rem;color:var(--text2);border-bottom:2px solid transparent;white-space:nowrap;transition:all .15s}}
.tab:hover{{color:var(--text)}}
.tab.active{{color:var(--accent2);border-bottom-color:var(--accent2)}}
.alerts{{padding:0 1.5rem;margin-top:1rem;display:flex;flex-direction:column;gap:.5rem}}
.alert{{padding:.7rem 1rem;border-radius:8px;font-size:.85rem}}
.alert-red{{background:#fef2f2;border:1px solid #fca5a5;color:#991b1b}}
.alert-yellow{{background:#fffbeb;border:1px solid #fcd34d;color:#92400e}}
.alert ul{{margin-left:1.25rem;margin-top:.2rem}}
.panels{{padding:1rem 1.5rem 2rem}}
.panel{{display:none}}.panel.active{{display:block}}
.panel-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem;margin-bottom:1rem}}
.panel-header h2{{font-size:1.05rem;font-weight:700}}
.kpi-row{{display:flex;gap:.6rem;flex-wrap:wrap}}
.kpi{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:.45rem .9rem;text-align:center;min-width:65px}}
.kpi-val{{display:block;font-size:1.15rem;font-weight:700;color:var(--accent2)}}
.kpi-label{{display:block;font-size:.68rem;color:var(--text2)}}
.toolbar{{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}}
.filter-bar{{display:flex;gap:.5rem;margin-bottom:.75rem;flex-wrap:wrap}}
.search-input,.filter-select{{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:.38rem .7rem;border-radius:6px;font-size:.8rem;outline:none}}
.search-input{{flex:1;min-width:180px}}
.search-input:focus,.filter-select:focus{{border-color:var(--accent)}}
table{{width:100%;border-collapse:collapse;font-size:.84rem}}
thead th{{background:var(--surface2);color:var(--text2);padding:.55rem .7rem;text-align:left;font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;position:sticky;top:0}}
tbody tr{{border-bottom:1px solid var(--border);transition:background .1s}}
tbody tr:hover{{background:var(--surface2)}}
td{{padding:.55rem .7rem;vertical-align:top}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.69rem;font-weight:600;color:#fff;white-space:nowrap}}
.task-id{{font-family:monospace;font-size:.72rem;color:var(--text2);background:var(--surface2);padding:2px 5px;border-radius:4px}}
tr.hidden{{display:none}}
/* ── KONTAKT-LOG DRAWER ── */
#log-drawer{{position:fixed;bottom:0;left:0;right:0;background:var(--surface);border-top:2px solid var(--accent);box-shadow:0 -8px 32px rgba(0,0,0,.18);transform:translateY(100%);transition:transform .25s ease;z-index:50;max-height:55vh;display:flex;flex-direction:column}}
#log-drawer.open{{transform:translateY(0)}}
#log-drawer-header{{display:flex;align-items:center;justify-content:space-between;padding:.7rem 1.25rem;border-bottom:1px solid var(--border);background:var(--surface2);flex-shrink:0}}
#log-drawer-title{{font-weight:700;font-size:.95rem;color:var(--accent2)}}
#log-drawer-close{{background:none;border:none;font-size:1.2rem;cursor:pointer;color:var(--text2);line-height:1;padding:.2rem .4rem;border-radius:4px}}
#log-drawer-close:hover{{background:var(--surface);color:var(--text)}}
#log-entries{{flex:1;overflow-y:auto;padding:.65rem 1.25rem;display:flex;flex-direction:column;gap:.35rem}}
.log-entry{{display:flex;gap:.7rem;align-items:flex-start;padding:.45rem .6rem;border-radius:6px;background:var(--surface2);font-size:.83rem}}
.log-entry:hover{{background:var(--border)}}
.log-date{{color:var(--accent2);font-weight:600;white-space:nowrap;font-size:.77rem;min-width:78px;padding-top:1px}}
.log-text{{color:var(--text);flex:1}}
.log-delete{{background:none;border:none;cursor:pointer;color:var(--text2);font-size:.78rem;padding:0 4px;opacity:.35}}
.log-delete:hover{{opacity:1;color:#ef4444}}
.log-empty{{color:var(--text2);font-size:.82rem;font-style:italic;padding:.4rem 0}}
#log-input-row{{display:flex;gap:.5rem;padding:.65rem 1.25rem;border-top:1px solid var(--border);flex-shrink:0;background:var(--surface);align-items:center}}
#log-date-field{{background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:.42rem .6rem;border-radius:6px;font-size:.84rem;outline:none;font-family:inherit;width:145px;flex-shrink:0}}
#log-date-field:focus{{border-color:var(--accent)}}
#log-text-field{{flex:1;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:.42rem .7rem;border-radius:6px;font-size:.84rem;outline:none;font-family:inherit}}
#log-text-field:focus{{border-color:var(--accent)}}
#log-text-field::placeholder{{color:var(--text2)}}
#c-tbl tbody tr{{cursor:pointer}}
#o-tbl tbody tr{{cursor:pointer}}
#c-tbl tbody tr.log-active,#o-tbl tbody tr.log-active{{background:#eef2ff !important}}
.log-tag{{display:inline-block;padding:1px 7px;border-radius:999px;font-size:.66rem;font-weight:700;white-space:nowrap;flex-shrink:0;margin-top:1px}}
.log-tag-kontakt{{background:#e0e7ff;color:#4338ca}}
.log-tag-pipeline{{background:#dcfce7;color:#15803d}}
.btn-edit{{background:none;border:none;cursor:pointer;font-size:.95rem;opacity:.5;transition:opacity .15s;padding:2px 4px;border-radius:4px}}
.btn-edit:hover{{opacity:1;background:var(--surface2)}}
.btn{{display:inline-flex;align-items:center;gap:.3rem;padding:.38rem .85rem;border-radius:6px;font-size:.8rem;font-weight:600;cursor:pointer;border:none;transition:all .15s}}
.btn-primary{{background:var(--accent);color:#fff}}
.btn-primary:hover{{background:var(--accent2)}}
.btn-ghost{{background:var(--surface2);color:var(--text2);border:1px solid var(--border)}}
.btn-ghost:hover{{color:var(--text)}}
.btn-danger{{background:#fef2f2;color:#991b1b;border:1px solid #fca5a5}}
.btn-danger:hover{{background:#fee2e2}}
.status-pill{{padding:4px 12px;border-radius:999px;border:1.5px solid var(--border);background:var(--surface2);color:var(--text2);font-size:.8rem;cursor:pointer;transition:all .15s}}
.status-pill:hover{{border-color:var(--accent);color:var(--accent)}}
.status-pill.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.firma-group-header{{background:var(--surface2);cursor:pointer;user-select:none}}
.firma-group-header:hover{{background:var(--border)}}
.firma-sub-row td:first-child{{padding-left:2rem;color:var(--text2)}}
/* MODAL */
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:200;align-items:center;justify-content:center}}
.modal-overlay.open{{display:flex}}
.modal{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem;width:500px;max-width:96vw;max-height:90vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.12)}}
.modal h3{{font-size:1rem;font-weight:700;margin-bottom:1.1rem;color:var(--accent2)}}
.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:.6rem .8rem}}
.form-grid .full{{grid-column:1/-1}}
.form-row{{margin-bottom:.6rem}}
.form-row label{{display:block;font-size:.72rem;font-weight:600;color:var(--text2);margin-bottom:.2rem;text-transform:uppercase;letter-spacing:.04em}}
.form-row input,.form-row select,.form-row textarea{{width:100%;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:.42rem .65rem;border-radius:6px;font-size:.84rem;outline:none;font-family:inherit}}
.form-row input:focus,.form-row select:focus,.form-row textarea:focus{{border-color:var(--accent)}}
.form-row textarea{{resize:vertical;min-height:60px}}
.modal-footer{{display:flex;gap:.5rem;justify-content:space-between;margin-top:1.2rem;align-items:center}}
.modal-footer-right{{display:flex;gap:.5rem}}
.save-status{{font-size:.78rem;color:var(--green);display:none}}
.save-error{{font-size:.78rem;color:var(--red);display:none}}
/* CONTACT LINKS */
.contact-link{{color:var(--accent);text-decoration:none;font-weight:500}}
.contact-link:hover{{text-decoration:underline}}
/* RELATED ITEMS */
.related-section{{margin-top:1rem;border-top:1px solid var(--border);padding-top:.9rem}}
.related-section h4{{font-size:.75rem;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:.5rem}}
.related-list{{display:flex;flex-direction:column;gap:.3rem}}
.related-item{{display:flex;align-items:center;justify-content:space-between;padding:.3rem .6rem;background:var(--surface2);border-radius:6px;font-size:.8rem;cursor:pointer;transition:background .1s}}
.related-item:hover{{background:var(--border)}}
.related-item-title{{font-weight:500}}
.related-empty{{font-size:.78rem;color:var(--text2);font-style:italic}}
/* SCHNELL-IMPORT */
.parse-section{{margin-top:1rem;border:1px solid var(--border);border-radius:8px;overflow:hidden}}
.parse-header{{display:flex;justify-content:space-between;align-items:center;padding:.55rem .8rem;
  background:var(--surface2);cursor:pointer;font-size:.8rem;font-weight:600;color:var(--text2);
  user-select:none;transition:background .15s}}
.parse-header:hover{{background:var(--border)}}
#parse-body{{padding:.75rem;border-top:1px solid var(--border)}}
#c-paste{{width:100%;min-height:90px;resize:vertical;background:var(--surface2);
  border:1px solid var(--border);border-radius:6px;padding:.5rem .65rem;
  font-size:.8rem;font-family:inherit;color:var(--text);outline:none;line-height:1.5}}
#c-paste:focus{{border-color:var(--accent)}}
</style>
</head>
<body>

<div class="header">
  <h1>⚡ CRM Dashboard – digitalkonzepte.biz</h1>
  <div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap">
    <span class="header-meta">Stand: {generated} · <a href="javascript:location.reload()">Aktualisieren</a></span>
    <div style="display:flex;gap:.4rem">
      <button class="btn btn-ghost" style="font-size:.75rem;padding:.3rem .7rem" onclick="serverAction('restart')" title="Server neu starten">↺ Restart</button>
      <button class="btn btn-ghost" style="font-size:.75rem;padding:.3rem .7rem" onclick="window.open('http://localhost:8765','_blank')" title="In neuem Tab öffnen">⧉ Open</button>
      <button class="btn btn-danger" style="font-size:.75rem;padding:.3rem .7rem" onclick="serverAction('shutdown')" title="Server stoppen">⏹ Stop</button>
    </div>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showPanel('tasks',this)">📋 Aufgaben ({len(active_tasks)})</div>
  <div class="tab" onclick="showPanel('contacts',this)">👥 Kontakte ({len(contacts)})</div>
  <div class="tab" onclick="showPanel('pipeline',this)">📈 Pipeline ({len(opps)})</div>
</div>

<div class="alerts">{alert_html}</div>

<div class="panels">

<!-- ══ AUFGABEN ══════════════════════════════════════════════════════ -->
<div id="view-tasks" class="panel active">
  <div class="panel-header">
    <h2>📋 Aufgaben</h2>
    <div class="toolbar">
      <div class="kpi-row">
        <div class="kpi"><span class="kpi-val">{len(active_tasks)}</span><span class="kpi-label">Offen</span></div>
        <div class="kpi"><span class="kpi-val">{done_count}</span><span class="kpi-label">Erledigt</span></div>
        <div class="kpi"><span class="kpi-val">{len(tasks)}</span><span class="kpi-label">Gesamt</span></div>
      </div>
      <button class="btn btn-primary" onclick="newTask()">＋ Aufgabe</button>
    </div>
  </div>
  <div class="filter-bar">
    <input class="search-input" placeholder="Suchen..." oninput="filterTable('t-tbl',this.value)">
    <select class="filter-select" onchange="filterByCol('t-tbl',4,this.value)">
      <option value="">Alle Status</option>
      <option>Offen</option><option>In Bearbeitung</option><option>Blockiert</option><option>Verschoben</option>
    </select>
    <select class="filter-select" onchange="filterByCol('t-tbl',3,this.value)">
      <option value="">Alle Prioritäten</option>
      <option>Kritisch</option><option>Hoch</option><option>Mittel</option><option>Niedrig</option>
    </select>
  </div>
  <table id="t-tbl">
    <thead><tr><th>ID</th><th>Aufgabe</th><th>Kontakt</th><th>Prio</th><th>Status</th><th>Deadline</th><th></th></tr></thead>
    <tbody>{task_rows}</tbody>
  </table>
</div>

<!-- ══ KONTAKTE ══════════════════════════════════════════════════════ -->
<div id="view-contacts" class="panel">
  <div class="panel-header">
    <h2>👥 Kontakte & Leads</h2>
    <div class="toolbar">
      <div class="kpi-row">
        <div class="kpi"><span class="kpi-val">{len(contacts)}</span><span class="kpi-label">Gesamt</span></div>
        <div class="kpi"><span class="kpi-val">{leads_n}</span><span class="kpi-label">Leads</span></div>
        <div class="kpi"><span class="kpi-val">{kunden_n}</span><span class="kpi-label">Kunden</span></div>
      </div>
      <button class="btn btn-primary" onclick="newContact()">＋ Kontakt</button>
    </div>
  </div>
  <div class="filter-bar">
    <input class="search-input" placeholder="Suchen..." oninput="filterTable('c-tbl',this.value)">
    <select class="filter-select" onchange="filterByCol('c-tbl',1,this.value)">
      <option value="">Alle Status</option>
      <option>lead</option><option>interessent</option><option>kunde</option><option>netzwerk</option><option>partner</option><option>dienstleister</option><option>aktiv</option><option>inaktiv</option>
    </select>
  </div>
  <div style="overflow-y:auto;max-height:60vh;border:1px solid var(--border);border-radius:8px">
  <table id="c-tbl">
    <thead><tr><th>Firma / Person</th><th>Status</th><th>Branche</th><th>Letzter Kontakt</th><th>Quelle</th><th></th></tr></thead>
    <tbody>{contact_rows}</tbody>
  </table>
  </div>
</div>

<!-- ══ PIPELINE ══════════════════════════════════════════════════════ -->
<div id="view-pipeline" class="panel">
  <div class="panel-header">
    <h2>📈 Vertrieb & Pipeline</h2>
    <div class="toolbar">
      <div class="kpi-row">
        <div class="kpi"><span class="kpi-val">{len(opps)}</span><span class="kpi-label">Opportunities</span></div>
        <div class="kpi"><span class="kpi-val">{aktiv_n}</span><span class="kpi-label">Aktiv</span></div>
        <div class="kpi"><span class="kpi-val">{value_display}</span><span class="kpi-label">Pipeline</span></div>
      </div>
      <button class="btn btn-primary" onclick="newOpp()">＋ Opportunity</button>
    </div>
  </div>
  <div class="filter-bar">
    <input class="search-input" placeholder="Suchen..." oninput="filterTable('o-tbl',this.value)">
    <select class="filter-select" onchange="filterByCol('o-tbl',2,this.value)">
      <option value="">Alle Status</option>
      <option>aktiv</option><option>kunde</option><option>won</option><option>lost</option>
    </select>
  </div>
  <table id="o-tbl">
    <thead><tr><th>Opportunity</th><th>Kontakt</th><th>Status</th><th>Wert</th><th>WSK</th><th>Nächste Aktion</th><th>Deadline</th><th></th></tr></thead>
    <tbody>{opp_rows}</tbody>
  </table>
</div>

</div><!-- /panels -->

<!-- Datalist für Kontakt-Autocomplete -->
<datalist id="contact-names">
  {"".join(f'<option value="{c["firma"]}">' for c in contacts)}
</datalist>

<!-- ══ MODAL: AUFGABE ═══════════════════════════════════════════════ -->
<div class="modal-overlay" id="modal-task" onclick="if(event.target===this)closeModal('task')">
<div class="modal">
  <h3 id="task-modal-title">Aufgabe</h3>
  <input type="hidden" id="t-id">
  <div class="form-grid">
    <div class="form-row full"><label>Aufgabe *</label><input id="t-title" placeholder="Angebot erstellen"></div>
    <div class="form-row"><label>Firma</label><input id="t-contact" list="contact-names" placeholder="Firma auswählen..." oninput="updatePersonSelect('t-contact','t-person')"></div>
    <div class="form-row"><label>Ansprechpartner</label><select id="t-person"><option value="">– kein spez. Ansprechpartner –</option></select></div>
    <div class="form-row"><label>Kategorie</label>
      <select id="t-category"><option>Projektmanagement</option><option>Kundenakquise</option><option>Administrativ</option><option>Follow-up</option></select>
    </div>
    <div class="form-row"><label>Priorität</label>
      <select id="t-prio"><option>Mittel</option><option>Kritisch</option><option>Hoch</option><option>Niedrig</option></select>
    </div>
    <div class="form-row"><label>Status</label>
      <select id="t-status"><option>Offen</option><option>In Bearbeitung</option><option>Blockiert</option><option>Erledigt</option><option>Verschoben</option></select>
    </div>
    <div class="form-row"><label>Deadline (YYYY-MM-DD)</label><input id="t-deadline" placeholder="2026-06-30" type="date"></div>
    <div class="form-row"><label>Zugewiesen</label><input id="t-assignee" placeholder="Ronald"></div>
    <div class="form-row full"><label>Notizen</label><textarea id="t-notes" placeholder="Weitere Details..."></textarea></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-danger" id="t-delete-btn" onclick="deleteTask()" style="display:none">🗑 Löschen</button>
    <div class="modal-footer-right">
      <span class="save-status" id="t-ok">✓ Gespeichert</span>
      <span class="save-error" id="t-err">Fehler!</span>
      <button class="btn btn-ghost" onclick="closeModal('task')">Abbrechen</button>
      <button class="btn btn-primary" onclick="saveTask()">Speichern</button>
    </div>
  </div>
</div>
</div>

<!-- ══ MODAL: KONTAKT ════════════════════════════════════════════════ -->
<div class="modal-overlay" id="modal-contact" onclick="if(event.target===this)closeModal('contact')">
<div class="modal">
  <h3 id="contact-modal-title">Kontakt</h3>
  <input type="hidden" id="c-id">
  <div class="form-grid">
    <div class="form-row full"><label>Firma *</label>
      <input id="c-firma" placeholder="Mustermann GmbH" list="contact-names" oninput="prefillFromFirma(this.value)" style="width:100%">
      <small id="c-firma-hint" style="color:var(--accent);margin-top:3px;display:block;min-height:1.2em"></small>
    </div>

    <!-- Bestehende Ansprechpartner (nur im Edit-Modus) -->
    <div id="c-persons-section" class="form-row full" style="display:none">
      <label>Ansprechpartner</label>
      <div id="c-persons-list" style="display:flex;flex-direction:column;gap:6px;margin-top:4px"></div>
      <button type="button" class="btn btn-ghost" style="margin-top:8px;font-size:.78rem" onclick="toggleNewPerson()">＋ Weitere Person hinzufügen</button>
    </div>

    <!-- Neue Person (immer sichtbar bei neuem Kontakt, ausklappbar bei bestehendem) -->
    <div id="c-new-person-section">
      <div class="form-row"><label id="c-name-label">Ansprechpartner</label><input id="c-name" placeholder="Max Mustermann"></div>
      <div class="form-row"><label>E-Mail</label><input id="c-email" type="email" placeholder="max@firma.de"></div>
      <div class="form-row"><label>Telefon</label><input id="c-tel" placeholder="+49 800 123456"></div>
    </div>
    <div class="form-row full"><label>Status</label>
      <div id="c-status-pills" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">
        <button type="button" class="status-pill" data-val="lead" onclick="togglePill(this)">Lead</button>
        <button type="button" class="status-pill" data-val="interessent" onclick="togglePill(this)">Interessent</button>
        <button type="button" class="status-pill" data-val="kunde" onclick="togglePill(this)">Kunde</button>
        <button type="button" class="status-pill" data-val="netzwerk" onclick="togglePill(this)">Netzwerk</button>
        <button type="button" class="status-pill" data-val="partner" onclick="togglePill(this)">Partner</button>
        <button type="button" class="status-pill" data-val="dienstleister" onclick="togglePill(this)">Dienstleister</button>
        <button type="button" class="status-pill" data-val="aktiv" onclick="togglePill(this)">Aktiv</button>
        <button type="button" class="status-pill" data-val="inaktiv" onclick="togglePill(this)">Inaktiv</button>
      </div>
    </div>
    <div class="form-row"><label>Letzter Kontakt</label><input id="c-last" type="date"></div>
    <div class="form-row"><label>Quelle</label><input id="c-source" placeholder="Eigenakquise / Empfehlung"></div>
    <div class="form-row"><label>Branche</label><input id="c-branch" placeholder="Fahrschule, IT, ..."></div>
    <div class="form-row full"><label>Adresse</label><input id="c-address" placeholder="Musterstraße 1, 80333 München"></div>
  </div>

  <!-- ── VERKNÜPFTE ITEMS ── -->
  <div class="related-section" id="c-related" style="display:none">
    <h4>🔗 Verknüpfte Tasks & Opportunities</h4>
    <div id="c-related-tasks" class="related-list"></div>
    <div id="c-related-opps" class="related-list" style="margin-top:.5rem"></div>
  </div>

  <!-- ── SCHNELL-IMPORT ── -->
  <div class="parse-section">
    <div class="parse-header" onclick="toggleParser()">
      <span>⚡ Schnell-Import: Text einfügen & parsen</span>
      <span id="parse-arrow">▸</span>
    </div>
    <div id="parse-body" style="display:none">
      <textarea id="c-paste" placeholder="E-Mail-Signatur, LinkedIn-Profil oder beliebigen Kontakttext hier einfügen...&#10;&#10;Beispiel:&#10;Max Mustermann&#10;Geschäftsführer · Mustermann GmbH&#10;max@mustermann.de&#10;+49 89 123456&#10;www.mustermann.de"></textarea>
      <div style="display:flex;align-items:center;gap:.6rem;margin-top:.5rem">
        <button class="btn btn-primary" onclick="parseContactText()">⚡ Parsen & Felder füllen</button>
        <span id="parse-result" style="font-size:.78rem;color:var(--text2)"></span>
      </div>
    </div>
  </div>

  <div class="modal-footer">
    <div>
      <button class="btn btn-danger" id="c-delete-btn" onclick="archiveContact()" style="display:none">🗄 Archivieren</button>
    </div>
    <div class="modal-footer-right">
      <span class="save-status" id="c-ok">✓ Gespeichert</span>
      <span class="save-error" id="c-err">Fehler!</span>
      <button class="btn btn-ghost" onclick="closeModal('contact')">Abbrechen</button>
      <button class="btn btn-primary" onclick="saveContact()">Speichern</button>
    </div>
  </div>
</div>
</div>

<!-- ══ MODAL: OPPORTUNITY ════════════════════════════════════════════ -->
<div class="modal-overlay" id="modal-opportunity" onclick="if(event.target===this)closeModal('opportunity')">
<div class="modal">
  <h3 id="opp-modal-title">Opportunity</h3>
  <input type="hidden" id="o-id">
  <div class="form-grid">
    <div class="form-row full"><label>Titel *</label><input id="o-title" placeholder="KI-Automatisierung Vertrieb"></div>
    <div class="form-row"><label>Firma *</label><input id="o-contact" list="contact-names" placeholder="Firma auswählen..." oninput="updatePersonSelect('o-contact','o-person')"></div>
    <div class="form-row"><label>Ansprechpartner</label><select id="o-person"><option value="">– kein spez. Ansprechpartner –</option></select></div>
    <div class="form-row"><label>Status</label>
      <select id="o-status"><option>aktiv</option><option>lead</option><option>won</option><option>lost</option><option>inaktiv</option></select>
    </div>
    <div class="form-row"><label>Wert (€)</label><input id="o-value" placeholder="25000"></div>
    <div class="form-row"><label>Wahrscheinlichkeit (%)</label><input id="o-prob" placeholder="50%"></div>
    <div class="form-row"><label>Deadline</label><input id="o-deadline" type="date"></div>
    <div class="form-row full"><label>Nächste Aktion</label><input id="o-action" placeholder="Angebot erstellen"></div>
    <div class="form-row full"><label>Zusammenfassung</label><textarea id="o-summary" placeholder="Kurzbeschreibung der Opportunity..."></textarea></div>
  </div>
  <div class="modal-footer">
    <div>
      <button class="btn btn-danger" id="o-delete-btn" onclick="archiveOpp()" style="display:none">🗄 Archivieren</button>
    </div>
    <div class="modal-footer-right">
      <span class="save-status" id="o-ok">✓ Gespeichert</span>
      <span class="save-error" id="o-err">Fehler!</span>
      <button class="btn btn-ghost" onclick="closeModal('opportunity')">Abbrechen</button>
      <button class="btn btn-primary" onclick="saveOpp()">Speichern</button>
    </div>
  </div>
</div>
</div>

<!-- ══ MODAL: ANSPRECHPARTNER ═══════════════════════════════════════ -->
<div class="modal-overlay" id="modal-person" onclick="if(event.target===this)closeModal('person')">
<div class="modal" style="max-width:420px">
  <h3 id="person-modal-title">👤 Ansprechpartner</h3>
  <input type="hidden" id="p-firma-id">
  <input type="hidden" id="p-index">
  <div class="form-grid">
    <div class="form-row full"><label>Name *</label><input id="p-name" placeholder="Max Mustermann"></div>
    <div class="form-row"><label>Titel</label><input id="p-titel" placeholder="Geschäftsführer"></div>
    <div class="form-row"><label>Abteilung</label><input id="p-abt" placeholder="Vertrieb"></div>
    <div class="form-row"><label>E-Mail</label><input id="p-email" type="email" placeholder="max@firma.de"></div>
    <div class="form-row"><label>Telefon</label><input id="p-tel" placeholder="+49 800 123456"></div>
  </div>
  <div class="modal-footer">
    <div></div>
    <div class="modal-footer-right">
      <span class="save-status" id="p-ok">✓ Gespeichert</span>
      <span class="save-error" id="p-err">Fehler!</span>
      <button class="btn btn-ghost" onclick="closeModal('person')">Abbrechen</button>
      <button class="btn btn-primary" onclick="savePerson()">Speichern</button>
    </div>
  </div>
</div>
</div>

<script>
// ── CRM Data (embedded) ──────────────────────────────────────────────
const CRM_CONTACTS = {contacts_json};
const CRM_TASKS    = {tasks_json};
const CRM_OPPS     = {opps_json};

// ── Contact linking ───────────────────────────────────────────────────
function openContactByName(name) {{
  // Suche Kontakt anhand Firmenname (fuzzy)
  const norm = s => s.toLowerCase().replace(/\s+/g,'');
  const c = CRM_CONTACTS.find(x => norm(x.firma) === norm(name) || norm(x.id) === norm(name));
  if (c) {{
    editContact(c.id);
  }} else {{
    // Nicht gefunden → Kontakte-Tab öffnen und filtern
    const tab = document.querySelectorAll('.tab')[1];
    showPanel('contacts', tab);
    const inp = document.querySelector('#c-tbl').closest('.panel').querySelector('.search-input');
    if (inp) {{ inp.value = name; filterTable('c-tbl', name); }}
  }}
}}

function showRelatedItems(firmaName) {{
  const norm = s => (s||'').toLowerCase().replace(/\s+/g,'');
  const fn = norm(firmaName);

  // Tasks
  const relTasks = CRM_TASKS.filter(t => norm(t.contact) === fn || norm(t.contact).includes(fn));
  const taskDiv = document.getElementById('c-related-tasks');
  if (relTasks.length > 0) {{
    taskDiv.innerHTML = '<div style="font-size:.72rem;color:var(--text2);font-weight:600;margin-bottom:.25rem">AUFGABEN</div>' +
      relTasks.map(t => `<div class="related-item" onclick="closeModal('contact');editTask('${{t.taskId}}')">
        <span class="related-item-title">${{t.title}}</span>
        <span class="badge" style="background:#6b7280;font-size:.65rem">${{t.status}}</span>
      </div>`).join('');
  }} else {{
    taskDiv.innerHTML = '<span class="related-empty">Keine verknüpften Tasks</span>';
  }}

  // Opportunities
  const relOpps = CRM_OPPS.filter(o => norm(o.kontakt) === fn || norm(o.kontakt).includes(fn));
  const oppDiv = document.getElementById('c-related-opps');
  if (relOpps.length > 0) {{
    oppDiv.innerHTML = '<div style="font-size:.72rem;color:var(--text2);font-weight:600;margin-bottom:.25rem">OPPORTUNITIES</div>' +
      relOpps.map(o => `<div class="related-item" onclick="closeModal('contact');editOpp('${{o.id}}')">
        <span class="related-item-title">${{o.title}}</span>
        <span class="badge" style="background:#3b82f6;font-size:.65rem">${{o.status}}</span>
      </div>`).join('');
  }} else {{
    oppDiv.innerHTML = '<span class="related-empty">Keine verknüpften Opportunities</span>';
  }}

  const section = document.getElementById('c-related');
  section.style.display = (relTasks.length + relOpps.length > 0) ? 'block' : 'none';
}}

// ── Server management ────────────────────────────────────────────────
function serverAction(action) {{
  if (action === 'shutdown' && !confirm('Server wirklich stoppen?')) return;
  fetch('/api/server/' + action)
    .then(r => r.json())
    .then(d => {{
      if (action === 'restart') {{
        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#4f46e5;font-size:1.1rem">↺ Server startet neu… <a href="/" style="margin-left:1rem" onclick="setTimeout(()=>location.reload(),2000)">Neu laden</a></div>';
        setTimeout(() => location.reload(), 3000);
      }} else {{
        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;color:#64748b;font-size:1rem">⏹ Server gestoppt. Starte neu mit:<br><code style="margin-top:.5rem;display:block;background:#f1f5f9;padding:.5rem 1rem;border-radius:6px">nohup python3 .../crm_server.py &</code></div>';
      }}
    }})
    .catch(() => alert('Fehler beim Server-Befehl'));
}}

// ── Panel navigation ──────────────────────────────────────────────────
function showPanel(name, tab) {{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('view-'+name).classList.add('active');
  tab.classList.add('active');
  sessionStorage.setItem('crm_active_panel', name);
}}
function reloadKeepPanel() {{
  sessionStorage.setItem('crm_active_panel', _activePanel());
  location.reload();
}}
function _activePanel() {{
  const p = document.querySelector('.panel.active');
  return p ? p.id.replace('view-','') : 'tasks';
}}
(function restorePanel() {{
  const saved = sessionStorage.getItem('crm_active_panel');
  if (saved && saved !== 'tasks') {{
    const panel = document.getElementById('view-'+saved);
    const tab = Array.from(document.querySelectorAll('.tab')).find(t =>
      (t.getAttribute('onclick')||'').includes(saved));
    if (panel && tab) {{
      document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
      document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
      panel.classList.add('active');
      tab.classList.add('active');
    }}
  }}
}})();
function filterTable(id, q) {{
  q = q.toLowerCase();
  document.querySelectorAll('#'+id+' tbody tr').forEach(r=>
    r.classList.toggle('hidden', q.length>0 && !r.textContent.toLowerCase().includes(q)));
}}
function toggleFirmaGroup(gid) {{
  const rows = document.querySelectorAll('[data-group="'+gid+'"]');
  const icon = document.getElementById('fgi-'+gid);
  const hidden = rows.length && rows[0].style.display === 'none';
  rows.forEach(r => r.style.display = hidden ? '' : 'none');
  if (icon) icon.textContent = hidden ? '▼' : '▶';
}}
function updatePersonSelect(firmaInputId, personSelectId) {{
  const firma = (document.getElementById(firmaInputId).value||'').toLowerCase();
  const sel = document.getElementById(personSelectId);
  const current = sel.value;
  sel.innerHTML = '<option value="">– kein spez. Ansprechpartner –</option>';
  const names = [];
  CRM_CONTACTS.filter(c => c.firma && c.firma.toLowerCase() === firma)
    .forEach(c => {{
      (c.ansprechpartner_list && c.ansprechpartner_list.length ? c.ansprechpartner_list : (c.ansprechpartner ? [c.ansprechpartner] : []))
        .forEach(n => {{ if (n && !names.includes(n)) names.push(n); }});
    }});
  names.forEach(n => {{
    const opt = document.createElement('option');
    opt.value = n;
    opt.textContent = n;
    if (n === current) opt.selected = true;
    sel.appendChild(opt);
  }});
}}
function filterByCol(id, col, v) {{
  v = v.toLowerCase();
  document.querySelectorAll('#'+id+' tbody tr').forEach(r=>{{
    const c = r.cells[col]; const t = c ? c.textContent.toLowerCase() : '';
    r.classList.toggle('hidden', v.length>0 && !t.includes(v));
  }});
}}
function closeModal(type) {{
  document.getElementById('modal-'+type).classList.remove('open');
}}
function flash(okId, errId, ok) {{
  const el = document.getElementById(ok ? okId : errId);
  el.style.display='inline';
  setTimeout(()=>el.style.display='none', 2500);
}}

// ── API helpers ───────────────────────────────────────────────────────
async function api(method, path, body) {{
  const r = await fetch(path, {{
    method, headers:{{'Content-Type':'application/json'}},
    body: body ? JSON.stringify(body) : undefined
  }});
  return r.ok ? r.json() : Promise.reject(await r.text());
}}

// ── TASK ──────────────────────────────────────────────────────────────
let _taskData = {{}};
function newTask() {{
  document.getElementById('task-modal-title').textContent='＋ Neue Aufgabe';
  ['t-id','t-title','t-contact','t-notes','t-deadline'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('t-person').innerHTML='<option value="">– kein spez. Ansprechpartner –</option>';
  document.getElementById('t-prio').value='Mittel';
  document.getElementById('t-status').value='Offen';
  document.getElementById('t-category').value='Projektmanagement';
  document.getElementById('t-assignee').value='Ronald';
  document.getElementById('t-delete-btn').style.display='none';
  document.getElementById('modal-task').classList.add('open');
}}
function editTask(id) {{
  api('GET','/api/tasks').then(data=>{{
    const t = data.find(x=>x.taskId===id);
    if(!t) return;
    _taskData = t;
    document.getElementById('task-modal-title').textContent='✏️ Aufgabe: '+t.taskId;
    document.getElementById('t-id').value = t.taskId;
    document.getElementById('t-title').value = t.title||'';
    document.getElementById('t-contact').value = t.contact||'';
    updatePersonSelect('t-contact','t-person');
    setTimeout(()=>{{ document.getElementById('t-person').value = t.ansprechpartner||''; }}, 50);
    document.getElementById('t-category').value = t.category||'Projektmanagement';
    document.getElementById('t-prio').value = t.priority||'Mittel';
    document.getElementById('t-status').value = t.status||'Offen';
    document.getElementById('t-deadline').value = t.deadline||'';
    document.getElementById('t-assignee').value = t.assignedTo||'Ronald';
    document.getElementById('t-notes').value = t.notes||'';
    document.getElementById('t-delete-btn').style.display='inline-flex';
    document.getElementById('modal-task').classList.add('open');
  }});
}}
function saveTask() {{
  const id = document.getElementById('t-id').value;
  const body = {{
    title:      document.getElementById('t-title').value,
    contact:        document.getElementById('t-contact').value,
    ansprechpartner:document.getElementById('t-person').value,
    category:       document.getElementById('t-category').value,
    priority:   document.getElementById('t-prio').value,
    status:     document.getElementById('t-status').value,
    deadline:   document.getElementById('t-deadline').value,
    assignedTo: document.getElementById('t-assignee').value,
    notes:      document.getElementById('t-notes').value,
  }};
  const method = id ? 'PUT' : 'POST';
  const path   = id ? '/api/tasks/'+id : '/api/tasks';
  api(method, path, body)
    .then(()=>{{ flash('t-ok','t-err',true); setTimeout(()=>reloadKeepPanel(),800); }})
    .catch(()=>flash('t-ok','t-err',false));
}}
function deleteTask() {{
  if(!confirm('Aufgabe wirklich löschen?')) return;
  const id = document.getElementById('t-id').value;
  api('DELETE','/api/tasks/'+id)
    .then(()=>{{ closeModal('task'); reloadKeepPanel(); }})
    .catch(()=>flash('t-ok','t-err',false));
}}

// ── CONTACT PARSER (raw JS – kein Python f-string escaping) ──────────
{PARSE_JS}

// ── CONTACT ───────────────────────────────────────────────────────────
function prefillFromFirma(val) {{
  const firma = (val||'').toLowerCase().trim();
  if (!firma) return;
  // Nur beim Neu-Anlegen (kein c-id gesetzt)
  if (document.getElementById('c-id').value) return;
  const existing = CRM_CONTACTS.filter(c => c.firma && c.firma.toLowerCase() === firma);
  if (!existing.length) return;
  const ref = existing[0];
  // Firmendaten übernehmen, Personendaten leer lassen
  if (ref.branch)  document.getElementById('c-branch').value = ref.branch;
  if (ref.source)  document.getElementById('c-source').value = ref.source;
  if (ref.status)  _setStatusBoxes(ref.status);
  // Hinweis
  const hint = document.getElementById('c-firma-hint');
  if (hint) hint.textContent = existing.length === 1
    ? '✓ Firma bekannt – Branche & Quelle vorausgefüllt'
    : existing.length + ' Personen bekannt – Firmendaten übernommen';
}}
function togglePill(el) {{
  el.classList.toggle('active');
}}
function _setStatusBoxes(val) {{
  const vals = (val||'').split(',').map(s=>s.trim().toLowerCase());
  document.querySelectorAll('#c-status-pills .status-pill').forEach(p => {{
    p.classList.toggle('active', vals.includes(p.dataset.val));
  }});
}}
function _getStatusBoxes() {{
  return Array.from(document.querySelectorAll('#c-status-pills .status-pill.active')).map(p=>p.dataset.val).join(',');
}}
function newContact() {{
  document.getElementById('contact-modal-title').textContent='＋ Neuer Kontakt';
  ['c-id','c-firma','c-name','c-email','c-tel','c-last','c-source','c-branch','c-address'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('c-firma-hint').textContent='';
  document.getElementById('c-firma').disabled = false;
  document.getElementById('c-persons-section').style.display='none';
  document.getElementById('c-new-person-section').style.display='';
  document.getElementById('c-name-label').textContent='Ansprechpartner';
  _setStatusBoxes('lead');
  document.getElementById('c-delete-btn').style.display='none';
  document.getElementById('modal-contact').classList.add('open');
}}
function editContact(id) {{
  api('GET','/api/contacts').then(data=>{{
    const c = data.find(x=>x.id===id);
    if(!c) return;
    document.getElementById('contact-modal-title').textContent='✏️ '+c.firma;
    document.getElementById('c-id').value = c.id;
    document.getElementById('c-firma').value = c.firma||'';
    document.getElementById('c-firma').disabled = true;
    document.getElementById('c-email').value='';
    document.getElementById('c-tel').value='';
    _setStatusBoxes(c.status||'lead');
    document.getElementById('c-last').value = c.last_contact||'';
    document.getElementById('c-source').value = c.source||'';
    document.getElementById('c-branch').value = c.branch||'';
    document.getElementById('c-address').value = c.address||'';
    document.getElementById('c-delete-btn').style.display='inline-flex';

    // Ansprechpartner-Liste anzeigen
    const persons = c.ansprechpartner_list || [];
    const listEl = document.getElementById('c-persons-list');
    if (persons.length > 0) {{
      listEl.innerHTML = persons.map(p =>
        `<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--surface2);border-radius:6px;font-size:.82rem">
          <span>👤 <strong>${{p.name}}</strong>${{p.email ? ' · ' + p.email : ''}}${{p.phone ? ' · ' + p.phone : ''}}</span>
          <button class="btn-edit" style="margin-left:auto" onclick="closeModal('contact');editPerson('${{c.id}}','${{p.id}}')">✏️</button>
        </div>`
      ).join('');
      document.getElementById('c-persons-section').style.display='';
      // Neue-Person-Felder ausblenden (aufklappbar)
      document.getElementById('c-new-person-section').style.display='none';
      document.getElementById('c-name').value='';
    }} else {{
      document.getElementById('c-persons-section').style.display='none';
      document.getElementById('c-new-person-section').style.display='';
      document.getElementById('c-name-label').textContent='Ansprechpartner';
    }}

    document.getElementById('modal-contact').classList.add('open');
    showRelatedItems(c.firma);
  }});
}}
function toggleNewPerson() {{
  const s = document.getElementById('c-new-person-section');
  const visible = s.style.display !== 'none';
  s.style.display = visible ? 'none' : '';
  if (!visible) document.getElementById('c-name-label').textContent='＋ Neue Person';
}}
function archiveContact() {{
  if(!confirm('Kontakt archivieren? Er wird ausgeblendet, bleibt aber als Datei erhalten.')) return;
  const id = document.getElementById('c-id').value;
  api('DELETE','/api/contacts/'+encodeURIComponent(id))
    .then(()=>{{ closeModal('contact'); reloadKeepPanel(); }})
    .catch(()=>flash('c-ok','c-err',false));
}}
function saveContact() {{
  const id   = document.getElementById('c-id').value;
  const name = document.getElementById('c-name').value.trim();

  if (id) {{
    // Edit-Modus: nur Firmendaten + ggf. neue Person
    const firmBody = {{
      status:       _getStatusBoxes(),
      last_contact: document.getElementById('c-last').value,
      next_action:  '',
      source:       document.getElementById('c-source').value,
      branch:       document.getElementById('c-branch').value,
      address:      document.getElementById('c-address').value,
    }};
    api('PUT', '/api/contacts/'+encodeURIComponent(id), firmBody)
      .then(() => {{
        if (name) {{
          // Neue Person zur bestehenden Firma hinzufügen
          const personBody = {{
            firma: document.getElementById('c-firma').value,
            ansprechpartner: name,
            email: document.getElementById('c-email').value,
            phone: document.getElementById('c-tel').value,
            status: _getStatusBoxes(),
            source: document.getElementById('c-source').value,
          }};
          return api('POST', '/api/contacts', personBody);
        }}
      }})
      .then(()=>{{ flash('c-ok','c-err',true); setTimeout(()=>reloadKeepPanel(),800); }})
      .catch(()=>flash('c-ok','c-err',false));
  }} else {{
    // Neu-Modus: Firma + Person anlegen
    const body = {{
      firma:           document.getElementById('c-firma').value,
      ansprechpartner: name,
      email:           document.getElementById('c-email').value,
      phone:           document.getElementById('c-tel').value,
      status:          _getStatusBoxes(),
      last_contact:    document.getElementById('c-last').value,
      source:          document.getElementById('c-source').value,
      branch:          document.getElementById('c-branch').value,
      address:         document.getElementById('c-address').value,
    }};
    api('POST', '/api/contacts', body)
      .then(()=>{{ flash('c-ok','c-err',true); setTimeout(()=>reloadKeepPanel(),800); }})
      .catch(()=>flash('c-ok','c-err',false));
  }}
}}

// ── OPPORTUNITY ───────────────────────────────────────────────────────
function newOpp() {{
  document.getElementById('opp-modal-title').textContent='＋ Neue Opportunity';
  ['o-id','o-title','o-contact','o-value','o-prob','o-deadline','o-action','o-summary'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('o-person').innerHTML='<option value="">– kein spez. Ansprechpartner –</option>';
  document.getElementById('o-status').value='aktiv';
  document.getElementById('o-delete-btn').style.display='none';
  document.getElementById('modal-opportunity').classList.add('open');
}}
function editOpp(id) {{
  api('GET','/api/opportunities').then(data=>{{
    const o = data.find(x=>x.id===id);
    if(!o) return;
    document.getElementById('opp-modal-title').textContent='✏️ '+o.title;
    document.getElementById('o-id').value = o.id;
    document.getElementById('o-title').value = o.title||'';
    document.getElementById('o-contact').value = o.kontakt||'';
    updatePersonSelect('o-contact','o-person');
    setTimeout(()=>{{ document.getElementById('o-person').value = o.ansprechpartner||''; }}, 50);
    document.getElementById('o-status').value = o.status||'aktiv';
    document.getElementById('o-value').value = o.value||'';
    document.getElementById('o-prob').value = o.probability||'';
    document.getElementById('o-deadline').value = o.deadline||'';
    document.getElementById('o-action').value = o.next_action||'';
    document.getElementById('o-summary').value = o.summary||'';
    document.getElementById('o-delete-btn').style.display='inline-flex';
    document.getElementById('modal-opportunity').classList.add('open');
  }});
}}
// ── ANSPRECHPARTNER ───────────────────────────────────────────────────
function editPerson(firmaId, personId) {{
  api('GET', '/api/contacts').then(data => {{
    const c = data.find(x => x.id === firmaId);
    if (!c) return;
    const persons = c.ansprechpartner_list || [];
    const p = persons.find(x => x.id === personId) || persons[0];
    if (!p) return;
    document.getElementById('person-modal-title').textContent = '👤 ' + (p.name || 'Ansprechpartner');
    document.getElementById('p-firma-id').value = firmaId;
    document.getElementById('p-index').value    = personId;
    document.getElementById('p-name').value  = p.name  || '';
    document.getElementById('p-titel').value = p.titel || '';
    document.getElementById('p-abt').value   = p.abteilung || '';
    document.getElementById('p-email').value = p.email || '';
    document.getElementById('p-tel').value   = p.phone || '';
    document.getElementById('modal-person').classList.add('open');
  }});
}}
function savePerson() {{
  const firmaId  = document.getElementById('p-firma-id').value;
  const personId = document.getElementById('p-index').value;
  const body = {{
    name:      document.getElementById('p-name').value,
    titel:     document.getElementById('p-titel').value,
    abteilung: document.getElementById('p-abt').value,
    email:     document.getElementById('p-email').value,
    phone:     document.getElementById('p-tel').value,
  }};
  api('PUT', '/api/contacts/' + encodeURIComponent(firmaId) + '/persons/' + encodeURIComponent(personId), body)
    .then(() => {{ flash('p-ok','p-err',true); setTimeout(() => reloadKeepPanel(), 800); }})
    .catch(() => flash('p-ok','p-err',false));
}}

function archiveOpp() {{
  if(!confirm('Opportunity archivieren? Sie bleibt als Datei erhalten.')) return;
  const id = document.getElementById('o-id').value;
  api('DELETE','/api/opportunities/'+encodeURIComponent(id))
    .then(()=>{{ closeModal('opportunity'); reloadKeepPanel(); }})
    .catch(()=>flash('o-ok','o-err',false));
}}
function saveOpp() {{
  const id = document.getElementById('o-id').value;
  const body = {{
    title:       document.getElementById('o-title').value,
    kontakt:         document.getElementById('o-contact').value,
    ansprechpartner: document.getElementById('o-person').value,
    status:          document.getElementById('o-status').value,
    value:       document.getElementById('o-value').value,
    probability: document.getElementById('o-prob').value,
    deadline:    document.getElementById('o-deadline').value,
    next_action: document.getElementById('o-action').value,
    summary:     document.getElementById('o-summary').value,
  }};
  const method = id ? 'PUT' : 'POST';
  const path   = id ? '/api/opportunities/'+encodeURIComponent(id) : '/api/opportunities';
  api(method, path, body)
    .then(()=>{{ flash('o-ok','o-err',true); setTimeout(()=>reloadKeepPanel(),800); }})
    .catch(()=>flash('o-ok','o-err',false));
}}

/* ── KONTAKT-LOG JS ── */
let _logKey = null;
let _logContext = null;       // Kombinierter Kontext-Schlüssel: firma|source|pipelineName
let _logSource = 'kontakt';   // Quelle des zuletzt geöffneten Kontexts: 'kontakt' oder 'pipeline'
let _logPipelineName = '';    // Name der Pipeline (Opportunity), falls source==='pipeline'
const _LOG_SOURCE_LABELS = {{ kontakt: '👤 Kontakt', pipeline: '📈 Pipeline' }};
function _lsKey(firma){{ return 'crm_log_' + firma.trim().toLowerCase().replace(/\s+/g,'_'); }}
function _loadLog(firma){{ try{{ return JSON.parse(localStorage.getItem(_lsKey(firma))||'[]'); }}catch(e){{ return []; }} }}
function _saveLog(firma,entries){{ localStorage.setItem(_lsKey(firma),JSON.stringify(entries)); }}
function _fmtDate(iso){{
  const d = new Date(iso.length===10 ? iso+'T12:00:00' : iso);
  return d.toLocaleDateString('de-DE',{{day:'2-digit',month:'2-digit',year:'numeric'}});
}}
function _escH(s){{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function _escA(s){{ return s.replace(/'/g,"\\'"); }}
function _todayISO(){{ return new Date().toISOString().slice(0,10); }}

function renderLogEntries(firma){{
  const entries = _loadLog(firma);
  const el = document.getElementById('log-entries');
  if(!entries.length){{ el.innerHTML='<div class="log-empty">Noch keine Aktivitäten eingetragen.</div>'; return; }}
  el.innerHTML = [...entries].reverse().map((e,ri)=>{{
    const realIdx = entries.length-1-ri;
    const src = e.source === 'pipeline' ? 'pipeline' : 'kontakt'; // Altbestand ohne source → Kontakt
    let label = _LOG_SOURCE_LABELS[src];
    if(src === 'pipeline' && e.pipelineName){{ label += ' · ' + _escH(e.pipelineName); }}
    const tag = `<span class="log-tag log-tag-${{src}}">${{label}}</span>`;
    return `<div class="log-entry">
      <span class="log-date">${{_fmtDate(e.date)}}</span>
      ${{tag}}
      <span class="log-text">${{_escH(e.text)}}</span>
      <button class="log-delete" onclick="deleteLogEntry('${{_escA(firma)}}', ${{realIdx}})" title="Löschen">✕</button>
    </div>`;
  }}).join('');
}}

function openLogDrawer(firma, source, pipelineName){{
  _logKey = firma;
  _logSource = source === 'pipeline' ? 'pipeline' : 'kontakt';
  _logPipelineName = _logSource === 'pipeline' ? (pipelineName || '') : '';
  _logContext = firma + '|' + _logSource + '|' + _logPipelineName;
  document.getElementById('log-drawer-title').textContent = '📋 Log · ' + firma
    + (_logPipelineName ? ' — Pipeline: ' + _logPipelineName : '');
  renderLogEntries(firma);
  document.getElementById('log-drawer').classList.add('open');
  const df = document.getElementById('log-date-field');
  if(!df.value) df.value = _todayISO();
  document.getElementById('log-text-field').focus();
  document.querySelectorAll('#c-tbl tbody tr, #o-tbl tbody tr').forEach(r=>{{
    r.classList.toggle('log-active', r.dataset.firma===firma);
  }});
}}

function closeLogDrawer(){{
  document.getElementById('log-drawer').classList.remove('open');
  document.querySelectorAll('#c-tbl tbody tr, #o-tbl tbody tr').forEach(r=>r.classList.remove('log-active'));
  _logKey = null;
  _logContext = null;
}}

function addLogEntry(){{
  if(!_logKey) return;
  const tf = document.getElementById('log-text-field');
  const df = document.getElementById('log-date-field');
  const text = tf.value.trim();
  const date = df.value || _todayISO();
  if(!text){{ tf.focus(); return; }}
  const entries = _loadLog(_logKey);
  const entry = {{date, text, source: _logSource}};
  if(_logSource === 'pipeline' && _logPipelineName) entry.pipelineName = _logPipelineName;
  entries.push(entry);
  _saveLog(_logKey, entries);
  tf.value = '';
  renderLogEntries(_logKey);
  tf.focus();
}}

function deleteLogEntry(firma, idx){{
  if(!confirm('Eintrag löschen?')) return;
  const entries = _loadLog(firma);
  entries.splice(idx,1);
  _saveLog(firma, entries);
  renderLogEntries(firma);
}}

document.addEventListener('DOMContentLoaded', ()=>{{
  function wireLogRows(selector, source){{
    document.querySelectorAll(selector).forEach(row=>{{
      row.addEventListener('click', function(e){{
        if(e.target.tagName==='A'||e.target.tagName==='BUTTON') return;
        const firma = this.dataset.firma;
        if(!firma) return;
        const pipelineName = source === 'pipeline' ? (this.dataset.title || '') : '';
        const context = firma + '|' + source + '|' + pipelineName;
        if(_logContext===context && document.getElementById('log-drawer').classList.contains('open')){{
          closeLogDrawer();
        }} else {{
          openLogDrawer(firma, source, pipelineName);
        }}
      }});
    }});
  }}
  wireLogRows('#c-tbl tbody tr', 'kontakt');
  wireLogRows('#o-tbl tbody tr', 'pipeline');
  document.addEventListener('keydown', e=>{{ if(e.key==='Escape') closeLogDrawer(); }});
}});
</script>

<!-- ── KONTAKT-LOG DRAWER HTML ── -->
<div id="log-drawer">
  <div id="log-drawer-header">
    <span id="log-drawer-title">📋 Aktivitäten-Log</span>
    <button id="log-drawer-close" onclick="closeLogDrawer()" title="Schließen">✕</button>
  </div>
  <div id="log-entries"></div>
  <div id="log-input-row">
    <input id="log-date-field" type="date">
    <input id="log-text-field" type="text" placeholder="Aktivität beschreiben (z.B. Anruf – Termin vereinbart)…" onkeydown="if(event.key==='Enter')addLogEntry()">
    <button class="btn btn-primary" onclick="addLogEntry()">＋ Eintrag</button>
  </div>
</div>
</body></html>"""


# ──────────────────────────────────────────────────────────────────────────────
# REQUEST HANDLER
# ──────────────────────────────────────────────────────────────────────────────

class CRMHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path in ("", "/"):
            self.send_html(build_dashboard())
        elif path == "/api/tasks":
            self.send_json(load_tasks())
        elif path == "/api/contacts":
            self.send_json(load_contacts())
        elif path == "/api/opportunities":
            self.send_json(load_opportunities())
        elif path == "/api/server/restart":
            self.send_json({"ok": True, "action": "restart"})
            import threading, os, sys
            def _restart():
                import time; time.sleep(0.5)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            threading.Thread(target=_restart, daemon=True).start()
        elif path == "/api/server/shutdown":
            self.send_json({"ok": True, "action": "shutdown"})
            import threading
            def _stop():
                import time; time.sleep(0.5)
                self.server.shutdown()
            threading.Thread(target=_stop, daemon=True).start()
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        body = self.read_body()
        try:
            if path == "/api/tasks":
                self._create_task(body)
            elif path == "/api/contacts":
                self._create_contact(body)
            elif path == "/api/opportunities":
                self._create_opp(body)
            else:
                self.send_response(404); self.end_headers(); return
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_PUT(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        body = self.read_body()
        try:
            if parts[0] == "api" and parts[1] == "tasks" and len(parts) == 3:
                self._update_task(parts[2], body)
            elif parts[0] == "api" and parts[1] == "contacts" and len(parts) == 3:
                self._update_contact(unquote(parts[2]), body)
            elif parts[0] == "api" and parts[1] == "contacts" and len(parts) == 5 and parts[3] == "persons":
                # PUT /api/contacts/{firma}/persons/{person_id}
                self._update_person(unquote(parts[2]), unquote(parts[4]), body)
            elif parts[0] == "api" and parts[1] == "opportunities" and len(parts) == 3:
                self._update_opp(unquote(parts[2]), body)
            else:
                self.send_response(404); self.end_headers(); return
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def do_DELETE(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        try:
            if parts[0] == "api" and parts[1] == "tasks" and len(parts) == 3:
                tasks = load_tasks()
                tasks = [t for t in tasks if t["taskId"] != parts[2]]
                save_tasks(tasks)
            elif parts[0] == "api" and parts[1] == "contacts" and len(parts) == 3:
                contact_id = unquote(parts[2])
                filepath = FIRMEN_DIR / (self._safe(contact_id) + ".md")
                if not filepath.exists():
                    self.send_json({"error": "Nicht gefunden"}, 404); return
                archive_dir = FIRMEN_DIR / "_Archiv"
                archive_dir.mkdir(exist_ok=True)
                filepath.rename(archive_dir / filepath.name)
            elif parts[0] == "api" and parts[1] == "opportunities" and len(parts) == 3:
                opp_id = unquote(parts[2])
                filepath = OPPS_DIR / (opp_id + ".md")
                if not filepath.exists():
                    self.send_json({"error": "Nicht gefunden"}, 404); return
                archive_dir = OPPS_DIR / "_Archiv"
                archive_dir.mkdir(exist_ok=True)
                filepath.rename(archive_dir / filepath.name)
            else:
                self.send_response(404); self.end_headers(); return
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    # ── TASK CRUD ──
    def _create_task(self, body):
        tasks = load_tasks()
        existing = [t["taskId"] for t in tasks if re.match(r"PROJ-\d+", t["taskId"])]
        nums = [int(re.search(r"\d+", i).group()) for i in existing] if existing else [0]
        new_id = f"PROJ-{str(max(nums)+1).zfill(3)}"
        dl = body.get("deadline","")
        tasks.append({
            "taskId": new_id,
            "title": body.get("title",""),
            "description": body.get("notes","") or body.get("title",""),
            "category": body.get("category","Projektmanagement"),
            "contact": body.get("contact",""),
            "ansprechpartner": body.get("ansprechpartner",""),
            "priority": body.get("priority","Mittel"),
            "status": body.get("status","Offen"),
            "deadline": dl,
            "createdAt": NOW(), "updatedAt": NOW(), "completedAt": None,
            "assignedTo": body.get("assignedTo","Ronald"),
            "notes": body.get("notes",""),
            "tags": [], "dependencies": {"blockedBy":[],"blocks":[]}
        })
        save_tasks(tasks)

    def _update_task(self, task_id, body):
        tasks = load_tasks()
        for t in tasks:
            if t["taskId"] == task_id:
                for k in ("title","contact","ansprechpartner","category","priority","status","deadline","assignedTo","notes"):
                    if k in body:
                        t[k] = body[k]
                t["updatedAt"] = NOW()
                if body.get("status") == "Erledigt" and not t.get("completedAt"):
                    t["completedAt"] = NOW()
                break
        save_tasks(tasks)

    # ── CONTACT CRUD ──
    def _safe(self, s):
        return re.sub(r'[\\/*?:"<>|]', "", s).strip()

    def _create_contact(self, body):
        firma = body.get("firma", "Unbekannt").strip()
        name  = body.get("ansprechpartner", "").strip()
        FIRMEN_DIR.mkdir(parents=True, exist_ok=True)
        PERS_DIR.mkdir(parents=True, exist_ok=True)

        firma_file = FIRMEN_DIR / (self._safe(firma) + ".md")

        # ── Firma anlegen falls neu ──
        if not firma_file.exists():
            firma_content = f"""---
type: firma
status: {body.get('status','lead')}
last_contact: {body.get('last_contact', TODAY)}
next_action: {body.get('next_action','Erstgespräch planen')}
source: {body.get('source','')}
branch: {body.get('branch','')}
address: {body.get('address','')}
dsgvo_consent: nein
dsgvo_added: nein
---

# {firma}

## Grunddaten
- **Firma:** {firma}
- **Branche:** {body.get('branch','')}
- **Adresse:** {body.get('address','')}
- **Website:**
- **Größe:**

## Ansprechpartner
{('- [[' + name + ']]') if name else '-'}

## Beziehung
- **Quelle:** {body.get('source','')}
- **Erstkontakt:** {TODAY}
- **Qualifizierungsstufe:** 1

## Opportunities
-

## Letzte Aktivitäten
- Firma angelegt {TODAY}

## Notizen
-

## DSGVO-Compliance
- **Konsent:** E-Mail (nein), Telefon (nein), Newsletter (nein)
- **Datenverwertung:**
- **Recht auf Auskunft/Löschung:**
"""
            firma_file.write_text(firma_content, encoding="utf-8")
        else:
            # Firma existiert → Person in der Ansprechpartner-Liste ergänzen
            if name:
                ft = firma_file.read_text(encoding="utf-8")
                link = f"- [[{name}]]"
                if link not in ft:
                    ft = re.sub(
                        r"(## Ansprechpartner\n)",
                        rf"\1{link}\n",
                        ft, count=1
                    )
                    firma_file.write_text(ft, encoding="utf-8")

        # ── Person anlegen ──
        if not name:
            return
        pers_file = PERS_DIR / (self._safe(name) + ".md")
        if pers_file.exists():
            # Namenskonflikt: Suffix mit Firmenname
            pers_file = PERS_DIR / (self._safe(f"{name} ({firma})") + ".md")
        pers_content = f"""---
type: person
firma: "[[{firma}]]"
email: {body.get('email','')}
tel: {body.get('phone','')}
status: {body.get('status','lead')}
last_contact: {body.get('last_contact', TODAY)}
source: {body.get('source','')}
hinzugefuegt: {TODAY}
---

# {name}

## Kontaktdaten
- **Name:** {name}
- **Titel:**
- **Firma:** [[{firma}]]
- **Abteilung:**
- **E-Mail:** {body.get('email','')}
- **Telefon:** {body.get('phone','')}

## Notizen
-

## DSGVO-Compliance
- **Konsent:** E-Mail (nein), Telefon (nein), Newsletter (nein)
"""
        pers_file.write_text(pers_content, encoding="utf-8")

    def _update_person_file(self, person_id, body):
        """Direkt eine Personendatei in Personen/ aktualisieren."""
        pfile = PERS_DIR / (self._safe(person_id) + ".md")
        if not pfile.exists():
            raise FileNotFoundError(f"Person nicht gefunden: {person_id}")
        text = pfile.read_text(encoding="utf-8")
        for md_field, key in [("Name","name"),("E-Mail","email"),("Telefon","phone"),("Titel","titel"),("Abteilung","abteilung")]:
            if key in body and body[key]:
                text = update_md_field(text, md_field, body[key])
        for fm_key, key in [("email","email"),("tel","phone"),("status","status"),("last_contact","last_contact")]:
            if key in body and body[key]:
                text = update_frontmatter_field(text, fm_key, body[key])
        pfile.write_text(text, encoding="utf-8")

    def _update_contact(self, contact_id, body):
        """Firmendatei in Firmen/ aktualisieren (Status, next_action, branch, source)."""
        firma_file = FIRMEN_DIR / (self._safe(contact_id) + ".md")
        if not firma_file.exists():
            raise FileNotFoundError(f"Firma nicht gefunden: {contact_id}")
        text = firma_file.read_text(encoding="utf-8")
        for md_field, key in [("Branche","branch"),("Quelle","source"),("Firma","firma"),("Adresse","address")]:
            if key in body and body[key]:
                text = update_md_field(text, md_field, body[key])
        for fm_key, key in [("status","status"),("last_contact","last_contact"),
                             ("next_action","next_action"),("branch","branch"),("source","source"),("address","address")]:
            if key in body:
                text = update_frontmatter_field(text, fm_key, body[key])
        firma_file.write_text(text, encoding="utf-8")

    def _update_person(self, firma_id, person_id, body):
        """Personendatei in Personen/ aktualisieren (via person_id = Dateiname ohne .md)."""
        self._update_person_file(person_id, body)

    # ── OPPORTUNITY CRUD ──
    def _create_opp(self, body):
        title = body.get("title","Neue Opportunity")
        filename = re.sub(r'[\\/*?:"<>|]',"",title).strip() + ".md"
        filepath = OPPS_DIR / filename
        content = f"""---
type: opportunity
kontakt: "[[{body.get('kontakt','')}]]"
ansprechpartner: {body.get('ansprechpartner','')}
status: {body.get('status','aktiv')}
value: {body.get('value','')}
probability: {body.get('probability','')}
next_action: {body.get('next_action','')}
deadline: {body.get('deadline','')}
created: {TODAY}
---

# [{body.get('kontakt','')}] – [{title}]

## Zusammenfassung
{body.get('summary', title)}

## Bedarf
- Problem:
- Lösung:
- Gewünscht bis: {body.get('deadline','')}

## Geschätzter Wert
- **Umsatz:** {body.get('value','')}
- **Wahrscheinlichkeit:** {body.get('probability','')}
- **Expected Value:**

## Entscheidungsträger
-

## Nächste Schritte
1. {body.get('next_action','')}

## Aktivitäten
- Opportunity angelegt {TODAY}

## Risiken
-
"""
        filepath.write_text(content, encoding="utf-8")

    def _update_opp(self, opp_id, body):
        filepath = OPPS_DIR / (opp_id + ".md")
        if not filepath.exists():
            raise FileNotFoundError(f"Opportunity nicht gefunden: {opp_id}")
        text = filepath.read_text(encoding="utf-8")
        for fm_key, body_key in [
            ("status","status"),("value","value"),("probability","probability"),
            ("next_action","next_action"),("deadline","deadline"),
        ]:
            if body_key in body:
                text = update_frontmatter_field(text, fm_key, body[body_key])
        if "kontakt" in body and body["kontakt"]:
            text = update_frontmatter_field(text, "kontakt", f'"[[{body["kontakt"]}]]"')
        if "ansprechpartner" in body:
            text = update_frontmatter_field(text, "ansprechpartner", body["ansprechpartner"])
        if "summary" in body and body["summary"]:
            text = re.sub(
                r"(## Zusammenfassung\s*\n)(.+?)(?=\n##|\Z)",
                rf"\g<1>{body['summary']}\n",
                text, flags=re.DOTALL
            )
        filepath.write_text(text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

PORT = 8765

def main():
    server = HTTPServer(("localhost", PORT), CRMHandler)
    print(f"\n⚡ CRM Server läuft auf http://localhost:{PORT}")
    print("   Im Browser öffnen und loslegen.")
    print("   Stoppen: STRG+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Server gestoppt.")

if __name__ == "__main__":
    main()
