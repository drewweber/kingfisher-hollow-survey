"""Summarize the eligible iNaturalist records behind each seasonal chapter."""

from collections import Counter, defaultdict

from config import SPECIES_RANKS
from seasonal import (
    MONTH_SEASON, SEASONS, _eligible_records, _id, _observed_date, _period_label, _period_year,
)

_GROUPS = {
    'Amphibia': 'Amphibians',
    'Animalia': 'Other animals',
    'Actinopterygii': 'Ray-finned fish',
    'Arachnida': 'Arachnids',
    'Fungi': 'Fungi & lichens',
    'Insecta': 'Other insects',
    'Mammalia': 'Mammals',
    'Mollusca': 'Molluscs',
    'Plantae': 'Plants',
    'Reptilia': 'Reptiles',
}
_UNKNOWN = 'Unknown'


class _Records:
    def __init__(self):
        self.days_by_taxon = defaultdict(set)
        self.count_by_taxon = Counter()
        self.days = set()
        self.count = 0

    @property
    def taxa(self):
        return self.days_by_taxon.keys()

    def add(self, observed, taxon_id):
        self.count += 1
        self.days.add(observed)
        if taxon_id is not None:
            self.days_by_taxon[taxon_id].add(observed)
            self.count_by_taxon[taxon_id] += 1

    def summary(self, group_by_taxon):
        group_taxa = Counter()
        group_counts = Counter()
        group_days = defaultdict(set)
        for taxon_id, days in self.days_by_taxon.items():
            label = group_by_taxon[taxon_id]
            group_taxa[label] += 1
            group_counts[label] += self.count_by_taxon[taxon_id]
            group_days[label].update(days)
        return {
            'taxa_count': len(self.taxa),
            'record_count': self.count,
            'reporting_days': len(self.days),
            'first_date': min(self.days).isoformat() if self.days else '',
            'as_of': max(self.days).isoformat() if self.days else '',
            'groups': [
                {
                    'label': label,
                    'taxa_count': count,
                    'record_count': group_counts[label],
                    'reporting_days': len(group_days[label]),
                }
                for label, count in sorted(group_taxa.items(), key=lambda item: (-item[1], item[0]))
            ],
        }


def _moth_month(month, months, moth_ids):
    month_records = months[month]
    current = month_records.taxa & moth_ids
    previous = months[month - 1 or 12].taxa & moth_ids
    reporting_dates = {
        day for taxon_id in current for day in month_records.days_by_taxon[taxon_id]
    }
    # With no moth detections in either month we lack an observed community to compare.
    comparable = bool(current and previous)
    return {
        'month': month,
        'taxa_count': len(current),
        'reporting_days': len(reporting_dates),
        'source_years': sorted({day.year for day in reporting_dates}),
        'shared_with_previous': len(current & previous) if comparable else None,
        'only_this_month': len(current - previous) if comparable else None,
        'only_previous_month': len(previous - current) if comparable else None,
    }


def build_community(observations, *, today, moth_ids=(), butterfly_ids=(), odonate_ids=(),
                    family_by_taxon=None):
    """Return monthly and seasonal summaries of observed records through today.

    Counts of taxa use distinct species-level-or-finer IDs, including provisional
    identifications. Each group's record and reporting-day counts use the
    records supporting its taxon count. Overall reporting days include
    eligible records of all ranks. A reporting day has at least one record.
    Each month pools the available years. Source periods preserve their separate
    contributions, with December through February grouped as a single winter.
    Monthly source years are calendar years with records for the relevant
    summary. Adjacent-month moth comparisons describe overlap among recorded taxa.
    """
    cutoff = _observed_date(today)
    if cutoff is None:
        raise ValueError('today must be a valid local date')

    moth_ids = set(moth_ids)
    rosters = {taxon_id: 'Moths' for taxon_id in moth_ids}
    rosters.update(dict.fromkeys(butterfly_ids, 'Butterflies'))
    rosters.update(dict.fromkeys(odonate_ids, 'Dragonflies & damselflies'))
    family_by_taxon = {} if family_by_taxon is None else family_by_taxon

    months = defaultdict(_Records)
    seasons = defaultdict(_Records)
    periods = {key: defaultdict(_Records) for key in SEASONS}
    group_by_taxon = {}
    for observed, _, row in _eligible_records(observations, cutoff):
        taxon_id = _id(row.get('taxon_id')) if row.get('rank') in SPECIES_RANKS else None
        if taxon_id is not None and group_by_taxon.get(taxon_id, _UNKNOWN) == _UNKNOWN:
            group_by_taxon[taxon_id] = rosters.get(
                taxon_id, _GROUPS.get(row.get('iconic_taxon'), _UNKNOWN),
            )
        key = MONTH_SEASON[observed.month]
        months[observed.month].add(observed, taxon_id)
        seasons[key].add(observed, taxon_id)
        periods[key][_period_year(observed)].add(observed, taxon_id)

    summaries = {}
    for key, season_months in SEASONS.items():
        season = seasons[key]
        moth_taxa = season.taxa & moth_ids
        families = Counter()
        for taxon_id in moth_taxa:
            family = family_by_taxon.get(taxon_id)
            if isinstance(family, str) and family.strip():
                families[family.strip()] += 1

        summaries[key] = {
            **season.summary(group_by_taxon),
            'months': [
                {
                    'month': month,
                    'source_years': sorted({day.year for day in months[month].days}),
                    **months[month].summary(group_by_taxon),
                }
                for month in season_months
            ],
            'periods': [
                {
                    'period': _period_label(year, key),
                    **period.summary(group_by_taxon),
                    'moth_taxa_count': len(period.taxa & moth_ids),
                }
                for year, period in sorted(periods[key].items())
            ],
            'moths': {
                'taxa_count': len(moth_taxa),
                'family_count': len(families),
                'unknown_family_taxa_count': len(moth_taxa) - sum(families.values()),
                'families': [
                    {'name': name, 'taxa_count': count}
                    for name, count in sorted(families.items(), key=lambda item: (-item[1], item[0]))
                ],
                'months': [_moth_month(month, months, moth_ids) for month in season_months],
            },
        }
    return summaries
