import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import moth_page
from moth_story import build_story


class MothPageTests(unittest.TestCase):
    def setUp(self):
        self.story = build_story(pd.DataFrame(), pd.DataFrame())

    def test_empty_chronological_months_and_zero_meaning(self):
        html = moth_page.annual(self.story)
        labels = [f'<span>{row["name"]}</span>' for row in self.story['monthly']]
        positions = [html.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('not a documented visit with no moths', html)
        self.assertIn('January–February', html)
        self.assertIn('September–November', html)

    def test_comparison_direct_values_use_common_scale(self):
        self.story['comparisons'][6].update(shared=292, first_only=268, second_only=145)
        html = moth_page.comparison(self.story)
        for value in ['560 taxa', '437 taxa', '292 in both', '268 only in July', '145 only in August']:
            self.assertIn(value, html)
        self.assertIn('width:52.142857142857146%', html)

    def test_families_local_first_actual_overlap_and_escaping(self):
        rows = [{'family_name':'A','label':'A <script>','recorded':4,'region_total':2,'overlap':1,'gap':1,'reference_scope':'county'},
                {'family_name':'B','label':'Reference only','recorded':0,'region_total':6,'overlap':0,'gap':6,'reference_scope':'county'}]
        html = moth_page.family_chart(rows)
        self.assertIn('A &lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertIn('4 here; 1 shared with 2 recorded in Tioga County', html)
        self.assertNotIn('Reference only', html.split('<details')[0])

    def test_notable_links_photo_observation_and_credit(self):
        row = dict(label='Test', taxon_name='Taxon', taxon_id=1, first_obs_id=11,
                   photo_observation_id=22, photo_url='https://example.org/a.jpg', photo_attribution='Photo owner', photo_license='CC BY', photo_source='local_observation')
        html = moth_page.photo_card(row, 'Reason', notable=True)
        self.assertIn('/observations/22', html)
        self.assertNotIn('/observations/11', html)
        self.assertIn('Photo owner', html)

    def test_empty_and_stale_forecast_keeps_dates_and_update(self):
        forecast = {'nights':[{'date':'2026-11-12'}, {'date':'2026-11-15'}], 'is_stale':True,'source':'cache','fetched_at':'2026-11-10T12:00:00Z'}
        html = moth_page.forecast_panel(forecast, [], {})
        for text in ['2026-11-12–2026-11-15', 'Stale', 'cached forecast', '2026-11-10T12:00:00Z', 'No promising light session', 'independent of historical season']:
            self.assertIn(text, html)
        empty = moth_page.forecast_panel({}, [], {})
        self.assertIn('No forecast dates available', empty)

    def test_discovery_visible_endpoint_and_native_values(self):
        self.story['discovery'] = [{'date':'2025-07-03','cumulative_taxa':3},{'date':'2026-11-11','cumulative_taxa':889}]
        html = moth_page.discovery(self.story, {'observed':889,'estimated':1100,'pct_complete':81})
        self.assertIn('<strong>889 taxa</strong>', html)
        self.assertIn('estimated 1,100', html)
        self.assertIn('2025-07-03: <strong>3</strong>', html)

    def test_complete_native_timing_is_separate_and_escaped(self):
        self.story['timing'] = [{'id':1,'common_name':'A <B>','scientific_name':'Test','monthly_records':[0]*12,'stages':['larva']}]
        with tempfile.TemporaryDirectory() as tmp:
            moth_page.write_exploration(self.story,tmp)
            html = (Path(tmp)/'moths/timing/index.html').read_text()
            self.assertIn('A &lt;B&gt;', html)
            self.assertIn('Jan: 0', html)
            self.assertIn('Dec: 0', html)
            self.assertIn('larva', html)
        controls = moth_page.timing_controls(self.story)
        self.assertIn('/moths/timing/', controls)
        self.assertNotIn('A &lt;B&gt;', controls)

    def test_curated_photo_keeps_exact_record_and_does_not_backfill(self):
        row = dict(id=371184143, taxon_id=47916, taxon_name='Actias luna', common_name='Luna Moth', photo_url='https://example.org/luna.jpg', photo_attribution='Drew Weber', photo_license='cc-by-nc', observed_on='2026-06-12')
        html = moth_page.notable_cards([], [row])
        self.assertIn('/observations/371184143', html)
        self.assertIn('2026-06-12', html)
        self.assertIn('both long hindwing tails visible', html)
        self.assertIn('creativecommons.org/licenses/by-nc/4.0/', html)
        self.assertIn('divert attacking bats', html)
        self.assertNotIn('New York', html)
        self.assertNotIn('<figure', moth_page.notable_cards([row], []))

    def test_payload_url_changes_when_records_change(self):
        first, _ = moth_page.timing_payload(self.story)
        self.story['timing'].append({'id':1})
        second, _ = moth_page.timing_payload(self.story)
        self.assertNotEqual(first, second)
        self.assertIn('/assets/moth-timing-', first)
        self.assertRegex(moth_page.explorer_url(), r'\?v=[0-9a-f]{12}$')

    def test_journey_keeps_all_legacy_anchors(self):
        families = pd.DataFrame(columns=['recorded'])
        def section(id_, eyebrow, title, body, **kwargs):
            return f'<section id="{id_}"><h2>{title}</h2>{body}</section>'
        html = moth_page.render_moth_page(story=self.story,summary={'species':0},comp={},families=families,highlights=[],observations=[],forecast={},ranked_forecast=[],validation={},gap_html='',methods_html='',nightly_html='',section=section)
        for anchor in ['moths','moth-calendar','moth-families','moth-completeness','moth-diversity','moth-standouts','moth-methods','moth-gap','moth-gallery']:
            self.assertEqual(html.count(f'id="{anchor}"'),1)
        self.assertEqual(html.count('<section '),6)
        self.assertLess(html.index('The moth year'),html.index('Many ways to be a moth'))


if __name__ == '__main__':
    unittest.main()
