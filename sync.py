#!/usr/bin/env python3
"""Sync iNaturalist observations into the local database.

    python sync.py --property     # Kingfisher Hollow project (incremental)
    python sync.py --county       # Tioga County (id_above cursor)
    python sync.py --stats        # refresh uniqueness stats (stale/new taxa)
    python sync.py --all          # property + county + stats (nightly default)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import fetch  # noqa: E402
import stats  # noqa: E402
import weather  # noqa: E402
from db import init_db  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", action="store_true", help="sync property project")
    ap.add_argument("--county", action="store_true", help="sync Tioga County")
    ap.add_argument("--moths", action="store_true",
                    help="refresh moth + butterfly rosters")
    ap.add_argument("--mammals", action="store_true",
                    help="refresh mammal roster + regional pool")
    ap.add_argument("--plants", action="store_true",
                    help="refresh plant roster + regional pool")
    ap.add_argument("--stats", action="store_true", help="refresh uniqueness stats")
    ap.add_argument("--taxonomy", action="store_true",
                    help="enrich order/family for new species")
    ap.add_argument("--weather", action="store_true",
                    help="fetch/update weather cache for all observation dates")
    ap.add_argument("--all", action="store_true",
                    help="property + county + moths/butterflies + mammals + plants + taxonomy + stats + weather")
    args = ap.parse_args()

    flags = [args.property, args.county, args.moths, args.mammals, args.plants,
             args.taxonomy, args.stats, args.weather, args.all]
    if not any(flags):
        ap.print_help()
        return

    init_db()
    if args.all or args.property:
        fetch.sync_property()
    if args.all or args.county:
        fetch.sync_county()
        fetch.sync_county_moths()
        fetch.sync_region_moths()
    if args.all or args.moths:
        fetch.sync_moths()
        fetch.sync_butterflies()
    if args.all or args.mammals:
        fetch.sync_mammals()
        fetch.sync_region_mammals()
    if args.all or args.plants:
        fetch.sync_plants()
        fetch.sync_region_plants()
    if args.all or args.taxonomy:
        fetch.sync_taxonomy()
    if args.all or args.stats:
        stats.refresh_stats()
    if args.all or args.weather:
        weather.sync_weather(fetch.observation_dates())


if __name__ == "__main__":
    main()
