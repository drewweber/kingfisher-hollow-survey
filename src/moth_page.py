"""The moth visitor story: native values first, optional exploration second."""
from calendar import month_name
from datetime import date, timedelta
from html import escape
import json
import hashlib
import math
import csv
import io
import re
from pathlib import Path


def explorer_url():
    source = Path(__file__).resolve().parents[1] / 'assets/moth-explorer.js'
    return '/assets/moth-explorer.js?v=' + hashlib.sha256(source.read_bytes()).hexdigest()[:12]


def timing_payload(story):
    data = json.dumps(story['timing'], ensure_ascii=False, allow_nan=False)
    return '/assets/moth-timing-' + hashlib.sha256(data.encode()).hexdigest()[:16] + '.json', data


def esc(value):
    return escape('' if value is None or str(value) in ('nan', 'NaT') else str(value), quote=True)


def detail(title, body, id_=''):
    identity = f' id="{id_}"' if id_ else ''
    return f'<details class="moth-detail"{identity}><summary>{esc(title)}</summary><div>{body}</div></details>'


def bar(label, value, maximum, note=''):
    width = round(100 * value / max(maximum, 1), 2)
    return (f'<div class="moth-bar-row"><div class="moth-bar-label"><span>{esc(label)}</span>'
            f'<strong>{value:,}</strong></div><div class="moth-bar-track" aria-hidden="true">'
            f'<span style="width:{width}%"></span></div>'
            + (f'<p class="moth-small">{esc(note)}</p>' if note else '') + '</div>')


SEASONS = [
    ('winter', 'Winter’s quiet clues', 'January–February', 'Sheltered bark, persistent leaf mines and cases offer ways into moth life even when cold nights keep the lights quiet.', [1, 2]),
    ('spring', 'The year opens up', 'March–May', 'The first mild evenings bring an early-season cast. Fresh foliage offers another way to look as caterpillars emerge.', [3, 4, 5]),
    ('summer', 'A changing summer cast', 'June–August', 'The greatest variety arrives in summer, but each month brings a different combination of moths.', [6, 7, 8]),
    ('autumn', 'Beyond the summer peak', 'September–November', 'Cooler evenings bring another cast. A mild autumn night is a reason to return to a familiar light.', [9, 10, 11]),
    ('winter', 'The year comes full circle', 'December', 'The next moth year is already waiting in overwintering stages. Look closely at sheltered foliage and return when the weather softens.', [12]),
]


def annual(story):
    maximum = max((r['taxa'] for r in story['monthly']), default=1)
    blocks = []
    for key, title, months, copy, numbers in SEASONS:
        ext = 'webp' if key in ('spring', 'summer') else 'jpg'
        rows = []
        for row in story['monthly']:
            if row['month'] in numbers:
                years = ', '.join(map(str, row['years'])) or 'no contributing year'
                note = f"{row['reporting_dates']} reporting dates · {years}"
                rows.append(bar(row['name'], row['taxa'], maximum, note))
        blocks.append(f'<article class="moth-quarter moth-months-{len(numbers)}"><img src="/assets/seasons/{key}.{ext}" width="1280" height="720" loading="lazy" alt="{key.title()} landscape at Kingfisher Hollow">'
                      f'<div><p class="moth-kicker">{months}</p><h3>{title}</h3><p>{copy}</p>{"".join(rows)}</div></article>')
    peak = max(story['monthly'], key=lambda r: r['taxa'], default=None)
    takeaway = (f"{peak['name']} brings the broadest variety in the list, but the season keeps changing well beyond the peak." if peak and peak['taxa'] else 'The year will take shape as dated moth records arrive.')
    return (f'<p class="moth-takeaway">{takeaway}</p><p class="moth-small">Unique moth taxa per month · All recorded years · All life stages</p>'
            '<div class="moth-year">' + ''.join(blocks) + '</div>'
            '<p class="moth-small">0 means no dated moth records in that month, not a documented visit with no moths.</p>')


def comparison(story):
    pair = next((r for r in story['comparisons'] if r['first_month'] == 7), None)
    if not pair:
        return ''
    shared = pair['shared']
    maximum = max(shared + pair['first_only'], shared + pair['second_only'], 1)
    rows = []
    for name, only in [('July', pair['first_only']), ('August', pair['second_only'])]:
        rows.append(f'<div class="moth-compare-row"><div class="moth-bar-label"><h4>{name}</h4><strong>{shared + only:,} taxa</strong></div>'
                    f'<div class="moth-stack" aria-hidden="true"><span style="width:{100 * shared / maximum}%"></span><span style="width:{100 * only / maximum}%"></span></div>'
                    f'<p><span class="moth-key shared"></span>{shared:,} in both <span class="moth-key only"></span>{only:,} only in {name}</p></div>')
    return ('<div class="moth-panel"><h3>Summer changes its cast</h3>'
            f'<p>August adds <strong>{pair["second_only"]:,} moths</strong> absent from July’s list, alongside {shared:,} recorded in both months.</p>'
            + ''.join(rows) + '<p class="moth-small">July and August · All recorded years combined. “Only” refers to these two monthly lists.</p></div>')


def family_chart(families):
    rows = families.to_dict('records') if hasattr(families, 'to_dict') else families
    local = [r for r in rows if r['recorded'] > 0]
    maximum = max((r['recorded'] for r in local), default=1)
    charts = [bar(r['label'], int(r['recorded']), maximum) for r in local]
    regional = []
    for r in rows:
        if r.get('reference_scope'):
            scope = 'within about 50 miles' if r['reference_scope'] == 'region' else 'in Tioga County'
            regional.append(f'<li><strong>{esc(r["label"])}</strong>: {r["recorded"]} here; {r["overlap"]} shared with {r["region_total"]} recorded {scope}; {r["gap"]} in that reference without property records.</li>')
    counts = {r['family_name']: r['recorded'] for r in local}
    comparison_text = ''
    if 'Tortricidae' in counts and 'Geometridae' in counts:
        comparison_text = f'<p class="moth-takeaway">Leafrollers contribute {counts["Tortricidae"]} moths to the list, while geometers add another {counts["Geometridae"]}. Those family names open onto a surprising variety of forms and habits.</p>'
    return (comparison_text + '<p class="moth-small">Moth taxa recorded here · Sorted by local count, then family name</p>'
            + ''.join(charts[:6]) + (detail(f'Show all {len(local)} local families', ''.join(charts[6:])) if len(local) > 6 else '')
            + detail('Compare with the surrounding region', '<ul class="moth-native-list">' + ''.join(regional) + '</ul>' if regional else '<p>Regional family records are not available yet.</p>'))


def inventory_estimate(comp):
    observed, estimated = comp.get('observed', 0), comp.get('estimated', 0)
    lead = (f'<p class="moth-estimate"><strong>{comp.get("pct_complete", 0)}%</strong> estimated completeness</p>'
            f'<p>With {observed:,} moths recorded and an estimated total around {estimated:,}, there is plenty left to look forward to.</p>') if observed else '<p>The inventory estimate begins with the first dated record.</p>'
    methods = (f'<p>The Chao2 estimate uses {comp.get("nights", 0)} inferred reporting nights, including {comp.get("q1", 0)} taxa on one night and {comp.get("q2", 0)} on two nights. '
               f'Estimated total: {estimated:,}; model 95% interval: {comp.get("low", estimated):,}–{comp.get("high", estimated):,}. '
               'Records before noon are assigned to the preceding night for this calculation. Changing seasons, methods and identification can change the estimate.</p>')
    return lead + detail('How the estimate works', methods)


FREQUENCY_SERIES = [
    ('once', 'Recorded on one night', '#d8b783', '3 5'),
    ('twice', 'Recorded on two nights', '#a8c8ee', '10 5'),
    ('three_plus', 'Recorded on 3+ nights', '#8ec8b1', ''),
]


def frequency_history_csv(story):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['night', 'one_night', 'two_nights', 'three_plus_nights', 'total_taxa'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(dict(zip(writer.fieldnames, [row[key] for key in ('date', 'once', 'twice', 'three_plus', 'total')]))
                    for row in story['frequency_history'])
    text = output.getvalue()
    return '/assets/moth-frequency-' + hashlib.sha256(text.encode()).hexdigest()[:16] + '.csv', text


def _frequency_svg(rows, narrow=False):
    # Separate geometries preserve readable type rather than shrinking a desktop chart.
    width, height = (320, 300) if narrow else (800, 330)
    left, right, top, bottom = 40, width - 16, 30, height - 65
    first, last = date.fromisoformat(rows[0]['date']), date.fromisoformat(rows[-1]['date'])
    days = (last - first).days
    maximum = max(row[key] for row in rows for key, *_ in FREQUENCY_SERIES)
    rough_step = max(maximum / 3, 1)
    magnitude = 10 ** math.floor(math.log10(rough_step))
    step = math.ceil(rough_step / magnitude) * magnitude
    ceiling = max(step * math.ceil(maximum / step), step)
    def x(day):
        return (left + right) / 2 if not days else left + (right - left) * (day - first).days / days
    def y(value):
        return bottom - (bottom - top) * value / ceiling
    parts = [f'<svg class="moth-frequency-svg {"is-narrow" if narrow else "is-wide"}" viewBox="0 0 {width} {height}" aria-hidden="true" focusable="false">']
    for tick in range(0, ceiling + 1, step):
        parts.append(f'<line x1="{left}" x2="{right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}" stroke="#40584c"/>'
                     f'<text x="{left - 8}" y="{y(tick) + 5:.1f}" text-anchor="end">{tick}</text>')
    parts.append(f'<text x="{left}" y="17">Moth taxa</text>')
    tick_count = min(days + 1, 3 if narrow else 5)
    ticks = [first] if not days else [first + timedelta(days=round(days * i / (tick_count - 1))) for i in range(tick_count)]
    for index, day in enumerate(ticks):
        anchor = 'middle' if len(ticks) == 1 else ('start' if index == 0 else 'end' if index == len(ticks) - 1 else 'middle')
        parts.append(f'<line x1="{x(day):.1f}" x2="{x(day):.1f}" y1="{bottom}" y2="{bottom + 5}" stroke="#bfcec7"/>'
                     f'<text x="{x(day):.1f}" y="{bottom + 24}" text-anchor="{anchor}">{day:%b} {day.day}'
                     f'<tspan x="{x(day):.1f}" dy="19">{day.year}</tspan></text>')
    for key, label, color, dash in FREQUENCY_SERIES:
        points = [(x(date.fromisoformat(row['date'])), y(row[key])) for row in rows]
        path = f'M {points[0][0]:.2f} {points[0][1]:.2f}' + ''.join(f' H {px:.2f} V {py:.2f}' for px, py in points[1:])
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" stroke-dasharray="{dash}" vector-effect="non-scaling-stroke"/>'
                     f'<circle cx="{points[-1][0]:.2f}" cy="{points[-1][1]:.2f}" r="3.5" fill="{color}"/>')
    return ''.join(parts) + '</svg>'


def frequency_history_chart(story):
    rows = story['frequency_history']
    if not rows:
        return '<p>The pattern of repeat encounters will take shape with the first dated moth records.</p>'
    latest = rows[-1]
    labels = []
    for key, label, color, dash in FREQUENCY_SERIES:
        labels.append(f'<div><dt><svg viewBox="0 0 36 12" aria-hidden="true"><line x1="0" x2="36" y1="6" y2="6" stroke="{color}" stroke-width="3" stroke-dasharray="{dash}"/></svg>{label}</dt><dd>{latest[key]:,}</dd></div>')
    description = (f'From {rows[0]["date"]} to {latest["date"]}, these lines track moth taxa recorded on exactly one, exactly two, or three or more distinct nights. '
                   'The one-night and two-night groups are Q1 and Q2—the counts used in the completeness estimate above.')
    return ('<h3>Which finds return on another night?</h3>'
            f'<figure aria-label="Moth detection history by distinct night"><figcaption>{description}</figcaption>'
            + _frequency_svg(rows, narrow=True) + _frequency_svg(rows)
            + f'<p class="moth-small">Latest counts · {latest["date"]}</p><dl class="moth-frequency-labels">' + ''.join(labels) + '</dl></figure>'
            '<p class="moth-small">Inferred night date → · Repeat photos on the same night count once. A later night moves a moth to the next group, so the one- and two-night lines can fall. Records before noon belong to the preceding night; records without a time use their recorded date.</p>'
            f'<p><a class="moth-native-link" href="{frequency_history_csv(story)[0]}" download>Download exact night history (CSV)</a></p>')


def photo_card(row, caption, notable=False):
    name = next((value for value in (row.get('label'), row.get('common_name'), row.get('taxon_name')) if esc(value)), 'Moth')
    oid = row.get('photo_observation_id') if notable else row.get('id')
    oid = esc(oid)
    href = f'https://www.inaturalist.org/observations/{int(float(oid))}' if oid else f'https://www.inaturalist.org/taxa/{int(row["taxon_id"])}'
    photo = esc(row.get('photo_url'))
    image = f'<img src="{photo}" width="600" height="450" loading="lazy" decoding="async" alt="{esc(row.get("image_alt") or name)}">' if photo else ''
    source = 'Representative image' if row.get('photo_source') == 'representative' else 'Property observation'
    return (f'<figure class="moth-photo"><a href="{href}" target="_blank" rel="noopener">{image}<h3>{esc(name)} ↗</h3></a>'
            f'<p class="moth-small"><i>{esc(row.get("taxon_name"))}</i></p><figcaption><p>{caption}</p>'
            f'<p class="moth-small">{source} · {esc(str(row.get("observed_on") or "")[:10])}<br>{esc(row.get("photo_attribution"))}'
            + (' · <a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC</a>' if str(row.get('photo_license')).lower() == 'cc-by-nc' else f' {esc(row.get("photo_license"))}')
            + '</p></figcaption></figure>')


# Each selected photograph illustrates a life-history contrast, rather than a gallery quota.
DIVERSITY_PHOTOS = {
    365928311: ('Pink, yellow, and fueled entirely by its caterpillar days: an adult Rosy Maple Moth does not eat. Its caterpillars feed on leaves of maples and oaks.', 'Pink-and-yellow Rosy Maple Moth resting on pale fabric.'),
    389941743: ('Plume moth wings are divided into feathery lobes. Rolled tightly at rest, they make the distinctive T shape of this Morning-glory Plume Moth.', 'Morning-glory Plume Moth resting in a T shape on textured tree bark.'),
}
NOTABLE_PHOTOS = {
    371184143: ('Those long green tails do more than complete the silhouette: experiments show that they divert attacking bats toward expendable wing tips. June records at Kingfisher Hollow bring this remarkable defense into our own moth story.', 'Green Luna Moth with both long hindwing tails visible, resting on a white sheet.'),
    378280618: ('A bird dropping is an excellent thing for a moth to resemble. The Beautiful Wood-nymph folds its white-and-brown wings into just that disguise, with fluffy front legs completing the effect.', 'White-and-brown Beautiful Wood-nymph resting with its wings folded on a green fern.'),
    413254190: ('The moth year carries on after summer: Bicolored Sallows fly in autumn and spend winter as eggs. This golden visitor was photographed here on November 6.', 'Golden Bicolored Sallow resting on a dark outdoor fixture.'),
}


def selected_photos(records, selections):
    by_id = {int(r['id']): r for r in records if esc(r.get('id'))}
    return [photo_card(dict(by_id[oid], image_alt=alt), reason) for oid, (reason, alt) in selections.items()
            if oid in by_id and esc(by_id[oid].get('photo_url'))]


def purposeful_photos(records):
    cards = selected_photos(records, DIVERSITY_PHOTOS)
    return '<div class="moth-photo-grid moth-photo-pair">' + ''.join(cards) + '</div>' if cards else ''


def notable_cards(highlights, observations=None):
    cards = selected_photos(observations or [], NOTABLE_PHOTOS)
    sources = detail('The natural history behind these encounters', '<ul class="moth-native-list">'
        '<li><a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC4352808/">Luna Moth tails and bat attacks: experimental research</a></li>'
        '<li><a href="https://mdc.mo.gov/discover-nature/field-guide/beautiful-wood-nymph">Beautiful Wood-nymph: Missouri Department of Conservation</a></li>'
        '<li><a href="https://mynpn.usanpn.org/npnapps/species/Sunira/bicolorago">Bicolored Sallow: USA National Phenology Network</a></li>'
        '<li><a href="https://news.maryland.gov/dnr/2021/06/21/maryland-native-wildlife-rosy-maple-moth-dryocampa-rubicunda/">Rosy Maple Moth: Maryland Department of Natural Resources</a></li>'
        '<li><a href="https://mdc.mo.gov/discover-nature/field-guide/plume-moths">Plume moths: Missouri Department of Conservation</a></li></ul>')
    return '<div class="moth-photo-grid">' + ''.join(cards) + '</div>' + sources if cards else '<p>Remarkable local encounters will appear here as photographs become available.</p>'


def forecast_panel(forecast, ranked, validation):
    dates = sorted(r['date'] for r in forecast.get('nights', []) if r.get('date'))
    window = f'{dates[0]}–{dates[-1]}' if dates else 'No forecast dates available'
    status = 'Unavailable' if not dates or not forecast.get('fetched_at') else ('Stale' if forecast.get('is_stale') else 'Current')
    status += ' · cached forecast' if forecast.get('source') == 'cache' else ''
    updated = esc(forecast.get('fetched_at')) or 'unavailable'
    suitable = sorted((r for r in ranked if r.get('priority_rank') is not None), key=lambda r: r['priority_rank'])
    lead = (f'{esc(suitable[0]["date"])} looks the most promising evening in this forecast.' if suitable else
            'No promising light session in this forecast. Try a daytime search from the seasonal ideas above.')
    if status.startswith('Unavailable'):
        lead = 'Forecast temporarily unavailable. Try a daytime search from the seasonal ideas above.'
    rows = []
    for r in ranked:
        rows.append(f'<li><strong>{esc(r.get("date"))}</strong> · {esc(r.get("rating", "Incomplete"))}'
                    f'<br>{esc(r.get("temp_f_9pm") if r.get("temp_f_9pm") is not None else "—")}°F at 9 PM · Wind {esc(r.get("wind_mph_9pm") if r.get("wind_mph_9pm") is not None else "—")} mph · Rain {esc(r.get("rain_chance_pct") if r.get("rain_chance_pct") is not None else "—")}%</li>')
    return ('<div class="moth-panel" id="moth-forecast"><h3>Choose an evening</h3>'
            f'<p class="moth-small">Forecast: {window}<br>{status} · Updated {updated}</p><p class="moth-takeaway">{lead}</p>'
            + ('<ul class="moth-forecast-list">' + ''.join(rows) + '</ul>' if rows else '')
            + detail('About this weather guidance', f'<p>Weather guidance is independent of historical season selections. Local validation status: {esc(validation.get("status", "unavailable"))}; {validation.get("nights", 0)} nights with matching weather. The historical model uses a record-volume and timestamp-span screen, not logged survey duration. Mild, calm conditions offer a useful starting point; they do not guarantee a particular catch.</p>') + '</div>')


ACTIONS = [
    ('Early spring', 'Start before the summer rush', 'Try a mild late-March or April evening at a familiar light location. Meet the early-season cast before midsummer variety takes over.'),
    ('Early summer', 'Look at leaves by daylight', 'Search low foliage along the creek and woodland edge for rolled leaves, mines, cases and caterpillars. Feeding signs can be easier to find than their makers.'),
    ('Late summer', 'Offer a different attraction', 'Try sugar bait along a woodland edge on a warm evening, then compare its visitors with those at the lights. A different attraction can reveal another part of the community.'),
    ('Autumn and winter', 'Keep looking beyond the peak', 'Return on a mild September or October night and try short dusk visits later in autumn. On cold days, look for persistent leaf mines and cases in sheltered foliage.'),
]


def timing_controls(story):
    return detail('Explore the timing of any moth',
        '<p>Search the complete moth list, then select a name to see exact monthly records. Gaps remain visible; these records include all life stages.</p>'
        f'<div id="moth-explorer" data-src="{timing_payload(story)[0]}"><label for="moth-search">Common or scientific name</label>'
        '<input id="moth-search" type="search" placeholder="Try a moth name" autocomplete="off" disabled>'
        '<p id="moth-search-status" role="status">Loading the searchable list…</p><ul id="moth-search-results"></ul><div id="moth-timing-result"></div></div>'
        '<p><a class="moth-native-link" href="/moths/timing/" data-moth-context>Browse all monthly records without scripts →</a></p>', 'moth-timing')


def stylesheet_url(public_dir):
    css = Path(public_dir) / 'assets/survey.css'
    version = hashlib.sha256(css.read_bytes()).hexdigest()[:12] if css.exists() else 'dev'
    return '/assets/survey.css?v=' + version


def write_exploration(story, public_dir):
    """Keep the complete 889-taxon native fallback out of the main-page DOM."""
    public_dir = Path(public_dir)
    (public_dir / 'assets').mkdir(parents=True, exist_ok=True)
    # Only remove this generator's owned exports; unrelated CSVs stay visible to the guard.
    for old in (public_dir / 'assets').glob('moth-frequency-*.csv'):
        if re.fullmatch(r'moth-frequency-[0-9a-f]{16}\.csv', old.name):
            old.unlink()
    frequency_url, frequency_csv = frequency_history_csv(story)
    (public_dir / frequency_url.lstrip('/')).write_text(frequency_csv, encoding='utf-8')
    payload_url, payload = timing_payload(story)
    (public_dir / payload_url.lstrip('/')).write_text(payload, encoding='utf-8')
    rows = []
    for r in sorted(story['timing'], key=lambda r: (r['common_name'] or r['scientific_name'] or '').lower()):
        counts = ' · '.join(f'{month_name[i][:3]}: {n}' for i, n in enumerate(r['monthly_records'], 1))
        stages = ', '.join(r['stages']) or 'Stage not supplied'
        rows.append(f'<article id="taxon-{r["id"]}"><h2>{esc(r["common_name"] or r["scientific_name"])}</h2><p><i>{esc(r["scientific_name"])}</i> · {esc(stages)}</p><p>{counts}</p></article>')
    target = public_dir / 'moths/timing/index.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="robots" content="noindex"><title>Moth timing · Kingfisher Hollow</title><link rel="stylesheet" href="{stylesheet_url(public_dir)}"></head>'
        '<body class="moth-native-page"><main><a href="/moths/#moth-timing" id="moth-timing-back">← Back to the moth year</a><h1>Every moth, month by month</h1>'
        '<p>All recorded years · All life stages · Submitted records per month. Use your browser’s Find command to find a name. Zero means no dated record, not proven absence.</p>'
        + ''.join(rows) + f'</main><script src="{explorer_url()}" defer></script></body></html>', encoding='utf-8')


def search_targets(gap, all_gap, public_dir, scope='region'):
    """One strong seasonal lead plus the entire regional candidate list."""
    rows = all_gap['missing'].to_dict('records')
    place = 'within about 50 miles' if scope == 'region' else 'in Tioga County'
    path = Path(public_dir) / 'moths/targets/index.html'
    path.parent.mkdir(parents=True, exist_ok=True)
    values = ''.join(f'<li><a href="https://www.inaturalist.org/taxa/{int(r["taxon_id"])}">{esc(r["label"])}</a> · {int(r["ref_count"]):,} reference records</li>' for r in rows)
    path.write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Moth search leads · Kingfisher Hollow</title><link rel="stylesheet" href="{stylesheet_url(public_dir)}"></head>'
                    '<body class="moth-native-page"><main><a href="/moths/#moth-gap" id="moth-timing-back" data-return-anchor="moth-gap">← Back to what to try next</a><h1>Regional moth search leads</h1>'
                    f'<p>{len(rows):,} moth taxa recorded {place} without a property record. Sorted by reference record count. This wider area includes other habitats; use the list to explore possibilities.</p><ul class="moth-native-list">'
                    + values + f'</ul></main><script src="{explorer_url()}" defer></script></body></html>', encoding='utf-8')
    selected = next((r for r in rows if r['taxon_name'] == 'Alsophila pometaria'), None)
    lead = ''
    if selected:
        lead = ('<div class="moth-panel"><p class="moth-kicker">Late autumn · Tree trunks after dusk</p><h3>Look for a moth that walks</h3>'
                '<p>Female Fall Cankerworm Moths have no wings. In autumn they climb tree trunks to lay eggs, while the winged males fly. Try a slow flashlight search of deciduous trunks on a mild evening—a different way to meet a moth.</p>'
                f'<p><a href="https://www.inaturalist.org/taxa/{int(selected["taxon_id"])}">Fall Cankerworm Moth · <i>Alsophila pometaria</i> ↗</a></p>'
                f'<p class="moth-small">A regional search lead, not yet recorded here · {int(selected["ref_count"]):,} reference records {place}. '
                '<a href="https://extension.umn.edu/garden-and-home/yard-and-garden/yard-and-garden-insects/spring-and-fall-cankerworms">Life history: University of Minnesota Extension</a></p></div>')
    seasonal = gap['missing'].to_dict('records')
    months = ' and '.join(month_name[m] for m in gap.get('target_months', []))
    seasonal_html = f'<p>Regional candidates with Tioga County reports in {esc(months)}:</p><ul class="moth-native-list">' + ''.join(
        f'<li><a href="https://www.inaturalist.org/taxa/{int(r["taxon_id"])}">{esc(r["label"])}</a> · {int(r["ref_count"])} county records in these months</li>' for r in seasonal) + '</ul>'
    if not seasonal:
        seasonal_html = '<p>No regional candidates with county reports in the current month window.</p>'
    seasonal_html += f'<p><a href="/moths/targets/" class="moth-native-link" data-moth-context>Browse all {len(rows):,} regional candidates →</a></p>'
    return lead, seasonal_html


def render_moth_page(*, story, summary, comp, families, highlights, observations, forecast, ranked_forecast, validation, gap_html, methods_html, nightly_html, section, target_html=''):
    local = families[families['recorded'] > 0] if hasattr(families, 'columns') else []
    intro = ('The woods, creek margins and open edges of Kingfisher Hollow hold an extraordinary variety of moth life. '
             'Hundreds of moths are already on the list, from tiny leafrollers to striking visitors at the lights. '
             'Follow their changing seasons, meet some remarkable finds, and discover what to look for next.')
    if not summary['species']:
        intro = 'The moth inventory will take shape as local records arrive. Explore the seasonal search ideas while the first records are being prepared.'
    stats = '<dl class="moth-headline">' + ''.join(f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in [('Moths recorded', f'{summary["species"]:,}'), ('Families', len(local)), ('Estimated completeness', f'{comp.get("pct_complete", 0)}%' if comp.get('observed') else '—')]) + '</dl>'
    output = [section('moths', 'Kingfisher Hollow · After dark', 'The moths of Kingfisher Hollow', stats, intro=intro, dark=True)]
    seasons = annual(story) + comparison(story) + timing_controls(story) + detail('Explore individual moth nights', nightly_html)
    output.append(section('moth-calendar', 'A changing community', 'The moth year', seasons, intro='A moth night in spring is a different experience from one in midsummer. The cast keeps changing as the year unfolds, with familiar visitors joined by moths of a different season. Returning later means more than seeing fewer of the same things.', dark=True))
    recent, seen = [], set()
    for row in sorted(observations, key=lambda r: str(r.get('observed_on')), reverse=True):
        if row.get('taxon_id') not in seen and esc(row.get('photo_url')):
            seen.add(row.get('taxon_id'))
            recent.append(photo_card(row, f'Recorded {esc(str(row.get("observed_on"))[:10])}.'))
        if len(recent) == 6:
            break
    family_body = family_chart(families) + purposeful_photos(observations) + detail('Recent moth observations', '<div class="moth-photo-grid">' + ''.join(recent) + '</div>', 'moth-gallery')
    output.append(section('moth-families', 'Shapes, shelter and ways of living', 'Many ways to be a moth', family_body, intro='Moth diversity is a diversity of lifestyles. Caterpillars roll leaves, make mines and feed in the foliage; adults bring a remarkable range of shapes and camouflage to the lights. The families below offer different ways into that world.', dark=True))
    output.append(section('moth-completeness', 'A growing inventory', 'Still discovering', inventory_estimate(comp) + '<div id="moth-diversity" class="moth-panel">' + frequency_history_chart(story) + '</div>', intro='Discovery continues after a moth first joins the list. Visits on different nights reveal which finds recur, while new arrivals keep the cast changing. Watch those encounters become a more familiar picture of life here.', dark=True))
    output.append(section('moth-standouts', 'Encounters worth repeating', 'Rare and notable', notable_cards(highlights, observations), intro='Some finds deserve a second look: an ingenious defense, a convincing disguise, or a visitor well beyond the summer peak. These local encounters make the variety of moth life tangible.', dark=True))
    actions = '<div class="moth-action-grid">' + ''.join(f'<article><p class="moth-kicker">{season}</p><h3>{title}</h3><p>{copy}</p><a href="#moth-protocols">How to try it ↓</a></article>' for season, title, copy in ACTIONS) + '</div>'
    next_body = actions + target_html + forecast_panel(forecast, ranked_forecast, validation) + '<div id="moth-gap">' + detail('Current regional search leads', gap_html) + '</div>' + detail('How to try it: equipment and methods', methods_html, 'moth-protocols')
    output.append(section('moth-methods', 'Make another discovery', 'What to try next', next_body, intro='Change the season, the time of day or the way you look, and another part of moth life comes into view. Start with one of these searches, or use the coming weather to choose your next evening at the lights.', dark=True))
    return '<div class="moth-story">' + ''.join(output) + f'</div><script src="{explorer_url()}" defer></script>'
