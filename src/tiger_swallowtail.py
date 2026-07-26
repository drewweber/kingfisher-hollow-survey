"""Build and refresh the Tiger Swallowtail evidence case study.

The ordinary property table is intentionally compact.  This module keeps a
privacy-safe source snapshot for the few observations in the Eastern Tiger
Swallowtail complex, downloads every accessible observation photo, applies a
conservative evidence rubric, and generates a focused comparison page.

Source identification and site assessment are separate by design:

* iNaturalist taxon, community taxon, identifier history, and comments are
  refreshed from the source record.
* photo/view/morphology annotations live in a checked-in review file.
* an unreviewed observation is included automatically but is never promoted
  beyond ``Insufficient photographic evidence``.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from html import escape
import json
from pathlib import Path
import shutil

import requests

import inat_api
from config import DATA_DIR, PUBLIC_DIR, USER_AGENT
from db import connect


EASTERN_TAXON_ID = 60551
MIDSUMMER_TAXON_ID = 1610479
TIGER_COMPLEX_TAXON_ID = 1613196
TARGET_TAXON_IDS = frozenset(
    (EASTERN_TAXON_ID, MIDSUMMER_TAXON_ID, TIGER_COMPLEX_TAXON_ID)
)

ASSESSMENTS = (
    "Strong Eastern",
    "Leaning Eastern",
    "Strong Midsummer",
    "Leaning Midsummer",
    "Unresolved Eastern/Midsummer",
    "Insufficient photographic evidence",
)
VIEW_CLASSES = ("dorsal", "ventral", "partial")
WEAR_CLASSES = ("fresh", "moderate", "worn", "unknown")
MORPHOLOGY_SIGNALS = ("eastern", "midsummer", "mixed", "neutral", "not_assessable")

CASE_ROUTE = "/case-studies/tiger-swallowtails/"
CASE_URL = f"https://survey.kingfisher-hollow.com{CASE_ROUTE}"
PAPER_URL = "https://doi.org/10.3897/zookeys.1228.142202"
PROJECT_URL = (
    "https://www.inaturalist.org/projects/"
    "kingfisher-hollow-biodiversity-survey"
)
REVIEW_PATH = DATA_DIR / "reference" / "tiger-swallowtail-reviews.json"
PHOTO_CACHE_DIR = DATA_DIR / "cache" / "tiger-swallowtails" / "photos"
OUTPUT_DIR = PUBLIC_DIR / "case-studies" / "tiger-swallowtails"


def _taxon(taxon):
    taxon = taxon or {}
    return {
        "id": taxon.get("id"),
        "name": taxon.get("name") or "",
        "common_name": taxon.get("preferred_common_name") or "",
        "rank": taxon.get("rank") or "",
    }


def _user(user):
    user = user or {}
    return {
        "login": user.get("login") or "",
        "name": user.get("name") or user.get("login") or "",
    }


def qualifies_observation(observation):
    """Whether the current taxon is in the Eastern/Midsummer complex."""
    taxon = observation.get("taxon") or {}
    try:
        taxon_id = int(taxon.get("id"))
    except (TypeError, ValueError):
        taxon_id = None
    ancestor_ids = set()
    for value in taxon.get("ancestor_ids") or ():
        try:
            ancestor_ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return (
        taxon_id in TARGET_TAXON_IDS
        or TIGER_COMPLEX_TAXON_ID in ancestor_ids
    )


def _large_photo_url(photo):
    url = (photo or {}).get("url") or ""
    return url.replace("/square.", "/large.").replace("square.", "large.")


def normalize_observation(observation):
    """Return the public source fields used by the case study.

    Exact or private coordinates are intentionally never copied into this
    payload.  The page reports only the property/county and the source privacy
    state.
    """
    photos = []
    seen_photo_ids = set()
    for index, photo in enumerate(observation.get("photos") or (), start=1):
        photo_id = photo.get("id")
        key = str(photo_id) if photo_id is not None else _large_photo_url(photo)
        if not key or key in seen_photo_ids:
            continue
        seen_photo_ids.add(key)
        dimensions = photo.get("original_dimensions") or {}
        photos.append({
            "id": photo_id,
            "position": index,
            "url": _large_photo_url(photo),
            "width": dimensions.get("width"),
            "height": dimensions.get("height"),
            "attribution": photo.get("attribution") or "iNaturalist contributor",
            "license_code": photo.get("license_code") or "",
        })

    identifications = []
    for identification in observation.get("identifications") or ():
        identifications.append({
            "id": identification.get("id"),
            "current": bool(identification.get("current")),
            "category": identification.get("category") or "",
            "disagreement": identification.get("disagreement"),
            "body": identification.get("body") or "",
            "created_at": identification.get("created_at") or "",
            "user": _user(identification.get("user")),
            "taxon": _taxon(identification.get("taxon")),
            "previous_taxon": _taxon(
                identification.get("previous_observation_taxon")
            ),
        })

    comments = []
    for comment in observation.get("comments") or ():
        comments.append({
            "id": comment.get("id"),
            "body": comment.get("body") or "",
            "created_at": comment.get("created_at") or "",
            "user": _user(comment.get("user")),
        })

    observer = _user(observation.get("user"))
    source_taxon = _taxon(observation.get("taxon"))
    uri = observation.get("uri")
    if not uri and observation.get("id"):
        uri = f"https://www.inaturalist.org/observations/{observation['id']}"
    return {
        "id": int(observation["id"]),
        "uuid": observation.get("uuid") or "",
        "observed_on": observation.get("observed_on") or "",
        "observed_at": observation.get("time_observed_at") or "",
        "created_at": observation.get("created_at") or "",
        "updated_at": observation.get("updated_at") or "",
        "url": uri or "",
        "quality_grade": observation.get("quality_grade") or "",
        "source_taxon": source_taxon,
        "community_taxon": _taxon(observation.get("community_taxon")),
        "observer": observer,
        "photos": photos,
        "identifications": identifications,
        "comments": comments,
        "location": {
            "label": "Kingfisher Hollow, Tioga County, New York",
            "obscured_by_inaturalist": bool(
                observation.get("obscured")
                or observation.get("geoprivacy") in ("obscured", "private")
                or observation.get("private_location")
            ),
            "geoprivacy": observation.get("geoprivacy") or "open",
            "coordinates_published_here": False,
        },
    }


def capture_observation(conn, observation, in_project=True):
    """Insert/update a source record while preserving its first-ingested ID."""
    row = conn.execute(
        "SELECT observation_id FROM tiger_swallowtail_obs "
        "WHERE observation_id = ?",
        (observation.get("id"),),
    ).fetchone()
    if not row and not qualifies_observation(observation):
        return False

    payload = normalize_observation(observation)
    current = payload["source_taxon"]
    conn.execute(
        """
        INSERT INTO tiger_swallowtail_obs (
            observation_id, observed_on,
            original_taxon_id, original_taxon_name, original_common_name,
            original_rank,
            current_taxon_id, current_taxon_name, current_common_name,
            current_rank, source_updated_at, payload_json, in_project
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(observation_id) DO UPDATE SET
            observed_on = excluded.observed_on,
            current_taxon_id = excluded.current_taxon_id,
            current_taxon_name = excluded.current_taxon_name,
            current_common_name = excluded.current_common_name,
            current_rank = excluded.current_rank,
            source_updated_at = excluded.source_updated_at,
            payload_json = excluded.payload_json,
            in_project = excluded.in_project,
            last_synced_at = CURRENT_TIMESTAMP
        """,
        (
            payload["id"],
            payload["observed_on"],
            current.get("id"),
            current.get("name"),
            current.get("common_name"),
            current.get("rank"),
            current.get("id"),
            current.get("name"),
            current.get("common_name"),
            current.get("rank"),
            payload.get("updated_at"),
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            1 if in_project else 0,
        ),
    )
    return True


def _valid_image(path):
    if not path.exists() or path.stat().st_size < 1024:
        return False
    header = path.read_bytes()[:12]
    return (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )


def _photo_path(photo, cache_dir=PHOTO_CACHE_DIR):
    photo_id = photo.get("id")
    if photo_id is None:
        return None
    try:
        photo_id = int(photo_id)
    except (TypeError, ValueError):
        return None
    return Path(cache_dir) / f"{photo_id}.jpg"


def _download_photo(photo, cache_dir=PHOTO_CACHE_DIR):
    destination = _photo_path(photo, cache_dir)
    if destination is None or not photo.get("url"):
        return None
    if _valid_image(destination):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        photo["url"],
        timeout=45,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    partial = destination.with_suffix(".part")
    partial.write_bytes(response.content)
    if not _valid_image(partial):
        partial.unlink(missing_ok=True)
        raise ValueError(f"Downloaded image is invalid for photo {photo.get('id')}")
    partial.replace(destination)
    return destination


def cache_photos(payloads, cache_dir=PHOTO_CACHE_DIR, workers=4):
    """Download every distinct accessible photo, retaining failures for retry."""
    photos = {}
    for payload in payloads:
        for photo in payload.get("photos") or ():
            if photo.get("id") is not None and photo.get("url"):
                photos.setdefault(str(photo["id"]), photo)
    if not photos:
        return 0, []

    downloaded = 0
    warnings = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 6))) as pool:
        futures = {
            pool.submit(_download_photo, photo, cache_dir): photo
            for photo in photos.values()
        }
        for future in as_completed(futures):
            photo = futures[future]
            try:
                if future.result() is not None:
                    downloaded += 1
            except (requests.RequestException, OSError, ValueError) as error:
                warnings.append(f"photo {photo.get('id')}: {error}")
    return downloaded, warnings


def _payloads_from_connection(conn, active_only=True):
    where = "WHERE in_project = 1" if active_only else ""
    rows = conn.execute(
        "SELECT * FROM tiger_swallowtail_obs "
        f"{where} ORDER BY observed_on, observation_id"
    ).fetchall()
    records = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        payload["_source_record"] = {
            "original_taxon": {
                "id": row["original_taxon_id"],
                "name": row["original_taxon_name"] or "",
                "common_name": row["original_common_name"] or "",
                "rank": row["original_rank"] or "",
            },
            "first_ingested_at": row["first_ingested_at"],
            "last_synced_at": row["last_synced_at"],
        }
        records.append(payload)
    return records


def refresh_from_database():
    """Backfill/refresh full case-study records after the property sync."""
    with connect() as conn:
        property_ids = {
            int(row["id"])
            for row in conn.execute("SELECT id FROM property_obs").fetchall()
        }
        known_candidates = {
            int(row["id"])
            for row in conn.execute(
                """
                SELECT id
                FROM property_obs
                WHERE taxon_id IN (?, ?, ?)
                   OR lower(taxon_name) LIKE 'papilio glaucus%'
                   OR lower(taxon_name) LIKE 'papilio solstitius%'
                """,
                tuple(sorted(TARGET_TAXON_IDS)),
            ).fetchall()
        }
        historical_candidates = {
            int(row["observation_id"])
            for row in conn.execute(
                "SELECT observation_id FROM tiger_swallowtail_obs"
            ).fetchall()
        }
        conn.execute("UPDATE tiger_swallowtail_obs SET in_project = 0")
        active_historical = historical_candidates & property_ids
        if active_historical:
            placeholders = ",".join("?" for _value in active_historical)
            conn.execute(
                "UPDATE tiger_swallowtail_obs SET in_project = 1 "
                f"WHERE observation_id IN ({placeholders})",
                tuple(sorted(active_historical)),
            )

    candidate_ids = sorted(known_candidates | active_historical)
    observations = []
    try:
        observations = inat_api.fetch_observations(candidate_ids)
    except requests.RequestException as error:
        print(
            "[tiger-swallowtails] source refresh failed; retaining cached "
            f"records: {error}"
        )

    if observations:
        with connect() as conn:
            for observation in observations:
                capture_observation(
                    conn,
                    observation,
                    in_project=int(observation["id"]) in property_ids,
                )

    with connect() as conn:
        payloads = _payloads_from_connection(conn)
    cached, warnings = cache_photos(payloads)
    for warning in warnings:
        print(f"[tiger-swallowtails] photo warning: {warning}")
    print(
        f"[tiger-swallowtails] {len(payloads)} active observations; "
        f"{cached} photos cached or verified"
    )
    return len(payloads), cached


def _read_reviews(path=REVIEW_PATH):
    path = Path(path)
    if not path.exists():
        return {"schema_version": 1, "observations": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported tiger-swallowtail review schema")
    observations = data.get("observations")
    if not isinstance(observations, dict):
        raise ValueError("Tiger-swallowtail reviews must contain observations")
    return data


def _signal(value):
    value = str(value or "not_assessable").casefold()
    return value if value in MORPHOLOGY_SIGNALS else "not_assessable"


def _flight_period(observed_on):
    """A comparison bucket and context signal, never a species determination."""
    try:
        observed = date.fromisoformat(str(observed_on))
    except ValueError:
        return {
            "key": "unknown",
            "label": "Unknown seasonal period",
            "signal": "neutral",
            "finding": "The observation date is unavailable or invalid.",
        }
    month_day = (observed.month, observed.day)
    if month_day <= (6, 20):
        return {
            "key": "spring",
            "label": "Spring Eastern flight",
            "signal": "eastern",
            "finding": (
                f"{observed.strftime('%B')} {observed.day} falls in the spring "
                "flight context, before the expected late-June onset of the "
                "Midsummer flight."
            ),
        }
    if month_day <= (8, 10):
        return {
            "key": "midsummer",
            "label": "Expected Midsummer flight",
            "signal": "midsummer",
            "finding": (
                f"{observed.strftime('%B')} {observed.day} falls in the "
                "late-June–early-August overlap window. Midsummer is expected, "
                "but summer Easterns can overlap in the Finger Lakes region."
            ),
        }
    return {
        "key": "late",
        "label": "Late-summer Eastern flight",
        "signal": "eastern",
        "finding": (
            f"{observed.strftime('%B')} {observed.day} falls in the late-summer "
            "context, when a partial second Eastern flight is more plausible."
        ),
    }


def _taxon_direction(taxon):
    try:
        taxon_id = int((taxon or {}).get("id"))
    except (TypeError, ValueError):
        return "neutral"
    if taxon_id == EASTERN_TAXON_ID:
        return "eastern"
    if taxon_id == MIDSUMMER_TAXON_ID:
        return "midsummer"
    return "neutral"


def _morphology_assessment(review):
    override = review.get("assessment_override")
    if override:
        if override not in ASSESSMENTS:
            raise ValueError(f"Unknown assessment override: {override}")
        return override

    ventral_visible = bool(review.get("ventral_forewing_visible"))
    ventral = (
        _signal(review.get("ventral_forewing_pattern"))
        if ventral_visible
        else "not_assessable"
    )
    secondary_clear = bool(review.get("secondary_morphology_clear"))
    secondary = []
    if secondary_clear:
        secondary = [
            _signal((review.get("wing_shape") or {}).get("signal")),
            _signal((review.get("sex_or_dark_form") or {}).get("signal")),
        ]
        secondary = [
            value for value in secondary
            if value not in ("neutral", "not_assessable")
        ]

    if ventral == "mixed" or (
        ventral in ("eastern", "midsummer")
        and any(value not in (ventral, "mixed") for value in secondary)
    ):
        return "Unresolved Eastern/Midsummer"

    if ventral in ("eastern", "midsummer"):
        same_secondary = any(value == ventral for value in secondary)
        strength = "Strong" if same_secondary else "Leaning"
        name = "Eastern" if ventral == "eastern" else "Midsummer"
        return f"{strength} {name}"

    directions = set(secondary)
    if "mixed" in directions or directions == {"eastern", "midsummer"}:
        return "Unresolved Eastern/Midsummer"
    if directions == {"eastern"}:
        # A dorsal/secondary-only review is deliberately capped at "Leaning".
        return "Leaning Eastern"
    if directions == {"midsummer"}:
        return "Leaning Midsummer"
    return "Insufficient photographic evidence"


def _identifier_summary(payload):
    observer_login = (payload.get("observer") or {}).get("login")
    current = [
        identification
        for identification in payload.get("identifications") or ()
        if identification.get("current")
    ]
    independent = [
        identification for identification in current
        if (identification.get("user") or {}).get("login") != observer_login
    ]
    community = payload.get("community_taxon") or {}
    community_direction = _taxon_direction(community)
    directions = {
        _taxon_direction(identification.get("taxon"))
        for identification in independent
    } - {"neutral"}
    written = [
        identification for identification in payload.get("identifications") or ()
        if str(identification.get("body") or "").strip()
    ]
    written.extend(
        comment for comment in payload.get("comments") or ()
        if str(comment.get("body") or "").strip()
    )

    if community.get("id"):
        community_name = (
            community.get("common_name")
            or community.get("name")
            or "an unnamed taxon"
        )
        text = f"The iNaturalist community taxon is {community_name}."
    else:
        text = "iNaturalist has not assigned a community taxon."
    if not independent:
        text += " No independent current identifier is present."
    elif len(directions) > 1:
        text += " Current independent identifiers conflict at species level."
    elif directions:
        direction = "Eastern" if "eastern" in directions else "Midsummer"
        text += f" Independent current identifiers support {direction}."
    else:
        text += " Independent current identifiers stop at the broader complex."
    if written:
        text += f" {len(written)} written identifier/comment note(s) are shown below."
    else:
        text += " No written identification rationale has been provided."
    return text, community_direction, directions


def assess_observation(payload, review=None):
    """Apply the transparent rule set and return display-ready evidence."""
    review = dict(review or {})
    assessment = _morphology_assessment(review)
    flight = _flight_period(payload.get("observed_on"))
    source_direction = _taxon_direction(payload.get("source_taxon"))
    identifier_text, community_direction, identifier_directions = (
        _identifier_summary(payload)
    )

    view = str(review.get("view") or "partial").casefold()
    if view not in VIEW_CLASSES:
        view = "partial"
    wear = str(review.get("wear") or "unknown").casefold()
    if wear not in WEAR_CLASSES:
        wear = "unknown"
    ventral_visible = bool(review.get("ventral_forewing_visible"))
    ventral_note = str(
        review.get("ventral_forewing_note")
        or (
            "The ventral forewing has not been annotated as clearly visible; "
            "its submarginal pattern cannot be assessed."
        )
    )
    wing_shape = review.get("wing_shape") or {}
    sex_form = review.get("sex_or_dark_form") or {}
    limitations = [
        str(value) for value in review.get("image_limitations") or ()
        if str(value).strip()
    ]
    if not limitations:
        limitations = [
            "No manual photo review is available yet; view, wear, and "
            "diagnostic morphology remain unassessed."
        ]

    evidence = [
        {
            "label": "Date and seasonal flight period",
            "finding": (
                flight["finding"]
                + " Date is contextual evidence, not a definitive identification."
            ),
        },
        {
            "label": "Freshness or wear",
            "finding": (
                str(review.get("wear_note") or "")
                or (
                    "Apparent wear is unknown; the images have not been "
                    "reviewed closely enough to distinguish scale loss from "
                    "lighting or focus."
                    if wear == "unknown"
                    else f"The individual appears {wear}; wear can alter wing "
                    "edges and apparent pattern contrast."
                )
            ),
        },
        {
            "label": "Ventral forewing pattern",
            "finding": ventral_note,
        },
        {
            "label": "Wing shape",
            "finding": str(
                wing_shape.get("note")
                or "Wing shape is not sufficiently clear for assessment."
            ),
        },
        {
            "label": "Sex or dark-form evidence",
            "finding": str(
                sex_form.get("note")
                or "Sex and dark-form evidence are not sufficiently clear."
            ),
        },
        {
            "label": "Community and identifier agreement",
            "finding": identifier_text,
        },
        {
            "label": "Image limitations",
            "finding": " ".join(limitations),
        },
    ]

    assessment_direction = (
        "eastern" if assessment.endswith("Eastern")
        else "midsummer" if assessment.endswith("Midsummer")
        else "neutral"
    )
    review_reasons = []
    if not review:
        review_reasons.append("New observation: no manual image annotation yet.")
    if assessment.startswith("Leaning"):
        review_reasons.append("The analytical result is explicitly provisional.")
    if assessment in (
        "Unresolved Eastern/Midsummer",
        "Insufficient photographic evidence",
    ):
        review_reasons.append("The photographs do not support a resolved result.")
    if (
        assessment_direction != "neutral"
        and flight["signal"] != "neutral"
        and assessment_direction != flight["signal"]
    ):
        review_reasons.append(
            f"The {assessment_direction.title()} assessment conflicts with "
            f"the {flight['label'].lower()} date context."
        )
    if (
        assessment_direction != "neutral"
        and source_direction != "neutral"
        and assessment_direction != source_direction
    ):
        review_reasons.append(
            "The site assessment conflicts with the current source identification."
        )
    if (
        assessment_direction != "neutral"
        and community_direction != "neutral"
        and assessment_direction != community_direction
    ):
        review_reasons.append(
            "The site assessment conflicts with the iNaturalist community taxon."
        )
    if (
        assessment_direction != "neutral"
        and identifier_directions
        and any(value != assessment_direction for value in identifier_directions)
    ):
        review_reasons.append(
            "At least one current independent identifier points the other way."
        )
    for reason in review.get("manual_review_reasons") or ():
        if str(reason).strip():
            review_reasons.append(str(reason))
    review_reasons = list(dict.fromkeys(review_reasons))

    return {
        "assessment": assessment,
        "view": view,
        "wear": wear,
        "ventral_forewing_visible": ventral_visible,
        "flight": flight,
        "evidence": evidence,
        "manual_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "reviewed_at": review.get("reviewed_at") or "",
        "review_note": review.get("review_note") or "",
        "photo_reviews": review.get("photos") or {},
        "focus": review.get("focus") or {},
    }


def _e(value):
    return escape("" if value is None else str(value), quote=True)


def _display_date(value):
    try:
        observed = date.fromisoformat(str(value))
        return f"{observed.strftime('%B')} {observed.day}, {observed.year}"
    except ValueError:
        return str(value or "Date unavailable")


def _taxon_label(taxon):
    taxon = taxon or {}
    common = taxon.get("common_name") or ""
    scientific = taxon.get("name") or ""
    if common and scientific:
        return f"{common} — {scientific}"
    return common or scientific or "No taxon"


def _assessment_class(assessment):
    if assessment.startswith("Strong"):
        return "border-hollow-400 bg-hollow-50 text-hollow-900"
    if assessment.startswith("Leaning"):
        return "border-hollow-300 bg-white text-hollow-800"
    if assessment.startswith("Unresolved"):
        return "border-amber-300 bg-amber-50 text-amber-950"
    return "border-stone-300 bg-stone-100 text-stone-800"


def _photo_review(analysis, photo):
    review = (analysis.get("photo_reviews") or {}).get(str(photo.get("id")), {})
    view = str(review.get("view") or "partial").casefold()
    if view not in VIEW_CLASSES:
        view = "partial"
    return {
        "view": view,
        "ventral_forewing_visible": bool(
            review.get("ventral_forewing_visible")
        ),
        "note": review.get("note") or "",
    }


def _photo_public_path(photo, source_dir=PHOTO_CACHE_DIR):
    cached = _photo_path(photo, source_dir)
    if cached is not None and _valid_image(cached):
        return f"photos/{cached.name}", cached
    return photo.get("url") or "", None


def _render_photos(payload, analysis, cache_dir):
    cards = []
    observation_label = _taxon_label(payload.get("source_taxon"))
    for index, photo in enumerate(payload.get("photos") or (), start=1):
        review = _photo_review(analysis, photo)
        src, _cached = _photo_public_path(photo, cache_dir)
        view_label = (
            "Partial view"
            if review["view"] == "partial"
            else f"{review['view'].title()} view"
        )
        alt = (
            f"{view_label} in photo {index} of "
            f"{observation_label}, observed {_display_date(payload.get('observed_on'))}"
        )
        visible = (
            '<span class="rounded-full bg-hollow-100 px-2 py-1 text-xs '
            'font-medium text-hollow-800">Ventral forewing assessable</span>'
            if review["ventral_forewing_visible"]
            else '<span class="rounded-full bg-stone-100 px-2 py-1 text-xs '
                 'font-medium text-stone-600">Key region not assessable</span>'
        )
        note = (
            f'<p class="text-pretty text-xs leading-5 text-stone-600">'
            f'{_e(review["note"])}</p>'
            if review["note"] else ""
        )
        cards.append(f"""
        <figure class="overflow-hidden rounded-xl border border-stone-200 bg-white">
          <a href="{_e(src)}" target="_blank" rel="noopener"
             class="block bg-stone-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-500">
            <img src="{_e(src)}" alt="{_e(alt)}" width="{_e(photo.get('width') or 1024)}"
              height="{_e(photo.get('height') or 768)}"
              class="aspect-[4/3] w-full object-cover" loading="lazy" decoding="async">
          </a>
          <figcaption class="space-y-2 p-3">
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-full border border-stone-200 px-2 py-1 text-xs font-semibold capitalize text-stone-700">{_e(review["view"])}</span>
              {visible}
            </div>
            {note}
            <p class="text-pretty text-[0.7rem] leading-4 text-stone-500">{_e(photo.get("attribution"))} · {_e(photo.get("license_code") or "license not supplied")}</p>
          </figcaption>
        </figure>""")
    if not cards:
        return (
            '<div class="rounded-xl border border-dashed border-stone-300 p-6 '
            'text-center text-stone-600">No accessible photos are attached to '
            'this observation. Manual review cannot proceed.</div>'
        )
    return (
        '<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">'
        + "".join(cards)
        + "</div>"
    )


def _render_identifiers(payload):
    entries = []
    for identification in payload.get("identifications") or ():
        user = identification.get("user") or {}
        taxon = identification.get("taxon") or {}
        state = "current" if identification.get("current") else "historical"
        body = str(identification.get("body") or "").strip()
        comment = (
            f'<blockquote class="mt-2 border-l-2 border-stone-300 pl-3 '
            f'text-pretty text-sm leading-6 text-stone-700">{_e(body)}</blockquote>'
            if body
            else '<p class="mt-2 text-xs text-stone-500">No written rationale provided.</p>'
        )
        entries.append(f"""
        <li class="rounded-lg border border-stone-200 bg-stone-50 p-3">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <p class="font-medium text-stone-900">{_e(user.get("name") or user.get("login") or "Unknown identifier")}</p>
            <span class="text-xs font-medium uppercase text-stone-500">{_e(state)} · {_e(identification.get("category") or "identification")}</span>
          </div>
          <p class="mt-1 text-pretty text-sm text-stone-700">{_e(_taxon_label(taxon))}</p>
          {comment}
        </li>""")
    for comment_record in payload.get("comments") or ():
        user = comment_record.get("user") or {}
        body = str(comment_record.get("body") or "").strip()
        if not body:
            continue
        entries.append(f"""
        <li class="rounded-lg border border-stone-200 bg-white p-3">
          <p class="font-medium text-stone-900">{_e(user.get("name") or user.get("login") or "Unknown commenter")} · comment</p>
          <blockquote class="mt-2 border-l-2 border-stone-300 pl-3 text-pretty text-sm leading-6 text-stone-700">{_e(body)}</blockquote>
        </li>""")
    if not entries:
        return (
            '<p class="rounded-lg bg-stone-50 p-4 text-pretty text-sm '
            'text-stone-600">No public identifier history or comments were '
            'returned by iNaturalist.</p>'
        )
    return '<ul class="space-y-3">' + "".join(entries) + "</ul>"


def _render_evidence(analysis):
    items = []
    for item in analysis["evidence"]:
        items.append(f"""
        <li class="grid gap-1 border-t border-stone-200 py-3 first:border-t-0 md:grid-cols-[13rem_1fr] md:gap-5">
          <h4 class="text-sm font-semibold text-stone-900">{_e(item["label"])}</h4>
          <p class="text-pretty text-sm leading-6 text-stone-700">{_e(item["finding"])}</p>
        </li>""")
    return '<ul>' + "".join(items) + "</ul>"


def _render_source_summary(payload):
    original = (payload.get("_source_record") or {}).get("original_taxon") or {}
    current = payload.get("source_taxon") or {}
    community = payload.get("community_taxon") or {}
    community_label = (
        _taxon_label(community) if community.get("id")
        else "No community taxon yet"
    )
    changed = (
        original.get("id") is not None
        and current.get("id") is not None
        and int(original["id"]) != int(current["id"])
    )
    changed_note = (
        '<p class="mt-2 text-pretty text-xs leading-5 text-stone-600">'
        'The source identification changed after this record entered the case '
        'study; both states are retained.</p>'
        if changed else ""
    )
    return f"""
    <dl class="grid gap-3 sm:grid-cols-3">
      <div class="rounded-lg bg-stone-100 p-3">
        <dt class="text-xs font-semibold uppercase text-stone-500">At case-study ingestion</dt>
        <dd class="mt-1 text-pretty text-sm font-medium text-stone-900">{_e(_taxon_label(original))}</dd>
      </div>
      <div class="rounded-lg bg-stone-100 p-3">
        <dt class="text-xs font-semibold uppercase text-stone-500">Current iNaturalist taxon</dt>
        <dd class="mt-1 text-pretty text-sm font-medium text-stone-900">{_e(_taxon_label(current))}</dd>
      </div>
      <div class="rounded-lg bg-stone-100 p-3">
        <dt class="text-xs font-semibold uppercase text-stone-500">Community taxon</dt>
        <dd class="mt-1 text-pretty text-sm font-medium text-stone-900">{_e(community_label)}</dd>
      </div>
    </dl>
    {changed_note}"""


def _render_observation(payload, analysis, cache_dir):
    observation_id = int(payload["id"])
    review_badge = ""
    review_panel = ""
    if analysis["manual_review"]:
        reasons = "".join(
            f"<li>{_e(reason)}</li>" for reason in analysis["review_reasons"]
        )
        review_badge = (
            '<span class="rounded-full bg-amber-100 px-3 py-1 text-xs '
            'font-semibold text-amber-950">Manual review</span>'
        )
        review_panel = f"""
        <div class="rounded-xl border border-amber-300 bg-amber-50 p-4">
          <h4 class="font-semibold text-amber-950">Why this remains flagged</h4>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-pretty text-sm leading-6 text-amber-950">{reasons}</ul>
        </div>"""
    review_date = (
        f'<span>Photo review {_e(analysis["reviewed_at"])}</span>'
        if analysis["reviewed_at"]
        else "<span>Awaiting photo review</span>"
    )
    location = payload.get("location") or {}
    if location.get("obscured_by_inaturalist"):
        privacy = (
            "iNaturalist marks the coordinates as obscured or private; this "
            "page publishes no coordinates."
        )
    else:
        privacy = (
            "The public source is not obscured, but this page still withholds "
            "the property's precise coordinates."
        )
    photo_count = len(payload.get("photos") or ())
    return f"""
    <article id="observation-{observation_id}" data-observation-id="{observation_id}"
      class="rounded-2xl border border-stone-200 bg-stone-50 p-5 shadow-sm md:p-7">
      <header class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p class="tabular-nums text-sm font-semibold text-hollow-700">{_e(_display_date(payload.get("observed_on")))}</p>
          <h3 class="mt-1 text-balance font-serif text-2xl font-semibold text-stone-950">{_e(_taxon_label(payload.get("source_taxon")))}</h3>
          <p class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-stone-600">
            <span>{photo_count} photo{"s" if photo_count != 1 else ""}</span>
            <span class="capitalize">{_e(analysis["view"])} view</span>
            <span class="capitalize">{_e(analysis["wear"])} wear</span>
            {review_date}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          {review_badge}
          <label for="compare-{observation_id}" class="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-semibold text-stone-800 focus-within:ring-2 focus-within:ring-hollow-500">
            <input id="compare-{observation_id}" class="compare-checkbox size-4 accent-hollow-700"
              type="checkbox" value="{observation_id}"
              aria-label="Compare observation from {_e(_display_date(payload.get("observed_on")))}">
            Compare
          </label>
          <a href="{_e(payload.get("url"))}" target="_blank" rel="noopener"
             class="rounded-lg bg-hollow-800 px-3 py-2 text-sm font-semibold text-white hover:bg-hollow-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-500 focus-visible:ring-offset-2">
            iNaturalist record
          </a>
        </div>
      </header>

      <div class="mt-5 grid gap-3 lg:grid-cols-[1fr_auto] lg:items-start">
        <div class="rounded-xl border {_assessment_class(analysis["assessment"])} p-4">
          <p class="text-xs font-semibold uppercase">Site analytical assessment</p>
          <p class="mt-1 text-balance font-serif text-xl font-semibold">{_e(analysis["assessment"])}</p>
          <p class="mt-2 text-pretty text-xs leading-5">This is a revisable evidence assessment, not a replacement for the source identification.</p>
        </div>
        <div class="rounded-xl border border-stone-200 bg-white p-4 text-sm text-stone-700">
          <p class="font-semibold text-stone-900">{_e(analysis["flight"]["label"])}</p>
          <p class="mt-1 tabular-nums">{_e(_display_date(payload.get("observed_on")))}</p>
        </div>
      </div>

      <section class="mt-6" aria-labelledby="source-{observation_id}">
        <h4 id="source-{observation_id}" class="text-balance font-serif text-lg font-semibold text-stone-950">Source identification is preserved</h4>
        <div class="mt-3">{_render_source_summary(payload)}</div>
      </section>

      <section class="mt-6" aria-labelledby="photos-{observation_id}">
        <div class="mb-3 flex flex-wrap items-end justify-between gap-2">
          <h4 id="photos-{observation_id}" class="text-balance font-serif text-lg font-semibold text-stone-950">All observation photos</h4>
          <p class="text-sm text-stone-600">View class is recorded per image.</p>
        </div>
        {_render_photos(payload, analysis, cache_dir)}
      </section>

      <div class="mt-6 grid gap-5 xl:grid-cols-2">
        <section class="rounded-xl border border-stone-200 bg-white p-4" aria-labelledby="evidence-{observation_id}">
          <h4 id="evidence-{observation_id}" class="text-balance font-serif text-lg font-semibold text-stone-950">Evidence behind the assessment</h4>
          <div class="mt-2">{_render_evidence(analysis)}</div>
        </section>
        <div class="space-y-5">
          {review_panel}
          <section class="rounded-xl border border-stone-200 bg-white p-4" aria-labelledby="identifiers-{observation_id}">
            <h4 id="identifiers-{observation_id}" class="text-balance font-serif text-lg font-semibold text-stone-950">Community IDs and identifier comments</h4>
            <p class="mt-1 text-pretty text-xs leading-5 text-stone-600">iNaturalist does not label expertise in this response, so every relevant public identifier is shown without assigning an expert credential.</p>
            <div class="mt-3">{_render_identifiers(payload)}</div>
          </section>
          <section class="rounded-xl border border-stone-200 bg-white p-4" aria-labelledby="location-{observation_id}">
            <h4 id="location-{observation_id}" class="text-balance font-serif text-lg font-semibold text-stone-950">Location and privacy</h4>
            <p class="mt-2 text-pretty text-sm font-medium text-stone-800">{_e(location.get("label") or "Kingfisher Hollow, Tioga County, New York")}</p>
            <p class="mt-1 text-pretty text-sm leading-6 text-stone-600">{_e(privacy)}</p>
          </section>
        </div>
      </div>
    </article>"""


def _copy_cached_photos(records, output_dir, cache_dir):
    photos_dir = Path(output_dir) / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    copied = set()
    for payload in records:
        for photo in payload.get("photos") or ():
            _public, cached = _photo_public_path(photo, cache_dir)
            if cached is None or cached.name in copied:
                continue
            shutil.copy2(cached, photos_dir / cached.name)
            copied.add(cached.name)
    return len(copied)


def _comparison_data(payload, analysis, cache_dir):
    photos = payload.get("photos") or []
    focus = analysis.get("focus") or {}
    focus_photo_id = focus.get("photo_id")
    focus_photo = next(
        (
            photo for photo in photos
            if str(photo.get("id")) == str(focus_photo_id)
        ),
        None,
    )
    primary = focus_photo or (photos[0] if photos else None)
    src = ""
    if primary:
        src, _cached = _photo_public_path(primary, cache_dir)
    try:
        x = max(0.0, min(float(focus.get("x", 50)), 100.0))
        y = max(0.0, min(float(focus.get("y", 50)), 100.0))
        scale = max(1.0, min(float(focus.get("scale", 1)), 4.0))
    except (TypeError, ValueError):
        x, y, scale = 50.0, 50.0, 1.0
    return {
        "id": str(payload["id"]),
        "date": _display_date(payload.get("observed_on")),
        "source": _taxon_label(payload.get("source_taxon")),
        "assessment": analysis["assessment"],
        "image": src,
        "image_alt": (
            f"Comparison photograph for observation {payload['id']} on "
            f"{_display_date(payload.get('observed_on'))}"
        ),
        "ventral_visible": bool(
            analysis.get("ventral_forewing_visible") and focus_photo
        ),
        "focus": {"x": x, "y": y, "scale": scale},
        "evidence": [
            item["finding"] for item in analysis["evidence"]
            if item["label"] in (
                "Date and seasonal flight period",
                "Ventral forewing pattern",
                "Image limitations",
            )
        ],
        "url": payload.get("url") or "",
    }


def _render_timeline(records, analyses, cache_dir):
    by_year = {}
    for payload in records:
        try:
            year = date.fromisoformat(str(payload.get("observed_on"))).year
        except ValueError:
            year = "Date unknown"
        analysis = analyses[str(payload["id"])]
        by_year.setdefault(year, []).append((payload, analysis))

    years = []
    for year, entries in sorted(
        by_year.items(), key=lambda item: str(item[0])
    ):
        bands = []
        for key, label in (
            ("spring", "Spring Eastern flight"),
            ("midsummer", "Expected Midsummer flight"),
            ("late", "Late-summer Eastern flight"),
            ("unknown", "Date unresolved"),
        ):
            matching = [
                (payload, analysis)
                for payload, analysis in entries
                if analysis["flight"]["key"] == key
            ]
            if not matching:
                continue
            cards = "".join(
                _render_observation(payload, analysis, cache_dir)
                for payload, analysis in matching
            )
            bands.append(f"""
            <section class="relative border-l-2 border-hollow-200 pl-5 md:pl-7" aria-labelledby="band-{_e(year)}-{key}">
              <span class="absolute -left-2 top-1 size-3 rounded-full border-2 border-white bg-hollow-600" aria-hidden="true"></span>
              <h3 id="band-{_e(year)}-{key}" class="text-balance font-serif text-xl font-semibold text-stone-950">{_e(label)}</h3>
              <p class="mt-1 text-pretty text-sm leading-6 text-stone-600">A comparison window only—flight timing does not determine species.</p>
              <div class="mt-4 grid gap-6">{cards}</div>
            </section>""")
        years.append(f"""
        <section aria-labelledby="year-{_e(year)}">
          <div class="mb-6 flex items-center gap-4">
            <h2 id="year-{_e(year)}" class="tabular-nums text-balance font-serif text-3xl font-semibold text-stone-950">{_e(year)}</h2>
            <span class="h-px flex-1 bg-stone-300" aria-hidden="true"></span>
          </div>
          <div class="space-y-10">{"".join(bands)}</div>
        </section>""")
    if not years:
        return """
        <div class="rounded-2xl border border-dashed border-stone-300 bg-white p-8 text-center">
          <h2 class="text-balance font-serif text-2xl font-semibold text-stone-950">No qualifying observations yet</h2>
          <p class="mx-auto mt-2 max-w-xl text-pretty text-stone-600">Run the normal property refresh. A qualifying Eastern, Midsummer, or broader tiger-swallowtail-complex record will be added here automatically.</p>
          <a href="/" class="mt-5 inline-flex rounded-lg bg-hollow-800 px-4 py-2 font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-500 focus-visible:ring-offset-2">Return to the survey</a>
        </div>"""
    return '<div class="space-y-16">' + "".join(years) + "</div>"


def _default_comparison_ids(records):
    wanted_dates = ("2026-07-23", "2026-07-24")
    selected = [
        str(payload["id"]) for wanted in wanted_dates
        for payload in records if payload.get("observed_on") == wanted
    ]
    if len(selected) >= 2:
        return selected[:2]
    return [str(payload["id"]) for payload in records[-2:]]


def _page_html(records, analyses, cache_dir):
    comparison = [
        _comparison_data(payload, analyses[str(payload["id"])], cache_dir)
        for payload in records
    ]
    default_ids = _default_comparison_ids(records)
    latest = records[-1] if records else {}
    latest_photo = next(iter(latest.get("photos") or ()), {})
    social_image = latest_photo.get("url") or (
        "https://www.kingfisher-hollow.com/aerial/"
        "dji_fly_20251020_173830_305_1760996794506_photo_optimized.JPG"
    )
    years = {
        str(payload.get("observed_on") or "")[:4]
        for payload in records if payload.get("observed_on")
    }
    uncertain = sum(
        analyses[str(payload["id"])]["manual_review"]
        for payload in records
    )
    timeline = _render_timeline(records, analyses, cache_dir)
    data_json = json.dumps(
        comparison, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    defaults_json = json.dumps(default_ids, separators=(",", ":"))
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    description = (
        "A self-updating Kingfisher Hollow case study comparing Eastern and "
        "Midsummer Tiger Swallowtail observations, photographs, source "
        "identifications, and explicit image limitations."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tiger Swallowtail Case Study · Kingfisher Hollow</title>
  <meta name="description" content="{_e(description)}">
  <link rel="canonical" href="{CASE_URL}">
  <meta name="robots" content="index,follow">
  <meta name="theme-color" content="#0d221c">
  <meta property="og:type" content="article">
  <meta property="og:title" content="Tiger Swallowtail Case Study · Kingfisher Hollow">
  <meta property="og:description" content="{_e(description)}">
  <meta property="og:url" content="{CASE_URL}">
  <meta property="og:image" content="{_e(social_image)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Tiger Swallowtail Case Study · Kingfisher Hollow">
  <meta name="twitter:description" content="{_e(description)}">
  <meta name="twitter:image" content="{_e(social_image)}">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%230d221c'/%3E%3Cpath d='M12 36c9-18 21-18 20-2 1-16 13-16 20 2-6 11-14 12-20 3-6 9-14 8-20-3Z' fill='%238ec8b1'/%3E%3C/svg%3E">
  <link rel="preload" href="/assets/fonts/inter-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="preload" href="/assets/fonts/playfair-display-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="/assets/survey.css">
  <style>
    .focus-frame img {{ transform: scale(var(--focus-scale, 1)); object-position: var(--focus-x, 50%) var(--focus-y, 50%); }}
    @media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} }}
  </style>
</head>
<body class="bg-stone-100 font-sans text-stone-800 antialiased">
  <a href="#main" class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-stone-950 focus:ring-2 focus:ring-hollow-500">Skip to case study</a>
  <header class="border-b border-white/10 bg-hollow-950 text-white">
    <nav aria-label="Case-study navigation" class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
      <a href="/" class="font-serif text-lg font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-300">Kingfisher Hollow Survey</a>
      <div class="flex flex-wrap gap-4 text-sm">
        <a href="/#butterflies" class="text-white/80 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-300">Butterflies</a>
        <a href="{PROJECT_URL}" target="_blank" rel="noopener" class="text-white/80 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-300">iNaturalist project</a>
      </div>
    </nav>
    <div class="mx-auto max-w-6xl px-6 pb-16 pt-12 md:pb-20 md:pt-16">
      <p class="font-semibold text-hollow-300">Living case study · Papilio glaucus complex</p>
      <h1 class="mt-3 max-w-4xl text-balance font-serif text-4xl font-semibold leading-tight md:text-6xl">Tiger swallowtails, evidence first</h1>
      <p class="mt-5 max-w-3xl text-pretty text-lg leading-8 text-white/75">A chronological record of Eastern Tiger Swallowtail, Midsummer Tiger Swallowtail, and observations that photographs cannot safely resolve. Source IDs remain visible beside a separate, revisable site assessment.</p>
      <dl class="mt-8 flex flex-wrap gap-x-10 gap-y-5">
        <div><dt class="text-sm text-white/60">Observations</dt><dd class="tabular-nums mt-1 font-serif text-3xl text-hollow-200">{len(records)}</dd></div>
        <div><dt class="text-sm text-white/60">Years represented</dt><dd class="tabular-nums mt-1 font-serif text-3xl text-hollow-200">{len(years)}</dd></div>
        <div><dt class="text-sm text-white/60">Flagged for review</dt><dd class="tabular-nums mt-1 font-serif text-3xl text-hollow-200">{uncertain}</dd></div>
      </dl>
    </div>
  </header>

  <main id="main">
    <section class="border-b border-stone-200 bg-white px-6 py-10">
      <div class="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h2 class="text-balance font-serif text-2xl font-semibold text-stone-950">What this page can—and cannot—show</h2>
          <p class="mt-3 text-pretty leading-7 text-stone-700">The 2025 species description emphasizes a suite of characters: the ventral forewing submarginal band, hindwing margin and lunules, wing shape, sex-linked traits, phenology, and location. Individual characters overlap. External appearance and date may not be sufficient for a definitive identification.</p>
          <p class="mt-3 text-pretty leading-7 text-stone-700">Accordingly, a dorsal-only, distant, worn, or newly added observation stays unresolved unless multiple visible traits support the same direction. “Strong” is still an analytical reading of photographs—not a genetic determination.</p>
          <a href="{PAPER_URL}" target="_blank" rel="noopener" class="mt-4 inline-flex font-semibold text-hollow-800 underline decoration-hollow-300 underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-500">Read the primary species description</a>
        </div>
        <aside class="rounded-2xl border border-hollow-200 bg-hollow-50 p-5">
          <h2 class="text-balance font-serif text-xl font-semibold text-hollow-950">Automatic update rule</h2>
          <ol class="mt-3 list-decimal space-y-2 pl-5 text-pretty text-sm leading-6 text-hollow-950">
            <li>Include any Eastern, Midsummer, or broader glaucus-complex observation on the next normal refresh.</li>
            <li>Cache and publish every accessible observation photo.</li>
            <li>Apply the evidence rubric; default unseen morphology to insufficient evidence.</li>
            <li>Flag provisional, conflicting, or date-conflicting records for manual review.</li>
          </ol>
        </aside>
      </div>
      <div class="mx-auto mt-6 max-w-6xl rounded-2xl border border-stone-200 bg-stone-50 p-5">
        <h2 class="text-balance font-serif text-xl font-semibold text-stone-950">Assessment vocabulary—not a confidence score</h2>
        <dl class="mt-3 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div><dt class="font-semibold text-stone-950">Strong Eastern / Strong Midsummer</dt><dd class="mt-1 text-pretty leading-6 text-stone-600">The key ventral character and at least one additional visible morphological trait point the same way.</dd></div>
          <div><dt class="font-semibold text-stone-950">Leaning Eastern / Leaning Midsummer</dt><dd class="mt-1 text-pretty leading-6 text-stone-600">Visible evidence has a direction, but the suite is incomplete or limited to secondary characters.</dd></div>
          <div><dt class="font-semibold text-stone-950">Unresolved Eastern/Midsummer</dt><dd class="mt-1 text-pretty leading-6 text-stone-600">Usable characters overlap or point in conflicting directions.</dd></div>
          <div><dt class="font-semibold text-stone-950">Insufficient photographic evidence</dt><dd class="mt-1 text-pretty leading-6 text-stone-600">The needed surface, detail, angle, or quality is absent; date and source ID do not fill the gap.</dd></div>
        </dl>
      </div>
    </section>

    <section id="comparison" class="bg-hollow-950 px-6 py-14 text-white" aria-labelledby="comparison-title">
      <div class="mx-auto max-w-6xl">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p class="font-semibold text-hollow-300">Focused comparison</p>
            <h2 id="comparison-title" class="mt-2 text-balance font-serif text-3xl font-semibold md:text-4xl">Put the same wing region side by side</h2>
            <p class="mt-3 max-w-3xl text-pretty leading-7 text-white/70">Select two to four timeline records. Region focus prioritizes the underside of the forewing; when that region is missing, the comparison says so instead of implying a crop exists.</p>
          </div>
          <fieldset class="rounded-xl border border-white/20 p-3">
            <legend class="px-1 text-sm font-semibold text-white">Comparison view</legend>
            <div class="mt-1 flex flex-wrap gap-3">
              <label class="flex cursor-pointer items-center gap-2"><input type="radio" name="compare-view" value="focus" class="size-4 accent-hollow-300" checked> Wing-region focus</label>
              <label class="flex cursor-pointer items-center gap-2"><input type="radio" name="compare-view" value="full" class="size-4 accent-hollow-300"> Full photograph</label>
            </div>
          </fieldset>
        </div>
        <p id="compare-status" class="mt-5 min-h-6 text-sm font-medium text-hollow-200" role="status" aria-live="polite"></p>
        <div id="compare-grid" class="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-4" aria-live="polite"></div>
      </div>
    </section>

    <section id="timeline" class="px-6 py-16 md:py-20" aria-labelledby="timeline-title">
      <div class="mx-auto max-w-6xl">
        <div class="mb-12 max-w-3xl">
          <p class="font-semibold text-hollow-700">All observations</p>
          <h2 id="timeline-title" class="mt-2 text-balance font-serif text-3xl font-semibold text-stone-950 md:text-4xl">Chronological evidence timeline</h2>
          <p class="mt-3 text-pretty leading-7 text-stone-700">Years are separated, then records are placed in three comparison windows. Similar dates share a row so spring, midsummer-overlap, and late-summer evidence can be read together.</p>
        </div>
        {timeline}
      </div>
    </section>
  </main>

  <footer class="bg-hollow-950 px-6 py-10 text-white/70">
    <div class="mx-auto flex max-w-6xl flex-col gap-3 text-pretty text-sm md:flex-row md:items-center md:justify-between">
      <p>Data from iNaturalist · Photos retain source attribution and license · Exact property coordinates withheld</p>
      <p class="tabular-nums">Generated {_e(generated)}</p>
    </div>
  </footer>

  <script type="application/json" id="comparison-data">{data_json}</script>
  <script type="application/json" id="comparison-defaults">{defaults_json}</script>
  <script>
  (() => {{
    const records = JSON.parse(document.getElementById('comparison-data').textContent);
    const defaults = JSON.parse(document.getElementById('comparison-defaults').textContent);
    const byId = new Map(records.map(record => [record.id, record]));
    const boxes = [...document.querySelectorAll('.compare-checkbox')];
    const grid = document.getElementById('compare-grid');
    const status = document.getElementById('compare-status');
    const modes = [...document.querySelectorAll('input[name="compare-view"]')];
    const params = new URLSearchParams(location.search);
    const requested = (params.get('compare') || '').split(',').filter(id => byId.has(id));
    const initial = (requested.length >= 2 ? requested : defaults).slice(0, 4);
    boxes.forEach(box => {{ box.checked = initial.includes(box.value); }});

    const element = (name, className, text) => {{
      const node = document.createElement(name);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }};

    function selectedIds() {{
      return boxes.filter(box => box.checked).map(box => box.value);
    }}

    function render() {{
      const ids = selectedIds();
      const mode = modes.find(input => input.checked)?.value || 'focus';
      grid.replaceChildren();
      grid.className = ids.length <= 2
        ? 'mt-5 grid gap-5 md:grid-cols-2'
        : 'mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-4';
      boxes.forEach(box => {{
        box.disabled = !box.checked && ids.length >= 4;
        box.closest('label')?.classList.toggle('opacity-50', box.disabled);
      }});
      status.textContent = ids.length < 2
        ? 'Select at least two observations to compare.'
        : `${{ids.length}} observations aligned in ${{mode === 'focus' ? 'wing-region focus' : 'full-photo'}} view.`;

      ids.forEach(id => {{
        const record = byId.get(id);
        if (!record) return;
        const card = element('article', 'rounded-2xl border border-white/15 bg-white/5 p-4');
        card.append(
          element('p', 'tabular-nums text-sm font-semibold text-hollow-200', record.date),
          element('h3', 'mt-1 text-balance font-serif text-xl font-semibold text-white', record.assessment),
          element('p', 'mt-1 text-pretty text-xs leading-5 text-white/60', `Source: ${{record.source}}`)
        );
        const frame = element('div', 'focus-frame relative mt-4 aspect-[4/3] overflow-hidden rounded-xl bg-white/10');
        if (record.image) {{
          const image = document.createElement('img');
          image.src = record.image;
          image.alt = record.image_alt;
          image.loading = 'lazy';
          image.decoding = 'async';
          image.className = `size-full ${{mode === 'focus' ? 'object-cover' : 'object-contain'}}`;
          if (mode === 'focus' && record.ventral_visible) {{
            image.style.setProperty('--focus-x', `${{record.focus.x}}%`);
            image.style.setProperty('--focus-y', `${{record.focus.y}}%`);
            image.style.setProperty('--focus-scale', String(record.focus.scale));
          }}
          frame.append(image);
        }} else {{
          frame.append(element('p', 'grid size-full place-items-center p-4 text-center text-sm text-white/70', 'No accessible photograph'));
        }}
        if (mode === 'focus' && !record.ventral_visible) {{
          const note = element('p', 'absolute inset-x-3 bottom-3 rounded-lg bg-hollow-950/95 p-3 text-center text-sm font-semibold text-white', 'Ventral forewing not visible clearly enough');
          frame.append(note);
        }}
        card.append(frame);
        const list = element('ul', 'mt-4 list-disc space-y-2 pl-5 text-pretty text-xs leading-5 text-white/70');
        record.evidence.forEach(finding => list.append(element('li', '', finding)));
        card.append(list);
        const link = element('a', 'mt-4 inline-flex text-sm font-semibold text-hollow-200 underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-hollow-300', 'Open source record');
        link.href = record.url;
        link.target = '_blank';
        link.rel = 'noopener';
        card.append(link);
        grid.append(card);
      }});

      const url = new URL(location.href);
      if (ids.length) url.searchParams.set('compare', ids.join(','));
      else url.searchParams.delete('compare');
      history.replaceState(null, '', url);
    }}

    boxes.forEach(box => box.addEventListener('change', render));
    modes.forEach(input => input.addEventListener('change', render));
    render();
  }})();
  </script>
</body>
</html>
"""


def build(
    output_dir=OUTPUT_DIR,
    review_path=REVIEW_PATH,
    cache_dir=PHOTO_CACHE_DIR,
    records=None,
):
    """Generate the case-study route from the current local source snapshot."""
    if records is None:
        with connect() as conn:
            records = _payloads_from_connection(conn)
    records = sorted(
        records,
        key=lambda payload: (
            str(payload.get("observed_on") or ""),
            int(payload.get("id") or 0),
        ),
    )
    reviews = _read_reviews(review_path)
    review_records = reviews.get("observations") or {}
    analyses = {
        str(payload["id"]): assess_observation(
            payload,
            review_records.get(str(payload["id"])),
        )
        for payload in records
    }

    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_cached_photos(records, output_dir, Path(cache_dir))
    output = output_dir / "index.html"
    output.write_text(
        _page_html(records, analyses, Path(cache_dir)),
        encoding="utf-8",
    )
    print(
        f"Wrote {output} ({len(records)} observations; "
        f"{copied} locally cached photos)"
    )
    return output


if __name__ == "__main__":
    build()
