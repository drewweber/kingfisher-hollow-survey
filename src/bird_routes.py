"""Load only the owner-approved public aggregate, never the private archive."""
import json
import math
from datetime import date
from pathlib import Path

PUBLIC_CELLS = Path(__file__).resolve().parents[1] / 'data' / 'bird-route-use-5m.json'
META_KEYS = {
    'inventory_count', 'route_count', 'unresolved_count', 'flagged_unresolved_count',
    'missing_unresolved_count', 'cell_size_m', 'snapshot_date', 'date_start',
    'date_end', 'suppressed_edge_count', 'max_count', 'cell_count',
}


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError('Public route data contains missing or unapproved fields')


def validate(data):
    """Fail closed on extra fields so membership or source paths cannot publish."""
    _keys(data, {'metadata', 'geojson'})
    meta = data['metadata']
    _keys(meta, META_KEYS)
    for key in META_KEYS - {'snapshot_date', 'date_start', 'date_end'}:
        if type(meta[key]) is not int or meta[key] < 0:
            raise ValueError('Route summary counts must be nonnegative integers')
    if (meta['cell_size_m'] != 5 or not meta['route_count']
            or meta['route_count'] + meta['unresolved_count'] != meta['inventory_count']
            or meta['flagged_unresolved_count'] + meta['missing_unresolved_count'] != meta['unresolved_count']):
        raise ValueError('Invalid route coverage or cell size')
    dates = [date.fromisoformat(meta[key]) for key in ('date_start', 'date_end', 'snapshot_date')]
    if dates != sorted(dates):
        raise ValueError('Route date range must precede snapshot date')
    geo = data['geojson']
    _keys(geo, {'type', 'features'})
    if geo['type'] != 'FeatureCollection' or not isinstance(geo['features'], list):
        raise ValueError('Expected aggregate FeatureCollection')
    if len(geo['features']) != meta['cell_count'] or not geo['features']:
        raise ValueError('Cell count does not match aggregate summary')
    ids = set()
    counts = []
    for feature in geo['features']:
        _keys(feature, {'type', 'id', 'properties', 'geometry'})
        cell_id = feature['id']
        if (feature['type'] != 'Feature' or not isinstance(cell_id, str)
                or not cell_id.startswith('cell-') or not cell_id[5:].isdigit()
                or cell_id in ids):
            raise ValueError('Expected unique public cell identifier')
        ids.add(cell_id)
        _keys(feature['properties'], {'route_count'})
        count = feature['properties']['route_count']
        if type(count) is not int or not 1 <= count <= meta['route_count']:
            raise ValueError('Invalid distinct route count')
        counts.append(count)
        geom = feature['geometry']
        _keys(geom, {'type', 'coordinates'})
        coords = geom['coordinates']
        if (geom['type'] != 'Polygon' or not isinstance(coords, list)
                or len(coords) != 1 or len(coords[0]) != 5 or coords[0][0] != coords[0][-1]):
            raise ValueError('Expected one closed cell polygon')
        for point in coords[0]:
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(v) not in (float, int) or not math.isfinite(v) for v in point)
                    or not -180 <= point[0] <= 180 or not -85 <= point[1] <= 85):
                raise ValueError('Invalid cell coordinates')
    if max(counts) != meta['max_count']:
        raise ValueError('Maximum route count does not match cells')
    return data


def load(path=PUBLIC_CELLS):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def legend_ticks(maximum):
    """Readable raw-count labels placed at their logarithmic color positions."""
    if maximum <= 1:
        return [(1, 0)]
    candidates = {base * 10 ** exponent
                  for exponent in range(math.ceil(math.log10(maximum)) + 1)
                  for base in (1, 2, 5)
                  if 1 < base * 10 ** exponent < maximum}
    values = {1, maximum}
    for fraction in (0.25, 0.5, 0.75):
        if candidates:
            value = min(candidates, key=lambda n: (abs(math.log(n) / math.log(maximum) - fraction), n))
            values.add(value)
    return [(value, math.log(value) / math.log(maximum)) for value in sorted(values)]


def map_html(data):
    """Accessible map shell; SVG and raster tiles work without WebGL or plugins."""
    validate(data)
    payload = json.dumps(data, separators=(',', ':'), ensure_ascii=True).replace('<', '\\u003c')
    maximum = data['metadata']['max_count']
    labels = []
    for value, position in legend_ticks(maximum):
        alignment = '0' if position == 0 else '-100%' if position == 1 else '-50%'
        labels.append(f'<span style="position:absolute;left:{position * 100:.4f}%;transform:translateX({alignment})">{value:,}</span>')
    legend_labels = ''.join(labels)
    gradient = 'linear-gradient(to right,#00224e,#7d7c78,#fee838)' if maximum > 1 else '#00224e'
    button = ('min-h-11 rounded-lg border border-white/30 px-4 text-sm '
              'text-white hover:bg-white/10 focus-visible:outline focus-visible:outline-2 '
              'focus-visible:outline-offset-2 focus-visible:outline-hollow-300')
    return f'''<div data-bird-route-map>
      <div class="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Route map controls">
        <button type="button" class="{button}" data-map-action="in" aria-label="Zoom in">+ Zoom in</button>
        <button type="button" class="{button}" data-map-action="out" aria-label="Zoom out">− Zoom out</button>
        <button type="button" class="{button}" data-map-action="reset">Reset view</button>
        <details class="text-sm text-white">
          <summary class="flex min-h-11 cursor-pointer items-center px-3">Pan map</summary>
          <div class="flex gap-1 pb-2">
            <button type="button" class="{button}" data-map-action="west" aria-label="Pan west">←</button>
            <button type="button" class="{button}" data-map-action="north" aria-label="Pan north">↑</button>
            <button type="button" class="{button}" data-map-action="south" aria-label="Pan south">↓</button>
            <button type="button" class="{button}" data-map-action="east" aria-label="Pan east">→</button>
          </div>
        </details>
        <label class="flex min-h-11 cursor-pointer items-center gap-2 px-3 text-sm text-white">
          <input type="checkbox" data-map-overlay checked class="h-4 w-4"> Show cells
        </label>
      </div>
      <svg data-route-map-svg role="img" aria-label="Map of recorded checklist route coverage in 5 metre cells"
           aria-describedby="bird-route-help" tabindex="0"
           style="display:block;width:100%;height:420px;background:#15191b;touch-action:none;border-radius:8px;cursor:grab">
        <g data-map-tiles></g><g data-map-cells></g>
      </svg>
      <div class="mt-3 text-sm text-white/70">
        <p class="mb-2">Checklist routes per 5 m cell · log scale</p>
        <div aria-hidden="true" style="height:12px;background:{gradient};border-radius:3px"></div>
        <div class="mt-1 tabular-nums" style="position:relative;height:1.5em">{legend_labels}</div>
        <p class="mt-2 text-xs leading-5 text-white/60">Logarithmic colors bring out differences among lightly used cells. Labels show actual checklist counts.</p>
      </div>
      <p id="bird-route-help" class="mt-3 text-xs leading-5 text-white/60">Drag to pan. With the map focused, use arrow keys to pan, + or − to zoom, and Home to reset. Hover or tap a cell for its count.</p>
      <p data-map-status aria-live="polite" class="mt-1 min-h-5 text-sm text-white/80">Loading route map…</p>
      <p class="mt-3 text-right text-xs text-white/60">Map: © <a href="https://www.openstreetmap.org/copyright" class="underline">OpenStreetMap contributors</a> · <a href="https://www.openstreetmap.org/fixthemap" class="underline">Report a map issue</a></p>
      <script type="application/json" data-route-cells>{payload}</script>
      <noscript><p class="mt-3 text-sm text-white/80">Enable JavaScript to explore the map. The coverage summary and method below remain available.</p></noscript>
    </div>'''
