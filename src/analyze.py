"""pandas analyses over the SQLite tables. Each function returns a DataFrame
(or dict) that viz.py turns into a chart, keeping data and presentation apart."""

import pandas as pd

from db import connect


def load_property():
    """Property observations as a DataFrame with parsed date columns."""
    with connect() as conn:
        df = pd.read_sql_query("SELECT * FROM property_obs", conn)
    df["observed_on"] = pd.to_datetime(df["observed_on"], errors="coerce")
    df["created_at"] = pd.to_datetime(
        df["created_at"], errors="coerce", utc=True
    )
    return df


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
