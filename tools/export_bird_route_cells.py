#!/usr/bin/env python3
"""Create a new public 5 m cell-count snapshot from private route analysis.

This is an explicit publication boundary: only aggregate counts, calendar-date
coverage and cell polygons are constructed in the output. Checklist identifiers,
individual routes, source filenames, timestamps and projection records are never
copied. The output must not already exist so refreshes can be reviewed separately.
Uses only Python's standard library; the original private inputs remain read-only.
"""

import argparse
from datetime import date, datetime
import json
import math
from pathlib import Path


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def anchor(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("grid anchor must contain two metre coordinates")
    return [finite(item, "grid anchor") for item in value]


def inventory_dates(inventory):
    records = inventory["checklists"]
    if not isinstance(records, list) or not records:
        raise ValueError("inventory must contain checklists")
    identifiers = [record["checklist_id"] for record in records]
    if any(not isinstance(item, str) or not item for item in identifiers) or len(set(identifiers)) != len(records):
        raise ValueError("inventory must have unique nonempty checklist identifiers")
    if any(inventory.get(field, len(records)) != len(records) for field in ("expected_count", "displayed_count")):
        raise ValueError("inventory totals do not match its records")
    dates = []
    for record in records:
        # eBird's displayed date labels are English, regardless of the host locale.
        parts = record["date_label"].split()
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        if len(parts) < 3 or parts[1] not in months:
            raise ValueError("inventory contains an invalid date label")
        dates.append(date(int(parts[2]), months.index(parts[1]) + 1, int(parts[0])))
    return len(records), min(dates).isoformat(), max(dates).isoformat()


def export_cells(grid, methods, inventory, snapshot_date=None):
    """Validate private inputs and construct an entirely new allowlisted object."""
    inventory_count, date_start, date_end = inventory_dates(inventory)
    captured_date = datetime.fromisoformat(inventory["captured_at"].replace("Z", "+00:00")).date()
    snapshot = date.fromisoformat(snapshot_date) if snapshot_date else captured_date
    if snapshot.isoformat() < date_end:
        raise ValueError("snapshot date precedes the latest inventory checklist")
    coverage = methods["coverage"]
    source = coverage["source_coverage"]
    statuses = source["status_counts"]
    route_count = integer(coverage["distinct_acquired_route_checklists"], "route count", 1)
    unresolved = integer(coverage["inventory_checklists_without_acquired_route"], "unresolved count")
    flagged = integer(statuses["flagged_unresolved"], "flagged unresolved count")
    missing = integer(statuses["missing_unresolved"], "missing unresolved count")
    expected_counts = (
        (coverage["inventory_count"], inventory_count),
        (source["inventory_count"], inventory_count),
        (source["exported_route_count"], route_count),
        (statuses["exported"], route_count),
        (source["unresolved_count"], unresolved),
    )
    if any(integer(actual, "coverage count") != expected for actual, expected in expected_counts):
        raise ValueError("coverage totals disagree with the inventory or route count")
    if route_count + unresolved != inventory_count or flagged + missing != unresolved:
        raise ValueError("coverage categories do not add up")
    suppressed = integer(methods["suppressed_gap_count"], "suppressed edge count")
    if finite(methods["max_gap_m"], "maximum connected gap") != 100:
        raise ValueError("the reviewed map method requires a 100 metre gap threshold")

    cell_size = finite(grid["cell_size_m"], "cell size")
    if cell_size != 5:
        raise ValueError("only the approved 5 metre aggregate grid is supported")
    projection = methods["projection"]
    if (projection.get("projection_engine") != "equirectangular"
            or projection.get("method") != "Local spherical equirectangular"
            or projection.get("units") != "metres"):
        raise ValueError("unsupported projection; expected local spherical equirectangular in metres")
    radius = finite(projection["earth_radius_m"], "earth radius")
    longitude = finite(projection["origin_longitude"], "origin longitude")
    latitude = finite(projection["origin_latitude"], "origin latitude")
    if radius <= 0 or not -180 <= longitude <= 180 or not -90 < latitude < 90:
        raise ValueError("invalid projection radius or origin")
    grid_anchor = anchor(grid["grid_anchor_xy_m"])
    if grid_anchor != anchor(projection["grid_anchor_xy_m"]):
        raise ValueError("grid anchor disagrees with the recorded projection")
    cos_latitude = math.cos(math.radians(latitude))

    def point(x, y):
        lon = longitude + math.degrees(x / (radius * cos_latitude))
        lat = latitude + math.degrees(y / radius)
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("cell falls outside valid geographic coordinates")
        return [round(lon, 7), round(lat, 7)]

    cells = grid["cells"]
    if not isinstance(cells, list) or not cells:
        raise ValueError("grid must contain occupied cells")
    features = []
    seen = set()
    for cell in cells:
        column, row = cell["column"], cell["row"]
        if type(column) is not int or type(row) is not int:
            raise ValueError("cell column and row must be integers")
        if (column, row) in seen:
            raise ValueError("duplicate cell coordinates")
        seen.add((column, row))
        x = finite(cell["xmin_m"], "cell xmin")
        y = finite(cell["ymin_m"], "cell ymin")
        if not (math.isclose(x, grid_anchor[0] + column * cell_size, rel_tol=0, abs_tol=1e-8)
                and math.isclose(y, grid_anchor[1] + row * cell_size, rel_tol=0, abs_tol=1e-8)):
            raise ValueError("cell geometry is not aligned to its recorded 5 metre grid")
        count = integer(cell["count"], "cell route count", 1)
        if count > route_count:
            raise ValueError("cell route count exceeds acquired route count")
        ring = [point(x, y), point(x + cell_size, y),
                point(x + cell_size, y + cell_size), point(x, y + cell_size), point(x, y)]
        if len({tuple(corner) for corner in ring}) != 4:
            raise ValueError("cell geometry collapses at the published precision")
        features.append({
            "type": "Feature", "id": f"cell-{len(features) + 1}",
            "properties": {"route_count": count},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    maximum = max(feature["properties"]["route_count"] for feature in features)
    summary = methods["summary"]["5"]
    if (integer(summary["touched_cells"], "summary cell count", 1) != len(features)
            or integer(summary["maximum_checklists_per_cell"], "summary maximum", 1) != maximum):
        raise ValueError("grid counts disagree with the analysis summary")
    return {
        "metadata": {
            "inventory_count": inventory_count, "route_count": route_count,
            "unresolved_count": unresolved, "flagged_unresolved_count": flagged,
            "missing_unresolved_count": missing, "cell_size_m": 5,
            "snapshot_date": snapshot.isoformat(), "date_start": date_start, "date_end": date_end,
            "suppressed_edge_count": suppressed, "max_count": maximum, "cell_count": len(features),
        },
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("grid", "methods", "inventory", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--snapshot-date", help="Optional ISO calendar date; defaults to inventory capture date")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("output already exists; choose a new snapshot path for review")
        inputs = [json.loads(path.read_text(encoding="utf-8")) for path in (args.grid, args.methods, args.inventory)]
        document = export_cells(*inputs, snapshot_date=args.snapshot_date)
        encoded = json.dumps(document, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also closes the race between the existence check and write.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(encoded)
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as error:
        parser.exit(1, f"Aggregate export failed: {error}\n")
    print(f"Created aggregate snapshot: {document['metadata']['cell_count']} cells, {document['metadata']['route_count']} routes")


if __name__ == "__main__":
    main()
