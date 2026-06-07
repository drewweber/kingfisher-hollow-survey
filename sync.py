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
from db import init_db  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", action="store_true", help="sync property project")
    ap.add_argument("--county", action="store_true", help="sync Tioga County")
    ap.add_argument("--moths", action="store_true", help="refresh moth roster")
    ap.add_argument("--stats", action="store_true", help="refresh uniqueness stats")
    ap.add_argument("--all", action="store_true",
                    help="property + county + moths + stats")
    args = ap.parse_args()

    if not any([args.property, args.county, args.moths, args.stats, args.all]):
        ap.print_help()
        return

    init_db()
    if args.all or args.property:
        fetch.sync_property()
    if args.all or args.county:
        fetch.sync_county()
    if args.all or args.moths:
        fetch.sync_moths()
    if args.all or args.stats:
        stats.refresh_stats()


if __name__ == "__main__":
    main()
