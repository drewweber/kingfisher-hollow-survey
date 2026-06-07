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
.venv/bin/python report.py          # build reports/report.html
open reports/report.html
```
The first county sync downloads all ~25k observations (a few minutes); later
runs only fetch newer ones. Uniqueness stats are cached for 7 days, so nightly
runs only hit the API for new or stale species.

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

## Layout
```
src/config.py   IDs and paths        sync.py     fetch CLI
src/inat_api.py API client           report.py   report builder
src/db.py       SQLite schema        run.sh      nightly wrapper
src/fetch.py    property/county sync  data/inat.db
src/stats.py    uniqueness lookups    reports/report.html
src/analyze.py  pandas analyses
src/viz.py      Plotly charts
```
