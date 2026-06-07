"""pandas analyses over the SQLite tables. Each function returns a DataFrame
(or dict) that viz.py turns into a chart, keeping data and presentation apart."""

import pandas as pd

from config import SPECIES_RANKS
from db import connect


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
def phenology(df, iconic_taxon=None):
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
    return matrix.head(40)


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


def moth_highlights(moths, stats, n=12):
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
    return chosen.head(n)


# --- moth-scoped scientific analyses ----------------------------------------
def moth_obs(df, moths):
    """Property observations that are moths (species-level, Aves already gone)."""
    return df[df["taxon_id"].isin(set(moths["taxon_id"].dropna()))]


def _species_counts(sub):
    """Per-species observation counts (abundance proxy) for a sub-frame."""
    return sub.dropna(subset=["taxon_id"]).groupby("taxon_id").size()


def moth_completeness(df, moths):
    """Chao1 richness estimate for the moth inventory.

    Abundance-based Chao1 from per-species observation counts: how many moth
    species likely occur on the property vs. how many we've recorded. Obs counts
    stand in for abundance — a standard but imperfect proxy, so it's an estimate.
    """
    counts = _species_counts(moth_obs(df, moths))
    s_obs = int((counts > 0).sum())
    f1 = int((counts == 1).sum())          # singletons
    f2 = int((counts == 2).sum())          # doubletons
    import math
    if f2 > 0:
        chao1 = s_obs + f1 * f1 / (2 * f2)
    else:                                   # bias-corrected form when no doubletons
        chao1 = s_obs + f1 * (f1 - 1) / 2
    chao1 = max(chao1, s_obs)
    # Chao (1987) log-normal 95% CI on the *estimated missing* species.
    t = chao1 - s_obs
    low = high = int(round(chao1))
    if t > 0 and f1 > 0 and f2 > 0:
        r = f1 / f2
        var = f2 * (0.5 * r ** 2 + r ** 3 + 0.25 * r ** 4)
        if var > 0:
            c = math.exp(1.96 * math.sqrt(math.log(1 + var / (t * t))))
            low = int(round(s_obs + t / c))
            high = int(round(s_obs + t * c))
    pct = round(100 * s_obs / chao1) if chao1 else 100
    return {
        "observed": s_obs,
        "estimated": int(round(chao1)),
        "remaining": int(round(chao1)) - s_obs,
        "pct_complete": int(pct),
        "low": low,
        "high": high,
        "singletons": f1,
        "doubletons": f2,
    }


def moth_survey_nights(df, moths):
    """Distinct dates with a moth record + the date range — survey effort, for
    the Methods panel and effort-aware caveats."""
    sub = moth_obs(df, moths).dropna(subset=["observed_on"])
    if sub.empty:
        return {"nights": 0, "first": None, "last": None}
    dates = sub["observed_on"].dt.date
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


def moth_county_gap(moths, n=15):
    """Tioga County moths not yet recorded on the property, ranked by how common
    they are in the county (most-recorded-nearby first = likeliest to find)."""
    county = _load_table("county_moth_taxa")
    have = set(moths["taxon_id"].dropna().astype(int))
    if county.empty:
        return {"county_total": 0, "have": len(have), "pct": 0,
                "missing_count": 0, "missing": county}
    county_total = int(county["taxon_id"].nunique())
    recorded = int(county["taxon_id"].isin(have).sum())
    missing = county[~county["taxon_id"].isin(have)].copy()
    missing["label"] = missing["common_name"].fillna(missing["taxon_name"])
    missing = missing.sort_values("county_count", ascending=False)
    return {
        "county_total": county_total,
        "have": recorded,
        "pct": round(100 * recorded / county_total) if county_total else 0,
        "missing_count": int(len(missing)),
        "missing": missing.head(n),
    }


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
