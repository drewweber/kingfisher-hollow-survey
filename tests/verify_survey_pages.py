#!/usr/bin/env python3
"""Verify the generated survey routes remain independently lightweight.

This runs after ``report.py`` in the publishing workflow.  It checks the
document boundaries that prevent a mobile reader from retaining every taxon,
the Life List, the field journal, and all chart payloads at once, then prints
stable payload/DOM proxies for each page.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import report


class _TagCounter(HTMLParser):
    """Count HTML start tags without treating JavaScript strings as markup."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1

    def handle_startendtag(self, tag, attrs):
        self.count += 1


# These generous ceilings are regression guards, not content limits.  Their
# purpose is to catch a return to the monolithic document, while normal survey
# growth stays well below them.
_BUDGETS = {
    "all": (180_000, 1_600),
    "life-list": (2_500_000, 25_000),
    "moths": (250_000, 3_000),
    "log": (900_000, 12_000),
}
_PAYLOAD_RE = re.compile(r'data-plotly-src="([^"]+)"')
_CHART_ELEMENT_RE = re.compile(r'<div\b[^>]*\bdata-plotly-chart\b')
_VIEW_RE = re.compile(r'id="(view-[^"]+)"')


def _tag_count(html: str) -> int:
    parser = _TagCounter()
    parser.feed(html)
    parser.close()
    return parser.count


def _fail(errors: list[str], route: str, message: str) -> None:
    errors.append(f"{route}: {message}")


def main() -> int:
    errors: list[str] = []
    expected_assets: set[Path] = set()
    rows: list[tuple[str, int, int, int, int, int]] = []
    anchors_by_mode: dict[str, list[str]] = {}

    for mode, config in report.VIEW_CONFIG.items():
        route = config["route"]
        output = report._view_output_path(mode)
        if not output.is_file():
            _fail(errors, route, f"missing generated document: {output}")
            continue

        raw = output.read_bytes()
        html = raw.decode("utf-8")
        gzip_bytes = len(gzip.compress(raw, mtime=0))
        tags = _tag_count(html)
        expected_view = f"view-{mode}"
        views = _VIEW_RE.findall(html)
        if views != [expected_view]:
            _fail(errors, route, f"expected only {expected_view!r}, found {views!r}")

        wrapper = re.search(rf'<div id="{re.escape(expected_view)}"(?P<attrs>[^>]*)>', html)
        if not wrapper:
            _fail(errors, route, f"missing opening wrapper for {expected_view}")
        elif "hidden" in wrapper.group("attrs") or 'aria-hidden="true"' in wrapper.group("attrs"):
            _fail(errors, route, "active view wrapper is hidden")
        view_start = html.find(f'<div id="{expected_view}"')
        view_end = html.find("</main>", view_start)
        anchors_by_mode[mode] = re.findall(r'\bid="([^"]+)"', html[view_start:view_end])

        expected_title = (
            "Kingfisher Hollow · Biodiversity Survey"
            if mode == "all"
            else f"Kingfisher Hollow · {config['label']} | Biodiversity Survey"
        )
        if f"<title>{expected_title}</title>" not in html:
            _fail(errors, route, "page-specific title is missing")
        if f'<link rel="canonical" href="{report._view_url(mode)}">' not in html:
            _fail(errors, route, "page-specific canonical URL is missing")
        if f'data-mode="{mode}"' not in html:
            _fail(errors, route, "body mode does not match its route")

        payloads = _PAYLOAD_RE.findall(html)
        chart_elements = _CHART_ELEMENT_RE.findall(html)
        chart_bytes = 0
        if config["plotly"]:
            if not payloads:
                _fail(errors, route, "chart page has no deferred chart payloads")
            if len(chart_elements) != len(payloads):
                _fail(errors, route, "chart placeholders and payloads do not match")
            if "window.__plotlyRender(" in html:
                _fail(errors, route, "chart payload remained inline in the document")
        elif payloads or chart_elements:
            _fail(errors, route, "non-chart page includes a chart payload")

        for source in payloads:
            if not source.startswith("/assets/charts/"):
                _fail(errors, route, f"unexpected chart payload source: {source}")
                continue
            asset = report.PUBLIC_DIR / source.lstrip("/")
            if not asset.is_file():
                _fail(errors, route, f"missing chart payload: {source}")
                continue
            expected_assets.add(asset.resolve())
            chart_bytes += asset.stat().st_size

        if mode in _BUDGETS:
            byte_limit, tag_limit = _BUDGETS[mode]
            if len(raw) > byte_limit:
                _fail(errors, route, f"HTML is {len(raw):,} B; budget is {byte_limit:,} B")
            if tags > tag_limit:
                _fail(errors, route, f"HTML has {tags:,} tags; budget is {tag_limit:,}")

        rows.append((route, len(raw), gzip_bytes, tags, len(payloads), chart_bytes))

    root = report._view_output_path("all")
    if root.is_file():
        root_html = root.read_text(encoding="utf-8")
        legacy_match = re.search(r"const routes=(\{.*?\});", root_html)
        if not legacy_match:
            errors.append("root page has no legacy hash route map")
        else:
            legacy_routes = json.loads(legacy_match.group(1))
            for mode, config in report.VIEW_CONFIG.items():
                if mode == "all":
                    continue
                for anchor in anchors_by_mode.get(mode, []):
                    if legacy_routes.get(anchor) != config["route"]:
                        _fail(errors, "/", f"legacy #{anchor} does not route to {config['route']}")

    chart_dir = report.PUBLIC_DIR / "assets" / "charts"
    written_assets = {path.resolve() for path in chart_dir.glob("*.js")} if chart_dir.is_dir() else set()
    if written_assets != expected_assets:
        extra = sorted(str(path.relative_to(report.PUBLIC_DIR)) for path in written_assets - expected_assets)
        missing = sorted(str(path.relative_to(report.PUBLIC_DIR)) for path in expected_assets - written_assets)
        if extra:
            errors.append("chart assets not referenced by a current page: " + ", ".join(extra))
        if missing:
            errors.append("chart assets missing from the build output: " + ", ".join(missing))

    print("route          HTML bytes   gzip bytes   HTML tags   lazy charts   lazy bytes")
    for route, raw_bytes, gzip_bytes, tags, payloads, chart_bytes in rows:
        print(f"{route:<15} {raw_bytes:>10,} {gzip_bytes:>12,} {tags:>11,} {payloads:>12} {chart_bytes:>12,}")

    if errors:
        print("\nGenerated survey-page verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
