import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from seasonal_community import build_community


def record(identifier, day, taxon_id, iconic='Insecta', **changes):
    return {
        'id': identifier, 'observed_on': day, 'taxon_id': taxon_id,
        'iconic_taxon': iconic, 'rank': 'species', **changes,
    }


class SeasonalCommunityTests(unittest.TestCase):
    def test_uses_all_eligible_records_and_counts_distinct_taxa_by_month(self):
        summer = build_community([
            record(1, '2025-07-03', 10),
            record(2, '2026-07-03', 10),
            record(2, '2026-07-03', 10),
            record(3, '2026-07-03', 20, 'Plantae', rank='subspecies'),
            record(4, '2026-07-04', 30, rank='genus'),
            record(5, '2026-07-05', 40, 'Aves'),
            record(6, '2026-07-06', 50, captive=True),
            record(7, '2026-07-07', 60, None),
            record(8, '2026-07-13', 70),
            record(9, '2026-07-31', 80),
            record(10, '2026-07-03', 10),
        ], today=date(2026, 7, 12), moth_ids={10})['summer']

        self.assertEqual(summer['taxa_count'], 3)
        self.assertEqual(summer['record_count'], 6)
        self.assertEqual(summer['reporting_days'], 4)
        self.assertEqual(summer['as_of'], '2026-07-07')
        self.assertEqual(summer['groups'], [
            {'label': 'Moths', 'taxa_count': 1, 'record_count': 3, 'reporting_days': 2},
            {'label': 'Plants', 'taxa_count': 1, 'record_count': 1, 'reporting_days': 1},
            {'label': 'Unknown', 'taxa_count': 1, 'record_count': 1, 'reporting_days': 1},
        ])
        self.assertEqual(
            [(row['month'], row['taxa_count']) for row in summer['months']],
            [(6, 0), (7, 3), (8, 0)],
        )
        self.assertEqual(
            [(row['period'], row['taxa_count'], row['reporting_days']) for row in summer['periods']],
            [('2025', 1, 1), ('2026', 3, 3)],
        )

    def test_moth_family_breadth_and_adjacent_month_overlap_use_distinct_taxa(self):
        chapters = build_community([
            record(1, '2026-05-30', 10),
            record(2, '2026-05-31', 20),
            record(3, '2026-06-01', 10),
            record(4, '2026-06-04', 30),
            record(5, '2026-06-04', 30),
            record(6, '2026-06-05', 40),
            record(7, '2026-06-06', 50),
            record(8, '2026-08-10', 10),
        ], today=date(2026, 9, 1), moth_ids={10, 20, 30},
           butterfly_ids={40}, odonate_ids={50}, family_by_taxon={10: 'Noctuidae'})

        moths = chapters['summer']['moths']
        self.assertEqual(moths['taxa_count'], 2)
        self.assertEqual(moths['family_count'], 1)
        self.assertEqual(moths['unknown_family_taxa_count'], 1)
        self.assertEqual(moths['families'], [{'name': 'Noctuidae', 'taxa_count': 1}])
        june, july, august = moths['months']
        self.assertEqual(
            (june['shared_with_previous'], june['only_this_month'], june['only_previous_month']),
            (1, 1, 1),
        )
        self.assertIsNone(july['shared_with_previous'])
        self.assertIsNone(august['shared_with_previous'])
        self.assertEqual(
            {row['label'] for row in chapters['summer']['groups']},
            {'Moths', 'Butterflies', 'Dragonflies & damselflies'},
        )

    def test_moth_months_report_their_own_years_and_distinct_dates(self):
        summer = build_community([
            record(1, '2025-06-03', 10),
            record(2, '2026-06-03', 10),
            record(3, '2026-06-03', 20),
            record(4, '2026-06-04', 30, 'Plantae'),
            record(5, '2025-07-03', 30, 'Plantae'),
            record(6, '2026-07-03', 10),
            record(7, '2026-07-05', 20),
            record(8, '2026-08-03', 30, 'Plantae'),
        ], today=date(2026, 9, 1), moth_ids={10, 20})['summer']

        self.assertEqual(
            [(month['source_years'], month['reporting_days']) for month in summer['months']],
            [([2025, 2026], 3), ([2025, 2026], 3), ([2026], 1)],
        )
        self.assertEqual(
            [(month['source_years'], month['reporting_days']) for month in summer['moths']['months']],
            [([2025, 2026], 2), ([2026], 2), ([], 0)],
        )

    def test_winter_period_starts_in_december_and_crosses_the_calendar_year(self):
        winter = build_community([
            record(1, '2025-12-31', 10, 'Mammalia'),
            record(2, '2026-01-01', 10, 'Mammalia'),
        ], today=date(2026, 2, 1))['winter']

        self.assertEqual([row['month'] for row in winter['months']], [12, 1, 2])
        self.assertEqual(
            [(row['period'], row['taxa_count'], row['reporting_days']) for row in winter['periods']],
            [('2025–26', 1, 2)],
        )


if __name__ == '__main__':
    unittest.main()
