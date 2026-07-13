# Creator Program Dashboard

Self-updating pipeline + budget dashboard for the Supernormal creator program.

- `index.html` — the dashboard (static, self-contained).
- `build.py` — regenerates the weekly data (Weekly snapshot + Recent work + "as of" date) from the Marketing Tracker Google Sheet (Live Influencer Partnerships tab).
- `.github/workflows/weekly.yml` — runs `build.py` every Monday and redeploys to Vercel, hands-free.

## Secrets (GitHub → Settings → Secrets → Actions)
- `GOOGLE_SHEETS_KEY` — the Google service-account JSON (whole file contents)
- `GOOGLE_SHEET_ID` — the Marketing Tracker spreadsheet id
- `VERCEL_TOKEN` — a Vercel access token
- `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` — from the Vercel project

## Manual refresh
Run the "Weekly dashboard refresh" workflow from the Actions tab, or locally: `python3 build.py`.

Note: the Active collabs, Invoices, Pipeline notes, and Forecast sections are curated by hand (they carry qualitative status). The weekly numbers and top-performer embeds refresh automatically.
