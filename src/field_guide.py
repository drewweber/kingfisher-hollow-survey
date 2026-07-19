"""Build the isolated, fully offline Kingfisher Hollow field-target PWA."""

from __future__ import annotations

import calendar
import hashlib
import json
import shutil
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

import analyze
import inat_api
from config import DATA_DIR, PUBLIC_DIR, REGION_RADIUS_KM, ROOT, USER_AGENT
from db import DB_PATH, connect
from field_guidance import build_guidance


APP_SOURCE = ROOT / "field-guide" / "app"
SW_TEMPLATE = ROOT / "field-guide" / "service-worker.js"
OUTPUT_DIR = PUBLIC_DIR / "field"
CACHE_DIR = DATA_DIR / "cache" / "field-guide"
IMAGE_CACHE_DIR = CACHE_DIR / "images"
PHOTO_CACHE = CACHE_DIR / "taxa.json"
GUIDANCE_REVISION = "2026-07-19.1"
SCHEMA_VERSION = "kh-field-targets/1.1.0"
TARGET_IMAGE_COUNT = 2
LOOKALIKE_IMAGE_COUNT = 1
MAX_PACKAGE_BYTES = 75 * 1024 * 1024

ALLOWED_LICENSES = {
    "cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa",
    "cc-by-nd", "cc-by-nc-nd",
}
LICENSE_LABELS = {
    "cc0": "CC0",
    "cc-by": "CC BY",
    "cc-by-sa": "CC BY-SA",
    "cc-by-nc": "CC BY-NC",
    "cc-by-nc-sa": "CC BY-NC-SA",
    "cc-by-nd": "CC BY-ND",
    "cc-by-nc-nd": "CC BY-NC-ND",
}
LICENSE_URLS = {
    "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-by": "https://creativecommons.org/licenses/by/4.0/",
    "cc-by-sa": "https://creativecommons.org/licenses/by-sa/4.0/",
    "cc-by-nc": "https://creativecommons.org/licenses/by-nc/4.0/",
    "cc-by-nc-sa": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "cc-by-nd": "https://creativecommons.org/licenses/by-nd/4.0/",
    "cc-by-nc-nd": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
}
DEFAULT_MONTHS = {
    "moths": [4, 5, 6, 7, 8, 9, 10],
    "butterflies": [4, 5, 6, 7, 8, 9, 10],
    "odonates": [5, 6, 7, 8, 9, 10],
}
GROUP_TABLES = {
    "moths": "region_moth_taxa",
    "butterflies": "region_butterfly_taxa",
    "odonates": "region_odonate_taxa",
}


def _clean(value, fallback=""):
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    return value


def _json_read(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _json_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _database_sha256():
    digest = hashlib.sha256()
    with DB_PATH.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_data_sync():
    with connect() as conn:
        row = conn.execute("SELECT MAX(synced_at) AS synced_at FROM sync_log").fetchone()
    return (row["synced_at"] if row and row["synced_at"] else
            datetime.now(timezone.utc).isoformat())


def _target_frames(effective_date):
    target_months = sorted({effective_date.month, (effective_date + timedelta(days=14)).month})
    return {
        "moths": analyze.moth_county_gap(
            analyze.load_moths(), n=50, target_months=target_months
        )["missing"].copy(),
        "butterflies": analyze.butterfly_gap(
            analyze.load_butterflies(), n=30
        )["missing"].copy(),
        "odonates": analyze.odonate_gap(
            analyze.load_odonates(), n=30
        )["missing"].copy(),
    }, target_months


def _month_counts(taxon_ids):
    if not taxon_ids:
        return {}
    placeholders = ",".join("?" for _ in taxon_ids)
    with connect() as conn:
        rows = conn.execute(
            "SELECT taxon_id, CAST(strftime('%m', observed_on) AS INTEGER) AS month, "
            "COUNT(*) AS count FROM county_obs WHERE taxon_id IN (" + placeholders + ") "
            "AND observed_on IS NOT NULL AND (captive IS NULL OR captive = 0) "
            "GROUP BY taxon_id, month",
            list(taxon_ids),
        ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(int(row["taxon_id"]), {})[int(row["month"])] = int(row["count"])
    return result


def _season_label(month_counts, fallback_months):
    months = sorted(month_counts) or list(fallback_months)
    if not months:
        return "the main field season"
    if len(months) == 1:
        span = calendar.month_name[months[0]]
    else:
        span = f"{calendar.month_abbr[months[0]]}-{calendar.month_abbr[months[-1]]}"
    if month_counts:
        peaks = sorted(month_counts, key=lambda m: (-month_counts[m], m))[:2]
        peak_label = "/".join(calendar.month_abbr[m] for m in peaks)
        return f"{span}; nearby records peak in {peak_label}"
    return f"{span}; local timing is not yet well sampled"


def _regional_peers():
    peers = {}
    with connect() as conn:
        for group, table in GROUP_TABLES.items():
            frame = pd.read_sql_query(
                f"SELECT r.*, m.family_name, m.family_common FROM {table} r "
                "LEFT JOIN taxon_meta m USING (taxon_id)", conn
            )
            peers[group] = frame
    return peers


def _lookalikes(group, taxon_name, family_name, peers, limit=3):
    frame = peers[group]
    if frame.empty:
        return []
    genus = (taxon_name or "").split(" ", 1)[0]
    same_genus = frame[
        frame["taxon_name"].fillna("").str.startswith(f"{genus} ")
        & (frame["taxon_name"] != taxon_name)
    ]
    candidates = same_genus
    if candidates.empty and family_name and "family_name" in frame.columns:
        candidates = frame[
            (frame["family_name"] == family_name) & (frame["taxon_name"] != taxon_name)
        ]
    if candidates.empty:
        return []
    count_col = "region_count" if "region_count" in candidates.columns else "ref_count"
    candidates = candidates.sort_values([count_col, "taxon_id"], ascending=[False, True])
    return [
        {
            "taxon_id": int(row["taxon_id"]),
            "common_name": _clean(row.get("common_name")),
            "scientific_name": _clean(row.get("taxon_name")),
        }
        for _, row in candidates.head(limit).iterrows()
    ]


def collect_targets(effective_date=None):
    """Return target records before remote photo enrichment.

    Membership comes directly from the same selectors and limits used by the
    public survey, which keeps the two products in lockstep without changing
    the survey itself.
    """
    effective_date = effective_date or date.today()
    frames, moth_months = _target_frames(effective_date)
    ids = [int(tid) for frame in frames.values() for tid in frame["taxon_id"].tolist()]
    months_by_taxon = _month_counts(ids)
    peers = _regional_peers()
    with connect() as conn:
        metadata = {
            int(row["taxon_id"]): dict(row)
            for row in conn.execute(
                "SELECT taxon_id, order_name, order_common, family_name, family_common FROM taxon_meta"
            ).fetchall()
        }

    records = []
    rank = 0
    for group, frame in frames.items():
        for group_rank, (_, row) in enumerate(frame.iterrows(), start=1):
            rank += 1
            taxon_id = int(row["taxon_id"])
            meta = metadata.get(taxon_id, {})
            scientific_name = _clean(row.get("taxon_name"))
            common_name = (_clean(row.get("common_name")) or scientific_name
                           or "Unidentified target")
            family_name = meta.get("family_name") or ""
            month_counts = months_by_taxon.get(taxon_id, {})
            fallback = moth_months if group == "moths" else DEFAULT_MONTHS[group]
            season_label = _season_label(month_counts, fallback)
            lookalikes = _lookalikes(group, scientific_name, family_name, peers)
            regional_count = int(_clean(row.get("ref_count"), 0)
                                 or _clean(row.get("region_count"), 0) or 0)
            guidance = build_guidance(
                group, family_name, common_name, season_label, regional_count, lookalikes
            )
            records.append({
                "id": taxon_id,
                "taxon_id": taxon_id,
                "group": group,
                "rank": rank,
                "group_rank": group_rank,
                "common_name": common_name,
                "scientific_name": scientific_name,
                "order_name": meta.get("order_name") or "",
                "order_common": meta.get("order_common") or "",
                "family_name": family_name,
                "family_common": meta.get("family_common") or "",
                "regional_count": regional_count,
                "season_label": season_label,
                "active_months": sorted(month_counts) or list(fallback),
                "phenology_scope": "Tioga County observations" if month_counts else "group field season",
                "taxon_url": f"https://www.inaturalist.org/taxa/{taxon_id}",
                "guidance_status": "family evidence protocol",
                "_peer_taxa": lookalikes,
                **guidance,
            })
    if len(ids) != len(set(ids)):
        raise ValueError("A taxon appears in more than one field target set")
    return records, {group: len(frame) for group, frame in frames.items()}, moth_months


def _normalize_taxon(taxon):
    ranks = {a.get("rank"): a for a in (taxon.get("ancestors") or [])}
    photo = taxon.get("default_photo") or {}
    code = (photo.get("license_code") or "").casefold()
    photo_record = None
    if code in ALLOWED_LICENSES and photo.get("medium_url") and photo.get("attribution"):
        photo_record = {
            "id": photo.get("id"),
            "medium_url": photo.get("medium_url"),
            "attribution": photo.get("attribution"),
            "license_code": code,
            "source_url": f"https://www.inaturalist.org/photos/{photo.get('id')}",
        }
    return {
        "taxon_id": int(taxon["id"]),
        "preferred_common_name": taxon.get("preferred_common_name") or "",
        "family_name": (ranks.get("family") or {}).get("name") or "",
        "family_common": (ranks.get("family") or {}).get("preferred_common_name") or "",
        "order_name": (ranks.get("order") or {}).get("name") or "",
        "order_common": (ranks.get("order") or {}).get("preferred_common_name") or "",
        "photo": photo_record,
    }


def _deduplicate_photos(photos):
    result = []
    seen = set()
    for photo in photos or []:
        if not isinstance(photo, dict):
            continue
        key = str(photo.get("id")) if photo.get("id") is not None else photo.get("medium_url")
        if not key or key in seen or not photo.get("medium_url"):
            continue
        seen.add(key)
        result.append(photo)
    return result


def _cached_photos(record):
    """Migrate the original single-photo cache without discarding usable media."""
    return _deduplicate_photos([*(record.get("photos") or []), record.get("photo")])


def resolve_taxa(photo_requirements):
    """Resolve taxonomy plus enough licensed photos for each requested taxon.

    ``photo_requirements`` maps taxon IDs to the number of local photos needed:
    two reference views for a target and one for a named lookalike.
    """
    target_ids = list(photo_requirements)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _json_read(PHOTO_CACHE, {"taxa": {}})
    taxa = cache.setdefault("taxa", {})
    missing = [tid for tid in target_ids if str(tid) not in taxa]
    for start in range(0, len(missing), 30):
        batch = missing[start:start + 30]
        for taxon in inat_api.fetch_taxa(batch):
            normalized = _normalize_taxon(taxon)
            taxa[str(normalized["taxon_id"])] = normalized

    unresolved = []
    photo_requests = []
    for taxon_id in target_ids:
        record = taxa.get(str(taxon_id))
        if not record:
            unresolved.append(taxon_id)
            continue
        required = max(1, int(photo_requirements[taxon_id]))
        photos = _cached_photos(record)
        if len(photos) < required:
            photo_requests.append((taxon_id, required, photos))
        else:
            record["photos"] = photos
            record["photo"] = photos[0]

    # Photo metadata is independent per taxon. Keep the pool deliberately
    # small because this runs against iNaturalist, while avoiding one-second
    # pauses serializing a whole new field-guide release.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(
                inat_api.fetch_licensed_photos,
                taxon_id,
                required - len(photos),
                tuple(sorted(ALLOWED_LICENSES)),
                [photo.get("id") for photo in photos],
            ): (taxon_id, required, photos)
            for taxon_id, required, photos in photo_requests
        }
        for future in as_completed(futures):
            taxon_id, required, photos = futures[future]
            photos.extend(future.result())
            photos = _deduplicate_photos(photos)
            record = taxa[str(taxon_id)]
            record["photos"] = photos
            record["photo"] = photos[0] if photos else None
            if len(photos) < required:
                unresolved.append(taxon_id)
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()
    _json_write(PHOTO_CACHE, cache)
    if unresolved:
        raise ValueError(
            "Insufficient Creative Commons reference photos for taxon IDs: "
            + ", ".join(map(str, unresolved))
        )
    return {tid: taxa[str(tid)] for tid in target_ids}


def _valid_image(path):
    if not path.exists() or path.stat().st_size < 1024:
        return False
    header = path.read_bytes()[:12]
    return header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG\r\n\x1a\n")


def _photo_key(photo):
    return str(photo.get("id") or hashlib.sha256(photo["medium_url"].encode()).hexdigest()[:16])


def _download_image(photo):
    photo_id = _photo_key(photo)
    cached = IMAGE_CACHE_DIR / f"{photo_id}.jpg"
    if _valid_image(cached):
        return photo_id, cached
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        photo["medium_url"], timeout=45, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    partial = cached.with_suffix(".part")
    partial.write_bytes(response.content)
    if not _valid_image(partial):
        partial.unlink(missing_ok=True)
        raise ValueError(f"Downloaded reference image is invalid for photo {photo_id}")
    partial.replace(cached)
    return photo_id, cached


def _write_png(path, size, maskable=False):
    """Write a dependency-free, reproducible field-target app icon."""
    dark = (13, 34, 28, 255)
    mint = (142, 200, 177, 255)
    white = (248, 250, 249, 255)
    pixels = [list(dark) for _ in range(size * size)]

    def paint_circle(cx, cy, radius, color):
        r2 = radius * radius
        y0, y1 = max(0, cy - radius), min(size, cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(size, cx + radius + 1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                    pixels[y * size + x] = list(color)

    center = size // 2
    outer = int(size * (0.25 if maskable else 0.31))
    paint_circle(center, center, outer, mint)
    paint_circle(center, center, int(outer * 0.72), dark)
    paint_circle(center, center, int(outer * 0.42), white)
    paint_circle(center, center, int(outer * 0.16), dark)
    # A small offset wing/leaf makes the target mark feel tied to field life.
    paint_circle(int(size * 0.69), int(size * 0.31), int(size * 0.09), white)
    paint_circle(int(size * 0.72), int(size * 0.28), int(size * 0.055), dark)

    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(pixels[y * size + x])
    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    payload = signature
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    payload += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _merge_taxon_metadata(targets, taxa):
    for target in targets:
        resolved = taxa[target["id"]]
        for key in ("family_name", "family_common", "order_name", "order_common"):
            if not target.get(key):
                target[key] = resolved.get(key) or ""
        if not target.get("common_name") or target["common_name"] == target["scientific_name"]:
            target["common_name"] = resolved.get("preferred_common_name") or target["scientific_name"]
        # Butterfly and Odonata family metadata is not yet stored in taxon_meta;
        # rebuild their protocol after the cached taxon API record fills it.
        peers = target.pop("_peer_taxa", [])
        target.update(build_guidance(
            target["group"], target["family_name"], target["common_name"],
            target["season_label"], target["regional_count"], peers,
        ))


def _image_data(photo, relative_path, destination, alt):
    code = photo["license_code"].casefold()
    return {
        "image": relative_path,
        "image_alt": alt,
        "image_attribution": photo["attribution"],
        "image_license_code": code,
        "image_license": LICENSE_LABELS[code],
        "image_license_url": LICENSE_URLS[code],
        "image_source_url": photo["source_url"],
        "image_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }


def _validate_targets(targets, output_dir=None):
    required_text = (
        "common_name", "scientific_name", "season_label", "target_reason",
        "id_limitations", "image", "image_attribution", "image_license", "image_source_url",
    )
    required_lists = (
        "active_months", "habitat_tags", "method_tags", "finding_help",
        "id_help", "photo_checklist",
    )
    seen = set()
    errors = []
    for target in targets:
        if target["id"] in seen:
            errors.append(f"duplicate taxon {target['id']}")
        seen.add(target["id"])
        for key in required_text:
            if not target.get(key):
                errors.append(f"taxon {target['id']} has no {key}")
        for key in required_lists:
            if not target.get(key):
                errors.append(f"taxon {target['id']} has no {key}")
        if target.get("image_license_code") not in ALLOWED_LICENSES:
            errors.append(f"taxon {target['id']} has an unapproved image license")
        if output_dir and not (output_dir / target["image"]).is_file():
            errors.append(f"taxon {target['id']} is missing local image {target['image']}")
        images = target.get("images") or []
        if len(images) != TARGET_IMAGE_COUNT:
            errors.append(f"taxon {target['id']} does not have {TARGET_IMAGE_COUNT} reference images")
        for image in images:
            if image.get("image_license_code") not in ALLOWED_LICENSES:
                errors.append(f"taxon {target['id']} has an unapproved reference image license")
            if output_dir and not (output_dir / image.get("image", "")).is_file():
                errors.append(f"taxon {target['id']} is missing local reference image")
        for lookalike in target.get("lookalikes") or []:
            if not lookalike.get("taxon_id") or not lookalike.get("image"):
                errors.append(f"taxon {target['id']} has an unillustrated lookalike")
            elif output_dir and not (output_dir / lookalike["image"]).is_file():
                errors.append(f"taxon {target['id']} is missing local lookalike image")
    if errors:
        raise ValueError("Invalid field guide release:\n- " + "\n- ".join(errors))


def build(effective_date=None, output_dir=None):
    """Generate `/field/` without modifying the survey's root document."""
    effective_date = effective_date or date.today()
    output_dir = Path(output_dir or OUTPUT_DIR)
    if not APP_SOURCE.is_dir() or not SW_TEMPLATE.is_file():
        raise FileNotFoundError("Field guide app sources are incomplete")

    targets, counts, moth_months = collect_targets(effective_date)
    photo_requirements = {target["id"]: TARGET_IMAGE_COUNT for target in targets}
    for target in targets:
        for lookalike in target.get("lookalikes") or []:
            taxon_id = lookalike.get("taxon_id")
            if taxon_id:
                photo_requirements.setdefault(int(taxon_id), LOOKALIKE_IMAGE_COUNT)
    taxa = resolve_taxa(photo_requirements)
    _merge_taxon_metadata(targets, taxa)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(APP_SOURCE, output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    required_photos = {}
    for taxon_id, count in photo_requirements.items():
        for photo in taxa[taxon_id]["photos"][:count]:
            required_photos.setdefault(_photo_key(photo), photo)
    image_paths = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_download_image, photo) for photo in required_photos.values()]
        for future in as_completed(futures):
            photo_id, cached = future.result()
            image_paths[photo_id] = cached

    for target in targets:
        images = []
        for index, photo in enumerate(taxa[target["id"]]["photos"][:TARGET_IMAGE_COUNT], start=1):
            relative_path = f"images/target-{target['id']}-{index}.jpg"
            destination = output_dir / relative_path
            shutil.copy2(image_paths[_photo_key(photo)], destination)
            images.append(_image_data(
                photo,
                relative_path,
                destination,
                f"Reference photograph {index} of {target['common_name']} ({target['scientific_name']})",
            ))
        target["images"] = images
        # Preserve the original first-image fields for older installed releases.
        target.update(images[0])

        for lookalike in target.get("lookalikes") or []:
            taxon_id = int(lookalike["taxon_id"])
            photo = taxa[taxon_id]["photos"][0]
            relative_path = f"images/lookalike-{taxon_id}.jpg"
            destination = output_dir / relative_path
            if not destination.exists():
                shutil.copy2(image_paths[_photo_key(photo)], destination)
            lookalike.update(_image_data(
                photo,
                relative_path,
                destination,
                f"Reference photograph of {lookalike['name']} ({lookalike.get('scientific_name', '')})",
            ))

    _validate_targets(targets, output_dir)
    generated_at = _latest_data_sync()
    base_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "effective_date": effective_date.isoformat(),
        "guidance_revision": GUIDANCE_REVISION,
        "database_sha256": _database_sha256(),
        "radius_km": REGION_RADIUS_KM,
        "target_months": {"moths": moth_months},
        "counts": {"all": len(targets), **counts},
        "targets": targets,
    }
    version_seed = json.dumps(base_payload, sort_keys=True, separators=(",", ":")).encode()
    for source in sorted(APP_SOURCE.rglob("*")):
        if source.is_file():
            version_seed += source.relative_to(APP_SOURCE).as_posix().encode() + source.read_bytes()
    version_seed += SW_TEMPLATE.read_bytes()
    version = hashlib.sha256(version_seed).hexdigest()[:16]
    payload = {"version": version, **base_payload}
    _json_write(output_dir / "targets.json", payload)

    _write_png(output_dir / "icons" / "icon-192.png", 192)
    _write_png(output_dir / "icons" / "apple-touch-icon.png", 180)
    _write_png(output_dir / "icons" / "icon-512.png", 512)
    _write_png(output_dir / "icons" / "icon-maskable-512.png", 512, maskable=True)

    assets = [
        "./", "./index.html", "./styles.css", "./app.js",
        "./manifest.webmanifest", "./targets.json",
        "./icons/icon-192.png", "./icons/apple-touch-icon.png", "./icons/icon-512.png",
        "./icons/icon-maskable-512.png",
        *sorted({
            f"./{image['image']}"
            for target in targets
            for image in [*(target.get("images") or []), *(target.get("lookalikes") or [])]
            if image.get("image")
        }),
    ]
    missing_assets = [
        asset for asset in assets
        if asset not in {"./"} and not (output_dir / asset.removeprefix("./")).is_file()
    ]
    if missing_assets:
        raise ValueError("Offline asset manifest references missing files: "
                         + ", ".join(missing_assets))
    sw = SW_TEMPLATE.read_text(encoding="utf-8")
    sw = sw.replace("__VERSION__", json.dumps(version))
    sw = sw.replace("__ASSETS__", json.dumps(assets, indent=2))
    (output_dir / "service-worker.js").write_text(sw, encoding="utf-8")

    # Cloudflare Pages reads this only from the publish root. These rules touch
    # the field-guide path exclusively; the survey's caching behavior is left
    # unchanged.
    if output_dir.resolve().parent == PUBLIC_DIR.resolve():
        (PUBLIC_DIR / "_headers").write_text(
            "/field/service-worker.js\n"
            "  Cache-Control: no-cache, no-store, must-revalidate\n"
            "  Service-Worker-Allowed: /field/\n"
            "/field/index.html\n"
            "  Cache-Control: no-cache\n"
            "/field/manifest.webmanifest\n"
            "  Cache-Control: no-cache\n"
            "/field/images/*\n"
            "  Cache-Control: public, max-age=31536000, immutable\n",
            encoding="utf-8",
        )

    package_bytes = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    if package_bytes > MAX_PACKAGE_BYTES:
        raise ValueError(
            f"Offline field guide is {package_bytes / 1024 / 1024:.1f} MB; limit is 75 MB"
        )
    print(
        f"Wrote {output_dir} ({len(targets)} targets, "
        f"{package_bytes / 1024 / 1024:.1f} MB, version {version})"
    )
    return output_dir


if __name__ == "__main__":
    build()
