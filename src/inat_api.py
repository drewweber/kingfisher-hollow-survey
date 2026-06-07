"""Thin iNaturalist API v1 client: a throttled requests session plus the two
access patterns this pipeline needs (count-only and full cursor pagination)."""

import time

import requests

from config import PER_PAGE, REQUEST_PAUSE, USER_AGENT

BASE = "https://api.inaturalist.org/v1"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def _get(path, **params):
    """GET with light retry on transient errors; honours a polite pause."""
    url = f"{BASE}/{path}"
    for attempt in range(4):
        resp = _session.get(url, params=params, timeout=60)
        if resp.status_code == 200:
            time.sleep(REQUEST_PAUSE)
            return resp.json()
        # 429 (rate limit) or 5xx -> back off and retry
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
    resp.raise_for_status()


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
