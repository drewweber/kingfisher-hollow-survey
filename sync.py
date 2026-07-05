#!/usr/bin/env python3
"""Sync iNaturalist observations into the local database.

    python sync.py --property     # Kingfisher Hollow project (incremental)
    python sync.py --county       # Tioga County (id_above cursor)
    python sync.py --stats        # refresh uniqueness stats (stale/new taxa)
    python sync.py --daily        # fast CI/default refresh
    python sync.py --all          # daily + regional reference pools
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import fetch  # noqa: E402
import stats  # noqa: E402
import weather  # noqa: E402
from db import init_db  # noqa: E402


def timed(label, func, *args, **kwargs):
    start = time.monotonic()
    try:
        return func(*args, **kwargs)
    finally:
        elapsed = time.monotonic() - start
        print(f"[timing] {label}: {elapsed:.1f}s", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", action="store_true", help="sync property project")
    ap.add_argument("--county", action="store_true", help="sync Tioga County")
    ap.add_argument("--moths", action="store_true",
                    help="refresh moth roster")
    ap.add_argument("--butterflies", action="store_true",
                    help="refresh butterfly roster + regional pool")
    ap.add_argument("--mammals", action="store_true",
                    help="refresh mammal roster + regional pool")
    ap.add_argument("--plants", action="store_true",
                    help="refresh plant roster + regional pool")
    ap.add_argument("--amphibians", action="store_true",
                    help="refresh amphibian roster + regional pool")
    ap.add_argument("--reptiles", action="store_true",
                    help="refresh reptile roster + regional pool")
    ap.add_argument("--stats", action="store_true", help="refresh uniqueness stats")
    ap.add_argument("--stats-workers", type=int, default=4,
                    help="parallel workers for uniqueness stats lookups")
    ap.add_argument("--taxonomy", action="store_true",
                    help="enrich order/family for new species")
    ap.add_argument("--weather", action="store_true",
                    help="fetch/update weather cache for all observation dates")
    ap.add_argument("--daily", action="store_true",
                    help="fast daily refresh: observations, property rosters, taxonomy, stats, weather")
    ap.add_argument("--reference", action="store_true",
                    help="refresh slower regional/county reference pools for gap lists")
    ap.add_argument("--all", action="store_true",
                    help="daily refresh + slower regional/county reference pools")
    args = ap.parse_args()

    flags = [args.property, args.county, args.moths, args.butterflies, args.mammals,
             args.plants, args.amphibians, args.reptiles, args.taxonomy, args.stats,
             args.weather, args.daily, args.reference, args.all]
    if not any(flags):
        ap.print_help()
        return

    init_db()
    daily = args.all or args.daily
    reference = args.all or args.reference

    if daily or args.property:
        timed("property", fetch.sync_property, incremental=args.daily and not args.all)
    if daily or args.county:
        timed("county", fetch.sync_county)
    if reference or args.county:
        timed("county-moths", fetch.sync_county_moths)
        timed("region-moths", fetch.sync_region_moths)
    if daily or args.moths:
        timed("moths", fetch.sync_moths)
    if daily or args.butterflies:
        timed("butterflies", fetch.sync_butterflies)
    if reference or args.butterflies:
        timed("region-butterflies", fetch.sync_region_butterflies)
    if daily or args.mammals:
        timed("mammals", fetch.sync_mammals)
    if reference or args.mammals:
        timed("region-mammals", fetch.sync_region_mammals)
    if daily or args.plants:
        timed("plants", fetch.sync_plants)
    if reference or args.plants:
        timed("region-plants", fetch.sync_region_plants)
    if daily or args.amphibians:
        timed("amphibians", fetch.sync_amphibians)
    if reference or args.amphibians:
        timed("region-amphibians", fetch.sync_region_amphibians)
    if daily or args.reptiles:
        timed("reptiles", fetch.sync_reptiles)
    if reference or args.reptiles:
        timed("region-reptiles", fetch.sync_region_reptiles)
    if daily or args.taxonomy:
        timed("taxonomy", fetch.sync_taxonomy)
    if daily or args.stats:
        timed("stats", stats.refresh_stats, workers=args.stats_workers)
    if daily or args.weather:
        timed("weather", weather.sync_weather, fetch.observation_dates())


if __name__ == "__main__":
    main()
