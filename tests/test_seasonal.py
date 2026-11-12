import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from seasonal import build_chapters, season_key


def seed_bug(identifier, observed_on, **overrides):
    record = {
        'id': identifier,
        'taxon_id': 67771,
        'taxon_name': 'Leptoglossus occidentalis',
        'common_name': 'Western Conifer Seed Bug',
        'rank': 'species',
        'iconic_taxon': 'Insecta',
        'observed_on': observed_on,
        'created_at': '2026-09-01T04:00:00Z',
        'quality_grade': 'research',
        'captive': 0,
        'photo_url': 'https://static.inaturalist.org/photos/123/medium.jpg',
        'photo_attribution': '(c) Observer',
        'photo_license': 'cc-by',
    }
    record.update(overrides)
    return record


class SeasonalTests(unittest.TestCase):
    def test_season_uses_observed_month_and_rejects_invalid_dates(self):
        for value, expected in [
            ('2026-02-28', 'winter'), ('2026-03-01', 'spring'),
            (date(2026, 5, 31), 'spring'), (datetime(2026, 6, 1), 'summer'),
            ('2026-08-31', 'summer'), ('2026-09-01', 'autumn'),
            ('2026-11-30', 'autumn'), ('2026-12-01', 'winter'),
            ('2026-02-29', None), ('2026-03-01junk', None),
            ('2026-03', None), (None, None), (float('nan'), None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(season_key(value), expected)

    def test_winter_groups_december_with_next_year_and_keeps_empty_months(self):
        chapters = build_chapters([
            seed_bug(1, '2024-12-01'),
            seed_bug(2, '2025-02-28'),
            seed_bug(3, '2025-12-01'),
            seed_bug(4, '2026-01-15'),
            seed_bug(5, '2026-02-28'),
        ], today=date(2026, 3, 1))
        winter = chapters['winter']
        self.assertEqual(winter['source_years'], ['2024–25', '2025–26'])
        self.assertEqual(winter['as_of'], '2026-02-28')
        self.assertEqual(winter['month_numbers'], [12, 1, 2])
        self.assertEqual(winter['coverage'][0], {
            'period': '2024–25',
            'months': [
                {'month': 12, 'label': 'December', 'record_count': 1, 'reporting_days': 1},
                {'month': 1, 'label': 'January', 'record_count': 0, 'reporting_days': 0},
                {'month': 2, 'label': 'February', 'record_count': 1, 'reporting_days': 1},
            ],
        })
        row = next(row for row in winter['rows'] if row['taxon_id'] == 67771)
        self.assertEqual(row['years'], ['2024–25', '2025–26'])
        self.assertEqual([item['period'] for item in row['records']],
                         ['2024–25', '2024–25', '2025–26', '2025–26', '2025–26'])
        self.assertEqual([row['records'][i]['position'] for i in (0, 1, 2, 4)], [0, 1, 0, 1])
        self.assertGreater(row['records'][3]['position'], 1 / 3)
        self.assertLess(row['records'][3]['position'], 2 / 3)

    def test_coverage_counts_distinct_ids_and_reporting_dates(self):
        eligible = seed_bug(10, '2026-01-10')
        observations = [
            eligible,
            dict(eligible, id=10.0, created_at='2026-10-01T00:00:00Z'),
            seed_bug(11, '2026-01-10'),
            seed_bug(12, '2026-01-11', rank='genus', taxon_id=42, taxon_name='Other genus'),
            seed_bug(13, '2026-01-11', captive=1.0),
            seed_bug(14, '2026-01-11', captive='true'),
            seed_bug(15, '2026-01-11', iconic_taxon='Aves'),
            seed_bug(16, '2026-01-31'),
            seed_bug(17, '2026-01-32'),
            seed_bug(None, '2026-01-11'),
        ]
        chapters = build_chapters(observations, today=date(2026, 1, 15))
        winter = chapters['winter']
        row = next(row for row in winter['rows'] if row['taxon_id'] == 67771)
        self.assertEqual([item['id'] for item in row['records']], [10, 11])
        self.assertEqual(row['record_count'], 2)
        self.assertEqual(row['reporting_days'], 1)
        self.assertEqual(winter['coverage'][0]['months'][1]['record_count'], 3)
        self.assertEqual(winter['coverage'][0]['months'][1]['reporting_days'], 2)
        self.assertEqual(winter['as_of'], '2026-01-11')
        self.assertEqual(chapters['autumn']['as_of'], '')

    def test_unknown_stage_and_ineligible_photos_keep_the_source_link(self):
        winter = build_chapters([
            seed_bug(20, '2026-01-01', quality_grade='needs_id'),
            seed_bug(21, '2026-01-02', photo_license='all-rights-reserved'),
            seed_bug(22, '2026-01-03', photo_attribution='  '),
            seed_bug(23, '2026-01-04', photo_url='http://example.org/photo.jpg'),
            seed_bug(24, '2026-01-05', photo_url='https://wrong.org@evil.test/photo.jpg'),
            seed_bug(25, '2026-01-06', photo_url='https://example.org/evil\\photo.jpg'),
            seed_bug(26, '2026-01-07', photo_license='cc-by-nd'),
        ], today=date(2026, 3, 1))['winter']
        records = next(row['records'] for row in winter['rows'] if row['taxon_id'] == 67771)
        self.assertEqual(records[0]['event_type'], 'Unspecified encounter')
        self.assertEqual(records[0]['quality'], 'needs_id')
        self.assertEqual(records[0]['photo_credit'], '(c) Observer')
        self.assertEqual(records[0]['photo_license'], 'cc-by')
        self.assertTrue(records[0]['photo_url'].startswith('https://'))
        for item in records[1:]:
            self.assertEqual((item['photo_url'], item['photo_credit'], item['photo_license']),
                             ('', '', ''))
            self.assertEqual(item['url'], f'https://www.inaturalist.org/observations/{item["id"]}')

    def test_identity_change_removes_curated_claims_and_passage_links(self):
        winter = build_chapters([
            seed_bug(30, '2026-01-01', taxon_name='Leptoglossus different'),
        ], today=date(2026, 3, 1))['winter']
        self.assertEqual(winter['rows'], [])
        self.assertTrue(all(not passage['row_ids'] for passage in winter['passages']))
        self.assertNotIn('Western Conifer Seed Bug', json.dumps(winter))
        self.assertEqual(winter['source_years'], ['2025–26'])

    def test_reviewed_stage_is_only_used_for_its_dated_voucher(self):
        egg_voucher = seed_bug(346449861, '2026-03-31', taxon_id=26790,
                               taxon_name='Ambystoma maculatum', iconic_taxon='Amphibia',
                               photo_url='https://static.inaturalist.org/photos/631527312/medium.jpg')
        later = dict(egg_voucher, id=999, observed_on='2026-04-15')
        spring = build_chapters([egg_voucher, later], today=date(2026, 6, 1))['spring']
        records = spring['rows'][0]['records']
        self.assertEqual([item['event_type'] for item in records],
                         ['Eggs', 'Unspecified encounter'])
        self.assertEqual(spring['rows'][0]['record_type'], 'Dated encounters')
        changed = build_chapters([dict(egg_voucher, observed_on='2026-03-30')],
                                 today=date(2026, 6, 1))['spring']
        self.assertEqual(changed['rows'][0]['records'][0]['event_type'], 'Unspecified encounter')

    def test_removed_or_replaced_reviewed_photo_suppresses_its_stage_and_claim(self):
        egg = seed_bug(346449861, '2026-03-31', taxon_id=26790,
                       taxon_name='Ambystoma maculatum', iconic_taxon='Amphibia',
                       photo_url='https://static.inaturalist.org/photos/631527312/medium.jpg')
        intact = build_chapters([egg], today=date(2026, 6, 1))['spring']
        claim = 'Spotted salamander eggs mark that early-spring transition at the Hollow.'
        self.assertEqual(intact['rows'][0]['records'][0]['event_type'], 'Eggs')
        self.assertNotIn(claim, intact['passages'][0]['body'])
        for photo in (None, 'https://static.inaturalist.org/photos/123/medium.jpg'):
            spring = build_chapters([dict(egg, photo_url=photo)],
                                    today=date(2026, 6, 1))['spring']
            self.assertEqual(spring['rows'][0]['records'][0]['event_type'],
                             'Unspecified encounter')
            self.assertNotIn(claim, spring['passages'][0]['body'])

        spring = build_chapters([dict(egg, photo_license=None)],
                                today=date(2026, 6, 1))['spring']
        item = spring['rows'][0]['records'][0]
        self.assertEqual(item['event_type'], 'Eggs')
        self.assertEqual(item['photo_url'], '')

    def test_bird_checklist_is_separate_from_coverage(self):
        winter = build_chapters([], today=date(2026, 3, 1))['winter']
        self.assertEqual(winter['bird_examples'][0]['date'], '2025-12-13')
        self.assertEqual(winter['coverage'], [])
        self.assertEqual(winter['source_years'], [])
        before = build_chapters([], today=date(2025, 12, 12))['winter']
        self.assertEqual(before['bird_examples'], [])

    def test_community_story_is_independent_of_selected_vouchers(self):
        egg = seed_bug(346449861, '2026-03-31', taxon_id=26790,
                       taxon_name='Ambystoma maculatum', iconic_taxon='Amphibia',
                       photo_url='https://static.inaturalist.org/photos/631527312/medium.jpg')
        with_voucher = build_chapters([egg], today=date(2026, 11, 11))
        without_voucher = build_chapters([], today=date(2026, 11, 11))
        self.assertEqual(len(with_voucher['spring']['rows']), 1)
        for key, chapter in with_voucher.items():
            self.assertIsNone(chapter['opening_detail_record_id'])
            self.assertEqual(chapter['passages'], without_voucher[key]['passages'])
            for passage in chapter['passages']:
                self.assertFalse(passage['row_ids'])
                self.assertIsNone(passage['photo_record_id'])

    def test_empty_input_still_produces_readable_chapters(self):
        chapters = build_chapters([], today=date(2026, 3, 1))
        self.assertEqual(list(chapters), ['spring', 'summer', 'autumn', 'winter'])
        for key, chapter in chapters.items():
            self.assertEqual(chapter['route'], f'/seasons/{key}/')
            self.assertEqual(chapter['as_of'], '')
            self.assertEqual(chapter['coverage'], [])
            self.assertEqual(chapter['source_years'], [])
            self.assertEqual(chapter['rows'], [])
            self.assertEqual(len(chapter['passages']), 3)
            self.assertTrue(chapter['framing'])
            self.assertTrue(chapter['next_observation'])


if __name__ == '__main__':
    unittest.main()
