"""Build seasonal chapters from dated iNaturalist property encounters."""

import calendar
import json
import re
from collections import defaultdict
from datetime import date, datetime
from numbers import Real
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from config import DATA_DIR, SPECIES_RANKS

SEASONS = {
    'spring': (3, 4, 5),
    'summer': (6, 7, 8),
    'autumn': (9, 10, 11),
    'winter': (12, 1, 2),
}
MONTH_SEASON = {month: key for key, months in SEASONS.items() for month in months}
# The chapter may display detail crops, so photos with no-derivatives licenses stay linked.
PHOTO_LICENSES = {'cc0', 'cc-by', 'cc-by-sa', 'cc-by-nc', 'cc-by-nc-sa'}
UNSPECIFIED = 'Unspecified encounter'
QUALITY_GRADES = {'research', 'needs_id', 'casual'}
SOURCES = [
    {'label': 'Kingfisher Hollow Biodiversity Survey on iNaturalist',
     'url': 'https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey'},
    {'label': 'iNaturalist observation quality grades',
     'url': 'https://help.inaturalist.org/en/support/solutions/articles/151000169936'},
]


def _observed_date(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value if value.year >= 1 else None  # Also excludes pandas NaT.
    if isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def season_key(observed_on):
    """Return the chapter for a local observed date, or None for invalid dates."""
    observed = _observed_date(observed_on)
    return MONTH_SEASON[observed.month] if observed else None


def _id(value):
    if isinstance(value, Real) and not isinstance(value, bool) and 0 < value < float('inf'):
        return int(value) if int(value) == value else None
    return None


def _period_year(observed):
    return observed.year - (observed.month in (1, 2))


def _period_label(year, key):
    return f'{year}–{(year + 1) % 100:02d}' if key == 'winter' else str(year)


def _position(observed, months):
    # Equal-width months keep calendar boundaries aligned across years, including leap winters.
    days = calendar.monthrange(observed.year, observed.month)[1]
    progress = (observed.day - 1) / days
    if observed.month == months[-1]:
        progress = (observed.day - 1) / (days - 1)
    return (months.index(observed.month) + progress) / len(months)


def _safe_photo_url(value):
    if not isinstance(value, str) or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and bool(url.hostname)
                and url.username is None and url.port in (None, 443))
    except ValueError:
        return False


def _photo_id(value):
    if _safe_photo_url(value):
        match = re.search(r'/photos/([0-9]+)/', urlsplit(value).path)
        return match[1] if match else None
    return None


def _photo_fields(row):
    photo_url = row.get('photo_url')
    credit = row.get('photo_attribution')
    license_code = row.get('photo_license')
    if (license_code in PHOTO_LICENSES and isinstance(credit, str) and credit.strip()
            and _safe_photo_url(photo_url)):
        return {'photo_url': photo_url, 'photo_credit': credit.strip(), 'photo_license': license_code}
    return {'photo_url': '', 'photo_credit': '', 'photo_license': ''}


def _eligible_records(observations, cutoff):
    seen = set()
    for row in observations:
        identifier = _id(row.get('id'))
        observed = _observed_date(row.get('observed_on'))
        if (identifier is None or identifier in seen or observed is None or observed > cutoff
                or row.get('iconic_taxon') == 'Aves'
                or str(row.get('captive')).strip().lower() in {'1', '1.0', 'true'}):
            continue
        seen.add(identifier)
        yield observed, identifier, row


def _coverage(month_dates, key, months):
    years = sorted({year for year, _ in month_dates})
    return [
        {
            'period': _period_label(year, key),
            'months': [
                {
                    'month': month, 'label': calendar.month_name[month],
                    'record_count': len(month_dates.get((year, month), [])),
                    'reporting_days': len(set(month_dates.get((year, month), []))),
                }
                for month in months
            ],
        }
        for year in years
    ]


def _record(observed, identifier, raw, name, key, months, events):
    event = events.get(str(identifier))
    event_type = UNSPECIFIED
    photo_url = raw.get('photo_url')
    if event and event['date'] == observed.isoformat() and _photo_id(photo_url) == event['photo_id']:
        event_type = event['type']
    quality = raw.get('quality_grade')
    return {
        'id': identifier,
        'date': observed.isoformat(),
        'period': _period_label(_period_year(observed), key),
        'month': observed.month,
        'position': _position(observed, months),
        'url': f'https://www.inaturalist.org/observations/{identifier}',
        'name': name,
        'quality': quality if quality in QUALITY_GRADES else '',
        'event_type': event_type,
        **_photo_fields(raw),
    }


def _join(words):
    if len(words) < 3:
        return ' and '.join(words)
    return ', '.join(words[:-1]) + ', and ' + words[-1]


def _date_words(observed):
    return f'{calendar.month_name[observed.month]} {observed.day}, {observed.year}'


def _build_rows(story, entries, key, months):
    rows = {}
    sources = []
    for entry in story['rows']:
        taxon = entry['taxon_id'], entry['taxon_name']
        records = [
            _record(observed, identifier, raw, entry['name'], key, months, entry.get('events', {}))
            for observed, identifier, raw in entries.get(taxon, ())
        ]
        if not records:
            continue
        records.sort(key=lambda item: (item['date'], item['id']))
        types = {item['event_type'] for item in records}
        row_id = entry['id']
        rows[row_id] = {
            'id': row_id, 'taxon_id': entry['taxon_id'], 'name': entry['name'],
            'group': entry['group'],
            'record_type': next(iter(types)) if len(types) == 1 else 'Dated encounters',
            'interpretation': entry['interpretation'],
            'records': records,
            'years': list(dict.fromkeys(item['period'] for item in records)),
            'record_count': len(records),
            'reporting_days': len({item['date'] for item in records}),
        }
        sources.extend(entry.get('sources', ()))
    return rows, sources


def _matches_record(record, reviewed):
    for field, value in reviewed.items():
        current = _photo_id(record.get('photo_url')) if field == 'photo_id' else record.get(field)
        if current != value:
            return False
    return True


def _build_passage(passage, rows):
    row_ids = [row_id for row_id in passage['row_ids'] if row_id in rows]
    records = {item['id']: item for rid in row_ids for item in rows[rid]['records']}
    body = [passage['body']]
    for claim in passage.get('claims', ()):
        if all(_matches_record(records.get(proof['id'], {}), proof) for proof in claim['requires']):
            body.append(claim['text'])

    illustration = passage.get('illustration')
    photo_record_id = None
    if illustration:
        record = records.get(illustration['id'], {})
        if record.get('month') == passage['phase_month'] and _matches_record(record, illustration):
            photo_record_id = record['id']
    return {
        'id': passage['id'], 'phase': passage['phase'], 'title': passage['title'],
        'phase_month': passage['phase_month'], 'photo_record_id': photo_record_id,
        'body': ' '.join(body), 'look_for': passage['look_for'], 'row_ids': row_ids,
    }


def _framing(coverage, latest, key):
    if not coverage:
        return ('The property survey has no dated iNaturalist records available for this chapter. '
                'The observation ideas are places to start.')
    labels = [period['period'] for period in coverage]
    if len(labels) == 1:
        scope = f'iNaturalist records are available for one {key}, {labels[0]}.'
    else:
        scope = f'This chapter draws on iNaturalist records from {key} {_join(labels)}.'
    return (f'{scope} The latest is dated {_date_words(latest)}. The calendar shows selected '
            'encounters. A reporting day is a date with at least one record. Gaps can reflect '
            'when, where, or how people looked.')


def build_chapters(observations, today=None):
    """Return the four chapters and their evidence without network or database reads."""
    cutoff = _observed_date(today) or datetime.now(ZoneInfo('America/New_York')).date()
    stories = json.loads((DATA_DIR / 'reference' / 'seasonal-stories.json').read_text(encoding='utf-8'))
    by_season = {key: defaultdict(list) for key in SEASONS}
    dates = {key: defaultdict(list) for key in SEASONS}
    for observed, identifier, raw in _eligible_records(observations, cutoff):
        key = MONTH_SEASON[observed.month]
        dates[key][(_period_year(observed), observed.month)].append(observed)
        if raw.get('rank') in SPECIES_RANKS:
            taxon = _id(raw.get('taxon_id')), raw.get('taxon_name')
            by_season[key][taxon].append((observed, identifier, raw))

    chapters = {}
    for key, months in SEASONS.items():
        story = stories[key]
        rows, sources = _build_rows(story, by_season[key], key, months)
        passages = [_build_passage(passage, rows) for passage in story['passages']]
        opening_detail = next((p['photo_record_id'] for p in passages
                               if p['id'] == story.get('opening_detail_passage')), None)
        coverage = _coverage(dates[key], key, months)
        intro = story['intro']
        if len(coverage) == 1 and story.get('single_period_intro'):
            intro = f"{intro} {story['single_period_intro']}"
        latest = max((max(days) for days in dates[key].values()), default=None)
        chapter_sources = {
            source['url']: source
            for source in [*SOURCES, *story.get('sources', ()), *sources]
        }
        chapters[key] = {
            'key': key, 'label': key.title(),
            'months': f'{calendar.month_name[months[0]]}–{calendar.month_name[months[-1]]}',
            'month_numbers': list(months), 'route': f'/seasons/{key}/',
            'title': story['title'], 'intro': intro, 'framing': _framing(coverage, latest, key),
            'opening_detail_record_id': opening_detail,
            'passages': passages, 'rows': list(rows.values()), 'coverage': coverage,
            'source_years': [period['period'] for period in coverage],
            'as_of': latest.isoformat() if latest else '',
            'next_observation': story['next_observation'], 'sources': list(chapter_sources.values()),
            'bird_examples': [
                example for example in story.get('bird_examples', ())
                if season_key(example['date']) == key and _observed_date(example['date']) <= cutoff
            ],
        }
    return chapters
