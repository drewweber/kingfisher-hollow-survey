"""Per-taxon uniqueness lookups: how rare is each property species in the
county and across New York State? Cached in species_stats with a TTL so
nightly runs only hit the API for new or stale taxa."""

import inat_api
from config import COUNTY_PLACE_ID, STATE_PLACE_ID, STATS_TTL_DAYS
from db import connect


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
          AND (s.taxon_id IS NULL
               OR s.cached_at < datetime('now', ?))
        GROUP BY p.taxon_id
        """,
        (f"-{STATS_TTL_DAYS} days",),
    ).fetchall()


UPSERT = (
    "INSERT OR REPLACE INTO species_stats "
    "(taxon_id, taxon_name, common_name, county_obs_count, state_obs_count, "
    " county_first_date, state_first_date, property_first_date, "
    " property_obs_count, is_county_first, state_rarity_rank, cached_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))"
)


def refresh_stats(verbose=True):
    """Refresh uniqueness stats for stale/new property taxa. Returns count."""
    with connect() as conn:
        todo = _stale_or_missing(conn)

    refreshed = 0
    for row in todo:
        tid = row["taxon_id"]
        county_count = inat_api.count(taxon_id=tid, place_id=COUNTY_PLACE_ID)
        state_count = inat_api.count(taxon_id=tid, place_id=STATE_PLACE_ID)
        county_first = inat_api.first_observed_date(
            taxon_id=tid, place_id=COUNTY_PLACE_ID
        )
        state_first = inat_api.first_observed_date(
            taxon_id=tid, place_id=STATE_PLACE_ID
        )
        prop_first = row["property_first_date"]
        # A county first record: nobody in the county recorded it before us.
        is_county_first = bool(
            prop_first and county_first and prop_first <= county_first
        )
        with connect() as conn:
            conn.execute(
                UPSERT,
                (
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
                    state_count,  # state_rarity_rank: low total == rare in NY
                ),
            )
        refreshed += 1
        if verbose:
            flag = " *COUNTY FIRST*" if is_county_first else ""
            print(f"[stats] {row['taxon_name']}: county={county_count} "
                  f"state={state_count}{flag}")
    if verbose:
        print(f"[stats] refreshed {refreshed} taxa "
              f"({len(todo)} were stale/new)")
    return refreshed
