"""Thin iNaturalist API v1 client: a throttled requests session plus the two
access patterns this pipeline needs (count-only and full cursor pagination)."""

import time

import requests

from config import PER_PAGE, REQUEST_PAUSE, USER_AGENT

BASE = "https://api.inaturalist.org/v1"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def _get(path, **params):
    """GET with retry on transient HTTP *and* connection errors.

    Long sweeps make thousands of calls, so dropped connections and brief
    rate-limit / 5xx blips are expected; back off and retry rather than abort
    the whole run.
    """
    url = f"{BASE}/{path}"
    last_exc = None
    for attempt in range(6):
        try:
            resp = _session.get(url, params=params, timeout=60)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            time.sleep(min(2 ** attempt, 30))
            continue
        if resp.status_code == 200:
            time.sleep(REQUEST_PAUSE)
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(2 ** attempt, 30))
            continue
        resp.raise_for_status()
    if last_exc:
        raise last_exc
    resp.raise_for_status()


def fetch_taxa(ids):
    """Fetch full taxon records (incl. ancestry with common names) for up to ~30
    ids at once via /v1/taxa/{comma_ids}. Returns the results list."""
    if not ids:
        return []
    path = "taxa/" + ",".join(str(i) for i in ids)
    return _get(path, per_page=len(ids)).get("results", [])


def count(**params):
    """total_results for a query, fetched with per_page=0 (no rows returned)."""
    return _get("observations", per_page=0, **params)["total_results"]


def first_observed_date(**params):
    """observed_on of the earliest matching observation, or None."""
    data = _get(
        "observations",
        per_page=1,
        order_by="observed_on",
        order="asc",
        **params,
    )
    results = data["results"]
    return results[0].get("observed_on") if results else None


def iter_species_counts(**params):
    """Yield taxa from /observations/species_counts (page-based pagination).

    Each result is {count, taxon{...}} — the taxon carries names and a
    representative default_photo, so one sweep gives a full species roster.
    """
    page = 1
    seen = 0
    while True:
        data = _get("observations/species_counts",
                    per_page=PER_PAGE, page=page, **params)
        results = data["results"]
        if not results:
            return
        for row in results:
            yield row
        seen += len(results)
        if seen >= data["total_results"] or len(results) < PER_PAGE:
            return
        page += 1


def fetch_id_changes(project_id, username, n=40):
    """Return recent identifications on `username`'s project observations where
    another user changed or improved the taxon (category 'improving' or 'maverick').

    Fetches the most recently updated observations from the project and scans
    their inline identifications. Returns a list of dicts sorted by the
    identification's created_at, newest first:
        obs_id, obs_date, obs_url,
        prev_taxon_id, prev_taxon_name, prev_taxon_common,
        new_taxon_id, new_taxon_name, new_taxon_common,
        identifier_login, identifier_name,
        category, id_created_at
    """
    changes = []
    seen_id_ids = set()
    page = 1
    while len(changes) < n:
        data = _get(
            "observations",
            project_id=project_id,
            user_login=username,
            order_by="updated_at",
            order="desc",
            per_page=PER_PAGE,
            page=page,
        )
        results = data.get("results", [])
        if not results:
            break
        for obs in results:
            for idn in obs.get("identifications", []):
                if idn.get("user", {}).get("login") == username:
                    continue
                if idn.get("category") not in ("improving", "maverick"):
                    continue
                if not idn.get("current"):
                    continue
                if idn["id"] in seen_id_ids:
                    continue
                seen_id_ids.add(idn["id"])
                prev = idn.get("previous_observation_taxon") or {}
                new = idn.get("taxon") or {}
                changes.append({
                    "obs_id": obs["id"],
                    "obs_date": obs.get("observed_on", ""),
                    "obs_url": f"https://www.inaturalist.org/observations/{obs['id']}",
                    "prev_taxon_id": prev.get("id"),
                    "prev_taxon_name": prev.get("name", ""),
                    "prev_taxon_common": prev.get("preferred_common_name", ""),
                    "new_taxon_id": new.get("id"),
                    "new_taxon_name": new.get("name", ""),
                    "new_taxon_common": new.get("preferred_common_name", ""),
                    "identifier_login": idn["user"]["login"],
                    "identifier_name": idn["user"].get("name") or idn["user"]["login"],
                    "category": idn["category"],
                    "id_created_at": idn.get("created_at", ""),
                })
        if len(results) < PER_PAGE:
            break
        # Stop after scanning enough pages
        if page >= 3:
            break
        page += 1
    changes.sort(key=lambda x: x["id_created_at"], reverse=True)
    return changes[:n]


def iter_all(id_above=0, **params):
    """Yield every observation matching `params`, ascending by id.

    Uses the id_above cursor instead of page numbers so we can move past
    iNat's 10,000-result ceiling on standard pagination.
    """
    while True:
        data = _get(
            "observations",
            per_page=PER_PAGE,
            order_by="id",
            order="asc",
            id_above=id_above,
            **params,
        )
        results = data["results"]
        if not results:
            return
        for obs in results:
            yield obs
        id_above = results[-1]["id"]
        if len(results) < PER_PAGE:
            return
