"""Incremental sync of property and county observations into SQLite."""

import inat_api
from config import (BUTTERFLY_TAXON_ID, COUNTY_PLACE_ID, LEPIDOPTERA_TAXON_ID,
                    PROPERTY_PROJECT_ID)
from db import connect, max_id, record_sync


def _parse_location(obs):
    """iNat returns location as a 'lat,lng' string (or None when obscured)."""
    loc = obs.get("location")
    if not loc:
        return None, None
    try:
        lat, lng = loc.split(",")
        return float(lat), float(lng)
    except (ValueError, AttributeError):
        return None, None


def _first_photo(obs):
    """(medium_url, attribution, license) for the first photo, or (None,)*3.

    iNat serves several sizes off one path; swap the 'square' thumb for the
    larger 'medium' rendition used in the gallery.
    """
    photos = obs.get("photos") or []
    if not photos:
        return None, None, None
    p = photos[0]
    url = (p.get("url") or "").replace("square", "medium") or None
    return url, p.get("attribution"), p.get("license_code")


def _property_row(obs):
    taxon = obs.get("taxon") or {}
    user = obs.get("user") or {}
    lat, lng = _parse_location(obs)
    photo_url, photo_attr, photo_lic = _first_photo(obs)
    return (
        obs["id"],
        obs.get("uuid"),
        obs.get("observed_on"),
        obs.get("time_observed_at"),
        taxon.get("id"),
        taxon.get("name"),
        taxon.get("preferred_common_name"),
        taxon.get("iconic_taxon_name"),
        taxon.get("rank"),
        obs.get("quality_grade"),
        user.get("login"),
        user.get("name"),
        lat,
        lng,
        obs.get("uri"),
        obs.get("created_at"),
        photo_url,
        photo_attr,
        photo_lic,
    )


def _county_row(obs):
    taxon = obs.get("taxon") or {}
    user = obs.get("user") or {}
    return (
        obs["id"],
        obs.get("observed_on"),
        taxon.get("id"),
        taxon.get("name"),
        taxon.get("preferred_common_name"),
        taxon.get("iconic_taxon_name"),
        obs.get("quality_grade"),
        user.get("login"),
    )


PROPERTY_INSERT = (
    "INSERT OR REPLACE INTO property_obs "
    "(id, uuid, observed_on, observed_at, taxon_id, taxon_name, common_name, "
    " iconic_taxon, rank, quality_grade, user_login, user_name, latitude, "
    " longitude, url, created_at, photo_url, photo_attribution, photo_license) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

COUNTY_INSERT = (
    "INSERT OR REPLACE INTO county_obs "
    "(id, observed_on, taxon_id, taxon_name, common_name, iconic_taxon, "
    " quality_grade, user_login) "
    "VALUES (?,?,?,?,?,?,?,?)"
)


def _distinct_taxa(conn, table):
    rows = conn.execute(
        f"SELECT DISTINCT taxon_id FROM {table} WHERE taxon_id IS NOT NULL"
    ).fetchall()
    return {r["taxon_id"] for r in rows}


def sync_property():
    """Pull the full project (small enough that a clean cursor sweep is fine;
    INSERT OR REPLACE makes it idempotent and self-healing on re-runs)."""
    with connect() as conn:
        before_taxa = _distinct_taxa(conn, "property_obs")
        before_count = conn.execute(
            "SELECT COUNT(*) AS c FROM property_obs"
        ).fetchone()["c"]
        last_created = None
        for obs in inat_api.iter_all(project_id=PROPERTY_PROJECT_ID):
            conn.execute(PROPERTY_INSERT, _property_row(obs))
            last_created = obs.get("created_at") or last_created
        after_count = conn.execute(
            "SELECT COUNT(*) AS c FROM property_obs"
        ).fetchone()["c"]
        after_taxa = _distinct_taxa(conn, "property_obs")
        added = after_count - before_count
        new_species = len(after_taxa - before_taxa)
        record_sync(conn, "property", last_created, added, new_species)
    print(f"[property] total {after_count} obs (+{added}), "
          f"+{new_species} new species")
    return added, new_species


def sync_county():
    """Ingest county observations beyond what we already have via id_above.

    First run sweeps all ~25.5k; later runs resume from the max stored id and
    only fetch newer observations.
    """
    with connect() as conn:
        cursor = max_id(conn, "county_obs")
        before_count = conn.execute(
            "SELECT COUNT(*) AS c FROM county_obs"
        ).fetchone()["c"]
        added = 0
        for obs in inat_api.iter_all(id_above=cursor, place_id=COUNTY_PLACE_ID):
            conn.execute(COUNTY_INSERT, _county_row(obs))
            added += 1
        after_count = before_count + added
        record_sync(conn, "county", None, added, 0)
    print(f"[county] total {after_count} obs (+{added})")
    return added, 0


def _sync_roster(table, count_col, **params):
    """Refresh a species roster table from /observations/species_counts.

    Stores (taxon_id, taxon_name, common_name, <count_col>, photo_url) for every
    species matching `params`. Used for moths, butterflies, and the county moth
    checklist — each is just a different species_counts filter.
    """
    rows = []
    for row in inat_api.iter_species_counts(rank="species", **params):
        t = row.get("taxon") or {}
        photo = (t.get("default_photo") or {}).get("medium_url")
        rows.append((t.get("id"), t.get("name"),
                     t.get("preferred_common_name"), row.get("count"), photo))
    with connect() as conn:
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} "
            f"(taxon_id, taxon_name, common_name, {count_col}, photo_url) "
            "VALUES (?,?,?,?,?)", rows)
    return len(rows)


def sync_moths():
    """Moth roster (Lepidoptera minus butterflies) for the project."""
    n = _sync_roster("moth_taxa", "obs_count",
                     project_id=PROPERTY_PROJECT_ID,
                     taxon_id=LEPIDOPTERA_TAXON_ID,
                     without_taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[moths] {n} moth species")
    return n, 0


def sync_butterflies():
    """Butterfly roster (Papilionoidea) for the project — for the Lepidoptera
    split in life-list groups."""
    n = _sync_roster("butterfly_taxa", "obs_count",
                     project_id=PROPERTY_PROJECT_ID,
                     taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[butterflies] {n} butterfly species")
    return n, 0


def sync_county_moths():
    """Tioga County moth checklist — for the 'moths you haven't found yet' gap."""
    n = _sync_roster("county_moth_taxa", "county_count",
                     place_id=COUNTY_PLACE_ID,
                     taxon_id=LEPIDOPTERA_TAXON_ID,
                     without_taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[county-moths] {n} county moth species")
    return n, 0


def sync_taxonomy(batch_size=30):
    """Fill taxon_meta (order/family names) for property species missing it.

    Incremental: only fetches taxa not already cached, so nightly runs touch the
    API only for newly recorded species.
    """
    with connect() as conn:
        todo = [r["taxon_id"] for r in conn.execute(
            "SELECT DISTINCT p.taxon_id FROM property_obs p "
            "LEFT JOIN taxon_meta m ON m.taxon_id = p.taxon_id "
            "WHERE p.taxon_id IS NOT NULL AND m.taxon_id IS NULL"
        ).fetchall()]
    added = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        rows = []
        for t in inat_api.fetch_taxa(batch):
            ranks = {a.get("rank"): a for a in (t.get("ancestors") or [])}
            order = ranks.get("order") or {}
            family = ranks.get("family") or {}
            rows.append((t.get("id"),
                         order.get("name"), order.get("preferred_common_name"),
                         family.get("name"), family.get("preferred_common_name")))
        with connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO taxon_meta "
                "(taxon_id, order_name, order_common, family_name, family_common) "
                "VALUES (?,?,?,?,?)", rows)
        added += len(rows)
    print(f"[taxonomy] enriched {added} taxa ({len(todo)} were missing)")
    return added, 0
