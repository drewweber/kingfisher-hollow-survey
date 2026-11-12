"""Local moth community datasets for the survey page."""

from calendar import month_name
from collections import Counter

import pandas as pd

from analyze import _observation_rows, moth_obs, moth_incidence


def build_story(df, moths):
    """Pool dated property observations by their recorded local calendar dates."""
    if df.empty or moths.empty:
        records = pd.DataFrame(columns=["taxon_id", "observed_on"])
    else:
        records = moth_obs(_observation_rows(df), moths).copy()
    # observed_on is the local calendar date, independent of the overnight
    # session convention and any time zone offset in observed_at.
    records["date"] = pd.to_datetime(
        records["observed_on"].astype("string").str.slice(stop=10),
        format="%Y-%m-%d",
        errors="coerce",
    )
    records = records.dropna(subset=["date"])
    records["month"] = records["date"].dt.month

    months = range(1, 13)
    monthly = []
    taxa_by_month = []
    for month in months:
        rows = records[records["month"] == month]
        taxa = set(rows["taxon_id"])
        taxa_by_month.append(taxa)
        monthly.append({
            "month": month,
            "name": month_name[month],
            "taxa": len(taxa),
            "records": len(rows),
            "reporting_dates": rows["date"].nunique(),
            "years": sorted({int(year) for year in rows["date"].dt.year}),
        })
    comparisons = []
    for month, (first, second) in enumerate(zip(taxa_by_month, taxa_by_month[1:]), 1):
        comparisons.append({
            "first_month": month,
            "second_month": month + 1,
            "shared": len(first & second),
            "first_only": len(first - second),
            "second_only": len(second - first),
        })

    discovery = []
    discovered = set()
    for day, rows in records.groupby("date", sort=True):
        discovered.update(rows["taxon_id"])
        discovery.append({"date": day.date().isoformat(), "cumulative_taxa": len(discovered)})

    incidence = moth_incidence(df, moths)
    running_counts = Counter()
    frequency_history = []
    for night, rows in incidence.groupby("night", sort=True):
        running_counts.update(rows["taxon_id"])
        frequency_history.append({
            "date": night.isoformat(),
            "once": sum(count == 1 for count in running_counts.values()),
            "twice": sum(count == 2 for count in running_counts.values()),
            "three_plus": sum(count >= 3 for count in running_counts.values()),
            "total": len(running_counts),
        })
    frequency = {key: frequency_history[-1][key] if frequency_history else 0
                 for key in ("once", "twice", "three_plus")}
    monthly_counts = records.groupby(["taxon_id", "month"]).size().to_dict()
    stages = {}
    if "life_stage" in records:
        for taxon_id, values in records.groupby("taxon_id")["life_stage"]:
            stages[taxon_id] = sorted({str(value).strip() for value in values.dropna()
                                       if str(value).strip()})

    timing = []
    if not moths.empty:
        roster = moths.dropna(subset=["taxon_id"]).drop_duplicates("taxon_id")
        for taxon in roster.sort_values("taxon_id").to_dict("records"):
            taxon_id = taxon["taxon_id"]
            common_name = taxon.get("common_name")
            scientific_name = taxon.get("taxon_name")
            timing.append({
                "id": int(taxon_id),
                "common_name": str(common_name) if pd.notna(common_name) else None,
                "scientific_name": str(scientific_name) if pd.notna(scientific_name) else None,
                "monthly_records": [int(monthly_counts.get((taxon_id, month), 0))
                                    for month in months],
                "stages": stages.get(taxon_id, []),
            })

    return {
        "monthly": monthly,
        "comparisons": comparisons,
        "discovery": discovery,
        "frequency": frequency,
        "frequency_history": frequency_history,
        "timing": timing,
        "years": sorted({int(year) for year in records["date"].dt.year}),
        "first_date": discovery[0]["date"] if discovery else None,
        "last_date": discovery[-1]["date"] if discovery else None,
    }
