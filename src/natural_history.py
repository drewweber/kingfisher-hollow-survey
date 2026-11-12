"""Small, source-aware selections for seasonal natural-history interpretation.

These are observations and search questions, not inferred breeding, substrates,
host relationships, or estimates of abundance.
"""

from datetime import date
import math
from numbers import Real
import re
from urllib.parse import urlsplit

NAMED_RANKS = {'species', 'subspecies', 'variety', 'form', 'subvariety', 'subform'}
PHOTO_LICENSES = {'cc0', 'cc-by', 'cc-by-sa', 'cc-by-nc', 'cc-by-nc-sa',
                  'cc-by-nd', 'cc-by-nc-nd'}
OBSERVATION_URL = re.compile(r'https://(?:www\.)?inaturalist\.org/observations/([1-9][0-9]*)/?')


def text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    return str(value)


def _date(value):
    candidate = text(value)[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return ''


def _wild(row):
    return text(row.get('captive')).lower() not in {'1', '1.0', 'true'}


def _positive_id(value):
    if (isinstance(value, Real) and not isinstance(value, bool)
            and value > 0 and math.isfinite(value) and value == int(value)):
        return int(value)
    return None


def _has_photo(row):
    try:
        url = urlsplit(text(row.get('photo_url')))
        return url.scheme == 'https' and bool(url.hostname) and url.username is None
    except ValueError:
        return False


def _photo(row):
    return (_has_photo(row)
            and row.get('photo_license') in PHOTO_LICENSES
            and bool(text(row.get('photo_attribution'))))


def record_evidence(observations, taxon_ids):
    """Count wild property records, independent of the roster's taxon photos.

    For each requested ID, prefer a linked photograph, then research grade,
    then the latest observation. A local photo need not be licensed for reuse
    to count here, since this helper links to the observation instead.
    """
    evidence = {tid: dict(records=0, photo_records=0, research_records=0, url=None)
                for value in taxon_ids if (tid := _positive_id(value)) is not None}
    best = {}
    for row in observations:
        tid = _positive_id(row.get('taxon_id'))
        entry = evidence.get(tid)
        if entry is None or not _wild(row):
            continue
        has_photo = _has_photo(row)
        research = text(row.get('quality_grade')) == 'research'
        entry['records'] += 1
        entry['photo_records'] += has_photo
        entry['research_records'] += research

        match = OBSERVATION_URL.fullmatch(text(row.get('url')))
        if not match:
            continue
        observation_id = int(match.group(1))
        row_id = _positive_id(row.get('id'))
        if row_id is not None and observation_id != row_id:
            continue
        score = (has_photo, research, _date(row.get('observed_on')), observation_id)
        if tid not in best or score > best[tid]:
            best[tid] = score
            entry['url'] = f'https://www.inaturalist.org/observations/{observation_id}'
    return evidence


def _wild_fungus(row):
    return text(row.get('iconic_taxon')) == 'Fungi' and _wild(row)


def named_fungal_records(observations):
    """Return the records eligible for the named fungal inventory."""
    return [row for row in observations if _wild_fungus(row)
            and row.get('rank') in NAMED_RANKS and _positive_id(row.get('taxon_id')) is not None]


def fungal_inventory(observations):
    rows = [r for r in observations if _wild_fungus(r)]
    named = named_fungal_records(rows)
    groups = {}
    for row in named:
        groups.setdefault(_positive_id(row['taxon_id']), []).append(row)
    taxa = []
    for tid, records in groups.items():
        ordered = sorted(records, key=lambda r: (_date(r.get('observed_on')), _positive_id(r.get('id')) or 0), reverse=True)
        latest = ordered[0]
        dates = sorted(d for r in records if (d := _date(r.get('observed_on'))))
        taxa.append(dict(taxon_id=tid, taxon_name=text(latest.get('taxon_name')),
                         common_name=text(latest.get('common_name')),
                         records=len(records), research_records=sum(text(r.get('quality_grade')) == 'research' for r in records),
                         first_seen=dates[0] if dates else '', last_seen=dates[-1] if dates else '',
                         record=latest, photo=next((r for r in ordered if _photo(r)), None)))
    taxa.sort(key=lambda r: (r['last_seen'], r['taxon_name']), reverse=True)
    dates = [_date(r.get('observed_on')) for r in rows]
    return dict(taxa=taxa, records=len(rows), unresolved_records=len(rows)-len(named),
                as_of=max(dates, default=''))


STORY_LENSES = (
    dict(key='fungi', title='A mushroom is one visible moment', route='/fungi/', link='Explore the fungi',
         body='A photograph catches a visible stage of a fungus. On the next visit, include what it grows on and the underside as well as the top. Repeat photographs can tell a richer story than a name alone.',
         source='https://sweetgum.nybg.org/science/collections/fungi/', source_label='NYBG fungal collections'),
    dict(key='plants', title='Look at the plant, then look again', route='/plants/', link='Explore the plants',
         body='A plant record can become the starting point for a second search: leaf mines, feeding signs, flower visitors, or developing fruit. Photograph the relationship directly before calling a plant a local host.',
         source='https://xerces.org/endangered-species/butterflies', source_label='Xerces on host plants'),
    dict(key='odonates', title='A visitor, or a life begun here?', route='/dragonflies/', link='Explore dragonflies',
         body='An adult dragonfly can travel beyond the water where it grew. An empty larval skin left at emergence tells a different story. Look along stems and banks, and keep sightings, egg laying, and emergence as distinct evidence.',
         source='https://home.nps.gov/articles/000/nature-watch-flying-jewels-living-flashes-of-light.htm', source_label='NPS on dragonfly life cycles'),
)


def story_records(observations, odonate_ids):
    rows = [r for r in observations if _wild(r) and _photo(r) and _date(r.get('observed_on'))
            and r.get('rank') in NAMED_RANKS]
    rows.sort(key=lambda r: (_date(r.get('observed_on')), int(r.get('id') or 0)), reverse=True)
    selected = []
    for lens in STORY_LENSES:
        def matches(row):
            if lens['key'] == 'odonates':
                return row.get('taxon_id') in odonate_ids
            return row.get('iconic_taxon') == {'fungi': 'Fungi', 'plants': 'Plantae'}[lens['key']]
        candidate = next((r for r in rows if matches(r)), None)
        if candidate:
            selected.append({**lens, 'record': candidate})
    return selected


SEASONS = (
    dict(key='spring', label='Spring', months='March–May', title='Follow the thaw',
         body='Return to the creek, pond margins, and forest floor as the season opens. Listen for frog calls and returning birds; photograph plants while flowers and fresh leaves make them identifiable.',
         cue='Woodland wildflowers · leafing trees · pond life', route='/seasons/spring/'),
    dict(key='summer', label='Summer', months='June–August', title='Long days, short nights',
         body='Sunny margins and the hours after dusk reveal different lives. Follow dragonflies around the water, look for insects on plants, and compare repeated nights at the moth sheet.',
         cue='Pond margins · plant life · moth nights', route='/seasons/summer/'),
    dict(key='autumn', label='Autumn', months='September–November', title='Look closer as the leaves fall',
         body='The end of the green season still rewards a slow look. Search for fungi after rain, watch migrating birds, and check the lights on mild evenings. Weather decides which of these seasonal possibilities becomes visible.',
         cue='Goldenrod · fallen leaves · fungi · late-season insects', route='/seasons/autumn/'),
    dict(key='winter', label='Winter', months='December–February', title='Read the quiet months',
         body='Snow, when it comes, makes tracks easier to follow. Open water, evergreen cover, bark, and standing stems offer other places to look. Keep notes on repeat visits, including quiet ones.',
         cue='Bare branches · evergreen shelter · animal tracks', route='/seasons/winter/'),
)


def seasonal_context(on=None):
    on = on or date.today()
    index = 3 if on.month in (12, 1, 2) else (on.month - 3) // 3
    return {**SEASONS[index], 'month': on.strftime('%B'), 'year': on.year}
