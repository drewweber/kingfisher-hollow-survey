"""pandas analyses over the SQLite tables. Each function returns a DataFrame
(or dict) that viz.py turns into a chart, keeping data and presentation apart."""

import pandas as pd

from config import SPECIES_RANKS
from db import connect


def load_property(species_only=True):
    """Property observations as a DataFrame with parsed date columns.

    By default restricted to species-level records (rank 'species' or finer);
    coarser IDs like genus/family are observations not resolved to a species.
    """
    with connect() as conn:
        df = pd.read_sql_query("SELECT * FROM property_obs", conn)
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
    return g.sort_values(["iconic_taxon", "label"])


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
def seasonal_timing(df, iconic_taxon="Aves", min_obs=4, max_species=28):
    """Per-species day-of-year distribution for a taxon group, for a dot/range
    plot of when each species appears through the year."""
    sub = df.dropna(subset=["observed_on", "taxon_id"])
    sub = sub[sub["iconic_taxon"] == iconic_taxon].copy()
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
    agg = agg.sort_values("median_doy").head(max_species)
    return agg


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
