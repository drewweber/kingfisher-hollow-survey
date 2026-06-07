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
