import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import natural_history


def record(**overrides):
    row = dict(id=1, taxon_id=10, taxon_name='Example fungus', common_name='Example',
               iconic_taxon='Fungi', rank='species', observed_on='2026-08-01',
               quality_grade='needs_id', captive=0, photo_url='https://example.org/photo.jpg',
               photo_license='cc-by', photo_attribution='Photographer, CC BY',
               url='https://www.inaturalist.org/observations/1')
    row.update(overrides)
    return row


class NaturalHistoryTests(unittest.TestCase):
    def test_inventory_separates_unresolved_and_cultivated_records(self):
        result = natural_history.fungal_inventory([
            record(), record(id=2, observed_on='2026-08-10', quality_grade='research'),
            record(id=3, taxon_id=20, rank='genus'),
            record(id=4, taxon_id=30, captive=1),
            record(id=5, taxon_id=40, iconic_taxon='Plantae'),
        ])
        self.assertEqual(result['records'], 3)
        self.assertEqual(result['unresolved_records'], 1)
        self.assertEqual(len(result['taxa']), 1)
        self.assertEqual(result['taxa'][0]['records'], 2)
        self.assertEqual(result['taxa'][0]['last_seen'], '2026-08-10')
        self.assertEqual(result['taxa'][0]['research_records'], 1)

    def test_empty_inventory_is_honest(self):
        self.assertEqual(natural_history.fungal_inventory([])['taxa'], [])
        self.assertEqual(natural_history.fungal_inventory([])['as_of'], '')
        self.assertEqual(natural_history.story_records([], set()), [])

    def test_named_fungal_records_share_the_inventory_filter(self):
        rows = [
            record(taxon_id=10.0),
            record(id=2, taxon_id=11, rank='subspecies'),
            record(id=3, taxon_id=None),
            record(id=4, taxon_id=float('nan')),
            record(id=5, taxon_id=15, rank='genus'),
            record(id=6, taxon_id=16, rank='hybrid'),
            record(id=7, taxon_id=17, captive=1.0),
            record(id=8, taxon_id=18, iconic_taxon='Plantae'),
        ]
        self.assertEqual(natural_history.named_fungal_records(iter(rows)), rows[:2])
        result = natural_history.fungal_inventory(rows)
        self.assertEqual({taxon['taxon_id'] for taxon in result['taxa']}, {10, 11})
        self.assertEqual(result['records'], 6)
        self.assertEqual(result['unresolved_records'], 4)

    def test_local_evidence_distinguishes_photos_research_and_missing_records(self):
        rows = [
            record(id=2, url='https://www.inaturalist.org/observations/2', quality_grade='research',
                   photo_url=None, observed_on='2026-08-13'),
            record(id=3, url='https://www.inaturalist.org/observations/3', photo_license=None,
                   observed_on='2026-08-12'),
            record(id=4, url='https://www.inaturalist.org/observations/4', captive=1,
                   quality_grade='research'),
            record(id=5, url='https://www.inaturalist.org/observations/5', taxon_id=20, photo_url=None),
            record(id=6, url='https://www.inaturalist.org/observations/6', taxon_id=99),
        ]
        evidence = natural_history.record_evidence(rows, {10, 20, 30})
        self.assertEqual(evidence, {
            10: dict(records=2, photo_records=1, research_records=1, url=rows[1]['url']),
            20: dict(records=1, photo_records=0, research_records=0, url=rows[3]['url']),
            30: dict(records=0, photo_records=0, research_records=0, url=None),
        })

    def test_local_evidence_prefers_the_latest_research_photo_with_a_safe_link(self):
        rows = [
            record(id=2, observed_on='2026-08-02', url='https://inaturalist.org/observations/2/',
                   quality_grade='research'),
            record(id=1, observed_on='2026-08-01', quality_grade='research'),
            record(id=3, observed_on='2026-08-03', url='https://www.inaturalist.org.example.com/observations/3',
                   quality_grade='research'),
            record(id=4, observed_on='2026-08-04', url='https://www.inaturalist.org/observations/5',
                   quality_grade='research'),
            record(id=7, observed_on='2026-08-20', url='https://www.inaturalist.org/observations/7'),
        ]
        evidence = natural_history.record_evidence(iter(rows), [10])
        self.assertEqual(evidence[10]['url'], 'https://www.inaturalist.org/observations/2')
        self.assertEqual(evidence[10]['photo_records'], 5)

    def test_local_evidence_keeps_counts_without_a_usable_link(self):
        row = record(photo_url=float('nan'), url='javascript:alert(1)')
        self.assertEqual(natural_history.record_evidence([row], [10])[10],
                         dict(records=1, photo_records=0, research_records=0, url=None))

    def test_story_selection_is_dated_licensed_and_one_per_lens(self):
        rows = [record(), record(id=2, observed_on='2026-08-02', photo_license=None),
                record(id=3, iconic_taxon='Plantae', observed_on='2026-08-03'),
                record(id=4, iconic_taxon='Insecta', taxon_id=44),
                record(id=5, taxon_id=50, photo_url='javascript:bad')]
        selected = natural_history.story_records(rows, {44})
        self.assertEqual([row['record']['id'] for row in selected], [1, 3, 4])
        self.assertEqual(len(selected), 3)
        self.assertEqual(selected[0]['record']['quality_grade'], 'needs_id')

    def test_unknown_photo_or_date_does_not_become_evidence(self):
        rows = [record(observed_on=None), record(id=2, photo_url=float('nan'))]
        self.assertEqual(natural_history.story_records(rows, set()), [])


if __name__ == '__main__':
    unittest.main()
