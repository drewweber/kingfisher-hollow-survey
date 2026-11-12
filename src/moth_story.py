"""Local moth community datasets for the survey page."""

from calendar import month_name

import pandas as pd

from analyze import _observation_rows, moth_obs


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
    for date, rows in records.groupby("date", sort=True):
        discovered.update(rows["taxon_id"])
        discovery.append({"date": date.date().isoformat(), "cumulative_taxa": len(discovered)})

    totals = records.groupby("taxon_id").size()
    frequency = {
        "once": int(totals.eq(1).sum()),
        "twice": int(totals.eq(2).sum()),
        "three_plus": int(totals.ge(3).sum()),
    }
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
        "timing": timing,
        "years": sorted({int(year) for year in records["date"].dt.year}),
        "first_date": discovery[0]["date"] if discovery else None,
        "last_date": discovery[-1]["date"] if discovery else None,
    }
