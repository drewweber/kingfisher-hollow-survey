"""Conservative host-guild signals for the offline moth target list."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


LOOKBACK_DAYS = 14
MAX_SCORING_HOST_GENERA = 12
MAX_SIGNAL_INDICATORS = 3
HOST_INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "moth-hosts.json"

HOST_LABELS = {
    "Acer": "maple",
    "Alnus": "alder",
    "Amelanchier": "serviceberry",
    "Ampelopsis": "peppervine",
    "Berberis": "barberry",
    "Betula": "birch",
    "Carya": "hickory",
    "Celtis": "hackberry",
    "Clematis": "clematis",
    "Cornus": "dogwood",
    "Crataegus": "hawthorn",
    "Hamamelis": "witch-hazel",
    "Juglans": "walnut",
    "Malus": "apple",
    "Mentha": "mint",
    "Monarda": "bee balm",
    "Oenothera": "evening-primrose",
    "Parthenocissus": "Virginia-creeper",
    "Platanus": "sycamore",
    "Populus": "poplar/aspen",
    "Prunus": "cherry/plum",
    "Quercus": "oak",
    "Rhus": "sumac",
    "Rosa": "rose",
    "Rubus": "raspberry/blackberry",
    "Salix": "willow",
    "Tilia": "basswood",
    "Ulmus": "elm",
    "Viburnum": "viburnum",
    "Vitis": "grape",
}

# Current names that are absent from HOSTS but have records under a documented
# synonym. The checked-in index records both names and retains this provenance.
HOST_TAXON_ALIASES = {
    "Lintneria eremitus": ["Sphinx eremitus"],
    "Macaria pustularia": ["Itame pustularia"],
    "Prochoerodes lineola": ["Prochoerodes transversata"],
}


def load_host_index(path=HOST_INDEX_PATH):
    """Load the checked-in HOSTS reduction; missing data means no guild boost."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"associations": {}, "source": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("associations"), dict):
        return {"associations": {}, "source": {}}
    return payload


def host_label(genus):
    return HOST_LABELS.get(genus, f"{genus} host")


def _breadth_weight(host_count):
    """Downweight broad feeders; very broad associations are informational only."""
    if host_count == 1:
        return 1.0
    if host_count <= 3:
        return 0.85
    if host_count <= 6:
        return 0.65
    if host_count <= MAX_SCORING_HOST_GENERA:
        return 0.35
    return 0.0


def _association(index, scientific_name):
    raw = (index.get("associations") or {}).get(scientific_name)
    if not isinstance(raw, dict):
        return None
    hosts = sorted({
        str(host).strip()
        for host in raw.get("host_genera") or []
        if str(host).strip()
    })
    if not hosts:
        return None
    return {**raw, "host_genera": hosts}


def local_flight_signal(scientific_name, recent_moths, index, effective_date):
    """Return a transparent recent-host-guild signal for one missing moth.

    A signal requires an exact shared larval-host genus between the target and
    another moth observed at Kingfisher Hollow during the previous 14 days.
    Broad feeders are strongly downweighted and associations broader than
    ``MAX_SCORING_HOST_GENERA`` do not affect ranking.
    """
    target = _association(index, scientific_name)
    if not target:
        return None
    target_hosts = set(target["host_genera"])
    target_weight = _breadth_weight(len(target_hosts))
    if not target_weight:
        return None

    matched = []
    guilds = {}
    for recent in recent_moths:
        indicator_name = recent.get("scientific_name") or ""
        if not indicator_name or indicator_name == scientific_name:
            continue
        indicator = _association(index, indicator_name)
        if not indicator:
            continue
        indicator_hosts = set(indicator["host_genera"])
        indicator_weight = _breadth_weight(len(indicator_hosts))
        if not indicator_weight:
            continue
        shared = sorted(target_hosts & indicator_hosts)
        if not shared:
            continue

        last_seen = recent.get("last_seen")
        if isinstance(last_seen, str):
            try:
                last_seen = date.fromisoformat(last_seen)
            except ValueError:
                continue
        if not isinstance(last_seen, date):
            continue
        age_days = (effective_date - last_seen).days
        if age_days < 0 or age_days >= LOOKBACK_DAYS:
            continue

        recency = max(0.55, 1.0 - age_days / (LOOKBACK_DAYS * 2))
        base = target_weight * indicator_weight * recency
        contribution = base * min(1.1, 1.0 + 0.05 * (len(shared) - 1))
        match = {
            "common_name": recent.get("common_name") or indicator_name,
            "scientific_name": indicator_name,
            "last_seen": last_seen.isoformat(),
            "observation_count": int(recent.get("observation_count") or 0),
            "shared_host_genera": shared,
            "contribution": contribution,
        }
        matched.append(match)
        for genus in shared:
            guilds.setdefault(genus, []).append(match)

    if not matched:
        return None
    matched.sort(key=lambda item: (-item["contribution"], item["scientific_name"]))
    leaders = matched[:MAX_SIGNAL_INDICATORS]
    score = leaders[0]["contribution"]
    if len(leaders) > 1:
        score += leaders[1]["contribution"] * 0.18
    if len(leaders) > 2:
        score += leaders[2]["contribution"] * 0.10
    score = round(min(1.2, score), 3)
    if score < 0.35:
        return None
    if score >= 0.9:
        strength = "strong"
        label = "Strong local flight signal"
    elif score >= 0.55:
        strength = "moderate"
        label = "Local flight signal"
    else:
        strength = "supporting"
        label = "Supporting local signal"

    guild_records = []
    for genus, indicators in guilds.items():
        indicators = sorted(
            indicators,
            key=lambda item: (-item["contribution"], item["scientific_name"]),
        )
        guild_records.append({
            "host_genus": genus,
            "host_label": host_label(genus),
            "latest_seen": max(item["last_seen"] for item in indicators),
            "indicators": [
                {
                    key: item[key]
                    for key in (
                        "common_name", "scientific_name", "last_seen",
                        "observation_count",
                    )
                }
                for item in indicators[:MAX_SIGNAL_INDICATORS]
            ],
            "_score": sum(item["contribution"] for item in indicators),
        })
    guild_records.sort(key=lambda item: (-item["_score"], item["host_genus"]))
    for guild in guild_records:
        guild.pop("_score", None)

    source = index.get("source") or {}
    return {
        "score": score,
        "strength": strength,
        "label": label,
        "lookback_days": LOOKBACK_DAYS,
        "target_host_genera": sorted(target_hosts),
        "guilds": guild_records[:4],
        "source_name": source.get("title") or "HOSTS",
        "source_url": source.get("url") or "",
        "caution": (
            "Shared larval hosts and recent adult activity are supporting timing "
            "evidence, not proof that this target is present."
        ),
    }
