"""Incremental sync of property and county observations into SQLite."""

import inat_api
from config import (AMPHIBIA_TAXON_ID, BUTTERFLY_TAXON_ID, COUNTY_PLACE_ID,
                    LEPIDOPTERA_TAXON_ID, MAMMALIA_TAXON_ID, PLANTAE_TAXON_ID,
                    PROPERTY_PROJECT_ID, REGION_RADIUS_KM, REPTILIA_TAXON_ID,
                    STATE_PLACE_ID)
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


def observation_dates():
    """Sorted list of all distinct observed_on dates in property_obs."""
    import datetime
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT observed_on FROM property_obs "
            "WHERE observed_on IS NOT NULL ORDER BY observed_on"
        ).fetchall()
    return [datetime.date.fromisoformat(r[0]) for r in rows]


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


def _bool_int(value):
    if value is None:
        return None
    return 1 if bool(value) else 0


def _taxon_establishment(taxon):
    means = taxon.get("preferred_establishment_means")
    if means:
        return means
    establishment = taxon.get("establishment_means") or {}
    return establishment.get("establishment_means")


def _establishment_flags(means):
    if not means:
        return None, None
    return _bool_int(means in ("native", "endemic")), _bool_int(means == "introduced")


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
        _bool_int(obs.get("captive")),
        _bool_int(taxon.get("native")),
        _bool_int(taxon.get("introduced")),
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
        _bool_int(obs.get("captive")),
    )


PROPERTY_INSERT = (
    "INSERT OR REPLACE INTO property_obs "
    "(id, uuid, observed_on, observed_at, taxon_id, taxon_name, common_name, "
    " iconic_taxon, rank, quality_grade, user_login, user_name, latitude, "
    " longitude, url, created_at, photo_url, photo_attribution, photo_license, "
    " captive, taxon_native, taxon_introduced) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

COUNTY_INSERT = (
    "INSERT OR REPLACE INTO county_obs "
    "(id, observed_on, taxon_id, taxon_name, common_name, iconic_taxon, "
    " quality_grade, user_login, captive) "
    "VALUES (?,?,?,?,?,?,?,?,?)"
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


def _sync_roster(table, count_col, include_establishment=False, **params):
    """Refresh a species roster table from /observations/species_counts.

    Stores (taxon_id, taxon_name, common_name, <count_col>, photo_url) for every
    species matching `params`. Used for moths, butterflies, and the county moth
    checklist — each is just a different species_counts filter.
    """
    rows = []
    for row in inat_api.iter_species_counts(rank="species", **params):
        t = row.get("taxon") or {}
        photo = (t.get("default_photo") or {}).get("medium_url")
        base = [t.get("id"), t.get("name"),
                t.get("preferred_common_name"), row.get("count"), photo]
        if include_establishment:
            means = _taxon_establishment(t)
            native, introduced = _establishment_flags(means)
            base.extend([
                means,
                native if native is not None else _bool_int(t.get("native")),
                introduced if introduced is not None else _bool_int(t.get("introduced")),
            ])
        rows.append(tuple(base))
    with connect() as conn:
        conn.execute(f"DELETE FROM {table}")
        if include_establishment:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} "
                f"(taxon_id, taxon_name, common_name, {count_col}, photo_url, "
                "establishment_means, native, introduced) "
                "VALUES (?,?,?,?,?,?,?,?)", rows)
        else:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} "
                f"(taxon_id, taxon_name, common_name, {count_col}, photo_url) "
                "VALUES (?,?,?,?,?)", rows)
    return len(rows)


_STATE_PLANT_ESTABLISHMENT = None


def _state_plant_establishment_map():
    """New York establishment status keyed by taxon_id.

    Radius-based species_counts do not consistently include establishment
    status, so plant gap filtering needs a separate state-checklist pass.
    """
    global _STATE_PLANT_ESTABLISHMENT
    if _STATE_PLANT_ESTABLISHMENT is not None:
        return _STATE_PLANT_ESTABLISHMENT

    status = {}
    for row in inat_api.iter_species_counts(
            rank="species",
            place_id=STATE_PLACE_ID,
            taxon_id=PLANTAE_TAXON_ID,
            captive="false"):
        t = row.get("taxon") or {}
        means = _taxon_establishment(t)
        if means and t.get("id"):
            status[t.get("id")] = means
    _STATE_PLANT_ESTABLISHMENT = status
    return status


def _apply_state_plant_establishment(table):
    """Backfill New York native/introduced flags for plant roster tables."""
    with connect() as conn:
        ids = {row["taxon_id"] for row in conn.execute(
            f"SELECT taxon_id FROM {table} WHERE taxon_id IS NOT NULL"
        ).fetchall()}
    if not ids:
        return

    status = _state_plant_establishment_map()
    updates = []
    for taxon_id in ids:
        means = status.get(taxon_id)
        if not means:
            continue
        native, introduced = _establishment_flags(means)
        updates.append((means, native, introduced, taxon_id))
    if updates:
        with connect() as conn:
            conn.executemany(
                f"UPDATE {table} SET establishment_means = ?, native = ?, introduced = ? "
                "WHERE taxon_id = ?",
                updates)


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
    split in life-list groups and the butterflies view."""
    n = _sync_roster("butterfly_taxa", "obs_count",
                     project_id=PROPERTY_PROJECT_ID,
                     taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[butterflies] {n} butterfly species")
    return n, 0


def sync_region_butterflies():
    """Butterflies recorded within REGION_RADIUS_KM of the property."""
    lat, lng = _property_center()
    if lat is None:
        print("[region-butterflies] no property coordinates yet; skipping")
        return 0, 0
    n = _sync_roster("region_butterfly_taxa", "region_count",
                     lat=round(lat, 5), lng=round(lng, 5), radius=REGION_RADIUS_KM,
                     taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[region-butterflies] {n} butterfly species within {REGION_RADIUS_KM} km")
    return n, 0


def sync_county_moths():
    """Tioga County moth checklist — for the 'moths you haven't found yet' gap."""
    n = _sync_roster("county_moth_taxa", "county_count",
                     place_id=COUNTY_PLACE_ID,
                     taxon_id=LEPIDOPTERA_TAXON_ID,
                     without_taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[county-moths] {n} county moth species")
    return n, 0


def _property_center():
    """Median lat/lng of recorded property observations — the regional center."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT latitude, longitude FROM property_obs "
            "WHERE latitude IS NOT NULL AND longitude IS NOT NULL").fetchall()
    if not rows:
        return None, None
    import statistics
    return (statistics.median(r["latitude"] for r in rows),
            statistics.median(r["longitude"] for r in rows))


def sync_region_moths():
    """Moths recorded within REGION_RADIUS_KM of the property — a better-sampled
    regional reference than the county for the gap analysis."""
    lat, lng = _property_center()
    if lat is None:
        print("[region-moths] no property coordinates yet; skipping")
        return 0, 0
    n = _sync_roster("region_moth_taxa", "region_count",
                     lat=round(lat, 5), lng=round(lng, 5), radius=REGION_RADIUS_KM,
                     taxon_id=LEPIDOPTERA_TAXON_ID,
                     without_taxon_id=BUTTERFLY_TAXON_ID)
    print(f"[region-moths] {n} moth species within {REGION_RADIUS_KM} km")
    return n, 0


def sync_mammals():
    """Mammal roster for the project."""
    n = _sync_roster("mammal_taxa", "obs_count",
                     project_id=PROPERTY_PROJECT_ID,
                     taxon_id=MAMMALIA_TAXON_ID)
    print(f"[mammals] {n} mammal species")
    return n, 0


def sync_region_mammals():
    """Mammals recorded within REGION_RADIUS_KM of the property."""
    lat, lng = _property_center()
    if lat is None:
        print("[region-mammals] no property coordinates yet; skipping")
        return 0, 0
    n = _sync_roster("region_mammal_taxa", "region_count",
                     lat=round(lat, 5), lng=round(lng, 5), radius=REGION_RADIUS_KM,
                     taxon_id=MAMMALIA_TAXON_ID)
    print(f"[region-mammals] {n} mammal species within {REGION_RADIUS_KM} km")
    return n, 0


def _restore_plant_groups(table):
    """Re-apply plant_group classifications after a roster sync wipes the column.

    Saves the existing (taxon_id → plant_group) mapping before the sync runs,
    restores it after, and classifies any new taxa via the iNat ancestry API.
    Returns a context manager that wraps the sync call.
    """
    import contextlib
    @contextlib.contextmanager
    def _ctx():
        # Ensure column exists (fresh CI database won't have it)
        with connect() as conn:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN plant_group TEXT")
            except Exception:
                pass  # already exists

        # 1. Save current mappings
        saved = {}
        with connect() as conn:
            for row in conn.execute(
                    f"SELECT taxon_id, plant_group FROM {table} WHERE plant_group IS NOT NULL"):
                saved[row[0]] = row[1]

        yield  # sync runs here

        # 2. Restore saved mappings
        if saved:
            with connect() as conn:
                conn.executemany(
                    f"UPDATE {table} SET plant_group = ? WHERE taxon_id = ?",
                    [(g, tid) for tid, g in saved.items()])

        # 3. Classify any new taxa that have no plant_group yet
        _classify_new_plant_taxa(table, saved)

    return _ctx()


def _classify_new_plant_taxa(table, already_classified):
    """Fetch iNat ancestry for taxa missing plant_group and classify them."""
    TRACHEOPHYTA = 211194
    ANGIOSPERM   = 47125
    CONIFER      = 136329

    with connect() as conn:
        unclassified = [row[0] for row in conn.execute(
            f"SELECT taxon_id FROM {table} WHERE plant_group IS NULL")]
    if not unclassified:
        return

    def classify(ancestry_str):
        ids = {int(x) for x in ancestry_str.split("/") if x}
        if TRACHEOPHYTA not in ids:
            return "Bryophyte"
        if ANGIOSPERM in ids:
            return "Angiosperm"
        if CONIFER in ids:
            return "Gymnosperm"
        return "Seedless Vascular"

    BATCH = 30
    updates = []
    for i in range(0, len(unclassified), BATCH):
        try:
            taxa = inat_api.fetch_taxa(unclassified[i:i + BATCH])
        except Exception:
            continue
        for t in taxa:
            grp = classify(t.get("ancestry") or "")
            updates.append((grp, t["id"]))

    if updates:
        with connect() as conn:
            conn.executemany(
                f"UPDATE {table} SET plant_group = ? WHERE taxon_id = ?", updates)


def sync_plants():
    """Wild/naturalized plant roster for the project.

    iNaturalist uses captive=false for plants that are not marked cultivated,
    which keeps planted ornamentals from inflating the property plant baseline.
    """
    with _restore_plant_groups("plant_taxa"):
        n = _sync_roster("plant_taxa", "obs_count",
                         project_id=PROPERTY_PROJECT_ID,
                         taxon_id=PLANTAE_TAXON_ID,
                         captive="false",
                         include_establishment=True)
    _apply_state_plant_establishment("plant_taxa")
    print(f"[plants] {n} wild/established plant species")
    return n, 0


def sync_region_plants():
    """Wild/naturalized plants recorded within REGION_RADIUS_KM of the property."""
    lat, lng = _property_center()
    if lat is None:
        print("[region-plants] no property coordinates yet; skipping")
        return 0, 0
    with _restore_plant_groups("region_plant_taxa"):
        n = _sync_roster("region_plant_taxa", "region_count",
                         lat=round(lat, 5), lng=round(lng, 5), radius=REGION_RADIUS_KM,
                         taxon_id=PLANTAE_TAXON_ID,
                         captive="false",
                         include_establishment=True)
    _apply_state_plant_establishment("region_plant_taxa")
    print(f"[region-plants] {n} wild/established plant species within {REGION_RADIUS_KM} km")
    return n, 0


def sync_amphibians():
    """Amphibian roster for the project."""
    n = _sync_roster("amphibian_taxa", "obs_count",
                     project_id=PROPERTY_PROJECT_ID,
                     taxon_id=AMPHIBIA_TAXON_ID)
    print(f"[amphibians] {n} amphibian species")
    return n, 0


def sync_region_amphibians():
    """Amphibians recorded within REGION_RADIUS_KM of the property."""
    lat, lng = _property_center()
    if lat is None:
        print("[region-amphibians] no property coordinates yet; skipping")
        return 0, 0
    n = _sync_roster("region_amphibian_taxa", "region_count",
                     lat=round(lat, 5), lng=round(lng, 5), radius=REGION_RADIUS_KM,
                     taxon_id=AMPHIBIA_TAXON_ID)
    print(f"[region-amphibians] {n} amphibian species within {REGION_RADIUS_KM} km")
    return n, 0


def sync_reptiles():
    """Reptile roster for the project."""
    n = _sync_roster("reptile_taxa", "obs_count",
                     project_id=PROPERTY_PROJECT_ID,
                     taxon_id=REPTILIA_TAXON_ID)
    print(f"[reptiles] {n} reptile species")
    return n, 0


def sync_region_reptiles():
    """Reptiles recorded within REGION_RADIUS_KM of the property."""
    lat, lng = _property_center()
    if lat is None:
        print("[region-reptiles] no property coordinates yet; skipping")
        return 0, 0
    n = _sync_roster("region_reptile_taxa", "region_count",
                     lat=round(lat, 5), lng=round(lng, 5), radius=REGION_RADIUS_KM,
                     taxon_id=REPTILIA_TAXON_ID)
    print(f"[region-reptiles] {n} reptile species within {REGION_RADIUS_KM} km")
    return n, 0


def sync_taxonomy(batch_size=30):
    """Fill taxon_meta (order/family names) for property species missing it.

    Incremental: only fetches taxa not already cached, so nightly runs touch the
    API only for newly recorded species.
    """
    # Enrich every taxon we display family/order for: property species *and* the
    # county moth checklist (needed for the per-family recorded-vs-county chart).
    with connect() as conn:
        todo = [r["taxon_id"] for r in conn.execute(
            "SELECT taxon_id FROM ("
            "  SELECT taxon_id FROM property_obs WHERE taxon_id IS NOT NULL"
            "  UNION SELECT taxon_id FROM county_moth_taxa WHERE taxon_id IS NOT NULL"
            "  UNION SELECT taxon_id FROM region_moth_taxa WHERE taxon_id IS NOT NULL"
            ") t LEFT JOIN taxon_meta m USING (taxon_id) WHERE m.taxon_id IS NULL"
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
