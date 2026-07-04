"""Per-taxon uniqueness lookups: how rare is each property species in the
county and across New York State? Cached in species_stats with a TTL so
nightly runs only hit the API for new or stale taxa."""

from concurrent.futures import ThreadPoolExecutor, as_completed

import inat_api
from config import (COUNTY_PLACE_ID, SPECIES_RANKS, STATE_PLACE_ID,
                    STATS_TTL_DAYS)
from db import connect

DEFAULT_STATS_WORKERS = 4


def _stale_or_missing(conn):
    """Property taxa whose cached stats are absent or older than the TTL.

    Returns rows of (taxon_id, taxon_name, common_name, property_first_date,
    property_obs_count) computed from the local property_obs table.
    """
    return conn.execute(
        """
        SELECT p.taxon_id,
               MAX(p.taxon_name)   AS taxon_name,
               MAX(p.common_name)  AS common_name,
               MIN(p.observed_on)  AS property_first_date,
               COUNT(*)            AS property_obs_count
        FROM property_obs p
        LEFT JOIN species_stats s ON s.taxon_id = p.taxon_id
        WHERE p.taxon_id IS NOT NULL
          AND p.rank IN ({placeholders})
          AND (s.taxon_id IS NULL
               OR s.cached_at < datetime('now', ?))
        GROUP BY p.taxon_id
        """.format(placeholders=",".join("?" * len(SPECIES_RANKS))),
        (*SPECIES_RANKS, f"-{STATS_TTL_DAYS} days"),
    ).fetchall()


UPSERT = (
    "INSERT OR REPLACE INTO species_stats "
    "(taxon_id, taxon_name, common_name, county_obs_count, state_obs_count, "
    " county_first_date, state_first_date, property_first_date, "
    " property_obs_count, is_county_first, state_rarity_rank, cached_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))"
)


def _stats_for_taxon(row):
    tid = row["taxon_id"]
    county_count, county_first = inat_api.count_and_first_observed_date(
        taxon_id=tid, place_id=COUNTY_PLACE_ID
    )
    state_count, state_first = inat_api.count_and_first_observed_date(
        taxon_id=tid, place_id=STATE_PLACE_ID
    )
    prop_first = row["property_first_date"]
    is_county_first = bool(
        prop_first and county_first and prop_first <= county_first
    )
    return (
        tid,
        row["taxon_name"],
        row["common_name"],
        county_count,
        state_count,
        county_first,
        state_first,
        prop_first,
        row["property_obs_count"],
        int(is_county_first),
        state_count,
    )


def refresh_stats(verbose=True, workers=DEFAULT_STATS_WORKERS):
    """Refresh uniqueness stats for stale/new property taxa. Returns count."""
    with connect() as conn:
        todo = _stale_or_missing(conn)

    if not todo:
        if verbose:
            print("[stats] refreshed 0 taxa (0 were stale/new)")
        return 0

    workers = max(1, int(workers or 1))
    rows = []
    if workers == 1 or len(todo) == 1:
        for row in todo:
            rows.append(_stats_for_taxon(row))
            if verbose:
                flag = " *COUNTY FIRST*" if rows[-1][9] else ""
                print(f"[stats] {rows[-1][1]}: county={rows[-1][3]} "
                      f"state={rows[-1][4]}{flag}")
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as pool:
            futures = [pool.submit(_stats_for_taxon, row) for row in todo]
            for future in as_completed(futures):
                result = future.result()
                rows.append(result)
                if verbose:
                    flag = " *COUNTY FIRST*" if result[9] else ""
                    print(f"[stats] {result[1]}: county={result[3]} "
                          f"state={result[4]}{flag}")

    with connect() as conn:
        conn.executemany(UPSERT, rows)

    if verbose:
        print(f"[stats] refreshed {len(rows)} taxa "
              f"({len(todo)} were stale/new)")
    return len(rows)
