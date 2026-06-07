# Kingfisher Hollow iNaturalist Pipeline

A self-updating pipeline that pulls observations from the
[Kingfisher Hollow Biodiversity Survey](https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey)
project and Tioga County, NY, then builds a single-file HTML report:
**what's new since last night**, species accumulation curves, observations
per day, phenology, an observer leaderboard, a map, and a per-species
*contribution uniqueness* view (how rare each species is in the county and in
New York State, and whether you hold a county-first record).

## iNaturalist identifiers (verified against the live API)
| Entity   | Identifier         | Notes |
|----------|--------------------|-------|
| Property | `project_id 249580` (place 218351) | collection project, ~3.5k obs |
| County   | `place_id 653` (Tioga County, NY)  | ~25.5k obs, fetched via `id_above` cursor (beats the 10k pagination ceiling) |
| State    | `place_id 48` (New York)           | counts only — never bulk-fetched |

The `…704429`/`…704431` numbers in the original CSV filenames were **export-job
IDs**, not place IDs. The CSVs are kept only as a historical snapshot; the
database is populated fresh from the API.

## Setup
```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage
```sh
.venv/bin/python sync.py --all      # property + county + uniqueness stats
.venv/bin/python report.py          # build public/index.html
open public/index.html
```
The first sync downloads all ~25k county observations plus uniqueness stats for
every property species (~90 min, one time). Later runs are incremental: only new
observations are fetched, and uniqueness stats refresh on a 30-day TTL (new
property species are always refreshed immediately), so nightly runs take a few
minutes.

Granular commands: `sync.py --property`, `--county`, `--stats`.

## Nightly automation (macOS launchd)
```sh
cp com.kingfisher.inat.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kingfisher.inat.plist
launchctl start com.kingfisher.inat        # test run now
```
Runs `run.sh` daily at 05:10 (logs in `logs/`). To stop:
`launchctl unload ~/Library/LaunchAgents/com.kingfisher.inat.plist`.

**cron alternative:** `10 5 * * * /…/inat-data/run.sh`

## Hosting on the web (Cloudflare Pages + GitHub Actions)
The report is published to **survey.kingfisher-hollow.com** by a nightly GitHub
Actions workflow (`.github/workflows/update.yml`) — independent of the existing
homepage on `www`. The job runs `sync.py --all` + `report.py`, then deploys the
`public/` directory to a dedicated Cloudflare Pages project (`kingfisher-survey`).
The SQLite DB is persisted between runs via Actions cache (a cache miss just
re-pulls from the API, since sync is idempotent), so nothing binary is committed.
A tiny `LAST_UPDATED.txt` marker is committed each run so the repo stays active —
otherwise GitHub disables scheduled workflows after 60 days of no commits.

One-time setup (the only steps that need your credentials):
1. **Push to GitHub** (a repo is initialised here):
   ```sh
   git remote add origin git@github.com:<you>/kingfisher-hollow-survey.git
   git push -u origin main
   ```
2. **Create the Pages project** (in the Cloudflare dashboard → Workers & Pages →
   Create → Pages → "Direct Upload", name it `kingfisher-survey`), then add the
   custom domain `survey.kingfisher-hollow.com` under its **Custom domains** tab.
3. **Add two GitHub repo secrets** (Settings → Secrets and variables → Actions):
   - `CLOUDFLARE_API_TOKEN` — a token with the *Cloudflare Pages: Edit* permission
   - `CLOUDFLARE_ACCOUNT_ID` — from the Cloudflare dashboard URL / overview

Then trigger the workflow once from the Actions tab (**Run workflow**) to verify.
The GitHub cron is in UTC; `09:10 UTC` ≈ `05:10 ET`.

## Layout
```
src/config.py   IDs and paths         sync.py     fetch CLI
src/inat_api.py API client            report.py   report builder
src/db.py       SQLite schema         run.sh      nightly wrapper (local launchd)
src/fetch.py    property/county sync  data/inat.db (gitignored; cached in CI)
src/stats.py    uniqueness lookups    public/index.html (generated report)
src/analyze.py  pandas analyses       .github/workflows/update.yml (cron + deploy)
src/viz.py      Plotly charts
```
