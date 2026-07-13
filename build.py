#!/usr/bin/env python3
"""
Regenerates the data-driven parts of index.html from the Marketing Tracker Google Sheet.

Auto-refreshed (from Sheets):
  - WEEKS (weekly snapshot) + TOPWEEKS (recent-work embeds)   [Live Influencer Partnerships]
  - budget spend-to-date, projected, available, bar widths     [LIP + $10K monthly budget]
  - all-time spend / post count, recent-months line            [LIP]
  - pipeline wave counts                                        [Later List Creators]
  - "as of" date

Left manual (not structured in the sheet): active-collab stages/health, invoices (Gmail),
pipeline "in motion" notes, forecast text. Monthly budget + committed estimate are constants below.
"""
import os, re, json, warnings
from datetime import date, timedelta
from collections import defaultdict
warnings.filterwarnings("ignore")
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")

MONTHLY_BUDGET = 10000      # curated: Mel confirmed $10K/mo
COMMITTED_EST  = 4500       # curated estimate of active run-rate not yet invoiced

# ---- credentials ----
def load_env():
    env = {}
    p = os.path.expanduser("~/.claude/.env")
    if os.path.exists(p):
        for l in open(p):
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    return env
env = load_env()
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID") or env.get("GOOGLE_SHEET_ID")
raw_key = os.environ.get("GOOGLE_SHEETS_KEY")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
if raw_key:
    creds = Credentials.from_service_account_info(json.loads(raw_key), scopes=SCOPES)
else:
    kp = os.environ.get("GOOGLE_SHEETS_KEY_PATH", os.path.expanduser("~/.claude/google-sheets-credentials.json"))
    creds = Credentials.from_service_account_file(kp, scopes=SCOPES)
sheets = build("sheets", "v4", credentials=creds)

def money(s):
    x = re.sub(r"[^\d.]", "", str(s)); return float(x) if x else 0.0
def vi(s):
    x = re.sub(r"[^\d]", "", str(s)); return int(x) if x else 0
def pdate(s):
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", str(s).strip())
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None
def plat(u):
    if "tiktok" in u: return "TikTok"
    if "instagram" in u: return "IG"
    if "youtu" in u: return "YouTube"
    return "Link"

# ---- LIP ----
vals = sheets.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="'Live Influencer Partnerships'!A5:W1000").execute().get("values", [])
rows = []
for r in vals:
    r = r + [""] * 23
    if not str(r[1]).strip(): continue
    rows.append({"d": pdate(r[3]), "name": str(r[1]).strip(), "src": str(r[2]).strip(),
                 "cost": money(r[9]), "views": vi(r[11]), "link": str(r[6]).strip()})

latest = max((x["d"] for x in rows if x["d"]), default=date.today())
end = latest - timedelta(days=latest.weekday()) + timedelta(days=6)
def fmt(d): return d.strftime("%-d %b")

WEEKS, TOPWEEKS = [], []
for i in range(8):
    hi = end - timedelta(days=7 * i); lo = hi - timedelta(days=6)
    wk = [x for x in rows if x["d"] and lo <= x["d"] <= hi]
    sc = {"Posted": 0, "Outreach": 0, "Later": 0}; top = (0, "")
    for x in wk:
        sc[x["src"]] = sc.get(x["src"], 0) + 1
        if x["views"] >= top[0]: top = (x["views"], x["name"])
    WEEKS.append({"lo": fmt(lo), "hi": fmt(hi), "posts": len(wk), "spend": round(sum(x["cost"] for x in wk)),
                  "top": top[1], "topv": top[0], "posted": sc["Posted"], "outreach": sc["Outreach"], "later": sc["Later"]})
    linked = sorted([x for x in wk if x["link"].startswith("http")], key=lambda x: -x["views"])[:4]
    TOPWEEKS.append({"lo": fmt(lo), "hi": fmt(hi),
                     "top": [{"name": x["name"], "url": x["link"], "views": x["views"], "plat": plat(x["link"])} for x in linked]})

# ---- budget / totals ----
today = date.today()
mspend = defaultdict(float)
for x in rows:
    if x["d"]: mspend[(x["d"].year, x["d"].month)] += x["cost"]
spent_mtd = round(mspend.get((today.year, today.month), 0))
projected = spent_mtd + COMMITTED_EST
available = max(0, MONTHLY_BUDGET - projected)
spent_pct = min(100, round(spent_mtd / MONTHLY_BUDGET * 100))
committed_pct = min(100 - spent_pct, round(COMMITTED_EST / MONTHLY_BUDGET * 100))
month_name = today.strftime("%B")
all_time = round(sum(x["cost"] for x in rows)); all_posts = len(rows)
# two prior calendar months
def mkey(y, m): return (y, m)
prev = []
y, m = today.year, today.month
for _ in range(2):
    m -= 1
    if m == 0: m = 12; y -= 1
    prev.append((y, m))
mo = lambda ym: date(ym[0], ym[1], 1).strftime("%b")
recent = " · ".join(f"{mo(k)} ${mspend.get(k,0)/1000:.1f}K" for k in reversed(prev))

# ---- pipeline wave counts (Later List Creators, col D = wave) ----
llc = sheets.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="'Later List Creators'!A2:D2000").execute().get("values", [])
wv = defaultdict(int); backlog = 0
for r in llc:
    r = r + [""] * 4
    if not str(r[0]).strip(): continue
    w = str(r[3]).strip()
    if w in ("Wave 1", "Wave 2", "Wave 3"): wv[w] += 1
    elif w != "Active": backlog += 1

# ---- inject ----
html = open(INDEX, encoding="utf-8").read()
def sub(pattern, repl, label, flags=0):
    global html
    html, n = re.subn(pattern, lambda m: repl, html, count=1, flags=flags)
    if n == 0: print(f"  WARN no match: {label}")

weeks_js = "[\n    " + ",\n    ".join(json.dumps(w, ensure_ascii=False) for w in WEEKS) + "\n  ]"
topweeks_js = "[\n    " + ",\n    ".join(json.dumps(w, ensure_ascii=False) for w in TOPWEEKS) + "\n  ]"
html = re.sub(r"const WEEKS=\[.*?\n  \];", "const WEEKS=" + weeks_js.replace("\\", "\\\\") + ";", html, count=1, flags=re.S)
html = re.sub(r"const TOPWEEKS=\[.*?\n  \];", "const TOPWEEKS=" + topweeks_js.replace("\\", "\\\\") + ";", html, count=1, flags=re.S)
sub(r"<span>as of [^<]*</span>", f"<span>as of {today.strftime('%-d %b %Y')}</span>", "as-of date")

# budget
sub(r'<span class="big">\$[\d.]+K</span> <span class="sub">projected spend', f'<span class="big">${projected/1000:.1f}K</span> <span class="sub">projected spend', "projected big")
sub(r'<div class="spent" style="width:\d+%">', f'<div class="spent" style="width:{spent_pct}%">', "bar spent")
sub(r'<div class="committed" style="width:\d+%">', f'<div class="committed" style="width:{committed_pct}%">', "bar committed")
sub(r"Spent to date \$[\d,]+", f"Spent to date ${spent_mtd:,}", "legend spent")
sub(r"Available ~\$[\d,]+", f"Available ~${available:,}", "legend available")
sub(r'<div class="n">\$[\d,]+</div><div class="l">spent in \w+ \(to date\)</div>',
    f'<div class="n">${spent_mtd:,}</div><div class="l">spent in {month_name} (to date)</div>', "kpi spent")
sub(r"Tracking to ~\$[\d.]+K of a \$10K monthly budget, so ~\$[\d.]+K headroom",
    f"Tracking to ~${projected/1000:.0f}K of a $10K monthly budget, so ~${available/1000:.0f}K headroom", "budget note")
sub(r"Recent months:.*?<span class=\"sub\">all-time",
    f'Recent months: {recent} · <span class="sub">all-time', "recent months", flags=re.S)
sub(r"all-time creator spend \$[\d.]+K across \d+ posts",
    f"all-time creator spend ${all_time/1000:.1f}K across {all_posts} posts", "all-time")
sub(r"Tracking to ~\$[\d.]+K/mo of a \$10K budget, roughly \$[\d.]+K/mo of headroom",
    f"Tracking to ~${projected/1000:.0f}K/mo of a $10K budget, roughly ${available/1000:.0f}K/mo of headroom", "forecast headroom")
sub(r"\b\w+ spend \$[\d,]+ of \$10K budget so far",
    f"{month_name} spend ${spent_mtd:,} of $10K budget so far", "snapshot budget line")

# pipeline wave counts
sub(r'<div class="n">\d+</div><div class="l">Wave 1', f'<div class="n">{wv["Wave 1"]}</div><div class="l">Wave 1', "wave1")
sub(r'<div class="n">\d+</div><div class="l">Wave 2', f'<div class="n">{wv["Wave 2"]}</div><div class="l">Wave 2', "wave2")
sub(r'<div class="n">\d+</div><div class="l">Wave 3', f'<div class="n">{wv["Wave 3"]}</div><div class="l">Wave 3', "wave3")
sub(r'<div class="n">\d+</div><div class="l">backlog', f'<div class="n">{backlog}</div><div class="l">backlog', "backlog")
total_prospects = wv["Wave 1"] + wv["Wave 2"] + wv["Wave 3"] + backlog
sub(r"Pipeline, \d+ prospects", f"Pipeline, {total_prospects} prospects", "pipeline heading")

# ---- Active / Wrapped collabs from Long-Term Partnerships tab (Dashboard/Stage/Health cols) ----
lt = sheets.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="'Long-Term Influencer Partnerships'!B8:T60").execute().get("values", [])
HEALTH_PILL = {"Healthy": "p-green", "Complete": "p-green", "At risk": "p-amber", "Parked": "p-amber",
               "New": "p-blue", "Volume engine": "p-blue", "Dormant": "p-gray", "Churned": "p-red"}
def pillcls(h): return HEALTH_PILL.get(h, "p-gray")
active, wrapped = [], []
for r in lt:
    r = r + [""] * 19
    name, dash, stage, health = r[0].strip(), r[16].strip(), r[17].strip(), r[18].strip()
    if not name or name == "Influencer Name" or dash not in ("Active", "Wrapped"): continue
    rec = {"name": name, "type": r[1].strip(), "link": r[5].strip(), "cost": r[9].strip(), "stage": stage, "health": health}
    (active if dash == "Active" else wrapped).append(rec)
active.insert(0, {"name": "Posted CPM cohort", "sub": "~20+ UGC creators/wk", "type": "Posted (volume)",
                  "link": "", "cost": "$20 flat and CPM", "stage": "Live · daily posts", "health": "Volume engine"})
wrapped.append({"name": "Corporate Bro (Ross)", "type": "Prospect", "link": "", "cost": "$20K quote",
                "stage": "Parked · $20K too high vs fit", "health": "Parked"})
def linkhtml(rec):
    if rec.get("sub"): return f'<br><span class="sub">{rec["sub"]}</span>'
    return f'<br><a href="{rec["link"]}" target="_blank">open ↗</a>' if rec["link"] else ""
def arow(rec):
    sc = pillcls(rec["health"])
    return (f'<tr><td><strong>{rec["name"]}</strong>{linkhtml(rec)}</td><td>{rec["type"]}</td>'
            f'<td><span class="pill {sc}">{rec["stage"]}</span></td><td>{rec["cost"]}</td>'
            f'<td><span class="pill {sc}">{rec["health"]}</span></td></tr>')
def wrow(rec):
    sc = pillcls(rec["health"])
    return (f'<tr><td><strong>{rec["name"]}</strong>{linkhtml(rec)}</td><td>{rec["type"]}</td>'
            f'<td><span class="pill {sc}">{rec["stage"]}</span></td><td>{rec["cost"]}</td></tr>')
active_html = "".join(arow(r) for r in active)
wrapped_html = "".join(wrow(r) for r in wrapped)
html, na = re.subn(r'(<tbody id="activeRows">).*?(</tbody>)', lambda m: m.group(1) + active_html + m.group(2), html, count=1, flags=re.S)
html, nw = re.subn(r'(<tbody id="wrappedRows">).*?(</tbody>)', lambda m: m.group(1) + wrapped_html + m.group(2), html, count=1, flags=re.S)
if not na: print("  WARN no match: activeRows")
if not nw: print("  WARN no match: wrappedRows")
print(f"  active collabs: {len(active)} | wrapped: {len(wrapped)}")

open(INDEX, "w", encoding="utf-8").write(html)
print(f"Rebuilt: week {WEEKS[0]['lo']}-{WEEKS[0]['hi']}, {month_name} spend ${spent_mtd:,}/{MONTHLY_BUDGET}, "
      f"waves {wv['Wave 1']}/{wv['Wave 2']}/{wv['Wave 3']}/{backlog}, all-time ${all_time/1000:.1f}K/{all_posts}")
