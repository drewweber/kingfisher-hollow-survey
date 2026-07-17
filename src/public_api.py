"""Build the privacy-safe data snapshot consumed by the public moth API."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config import PUBLIC_DIR
from db import connect


API_DATASET = "kingfisher-hollow-moths"
API_SCHEMA_VERSION = 1
LOCAL_TIMEZONE = "America/New_York"
SNAPSHOT_PATH = PUBLIC_DIR / "_api-data" / "moths.json"

_MOTH_OBSERVATIONS_SQL = """
SELECT
    p.id AS observation_id,
    p.taxon_id,
    p.taxon_name AS scientific_name,
    p.common_name,
    COALESCE(t.order_name, 'Lepidoptera') AS order_name,
    t.family_name AS family,
    p.rank,
    p.observed_at
FROM property_obs AS p
JOIN moth_taxa AS m ON m.taxon_id = p.taxon_id
LEFT JOIN taxon_meta AS t ON t.taxon_id = p.taxon_id
ORDER BY p.observed_at DESC, p.id DESC
"""


def _timestamp(value=None):
    if value is not None:
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _required_text(value, field, observation_id):
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(
            f"Moth observation {observation_id} is missing required field {field}"
        )
    return text


def _optional_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _local_observation_date(value, observation_id):
    observed_at = _required_text(value, "observed_at", observation_id)
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"Moth observation {observation_id} has an invalid observed_at timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(
            f"Moth observation {observation_id} has no observed_at timezone"
        )
    local_date = parsed.astimezone(ZoneInfo(LOCAL_TIMEZONE)).date().isoformat()
    return observed_at, local_date


def snapshot_from_connection(conn, generated_at=None):
    """Return a deduplicated API snapshot from an open SQLite connection."""
    observations = []
    seen_ids = set()

    for row in conn.execute(_MOTH_OBSERVATIONS_SQL):
        observation_id = int(row["observation_id"])
        if observation_id in seen_ids:
            continue
        seen_ids.add(observation_id)

        observed_at, observed_on = _local_observation_date(
            row["observed_at"], observation_id
        )
        observations.append(
            {
                "observation_id": observation_id,
                "taxon_id": int(row["taxon_id"]),
                "scientific_name": _required_text(
                    row["scientific_name"], "scientific_name", observation_id
                ),
                "common_name": _optional_text(row["common_name"]),
                "order": _required_text(row["order_name"], "order", observation_id),
                "family": _required_text(row["family"], "family", observation_id),
                "rank": _required_text(row["rank"], "rank", observation_id),
                "observed_on": observed_on,
                "observed_at": observed_at,
                "inat_url": (
                    f"https://www.inaturalist.org/observations/{observation_id}"
                ),
            }
        )

    dates = sorted({row["observed_on"] for row in observations})
    species = {row["taxon_id"] for row in observations}
    canonical = json.dumps(
        observations,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    return {
        "schema_version": API_SCHEMA_VERSION,
        "dataset": API_DATASET,
        "generated_at": _timestamp(generated_at),
        "timezone": LOCAL_TIMEZONE,
        "data_version": hashlib.sha256(canonical).hexdigest()[:16],
        "observation_count": len(observations),
        "species_count": len(species),
        "night_count": len(dates),
        "first_observation_date": dates[0] if dates else None,
        "last_observation_date": dates[-1] if dates else None,
        "observations": observations,
    }


def write_snapshot(conn, output_path=SNAPSHOT_PATH, generated_at=None):
    """Write the API snapshot and return its metadata payload."""
    payload = snapshot_from_connection(conn, generated_at=generated_at)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return payload


def build(output_path=SNAPSHOT_PATH):
    """Build the deployed API snapshot from the current survey database."""
    with connect() as conn:
        payload = write_snapshot(conn, output_path=output_path)
    size_kb = Path(output_path).stat().st_size // 1024
    print(
        f"Wrote {output_path} ({size_kb:,} KB; "
        f"{payload['observation_count']:,} moth observations)"
    )
    return Path(output_path)


if __name__ == "__main__":
    build()
