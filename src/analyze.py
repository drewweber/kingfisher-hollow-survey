"""pandas analyses over the SQLite tables. Each function returns a DataFrame
(or dict) that viz.py turns into a chart, keeping data and presentation apart."""

import pandas as pd

from config import REGION_RADIUS_KM, SPECIES_RANKS
from db import connect


def _join_taxonomy(df):
    """Merge order_name/family_name/family_common from taxon_meta into df.

    Used to enable taxonomic sorting in found-species grids. Rows with no
    taxon_meta entry get empty strings so sort order is stable.
    """
    with connect() as conn:
        meta = pd.read_sql_query(
            "SELECT taxon_id, order_name, family_name, family_common FROM taxon_meta",
            conn)
    df = df.merge(meta, on="taxon_id", how="left")
    for col in ("order_name", "family_name", "family_common"):
        df[col] = df[col].fillna("")
    return df


def _session_dates(sub, cutoff_hour=12):
    """Return a Series of session dates for mothing analysis.

    Mothing sessions span an evening and the following morning, so observations
    recorded before cutoff_hour are rolled back to the prior day. This ensures
    the morning check after a light-trap session is counted as the same survey
    night as the evening that started it, keeping Chao2 and survey-night counts
    accurate. Falls back to observed_on for rows without a timestamp.
    """
    # observed_at is stored as local ISO-8601 e.g. "2025-06-24T06:26:45-04:00".
    # The hour digits at positions 11-12 are already local time.
    hour = pd.to_numeric(sub["observed_at"].str[11:13], errors="coerce")
    base = sub["observed_on"].dt.normalize()  # midnight of each observed_on date
    rollback = hour.notna() & (hour < cutoff_hour)
    adjusted = base - pd.to_timedelta(rollback.astype(int), unit="D")
    return adjusted.dt.date


def load_property(species_only=True):
    """Property observations as a DataFrame with parsed date columns.

    By default restricted to species-level records (rank 'species' or finer);
    coarser IDs like genus/family are observations not resolved to a species.
    Birds (Aves) are excluded entirely — they're tracked on eBird instead.
    """
    with connect() as conn:
        df = pd.read_sql_query("SELECT * FROM property_obs", conn)
    df = df[df["iconic_taxon"] != "Aves"].copy()
    if species_only:
        df = df[df["rank"].isin(SPECIES_RANKS)].copy()
    df["observed_on"] = pd.to_datetime(df["observed_on"], errors="coerce")
    df["created_at"] = pd.to_datetime(
        df["created_at"], errors="coerce", utc=True
    )
    return df


def species_taxon_ids():
    """Set of species-level taxon_ids on the property — used to keep the
    uniqueness stats (which are cached per-taxon) species-level too."""
    return set(load_property()["taxon_id"].dropna().astype(int))


def load_stats():
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM species_stats", conn)


def _load_table(name):
    with connect() as conn:
        return pd.read_sql_query(f"SELECT * FROM {name}", conn)


# --- group labels (readable higher taxon) -----------------------------------
# Non-arthropod iconic taxa map straight to a friendly label; arthropods get
# their order's common name (so people can tell a harvestman from a moth).
ICONIC_LABELS = {
    "Plantae": "Plants", "Fungi": "Fungi", "Mammalia": "Mammals",
    "Amphibia": "Amphibians", "Reptilia": "Reptiles",
    "Actinopterygii": "Fish", "Mollusca": "Molluscs", "Animalia": "Other animals",
    "Protozoa": "Protozoans", "Chromista": "Chromists",
}


def group_labeler(moth_ids, butterfly_ids, order_common_by_taxon):
    """Build a function mapping a (taxon_id, iconic_taxon) to a readable group:
    Moths / Butterflies split out of Lepidoptera; other arthropods by order
    common name; everything else by a friendly iconic-taxon label."""
    def label(taxon_id, iconic):
        if taxon_id in moth_ids:
            return "Moths"
        if taxon_id in butterfly_ids:
            return "Butterflies"
        if iconic in ("Insecta", "Arachnida"):
            oc = order_common_by_taxon.get(taxon_id)
            # Lepidoptera not caught by the (verifiable) moth/butterfly rosters
            # are stragglers — almost always moths; butterflies handled above.
            if oc == "Butterflies and Moths":
                return "Moths"
            if oc:
                return oc
            return "Insects" if iconic == "Insecta" else "Arachnids"
        return ICONIC_LABELS.get(iconic, iconic or "Other")
    return label


def _group_inputs():
    """Load the membership sets + order-common map used for group labels."""
    moth_ids = set(_load_table("moth_taxa")["taxon_id"].dropna().astype(int))
    bf = _load_table("butterfly_taxa")
    butterfly_ids = set(bf["taxon_id"].dropna().astype(int)) if not bf.empty else set()
    meta = _load_table("taxon_meta")
    order_common = {}
    if not meta.empty:
        for _, r in meta.iterrows():
            oc = r.get("order_common") or r.get("order_name")
            if oc:
                order_common[int(r["taxon_id"])] = oc
    return moth_ids, butterfly_ids, order_common


def add_group_column(df):
    """Return df with a `group` column (readable higher taxon)."""
    moth_ids, butterfly_ids, order_common = _group_inputs()
    label = group_labeler(moth_ids, butterfly_ids, order_common)
    out = df.copy()
    out["group"] = [label(t, i) for t, i in
                    zip(out["taxon_id"], out.get("iconic_taxon"))]
    return out


# --- summary ----------------------------------------------------------------
def summary(df):
    return {
        "observations": len(df),
        "species": df["taxon_id"].nunique(),
        "observers": df["user_login"].nunique(),
        "research_grade": int((df["quality_grade"] == "research").sum()),
        "first_obs": df["observed_on"].min(),
        "latest_obs": df["observed_on"].max(),
    }


# --- what's new since last night --------------------------------------------
def whats_new(df, stats, days=2):
    """Observations created in the last `days`, with first-for-property and
    rarity flags joined in. This is the headline section of the report."""
    if df.empty or df["created_at"].isna().all():
        return pd.DataFrame()
    cutoff = df["created_at"].max() - pd.Timedelta(days=days)
    recent = df[df["created_at"] >= cutoff].copy()
    if recent.empty:
        return recent

    # First-ever appearance (by creation order) of each taxon on the property.
    recent["is_new_for_property"] = (
        recent["created_at"] == recent["taxon_id"].map(
            df.groupby("taxon_id")["created_at"].min()
        )
    )

    rarity = stats.set_index("taxon_id")[
        ["county_obs_count", "state_obs_count", "is_county_first"]
    ]
    recent = recent.join(rarity, on="taxon_id")
    return recent.sort_values("created_at", ascending=False)


# --- accumulation curve -----------------------------------------------------
def species_accumulation(df):
    """Cumulative count of unique species over time (by first observed date)."""
    sub = df.dropna(subset=["taxon_id", "observed_on"])
    firsts = sub.groupby("taxon_id")["observed_on"].min().sort_values()
    acc = pd.DataFrame({"observed_on": firsts.values})
    acc["cumulative_species"] = range(1, len(acc) + 1)
    return acc


# --- observations per day ---------------------------------------------------
def obs_per_day(df):
    daily = (
        df.dropna(subset=["observed_on"])
        .groupby(df["observed_on"].dt.date)
        .size()
        .rename("observations")
        .reset_index()
    )
    daily["observed_on"] = pd.to_datetime(daily["observed_on"])
    daily = daily.sort_values("observed_on")
    daily["rolling_30d"] = daily["observations"].rolling(30, min_periods=1).mean()
    return daily


# --- phenology --------------------------------------------------------------
def phenology(df, iconic_taxon=None, top=40):
    """Species x month observation-count matrix (optionally one taxon group)."""
    sub = df.dropna(subset=["observed_on", "taxon_id"])
    if iconic_taxon:
        sub = sub[sub["iconic_taxon"] == iconic_taxon]
    if sub.empty:
        return pd.DataFrame()
    sub = sub.copy()
    sub["month"] = sub["observed_on"].dt.month
    label = sub["common_name"].fillna(sub["taxon_name"])
    sub = sub.assign(label=label)
    matrix = (
        sub.groupby(["label", "month"]).size().unstack(fill_value=0)
        .reindex(columns=range(1, 13), fill_value=0)
    )
    # Keep the chart legible: most-observed species first.
    matrix = matrix.loc[matrix.sum(axis=1).sort_values(ascending=False).index]
    return matrix.head(top)


# --- observer leaderboard (crediting contributors) --------------------------
def observer_leaderboard(df):
    grouped = df.groupby("user_login").agg(
        observations=("id", "count"),
        species=("taxon_id", "nunique"),
        display_name=("user_name", "first"),
    )
    # Species found ONLY by this observer (their unique contribution).
    taxa_by_user = (
        df.dropna(subset=["taxon_id"]).groupby("taxon_id")["user_login"].nunique()
    )
    solo_taxa = set(taxa_by_user[taxa_by_user == 1].index)
    solo = (
        df[df["taxon_id"].isin(solo_taxa)]
        .groupby("user_login")["taxon_id"]
        .nunique()
        .rename("unique_species")
    )
    out = grouped.join(solo).fillna({"unique_species": 0})
    out["unique_species"] = out["unique_species"].astype(int)
    return out.sort_values("observations", ascending=False).reset_index()


# --- uniqueness table -------------------------------------------------------
def uniqueness_table(df, stats):
    """Every property species with county/state counts and record flags,
    sorted so the rarest (and any county firsts) surface first."""
    if stats.empty:
        return stats
    out = stats.copy()
    out["label"] = out["common_name"].fillna(out["taxon_name"])
    out = out.sort_values(
        ["is_county_first", "state_obs_count"], ascending=[False, True]
    )
    return out


# --- representative photo per taxon ----------------------------------------
def _photo_by_taxon(df):
    """Map taxon_id -> (photo_url, attribution) using each taxon's most recent
    photographed observation. Empty if photos haven't been synced yet."""
    if "photo_url" not in df.columns:
        return {}
    photographed = df.dropna(subset=["photo_url", "taxon_id"]).sort_values(
        "observed_on"
    )
    out = {}
    for _, r in photographed.iterrows():
        out[r["taxon_id"]] = (r["photo_url"], r.get("photo_attribution"))
    return out


def _label(row):
    return row.get("common_name") or row.get("taxon_name") or "Unidentified"


# --- life list --------------------------------------------------------------
def life_list(df):
    """One row per species: names, group, rank, first/last seen, counts."""
    sub = df.dropna(subset=["taxon_id"])
    g = sub.groupby("taxon_id").agg(
        common_name=("common_name", "first"),
        taxon_name=("taxon_name", "first"),
        iconic_taxon=("iconic_taxon", "first"),
        rank=("rank", "first"),
        observations=("id", "count"),
        first_seen=("observed_on", "min"),
        last_seen=("observed_on", "max"),
        observers=("user_login", "nunique"),
    ).reset_index()
    g["label"] = g["common_name"].fillna(g["taxon_name"])
    g["iconic_taxon"] = g["iconic_taxon"].fillna("Other")
    g = add_group_column(g)
    return g.sort_values(["group", "label"])


# --- rarest finds (fewest NY records) --------------------------------------
def rarest_finds(df, stats, n=12):
    if stats.empty:
        return stats
    photos = _photo_by_taxon(df)
    out = stats.copy()
    out["label"] = out["common_name"].fillna(out["taxon_name"])
    out = out[out["state_obs_count"].notna() & (out["state_obs_count"] > 0)]
    out = out.sort_values("state_obs_count").head(n)
    out["photo_url"] = out["taxon_id"].map(lambda t: (photos.get(t) or (None,))[0])
    return out


# --- county-first showcase --------------------------------------------------
def county_first_showcase(df, stats, n=12):
    """Species where the property holds the earliest record in Tioga County,
    each with a representative photo. The headline 'how unique' feature."""
    if stats.empty:
        return stats
    photos = _photo_by_taxon(df)
    firsts = stats[stats["is_county_first"] == 1].copy()
    firsts["label"] = firsts["common_name"].fillna(firsts["taxon_name"])
    firsts = firsts.sort_values("state_obs_count")
    firsts["photo_url"] = firsts["taxon_id"].map(
        lambda t: (photos.get(t) or (None, None))[0]
    )
    firsts["photo_attribution"] = firsts["taxon_id"].map(
        lambda t: (photos.get(t) or (None, None))[1]
    )
    # Prefer ones we have a photo for, but keep the rest.
    firsts["_has_photo"] = firsts["photo_url"].notna()
    firsts = firsts.sort_values(
        ["_has_photo", "state_obs_count"], ascending=[False, True]
    )
    return firsts.head(n)


# --- species "firsts" timeline ---------------------------------------------
def firsts_timeline(df):
    """The first time each species was recorded on the property — the
    discovery story. One row per taxon at its first observation."""
    sub = df.dropna(subset=["taxon_id", "observed_on"]).sort_values("observed_on")
    first_idx = sub.groupby("taxon_id")["observed_on"].idxmin()
    firsts = sub.loc[first_idx].copy()
    firsts["label"] = firsts["common_name"].fillna(firsts["taxon_name"])
    firsts = firsts.sort_values("observed_on")
    firsts["cumulative"] = range(1, len(firsts) + 1)
    return firsts


# --- seasonal / migration timing -------------------------------------------
def _seasonal_agg(sub, min_obs, max_species):
    """Day-of-year distribution per species for a (pre-filtered) sub-frame."""
    sub = sub.dropna(subset=["observed_on", "taxon_id"]).copy()
    if sub.empty:
        return pd.DataFrame()
    sub["doy"] = sub["observed_on"].dt.dayofyear
    sub["label"] = sub["common_name"].fillna(sub["taxon_name"])
    agg = sub.groupby("label").agg(
        n=("id", "count"),
        first_doy=("doy", "min"),
        last_doy=("doy", "max"),
        median_doy=("doy", "median"),
        q1=("doy", lambda s: s.quantile(0.25)),
        q3=("doy", lambda s: s.quantile(0.75)),
    ).reset_index()
    agg = agg[agg["n"] >= min_obs]
    # Order by median appearance so the chart reads as a seasonal cascade.
    return agg.sort_values("median_doy").head(max_species)


def seasonal_timing(df, iconic_taxon="Aves", min_obs=4, max_species=28):
    """Per-species day-of-year distribution for an iconic taxon group."""
    return _seasonal_agg(df[df["iconic_taxon"] == iconic_taxon],
                         min_obs, max_species)


# --- photo highlights -------------------------------------------------------
def photo_highlights(df, n=18):
    """Recent research-grade observations that have a photo, for the gallery."""
    if "photo_url" not in df.columns:
        return pd.DataFrame()
    sub = df.dropna(subset=["photo_url"]).copy()
    research = sub[sub["quality_grade"] == "research"]
    sub = research if not research.empty else sub
    sub["label"] = sub["common_name"].fillna(sub["taxon_name"])
    return sub.sort_values("observed_on", ascending=False).head(n)


# --- mammals & plants shared gap helper -------------------------------------
def _region_gap(taxa, region_table, n=30, target_months=None):
    """Generic regional gap: species in region_table not yet in taxa, with optional
    seasonal filter via county_obs phenology. Mirrors moth_county_gap logic."""
    region = _load_table(region_table)
    have = set(taxa["taxon_id"].dropna().astype(int)) if not taxa.empty else set()

    if region.empty:
        return {"region_total": 0, "region_radius_km": REGION_RADIUS_KM, "have": len(have),
                "pct": 0, "missing_count": 0, "missing": region,
                "target_months": target_months or []}

    region_total = int(region["taxon_id"].nunique())
    region_have = int(region["taxon_id"].isin(have).sum())
    region_pct = round(100 * region_have / region_total) if region_total else 0

    missing = region[~region["taxon_id"].isin(have)].copy()
    missing["label"] = missing["common_name"].fillna(missing["taxon_name"])

    if target_months:
        month_strs = ",".join(f"'{m:02d}'" for m in target_months)
        with connect() as conn:
            rows = conn.execute(
                f"SELECT taxon_id, COUNT(*) AS cnt FROM county_obs "
                f"WHERE taxon_id IS NOT NULL "
                f"AND strftime('%m', observed_on) IN ({month_strs}) "
                f"GROUP BY taxon_id"
            ).fetchall()
        seasonal_counts = {int(r["taxon_id"]): int(r["cnt"]) for r in rows}
        missing = missing[missing["taxon_id"].isin(seasonal_counts)].copy()
        missing["ref_count"] = missing["taxon_id"].map(
            lambda tid: seasonal_counts.get(int(tid), 0)
        )
        missing = missing.sort_values("ref_count", ascending=False)
    else:
        missing["ref_count"] = missing["region_count"]
        missing = missing.sort_values("region_count", ascending=False)

    return {
        "region_total": region_total,
        "region_radius_km": REGION_RADIUS_KM,
        "have": region_have,
        "pct": region_pct,
        "missing_count": int(len(missing)),
        "missing": missing.head(n),
        "target_months": target_months or [],
    }


# --- mammals -----------------------------------------------------------------
def load_mammals():
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM mammal_taxa", conn)


def mammal_summary(df, mammals):
    ids = set(mammals["taxon_id"].dropna())
    sub = df[df["taxon_id"].isin(ids)]
    return {
        "species": int(mammals["taxon_id"].nunique()),
        "records": int(len(sub)),
        "top_month": _peak_month(sub) if not sub.empty else "",
    }


_EXCLUDE_FROM_MAMMALS = {43584}  # Homo sapiens


def mammal_found(df, mammals):
    """Recorded mammals sorted taxonomically (order → family → species)."""
    if mammals.empty:
        return mammals
    found = mammals[~mammals["taxon_id"].isin(_EXCLUDE_FROM_MAMMALS)].copy()
    counts = (df[df["taxon_id"].isin(set(found["taxon_id"].dropna()))]
              .groupby("taxon_id").size())
    found["ref_count"] = found["taxon_id"].map(counts).fillna(0).astype(int)
    found["label"] = found["common_name"].fillna(found["taxon_name"])
    found = _join_taxonomy(found)
    return found.sort_values(["order_name", "family_name", "taxon_name"])


def mammal_gap(mammals, n=30, target_months=None):
    gap = _region_gap(mammals, "region_mammal_taxa", n=n + 5, target_months=target_months)
    gap["missing"] = gap["missing"][
        ~gap["missing"]["taxon_id"].isin(_EXCLUDE_FROM_MAMMALS)
    ].head(n)
    return gap


# --- plants ------------------------------------------------------------------
def load_plants():
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM plant_taxa", conn)


def plant_summary(df, plants):
    ids = set(plants["taxon_id"].dropna())
    sub = df[df["taxon_id"].isin(ids)]
    return {
        "species": int(plants["taxon_id"].nunique()),
        "records": int(len(sub)),
        "top_month": _peak_month(sub) if not sub.empty else "",
    }


def plant_found(df, plants):
    """Recorded plants sorted taxonomically (order → family → species)."""
    if plants.empty:
        return plants
    found = plants.copy()
    counts = (df[df["taxon_id"].isin(set(found["taxon_id"].dropna()))]
              .groupby("taxon_id").size())
    found["ref_count"] = found["taxon_id"].map(counts).fillna(0).astype(int)
    found["label"] = found["common_name"].fillna(found["taxon_name"])
    found = _join_taxonomy(found)
    return found.sort_values(["order_name", "family_name", "taxon_name"])


def plant_gap(plants, n=50, target_months=None):
    return _region_gap(plants, "region_plant_taxa", n=n, target_months=target_months)


# --- amphibians --------------------------------------------------------------
def load_amphibians():
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM amphibian_taxa", conn)


def amphibian_summary(df, amphibians):
    ids = set(amphibians["taxon_id"].dropna())
    sub = df[df["taxon_id"].isin(ids)]
    return {
        "species": int(amphibians["taxon_id"].nunique()),
        "records": int(len(sub)),
        "top_month": _peak_month(sub) if not sub.empty else "",
    }


def amphibian_found(df, amphibians):
    """Recorded amphibians sorted taxonomically (order → family → species)."""
    if amphibians.empty:
        return amphibians
    found = amphibians.copy()
    counts = (df[df["taxon_id"].isin(set(found["taxon_id"].dropna()))]
              .groupby("taxon_id").size())
    found["ref_count"] = found["taxon_id"].map(counts).fillna(0).astype(int)
    found["label"] = found["common_name"].fillna(found["taxon_name"])
    found = _join_taxonomy(found)
    return found.sort_values(["order_name", "family_name", "taxon_name"])


# Captive / out-of-range exotics that appear in the iNat regional pool (zoo,
# classroom, and pet records) but are not realistic field targets. Mirrors the
# _EXCLUDE_FROM_MAMMALS approach.
_EXCLUDE_FROM_AMPHIBIANS = {
    21121,  # Green-and-black Poison Dart Frog
    21217,  # Golden Poison Dart Frog
    23702,  # Red-eyed Tree Frog
    25457,  # African Clawed Frog
    26777,  # Axolotl
    66278,  # Strawberry Poison Dart Frog
}


def amphibian_gap(amphibians, n=30):
    """Regional amphibians not yet recorded here, ranked by regional frequency.

    Deliberately non-seasonal: amphibians are strongly spring-peaked, so a
    single-month slice surfaces almost nothing in summer. We rank by overall
    regional frequency and drop obvious captive/non-native pool records.
    """
    gap = _region_gap(amphibians, "region_amphibian_taxa",
                      n=n + len(_EXCLUDE_FROM_AMPHIBIANS))
    gap["missing"] = gap["missing"][
        ~gap["missing"]["taxon_id"].isin(_EXCLUDE_FROM_AMPHIBIANS)
    ].head(n)
    return gap


# --- butterflies -------------------------------------------------------------
def load_butterflies():
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM butterfly_taxa", conn)


def butterfly_summary(df, butterflies):
    ids = set(butterflies["taxon_id"].dropna())
    sub = df[df["taxon_id"].isin(ids)]
    return {
        "species": int(butterflies["taxon_id"].nunique()),
        "records": int(len(sub)),
        "top_month": _peak_month(sub) if not sub.empty else "",
    }


def butterfly_found(df, butterflies):
    """Recorded butterflies sorted taxonomically (family → species)."""
    if butterflies.empty:
        return butterflies
    found = butterflies.copy()
    counts = (df[df["taxon_id"].isin(set(found["taxon_id"].dropna()))]
              .groupby("taxon_id").size())
    found["ref_count"] = found["taxon_id"].map(counts).fillna(0).astype(int)
    found["label"] = found["common_name"].fillna(found["taxon_name"])
    found = _join_taxonomy(found)
    return found.sort_values(["family_name", "taxon_name"])


def butterfly_gap(butterflies, n=30):
    """Regional butterflies not yet recorded here, ranked by regional frequency.

    Non-seasonal, matching the amphibian gap: rank by how common each species is
    in the surrounding region so the list reads as realistic targets rather than
    a thin single-month slice.
    """
    return _region_gap(butterflies, "region_butterfly_taxa", n=n)


# --- reptiles ----------------------------------------------------------------
def load_reptiles():
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM reptile_taxa", conn)


def reptile_summary(df, reptiles):
    ids = set(reptiles["taxon_id"].dropna())
    sub = df[df["taxon_id"].isin(ids)]
    return {
        "species": int(reptiles["taxon_id"].nunique()),
        "records": int(len(sub)),
        "top_month": _peak_month(sub) if not sub.empty else "",
    }


def reptile_found(df, reptiles):
    """Recorded reptiles sorted taxonomically (order → family → species)."""
    if reptiles.empty:
        return reptiles
    found = reptiles.copy()
    counts = (df[df["taxon_id"].isin(set(found["taxon_id"].dropna()))]
              .groupby("taxon_id").size())
    found["ref_count"] = found["taxon_id"].map(counts).fillna(0).astype(int)
    found["label"] = found["common_name"].fillna(found["taxon_name"])
    found = _join_taxonomy(found)
    return found.sort_values(["order_name", "family_name", "taxon_name"])


_EXCLUDE_FROM_REPTILES = {
    39952,  # Red-eared Slider (common captive release)
}


def reptile_gap(reptiles, n=30):
    """Regional reptiles not yet recorded here, ranked by regional frequency.

    Non-seasonal: reptile activity windows vary widely by order, so overall
    regional frequency is a better guide than a single-month slice.
    """
    gap = _region_gap(reptiles, "region_reptile_taxa",
                      n=n + len(_EXCLUDE_FROM_REPTILES))
    gap["missing"] = gap["missing"][
        ~gap["missing"]["taxon_id"].isin(_EXCLUDE_FROM_REPTILES)
    ].head(n)
    return gap


# --- moths ("After Dark") ---------------------------------------------------
def load_moths():
    """Moth roster (Lepidoptera minus butterflies) with representative photos."""
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM moth_taxa", conn)


def moth_summary(df, moths):
    ids = set(moths["taxon_id"].dropna())
    sub = df[df["taxon_id"].isin(ids)]
    return {
        "species": int(moths["taxon_id"].nunique()),
        "records": int(len(sub)),
        "top_month": _peak_month(sub),
    }


def _peak_month(sub):
    if sub.empty or sub["observed_on"].isna().all():
        return ""
    m = sub["observed_on"].dt.month.value_counts().idxmax()
    import calendar
    return calendar.month_name[int(m)]


def moth_seasonal(df, moths, min_obs=3, max_species=42):
    """Flight-season cascade for moths: when each species is on the wing."""
    ids = set(moths["taxon_id"].dropna())
    return _seasonal_agg(df[df["taxon_id"].isin(ids)], min_obs, max_species)


def moth_highlights(moths, stats, df=None, n=12):
    """A showcase of standout moths: rarest in New York where we know it, topped
    up with the most-recorded species so the gallery is always full. Each keeps
    its representative photo."""
    if moths.empty:
        return moths
    m = moths.copy()
    m["label"] = m["common_name"].fillna(m["taxon_name"])
    if not stats.empty:
        m = m.merge(
            stats[["taxon_id", "state_obs_count", "county_obs_count",
                   "is_county_first"]],
            on="taxon_id", how="left")
    else:
        m["state_obs_count"] = float("nan")
    rare = m[m["state_obs_count"].notna()].sort_values("state_obs_count")
    chosen = rare.head(n)
    if len(chosen) < n:                       # backfill with most-recorded
        extra = (m[~m["taxon_id"].isin(chosen["taxon_id"])]
                 .sort_values("obs_count", ascending=False)
                 .head(n - len(chosen)))
        chosen = pd.concat([chosen, extra], ignore_index=True)
    chosen = chosen.head(n)
    if df is not None and not df.empty and "id" in df.columns:
        first = (df.dropna(subset=["taxon_id", "id"])
                   .sort_values("observed_on")
                   .groupby("taxon_id")["id"].first()
                   .reset_index()
                   .rename(columns={"id": "first_obs_id"}))
        chosen = chosen.merge(first, on="taxon_id", how="left")
    return chosen


# --- moth-scoped scientific analyses ----------------------------------------
def moth_obs(df, moths):
    """Property observations that are moths (species-level, Aves already gone)."""
    return df[df["taxon_id"].isin(set(moths["taxon_id"].dropna()))]


def _species_counts(sub):
    """Per-species observation counts (abundance proxy) for a sub-frame."""
    return sub.dropna(subset=["taxon_id"]).groupby("taxon_id").size()


def moth_completeness(df, moths):
    """Incidence-based Chao2 richness estimate for the moth inventory.

    Each survey night is a sampling unit; a species is "detected" on a night if
    it was recorded that night. This avoids the abundance trap (repeat photos of
    one moth at a sheet inflate observation counts), so it's the right estimator
    for a single-site inventory. Q1/Q2 = species detected on exactly one / two
    nights; m = number of survey nights.
    """
    import math
    sub = moth_obs(df, moths).dropna(subset=["taxon_id", "observed_on"]).copy()
    sub["night"] = _session_dates(sub)
    nights_per_species = sub.groupby("taxon_id")["night"].nunique()
    s_obs = int(len(nights_per_species))
    q1 = int((nights_per_species == 1).sum())
    q2 = int((nights_per_species == 2).sum())
    m = int(sub["night"].nunique())
    corr = (m - 1) / m if m > 1 else 1.0
    if q2 > 0:
        chao2 = s_obs + corr * q1 * q1 / (2 * q2)
    else:
        chao2 = s_obs + corr * q1 * (q1 - 1) / 2
    chao2 = max(chao2, s_obs)
    # Log-normal 95% CI on the estimated missing species (Chao 1987 form).
    t = chao2 - s_obs
    low = high = int(round(chao2))
    if t > 0 and q1 > 0 and q2 > 0:
        r = q1 / q2
        var = q2 * (0.5 * r ** 2 + r ** 3 + 0.25 * r ** 4)
        if var > 0:
            c = math.exp(1.96 * math.sqrt(math.log(1 + var / (t * t))))
            low = int(round(s_obs + t / c))
            high = int(round(s_obs + t * c))
    pct = round(100 * s_obs / chao2) if chao2 else 100
    return {
        "observed": s_obs,
        "estimated": int(round(chao2)),
        "remaining": int(round(chao2)) - s_obs,
        "pct_complete": int(pct),
        "low": low,
        "high": high,
        "q1": q1,           # species detected on a single night
        "q2": q2,           # ... on exactly two nights
        "nights": m,
    }


def moth_family_breakdown(moths, n=14):
    """Per-family: moth species recorded here vs. species known from the ~50-mile
    region. Reframes overall completeness — typically near-complete on the big
    macro-moth families, barely scratching the species-rich micro families.
    Uses the regional pool (county is too undersampled to compare fairly)."""
    meta = _load_table("taxon_meta")
    region = _load_table("region_moth_taxa")
    ref = region if not region.empty else _load_table("county_moth_taxa")
    if meta.empty or moths.empty or ref.empty:
        return pd.DataFrame()
    meta = meta[["taxon_id", "family_name", "family_common"]]
    fam_common = (meta.dropna(subset=["family_name"]).drop_duplicates("family_name")
                  .set_index("family_name")["family_common"].to_dict())
    prop = moths[["taxon_id"]].merge(meta, on="taxon_id", how="left")
    reg = ref[["taxon_id"]].merge(meta, on="taxon_id", how="left")
    rec = prop.dropna(subset=["family_name"]).groupby("family_name")["taxon_id"].nunique()
    rtot = reg.dropna(subset=["family_name"]).groupby("family_name")["taxon_id"].nunique()
    out = pd.DataFrame({"recorded": rec, "region_total": rtot}).fillna(0).astype(int)
    # Regional tally is a floor; never let it read below what we've recorded.
    out["region_total"] = out[["region_total", "recorded"]].max(axis=1)
    out["gap"] = out["region_total"] - out["recorded"]
    out["label"] = [fam_common.get(f) or f for f in out.index]
    return out.sort_values("region_total", ascending=False).head(n).reset_index(drop=True)


def moth_survey_nights(df, moths):
    """Distinct dates with a moth record + the date range — survey effort, for
    the Methods panel and effort-aware caveats."""
    sub = moth_obs(df, moths).dropna(subset=["observed_on"])
    if sub.empty:
        return {"nights": 0, "first": None, "last": None}
    dates = _session_dates(sub)
    return {"nights": int(dates.nunique()),
            "first": sub["observed_on"].min(), "last": sub["observed_on"].max()}


def moth_effort(df, moths):
    """Cumulative moth species vs. cumulative observations (the discovery/effort
    curve), for seeing how fast new species are still turning up."""
    sub = moth_obs(df, moths).dropna(subset=["observed_on", "taxon_id"])
    sub = sub.sort_values("observed_on")
    seen, cum_species, cum_obs = set(), [], []
    for i, t in enumerate(sub["taxon_id"], start=1):
        seen.add(t)
        cum_obs.append(i)
        cum_species.append(len(seen))
    return pd.DataFrame({"cum_obs": cum_obs, "cum_species": cum_species})


def moth_county_gap(moths, n=15, target_months=None):
    """Moths recorded near the property but not yet found here.

    Tioga County is undersampled, so the gap list and headline are driven by the
    well-sampled ~50-mile regional pool (a truer picture of what could occur),
    while still reporting county completeness for context. Missing species are
    ranked by how often they're recorded regionally — the likeliest next finds.

    target_months: optional list of month numbers (e.g. [6, 7]). When given,
    restricts the gap list to species with county_obs records in those months
    and re-ranks by seasonal county record count instead of overall region count.
    """
    region = _load_table("region_moth_taxa")
    county = _load_table("county_moth_taxa")
    have = set(moths["taxon_id"].dropna().astype(int))

    def completeness(tbl):
        if tbl.empty:
            return 0, 0, 0
        total = int(tbl["taxon_id"].nunique())
        rec = int(tbl["taxon_id"].isin(have).sum())
        return total, rec, (round(100 * rec / total) if total else 0)

    region_total, region_have, region_pct = completeness(region)
    county_total, county_have, county_pct = completeness(county)

    # Fall back to county if the region pool hasn't synced yet.
    pool = region if not region.empty else county
    count_col = "region_count" if not region.empty else "county_count"
    if pool.empty:
        return {"region_total": 0, "county_total": 0, "have": len(have),
                "pct": 0, "county_pct": 0, "missing_count": 0, "missing": pool,
                "target_months": target_months or []}
    missing = pool[~pool["taxon_id"].isin(have)].copy()
    missing["label"] = missing["common_name"].fillna(missing["taxon_name"])

    if target_months:
        month_strs = ",".join(f"'{m:02d}'" for m in target_months)
        with connect() as conn:
            rows = conn.execute(
                f"SELECT taxon_id, COUNT(*) AS cnt FROM county_obs "
                f"WHERE taxon_id IS NOT NULL "
                f"AND strftime('%m', observed_on) IN ({month_strs}) "
                f"GROUP BY taxon_id"
            ).fetchall()
        seasonal_counts = {int(r["taxon_id"]): int(r["cnt"]) for r in rows}
        seasonal_ids = set(seasonal_counts.keys())
        missing = missing[missing["taxon_id"].isin(seasonal_ids)].copy()
        missing["ref_count"] = missing["taxon_id"].map(
            lambda tid: seasonal_counts.get(int(tid), 0)
        )
        missing = missing.sort_values("ref_count", ascending=False)
    else:
        missing["ref_count"] = missing[count_col]
        missing = missing.sort_values(count_col, ascending=False)

    return {
        "region_total": region_total,
        "region_radius_km": REGION_RADIUS_KM,
        "county_total": county_total,
        "have": region_have if not region.empty else county_have,
        "pct": region_pct if not region.empty else county_pct,
        "county_pct": county_pct,
        "missing_count": int(len(missing)),
        "missing": missing.head(n),
        "target_months": target_months or [],
    }


def observation_dates(df=None):
    """Sorted list of all distinct observed_on dates on the property."""
    if df is None:
        df = load_property(species_only=False)
    return sorted(df["observed_on"].dt.date.dropna().unique())


# --- activity log -----------------------------------------------------------
def activity_log(df, stats):
    """Log of new-to-property species grouped by mothing session, for the Field Journal.

    Evening and the following morning are treated as one session (observations
    before noon are attributed to the prior day). Returns a list of dicts sorted
    chronologically, one per session that introduced at least one new species:
        date            datetime.date  (session start — the evening date)
        date_end        datetime.date or None  (the morning date, if session spans midnight)
        total_obs       int
        new_species     list of species dicts (see below)

    Each species dict:
        label           str  (common name or taxon_name)
        taxon_id        int
        obs_id          int  (iNaturalist observation id for the first record)
        taxon_name      str
        is_moth         bool
        is_morning      bool (True = morning-after half of an overnight session)
        group           str  (readable group label)
        county_obs      int or None
        state_obs       int or None
        is_county_first bool
    """
    import datetime

    if df.empty:
        return []

    moth_ids, butterfly_ids, order_common = _group_inputs()
    labeler = group_labeler(moth_ids, butterfly_ids, order_common)

    sub = df.dropna(subset=["taxon_id", "observed_on"]).sort_values("observed_on")
    sub = sub.copy()
    sub["session"] = _session_dates(sub)   # evening date (morning obs rolled back)
    sub["cal_date"] = sub["observed_on"].dt.date
    # is_morning: observation rolled back from the calendar day after the session
    sub["is_morning"] = sub["cal_date"] != sub["session"]

    # Build stats lookup.
    if not stats.empty:
        stat_by_taxon = stats.set_index("taxon_id")[
            ["county_obs_count", "state_obs_count", "is_county_first"]
        ].to_dict("index")
    else:
        stat_by_taxon = {}

    seen = set()
    entries_by_session = {}

    # Total obs per session.
    obs_per_session = sub.groupby("session")["id"].count().to_dict()

    # Observers per session: all distinct user_names (or user_login fallback)
    # drawn from ALL obs in the session (not just new-species ones).
    def _name(row):
        n = row.get("user_name")
        return n if (n and n == n and n.strip()) else (row.get("user_login") or "")

    observers_by_session = {}
    for _, row in sub.iterrows():
        sess = row["session"]
        n = _name(row)
        if n:
            observers_by_session.setdefault(sess, set()).add(n)

    # Whether the session has any morning obs at all (to know if it spans midnight).
    has_morning = sub[sub["is_morning"]]["session"].unique()
    has_morning_set = set(has_morning)

    for _, row in sub.iterrows():
        tid = int(row["taxon_id"])
        sess = row["session"]
        if tid not in seen:
            seen.add(tid)
            s = stat_by_taxon.get(tid, {})
            county_obs = s.get("county_obs_count")
            state_obs = s.get("state_obs_count")
            is_cf = bool(s.get("is_county_first") == 1)
            is_moth = tid in moth_ids
            grp = labeler(tid, row.get("iconic_taxon"))
            cn = row.get("common_name")
            tn = row.get("taxon_name")
            cn = None if (cn is None or (cn != cn)) else cn
            tn = None if (tn is None or (tn != tn)) else tn
            sp = {
                "label": cn or tn or "Unidentified",
                "taxon_id": tid,
                "obs_id": int(row["id"]),
                "taxon_name": tn or "",
                "is_moth": is_moth,
                "is_morning": bool(row["is_morning"]),
                "group": grp,
                "county_obs": int(county_obs) if county_obs == county_obs and county_obs is not None else None,
                "state_obs": int(state_obs) if state_obs == state_obs and state_obs is not None else None,
                "is_county_first": is_cf,
            }
            entries_by_session.setdefault(sess, []).append(sp)

    result = []
    for sess in sorted(entries_by_session):
        species = entries_by_session[sess]
        def _sort_key(sp):
            state = sp["state_obs"] if sp["state_obs"] is not None else 999999
            grp = sp["group"]
            if not isinstance(grp, str):
                grp = ""
            lbl = sp["label"]
            if not isinstance(lbl, str):
                lbl = ""
            return (0 if sp["is_moth"] else 1, grp, state, lbl)
        species.sort(key=_sort_key)
        observers = sorted(observers_by_session.get(sess, set()))
        result.append({
            "date": sess,
            "has_morning": sess in has_morning_set,
            "total_obs": obs_per_session.get(sess, 0),
            "observers": observers,
            "new_species": species,
        })
    return result


def moth_diversity(df, moths):
    """Shannon H', Gini-Simpson, Pielou evenness, and a rank-abundance series."""
    import math
    counts = _species_counts(moth_obs(df, moths)).sort_values(ascending=False)
    total = int(counts.sum())
    s = int(len(counts))
    if total == 0 or s == 0:
        return {"shannon": 0, "simpson": 0, "evenness": 0, "rank_abundance": []}
    p = counts / total
    shannon = float(-(p * p.map(math.log)).sum())
    simpson = float(1 - (p * p).sum())
    evenness = float(shannon / math.log(s)) if s > 1 else 1.0
    return {
        "shannon": round(shannon, 2),
        "simpson": round(simpson, 3),
        "evenness": round(evenness, 3),
        "species": s,
        "rank_abundance": counts.tolist(),
    }


def monthly_survey_summary(df, moths):
    """Returns a list of 12 dicts (one per calendar month, ordered 1–12) describing
    moth survey effort and discovery rate.

    Uses the existing _session_dates() noon-cutoff logic so overnight sessions
    spanning midnight are attributed to the correct evening date. 'new_species_count'
    is computed from each taxon's all-time first session-date — stable as new data
    arrives because a species' first month never changes.

    Returns list of 12 dicts with keys:
        month_num         int 1–12
        month_name        str
        obs_count         int
        species_count     int  (distinct species ever recorded that month)
        new_species_count int  (species whose first-ever property record fell in that month)
        nights_surveyed   int  (distinct session-dates with at least one moth observation)
        survey_season     bool (True for May–September inclusive)
    """
    import calendar
    sub = moth_obs(df, moths).dropna(subset=['taxon_id', 'observed_on']).copy()
    sub['night'] = _session_dates(sub)
    sub['month_num'] = sub['observed_on'].dt.month
    month_obs = sub.groupby('month_num')['id'].count().rename('obs_count')
    month_spp = sub.groupby('month_num')['taxon_id'].nunique().rename('species_count')
    sub['night_month'] = pd.to_datetime(sub['night']).dt.month
    month_nights = sub.drop_duplicates('night').groupby('night_month').size().rename('nights_surveyed')
    first_night = sub.groupby('taxon_id')['night'].min().reset_index()
    first_night['month_num'] = pd.to_datetime(first_night['night']).dt.month
    month_new = first_night.groupby('month_num').size().rename('new_species_count')
    rows = []
    for m in range(1, 13):
        rows.append({
            'month_num': m,
            'month_name': calendar.month_name[m],
            'obs_count': int(month_obs.get(m, 0)),
            'species_count': int(month_spp.get(m, 0)),
            'new_species_count': int(month_new.get(m, 0)),
            'nights_surveyed': int(month_nights.get(m, 0)),
            'survey_season': 5 <= m <= 9,
        })
    return rows
