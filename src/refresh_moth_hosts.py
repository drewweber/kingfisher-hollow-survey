"""Refresh the compact moth host index used by Field Targets.

This is an occasional reference-data maintenance command, not part of the
nightly sync. It queries the Natural History Museum HOSTS dataset only for the
current seasonal target pool and recently recorded Kingfisher Hollow moths.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import analyze
from db import connect
from moth_guilds import HOST_INDEX_PATH, HOST_TAXON_ALIASES


RESOURCE_ID = "877f387a-36a3-486c-a0c1-b8d5fb69f85a"
API_URL = "https://data.nhm.ac.uk/api/3/action/datastore_search"
SOURCE_URL = "https://data.nhm.ac.uk/dataset/hosts"
SOURCE_DOI = "10.5519/havt50xw"
REGIONAL_MARKERS = ("nearctic", "usa", "canada", "north america", "new world")


def _interest_names(effective_date, target_limit, recent_days):
    target_months = sorted({
        effective_date.month,
        (effective_date + timedelta(days=14)).month,
    })
    missing = analyze.moth_county_gap(
        analyze.load_moths(),
        n=target_limit,
        target_months=target_months,
    )["missing"]
    names = {
        str(name).strip()
        for name in missing.get("taxon_name", [])
        if str(name).strip()
    }
    cutoff = (effective_date - timedelta(days=recent_days - 1)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT m.taxon_name FROM property_obs p "
            "JOIN moth_taxa m USING (taxon_id) "
            "WHERE p.observed_on BETWEEN ? AND ? "
            "AND (p.captive IS NULL OR p.captive = 0)",
            (cutoff, effective_date.isoformat()),
        ).fetchall()
    names.update(row["taxon_name"] for row in rows if row["taxon_name"])
    return sorted(names)


def _fetch_name(name, session):
    source_names = [name, *HOST_TAXON_ALIASES.get(name, [])]
    rows = []
    for source_name in source_names:
        parts = source_name.split(" ", 1)
        if len(parts) != 2:
            continue
        filters = json.dumps({
            "Insect Genus": parts[0],
            "Insect Species": parts[1],
        })
        response = None
        for attempt in range(4):
            try:
                response = session.get(
                    API_URL,
                    params={
                        "resource_id": RESOURCE_ID,
                        "limit": 1000,
                        "filters": filters,
                    },
                    timeout=30,
                )
                if response.ok:
                    payload = response.json()
                    if payload.get("success"):
                        rows.extend(payload["result"]["records"])
                        break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(attempt + 1)
        else:
            status = response.status_code if response is not None else "network error"
            raise RuntimeError(f"HOSTS lookup failed for {source_name}: {status}")

    regional = []
    for row in rows:
        location = str(row.get("Location") or "").casefold()
        lab_rearing = str(row.get("Lab Rearing") or "").casefold()
        host_genus = str(row.get("Hostplant Genus") or "").strip()
        if not any(marker in location for marker in REGIONAL_MARKERS):
            continue
        if lab_rearing in {"true", "1", "yes"} or not host_genus:
            continue
        regional.append(row)
    hosts = sorted({str(row["Hostplant Genus"]).strip() for row in regional})
    if not hosts:
        return name, None
    return name, {
        "host_genera": hosts,
        "record_count": len(regional),
        "source_names": source_names,
    }


def build_index(effective_date, target_limit=200, recent_days=45, workers=5):
    names = _interest_names(effective_date, target_limit, recent_days)
    session = requests.Session()
    session.headers["User-Agent"] = "Kingfisher-Hollow-host-index/1.0"
    associations = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch_name, name, session) for name in names]
        for future in as_completed(futures):
            name, association = future.result()
            if association:
                associations[name] = association
    return {
        "schema_version": "kh-moth-hosts/1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "effective_date": effective_date.isoformat(),
        "source": {
            "title": "HOSTS: a Database of the World's Lepidopteran Hostplants",
            "url": SOURCE_URL,
            "doi": SOURCE_DOI,
            "resource_id": RESOURCE_ID,
            "record_scope": "Nearctic, United States, Canada, and New World records",
        },
        "selection": {
            "seasonal_target_limit": target_limit,
            "recent_property_days": recent_days,
            "queried_species": len(names),
            "matched_species": len(associations),
        },
        "associations": dict(sorted(associations.items())),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--target-limit", type=int, default=200)
    parser.add_argument("--recent-days", type=int, default=45)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--output", type=Path, default=HOST_INDEX_PATH)
    args = parser.parse_args()

    payload = build_index(
        args.date,
        target_limit=args.target_limit,
        recent_days=args.recent_days,
        workers=args.workers,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {args.output} "
        f"({payload['selection']['matched_species']} associations from "
        f"{payload['selection']['queried_species']} queried species)"
    )


if __name__ == "__main__":
    main()
