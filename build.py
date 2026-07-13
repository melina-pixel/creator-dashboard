#!/usr/bin/env python3
"""
Regenerates the weekly data in index.html from the Marketing Tracker Google Sheet.
Refreshes: WEEKS (weekly snapshot), TOPWEEKS (recent-work embeds), and the "as of" date.
Static/qualitative sections (active collabs, invoices, forecast) are left untouched.

Runs locally (build only) and in GitHub Actions (build + deploy).
Creds:
  - Google service-account JSON at $GOOGLE_SHEETS_KEY_PATH (default ~/.claude/google-sheets-credentials.json)
    OR raw JSON in env GOOGLE_SHEETS_KEY (used by CI secret).
  - Sheet id in env GOOGLE_SHEET_ID (or ~/.claude/.env).
"""
import os, re, json, warnings
from datetime import date, timedelta
warnings.filterwarnings("ignore")
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")

# ---- credentials ----
def load_env():
    env = {}
    p = os.path.expanduser("~/.claude/.env")
    if os.path.exists(p):
        for l in open(p):
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env
env = load_env()
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID") or env.get("GOOGLE_SHEET_ID")

raw_key = os.environ.get("GOOGLE_SHEETS_KEY")
if raw_key:
    info = json.loads(raw_key)
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
else:
    key_path = os.environ.get("GOOGLE_SHEETS_KEY_PATH", os.path.expanduser("~/.claude/google-sheets-credentials.json"))
    creds = Credentials.from_service_account_file(key_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
sheets = build("sheets", "v4", credentials=creds)

# ---- pull LIP ----
LIP = "Live Influencer Partnerships"
vals = sheets.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=f"'{LIP}'!A5:W1000").execute().get("values", [])

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

rows = []
for r in vals:
    r = r + [""] * 23
    if not str(r[1]).strip():
        continue
    d = pdate(r[3])
    rows.append({"d": d, "name": str(r[1]).strip(), "src": str(r[2]).strip(),
                 "cost": money(r[9]), "views": vi(r[11]), "link": str(r[6]).strip()})

# anchor "today" to the most recent Monday on/after the latest post date, so weeks stay aligned
latest = max((x["d"] for x in rows if x["d"]), default=date.today())
end = latest - timedelta(days=(latest.weekday()))  # Monday of latest week
end = end + timedelta(days=6)  # that week's Sunday-ish upper bound -> use 7-day windows ending here
# Use the same convention as the live dashboard: 7-day windows ending on `end`
def fmt(d): return d.strftime("%-d %b")

WEEKS, TOPWEEKS = [], []
for i in range(8):
    hi = end - timedelta(days=7 * i)
    lo = hi - timedelta(days=6)
    wk = [x for x in rows if x["d"] and lo <= x["d"] <= hi]
    posts = len(wk); spend = round(sum(x["cost"] for x in wk))
    sc = {"Posted": 0, "Outreach": 0, "Later": 0}
    top = (0, "")
    for x in wk:
        sc[x["src"]] = sc.get(x["src"], 0) + 1
        if x["views"] >= top[0]:
            top = (x["views"], x["name"])
    WEEKS.append({"lo": fmt(lo), "hi": fmt(hi), "posts": posts, "spend": spend,
                  "top": top[1], "topv": top[0],
                  "posted": sc["Posted"], "outreach": sc["Outreach"], "later": sc["Later"]})
    linked = sorted([x for x in wk if x["link"].startswith("http")], key=lambda x: -x["views"])[:4]
    TOPWEEKS.append({"lo": fmt(lo), "hi": fmt(hi),
                     "top": [{"name": x["name"], "url": x["link"], "views": x["views"], "plat": plat(x["link"])} for x in linked]})

weeks_js = "[\n    " + ",\n    ".join(json.dumps(w, ensure_ascii=False) for w in WEEKS) + "\n  ]"
topweeks_js = "[\n    " + ",\n    ".join(json.dumps(w, ensure_ascii=False) for w in TOPWEEKS) + "\n  ]"

# ---- rewrite index.html data blocks ----
html = open(INDEX, encoding="utf-8").read()
html = re.sub(r"const WEEKS=\[.*?\n  \];", "const WEEKS=" + weeks_js + ";", html, count=1, flags=re.S)
html = re.sub(r"const TOPWEEKS=\[.*?\n  \];", "const TOPWEEKS=" + topweeks_js + ";", html, count=1, flags=re.S)
today = date.today().strftime("%-d %b %Y")
html = re.sub(r"<span>as of [^<]*</span>", f"<span>as of {today}</span>", html)
open(INDEX, "w", encoding="utf-8").write(html)
print(f"Rebuilt index.html: {len(WEEKS)} weeks, latest window {WEEKS[0]['lo']}-{WEEKS[0]['hi']}, as of {today}")
