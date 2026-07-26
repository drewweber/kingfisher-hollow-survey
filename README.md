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
npm ci
```

## Usage
```sh
.venv/bin/python sync.py --daily    # fast daily refresh for new survey records
npm run build:css                   # compile the survey stylesheet
.venv/bin/python report.py          # build public/index.html
open public/index.html
```
The first sync downloads all ~25k county observations plus uniqueness stats for
every property species (~90 min, one time). Later runs are incremental: only new
observations are fetched, and uniqueness stats refresh on a 30-day TTL (new
property species are always refreshed immediately), so nightly runs take a few
minutes.

`sync.py` prints per-stage timings so slow refreshes show which step is taking
time. Uniqueness stats run with four bounded workers by default; tune that with
`--stats-workers N` or use `--stats-workers 1` for fully serial API lookups.
Use `--stats-limit N` to rotate through a bounded number of the oldest cached
records; the weekly workflow refreshes 300 at a time while new species remain
uncapped and are always handled by the daily run.

Use `sync.py --all` for a full refresh, including slower regional reference
pools used by gap lists. Use `sync.py --reference` to refresh only those
regional/county reference pools.
Daily runs use a fast incremental property sync keyed by observation ID. Full
refreshes still re-sweep the property project, which catches older observations
that were newly added to the project or changed below the current max ID.

Granular commands: `sync.py --property`, `--county`, `--stats`.

The Dragonflies & Damselflies view uses a dedicated Odonata property roster and
an 80 km regional comparison pool. Refresh both directly with
`sync.py --odonates`. The compact regional roster is also refreshed during the
daily run so the focused page and its gap list survive a fresh CI cache.

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
homepage on `www`. The job runs `sync.py` + `report.py`, then deploys the
`public/` directory to a dedicated Cloudflare Pages project (`kingfisher-survey`).
Normal scheduled runs and the Log view update button use the faster daily
refresh; a weekly scheduled run refreshes the full regional reference pools for
gap-list context.
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

The separate field-alert Worker uses `CLOUDFLARE_WORKERS_API_TOKEN`, created
from Cloudflare's **Edit Cloudflare Workers** token template and restricted to
the same account. Keeping this separate preserves the narrower Pages token.

Then trigger the workflow once from the Actions tab (**Run workflow**) to verify.
The GitHub cron is in UTC; `09:10 UTC` ≈ `05:10 ET`.

### Manual update link on the Log view

The Log view includes a small **Check for updates...** link. It calls a Cloudflare Pages
Function at `/api/update`, which triggers the fast daily GitHub Actions refresh.
The browser never receives a GitHub token.

Add these Cloudflare Pages environment variables for the `kingfisher-survey`
project:

- `UPDATE_TRIGGER_KEY` — a private passphrase you type into the browser when the
  button asks for the update key.
- `GITHUB_DISPATCH_TOKEN` — a GitHub fine-grained token for this repository with
  **Actions: Read and write** permission, used only by the Pages Function to
  call `workflow_dispatch` on `.github/workflows/update.yml`.

Without those variables, the link is visible but the endpoint returns a
configuration error instead of starting a workflow.

### Public read-only survey API

The Pages deployment also publishes a small public API for tools that need
combined Kingfisher Hollow species totals or moth occurrences without accessing
SQLite or calling iNaturalist directly:

- `/api/summary` — bird, moth, and deduplicated all-taxa species totals
- `/api/observations` — observation-level records
- `/api/species` — species counts and first/last dates
- `/api/nights` — one row per matching local calendar date
- `/api/stats` — aggregate observation, species, and distinct-date counts
- `/api/docs` — human-readable documentation
- `/api/openapi.json` — OpenAPI 3.1 contract

`report.py` calls `src/public_api.py` during every rebuild. The generator writes
compact snapshots to `public/_api-data/summary.json` and
`public/_api-data/moths.json`; Pages Functions read those assets through
Cloudflare's `ASSETS` binding. The biodiversity summary uses the countable eBird
location life list for birds, the current moth roster for moths, and the same
species-level deduplication rules as the report for the all-taxa total. The moth
snapshot contains only taxon names and IDs, taxonomic rank, family, observation
dates/times, and public iNaturalist links. It excludes coordinates, observers,
photos, and every other private pipeline field.

All API filters use AND semantics. Names and families are case-insensitive exact
matches. A "night" is a distinct `America/New_York` calendar date derived from
the timezone-aware observation timestamp, not a formal trapping-session record.
Observation IDs are deduplicated before any count is calculated. Collection
endpoints default to 100 rows and reject limits above 500. Their `count` is the
number of rows in the current page; `total` is the number matching the filters.
Add `format=csv` for CSV output.

The OpenAPI document exposes five GPT Action operation IDs:
`getBiodiversitySummary`, `listSpecies`, `listObservations`,
`listObservationNights`, and `getSurveyStats`. `/api/docs` includes clickable
examples and the copy-ready GPT instructions that require answers to be grounded
in API results.

The Functions enforce a lightweight per-client fallback limit of 120 requests
per minute. If the Pages project later receives an `API_RATE_LIMITER` Cloudflare
Rate Limiting binding, the same code uses that binding automatically.

Local checks:

```sh
.venv/bin/python src/public_api.py
node --test tests/public_api.test.mjs
field-alerts/node_modules/.bin/wrangler pages dev public
API_BASE_URL=http://127.0.0.1:8788 node --test tests/public_api_e2e.mjs
```

### Realtime moth field alerts

`field-alerts/` contains a separate Cloudflare Worker for immediate moth
documentation prompts. It checks Drew's recently uploaded or reidentified moth
observations every three minutes and sends an ntfy phone notification when the current
photographs may document a notable record:

- Red: possible New York or 80 km regional iNaturalist first.
- Yellow: possible Tioga County iNaturalist first with regional precedent.
- No alert: new only to Kingfisher Hollow or already known in Tioga County.

The 80 km search includes well-covered Tompkins County and nearby northern
Pennsylvania. Alerts are rapid screening results, not final rarity claims.

The Worker has its own protected, phone-friendly manual checker and durable
deduplication. Notable alerts also compare the proposed identification against
same-genus moths recorded within 80 km, then provide a short lookalike key and
the specific photographs needed to distinguish them. It does not rebuild the
report or trigger GitHub Actions. See
`field-alerts/README.md` for local testing, ntfy setup, Worker secrets, and the
one-time deployment process. `.github/workflows/deploy-field-alerts.yml` provides
a manual test-and-deploy action once the Cloudflare token has Workers edit
permission.

### Plant gap list filtering

Plant roster syncs use iNaturalist's `captive=false` filter, so the property
plant list and regional plant pool are based on records not marked
cultivated/planted. The gap list also enriches plants with New York
establishment status and excludes taxa listed as introduced in New York.

### Bird page source

Birds are tracked from eBird rather than iNaturalist. The Birds view reads the
checked-in eBird location life-list snapshot at
`data/ebird_L41961519_life_list.csv` and links to the live eBird barchart for
location `L41961519`. To refresh the local bird page, export a new location life
list from eBird, replace that CSV, rebuild with `report.py`, and push.

Bird gaps should be evaluated from eBird, not iNaturalist. The site links to the
Tioga County barchart as the relevant local comparison and Tompkins County as a
better-covered regional comparison, with the caveat that Cayuga Lake biases
Tompkins toward waterbirds and shoreline species. During report builds, the
Birds view reads those two barcharts, scores the current four-week seasonal
window, removes birds already on the Kingfisher Hollow eBird life list, and
renders a no-photo gap table sorted by likelihood.

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
