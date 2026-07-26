"""Thin iNaturalist API v1 client: a throttled requests session plus the two
access patterns this pipeline needs (count-only and full cursor pagination)."""

import threading
import time

import requests

from config import PER_PAGE, REQUEST_PAUSE, USER_AGENT

BASE = "https://api.inaturalist.org/v1"

_thread_local = threading.local()


def _retry_delay(resp, attempt):
    retry_after = resp.headers.get("Retry-After") if resp is not None else None
    if retry_after:
        try:
            return min(max(float(retry_after), 1), 120)
        except ValueError:
            pass
    if resp is not None and resp.status_code == 429:
        return min(10 * (attempt + 1), 120)
    return min(2 ** attempt, 30)


def _session():
    """Thread-local session for safe bounded parallel API work."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        _thread_local.session = session
    return session


def _get(path, **params):
    """GET with retry on transient HTTP *and* connection errors.

    Long sweeps make thousands of calls, so dropped connections and brief
    rate-limit / 5xx blips are expected; back off and retry rather than abort
    the whole run.
    """
    url = f"{BASE}/{path}"
    attempts = params.pop("_attempts", 6)
    timeout = params.pop("_timeout", 60)
    last_exc = None
    for attempt in range(attempts):
        try:
            resp = _session().get(url, params=params, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            print(f"[inat-api] retry {path} attempt {attempt + 1}/{attempts}: {exc}", flush=True)
            time.sleep(min(2 ** attempt, 30))
            continue
        if resp.status_code == 200:
            time.sleep(REQUEST_PAUSE)
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            print(f"[inat-api] retry {path} attempt {attempt + 1}/{attempts}: HTTP {resp.status_code}", flush=True)
            time.sleep(_retry_delay(resp, attempt))
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


def fetch_observations(ids, batch_size=100):
    """Fetch complete observation records, preserving the requested order.

    The standard property table intentionally stores a compact subset of each
    record.  Focused evidence pages also need every photo, the community taxon,
    identifier history, and written comments.  iNaturalist accepts a
    comma-separated list of observation IDs, so the extra refresh is one small
    request for the current case study rather than a project-wide resweep.
    """
    requested = []
    seen = set()
    for value in ids or ():
        try:
            observation_id = int(value)
        except (TypeError, ValueError):
            continue
        if observation_id <= 0 or observation_id in seen:
            continue
        seen.add(observation_id)
        requested.append(observation_id)
    if not requested:
        return []

    records = {}
    batch_size = max(1, min(int(batch_size), 100))
    for start in range(0, len(requested), batch_size):
        batch = requested[start:start + batch_size]
        path = "observations/" + ",".join(str(value) for value in batch)
        for observation in _get(path, per_page=len(batch)).get("results", []):
            if observation.get("id") is not None:
                records[int(observation["id"])] = observation
    return [records[value] for value in requested if value in records]


def fetch_licensed_photos(taxon_id, limit=2, license_codes=None, exclude_ids=None):
    """Return distinct redistributable reference photos for a taxon.

    Taxon default photos are occasionally all-rights-reserved.  The offline
    field guide must bundle its media, so we search research-grade observations
    for Creative Commons alternatives and preserve their source, attribution,
    and license metadata. Votes give the guide a practical quality signal; the
    caller retains multiple views where visual comparison matters.
    """
    limit = max(1, int(limit))
    excluded = {str(photo_id) for photo_id in (exclude_ids or ()) if photo_id is not None}
    licenses = license_codes or (
        "cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa",
        "cc-by-nd", "cc-by-nc-nd",
    )
    data = _get(
        "observations",
        taxon_id=taxon_id,
        photos="true",
        quality_grade="research",
        photo_license=",".join(licenses),
        order_by="votes",
        order="desc",
        per_page=100,
    )
    allowed = set(licenses)
    photos = []
    seen = set(excluded)
    for obs in data.get("results", []):
        for photo in obs.get("photos") or []:
            code = (photo.get("license_code") or "").casefold()
            if code not in allowed:
                continue
            photo_id = photo.get("id")
            key = str(photo_id) if photo_id is not None else (photo.get("url") or "")
            if not key or key in seen:
                continue
            url = photo.get("url") or ""
            medium = url.replace("square.", "medium.") if url else ""
            if not medium:
                continue
            seen.add(key)
            photos.append({
                "id": photo_id,
                "medium_url": medium,
                "attribution": photo.get("attribution") or "iNaturalist contributor",
                "license_code": code,
                "source_url": f"https://www.inaturalist.org/observations/{obs.get('id')}",
            })
            if len(photos) >= limit:
                return photos
    return photos


def fetch_licensed_photo(taxon_id, license_codes=None):
    """Return one redistributable representative photo for a taxon."""
    photos = fetch_licensed_photos(taxon_id, limit=1, license_codes=license_codes)
    return photos[0] if photos else None


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


def count_and_first_observed_date(**params):
    """Return (total_results, earliest observed_on) for a query.

    The API includes total_results on normal observation searches, so this
    combines the previous count-only and earliest-record requests into one call.
    """
    data = _get(
        "observations",
        per_page=1,
        order_by="observed_on",
        order="asc",
        **params,
    )
    results = data["results"]
    first = results[0].get("observed_on") if results else None
    return data["total_results"], first


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


def fetch_id_changes(project_id, username, n=40, attempts=3, timeout=15):
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
            _attempts=attempts,
            _timeout=timeout,
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


def iter_updated_since(updated_since, **params):
    """Yield observations changed after ``updated_since``, oldest first.

    iNaturalist keeps the same observation id when its identification changes.
    Incremental imports therefore need an ``updated_since`` pass as well as
    the historic id cursor used for long full sweeps. The result set is small
    for normal daily runs, so ordinary page pagination is sufficient here.
    """
    page = 1
    while True:
        data = _get(
            "observations",
            per_page=PER_PAGE,
            page=page,
            order_by="updated_at",
            order="asc",
            updated_since=updated_since,
            **params,
        )
        results = data["results"]
        if not results:
            return
        for obs in results:
            yield obs
        if len(results) < PER_PAGE:
            return
        page += 1
