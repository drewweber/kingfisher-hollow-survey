"""Chart alternatives preserve source values without Plotly or hover."""
from html.parser import HTMLParser
import re
import unittest
from unittest import mock

import pandas as pd

from src import viz


class TableParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows, self.headers, self.captions = [], [], []
        self.cell = self.row = self.caption = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th'):
            self.cell = ''
            if tag == 'th':
                self.headers.append(attrs.get('scope'))
        if tag == 'caption':
            self.caption = ''

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data
        if self.caption is not None:
            self.caption += data

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            self.row.append(self.cell)
            self.cell = None
        if tag == 'tr':
            self.rows.append(self.row)
            self.row = None
        if tag == 'caption':
            self.captions.append(self.caption)
            self.caption = None


class ChartAlternativeTests(unittest.TestCase):
    def table(self, html):
        self.assertIn('data-chart-figure', html)
        self.assertIn('data-chart-table', html)
        self.assertIn('tabindex="0"', html)
        self.assertIn('role="region"', html)
        self.assertRegex(html, r'<figcaption[^>]*>[^<]+</figcaption>')
        self.assertNotRegex(html, r'<figcaption[^>]*sr-only')
        table = TableParser(html)
        self.assertTrue(table.captions)
        self.assertIn('col', table.headers)
        self.assertIn('row', table.headers)
        self.assertNotIn(None, table.headers)
        # The Plotly payload remains externalizable without including the table.
        self.assertRegex(html, r'data-plotly-chart[^>]*></div>\s*<script')
        return table

    def test_discovery_links_to_inventory_without_publishing_duplicate_tables(self):
        import tempfile
        from pathlib import Path
        from src import chart_data
        firsts = pd.DataFrame({
            'observed_on': pd.to_datetime(['2025-01-01'] * 14 + ['2025-02-02']),
            'cumulative': range(1, 16),
        })
        html = viz.discovery_curve(firsts)
        self.assertIn('data-chart-figure', html)
        self.assertRegex(html, r'<a[^>]*href="/life-list/"[^>]*>[^<]*Life List</a>')
        self.assertNotIn('<details', html)
        self.assertNotIn('<table', html)
        self.assertIn('15 species with dated records by 2025-02-02', html)
        self.assertRegex(html, r'data-plotly-chart[^>]*></div>\s*<script')
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(chart_data.publish_tables(html, Path(tmp), '/'), html)
            self.assertFalse(list(Path(tmp).rglob('*.html')))
        # The chart still includes every discovery step, including same-day ties.
        with mock.patch.object(viz, '_html', return_value='') as render:
            viz.discovery_curve(firsts)
        figure = render.call_args.args[0]
        self.assertEqual(list(figure.data[0].y), list(range(1, 16)))
        self.assertEqual(list(figure.data[0].x), list(firsts['observed_on']))

    def test_combined_discovery_explains_sources_and_undated_species(self):
        firsts = pd.DataFrame({
            'observed_on': pd.to_datetime(['2025-01-01', '2025-02-02']),
            'cumulative': [1, 2], 'label': ['Wood Thrush', 'Luna Moth'],
            'source': ['eBird', 'iNaturalist'],
        })
        firsts.attrs.update(inventory_species=3, undated_species=1)
        html = viz.discovery_curve(firsts)
        self.assertIn('1 species without a usable date', html)
        self.assertIn('3 species in the combined inventory', html)
        self.assertIn('arrival or repeat frequency', html)
        self.assertIn('eBird life-list dates for birds and iNaturalist dates for other groups', html)
        self.assertIn('identification revisions', html)

    def test_discovery_with_only_undated_inventory_has_an_explanation(self):
        firsts = pd.DataFrame(columns=['observed_on', 'cumulative', 'label', 'source'])
        firsts.attrs.update(inventory_species=2, undated_species=2)
        html = viz.discovery_curve(firsts)
        self.assertIn('2 species without a usable date', html)
        self.assertIn('No dated records', html)
        self.assertIn('href="/life-list/"', html)

    def test_phenology_table_uses_raw_counts_even_when_normalized(self):
        matrix = pd.DataFrame([[0, 8] + [0] * 10, [2, 4] + [0] * 10], index=['Moth <one>', 'Moth two'], columns=range(1, 13))
        html = viz.phenology(matrix, normalize=True, dark=True)
        table = self.table(html)
        self.assertEqual(table.rows[0], ['Species', *viz.MONTHS])
        self.assertEqual(table.rows[1], ['Moth <one>', '0', '8'] + ['0'] * 10)
        self.assertIn('14 observations', html)
        self.assertIn('Moth &lt;one&gt;', html)
        self.assertNotIn('<th scope="row" class="py-2 pr-4 text-left font-normal">Moth <one>', html)

    def test_daily_values_and_average_are_distinct(self):
        html = viz.per_day(pd.DataFrame({'observed_on': pd.to_datetime(['2025-01-01', '2025-01-02']), 'observations': [3, 0], 'rolling_30d': [3., 1.5]}))
        self.assertEqual(self.table(html).rows[1:], [['2025-01-01', '3', '3.0'], ['2025-01-02', '0', '1.5']])
        self.assertIn('3 observations', html)

    def test_seasonal_table_exposes_full_distribution(self):
        agg = pd.DataFrame([dict(label='Luna moth', first_doy=100, q1=120.5, median_doy=140, q3=160.5, last_doy=190, n=8)])
        table = self.table(viz.seasonal_cascade(agg, dark=True))
        self.assertEqual(table.rows[1], ['Luna moth', '100', '120.5', '140', '160.5', '190', '8'])

    def test_rarity_preserves_counts_and_flags(self):
        stats = pd.DataFrame([dict(common_name=None, taxon_name='Actias luna', state_obs_count=25, property_obs_count=3, is_county_first=1), dict(common_name='Moth B', taxon_name='B', state_obs_count=100, property_obs_count=4, is_county_first=0)])
        table = self.table(viz.uniqueness_scatter(stats))
        self.assertEqual(table.rows[1:], [['Actias luna', '25', '3', 'Yes'], ['Moth B', '100', '4', 'No']])

    def test_observer_limit_and_extra_metrics_match_chart(self):
        board = pd.DataFrame([dict(display_name=None, user_login=f'user{i}', observations=20-i, species=i+1, unique_species=i) for i in range(16)])
        html = viz.leaderboard(board)
        table = self.table(html)
        self.assertEqual(len(table.rows), 16)
        self.assertEqual(table.rows[1], ['user0', '20', '1', '0'])
        self.assertEqual(table.rows[-1], ['user14', '6', '15', '14'])
        self.assertIn('15 of 16 observers', html)

    def test_monthly_counts_are_not_summed_as_unique_species(self):
        summary = [dict(month_name='May', species_count=8, new_species_count=3, nights_surveyed=4, survey_season=True), dict(month_name='June', species_count=8, new_species_count=2, nights_surveyed=5, survey_season=True)]
        html = viz.monthly_survey_bar(summary)
        self.assertEqual(self.table(html).rows[1:], [['May', '8', '3', '4'], ['June', '8', '2', '5']])
        self.assertIn('5 first records', html)
        self.assertNotIn('16 species', html)

    def test_moth_inventory_and_rank_tables_keep_chart_metrics(self):
        effort = pd.DataFrame({'cum_obs': [2, 5], 'cum_species': [1, 3]})
        html = viz.completeness_curve(effort, dict(estimated=7, low=4, high=10))
        self.assertEqual(self.table(html).rows[1:], [['2', '1'], ['5', '3']])
        self.assertIn('Chao2 estimate is 7', html)
        self.assertIn('4–10', html)
        html = viz.rank_abundance([9, 2, 1])
        self.assertEqual(self.table(html).rows[1:], [['1', '9'], ['2', '2'], ['3', '1']])

    def test_taxonomy_tables_use_distinct_counts(self):
        life = pd.DataFrame({'iconic_taxon': ['Aves', 'Aves', 'Insecta'], 'taxon_id': [1, 1, 2]})
        self.assertEqual(self.table(viz.taxa_bar(life)).rows[1:], [['Aves', '1'], ['Insecta', '1']])
        family = pd.DataFrame([dict(label='Silkmoths', recorded=3, region_total=8)])
        self.assertEqual(self.table(viz.family_breakdown(family)).rows[1], ['Silkmoths', '3', '8'])

    def test_missing_values_are_labeled_and_escaped(self):
        html = viz._with_data('<div>plot</div>', 'Names <&>', 'Plain <text>', ['Name', 'Count'], [('A < B', None)])
        self.assertIn('Plain &lt;text&gt;', html)
        self.assertIn('Names &lt;&amp;&gt;', html)
        self.assertEqual(TableParser(html).rows[1], ['A < B', 'Not available'])




class ChartDataPageTests(unittest.TestCase):
    def test_large_table_has_bounded_preview_and_complete_static_pages(self):
        import tempfile
        from pathlib import Path
        from src import chart_data
        rows = [(f'Species {i}', i) for i in range(213)]
        markup = viz._with_data('<div>plot</div>', 'Test & data', '213 species recorded.', ['Species', 'Count'], rows)
        with tempfile.TemporaryDirectory() as tmp:
            output = chart_data.publish_tables(markup, Path(tmp), '/moths/')
            self.assertEqual(len(TableParser(output).rows) - 1, 12)
            self.assertIn('Showing the first 12 of 213 rows', output)
            self.assertIn('Read all 213 rows', output)
            self.assertNotIn('Species 212', output)
            pages = sorted(Path(tmp).glob('chart-data/*/*.html'))
            self.assertEqual(len(pages), 3)
            all_rows = []
            for page in pages:
                html = page.read_text()
                all_rows.extend(TableParser(html).rows[1:])
                self.assertIn('href="/moths/#chart-data-', html)
                self.assertIn('Back to Moths', html)
                self.assertNotIn('<script', html)
                self.assertIn('Test &amp; data', html)
            self.assertEqual(all_rows, [[f'Species {i}', str(i)] for i in range(213)])
            self.assertIn('Next page', pages[0].read_text())
            self.assertNotIn('Previous page', pages[0].read_text())
            self.assertIn('Previous page', pages[-1].read_text())
            self.assertNotIn('Next page', pages[-1].read_text())

    def test_identical_data_has_stable_anchor_and_small_table_stays_inline(self):
        import tempfile
        from pathlib import Path
        from src import chart_data
        args = ('<div>plot</div>', 'One', 'One row', ['Name', 'Count'], [('A', 1)])
        one = viz._with_data(*args)
        self.assertEqual(one, viz._with_data(*args))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(chart_data.publish_tables(one, Path(tmp), '/'), one)
            self.assertFalse(list(Path(tmp).rglob('*.html')))

    def test_same_data_on_different_routes_keeps_correct_return_links(self):
        import tempfile
        from pathlib import Path
        from src import chart_data
        markup = viz._with_data('<div>plot</div>', 'Shared', 'Same data', ['Name', 'Count'], [(str(i), i) for i in range(15)])
        with tempfile.TemporaryDirectory() as tmp:
            for route in ('/', '/moths/'):
                chart_data.publish_tables(markup, Path(tmp), route, stylesheet='/assets/survey.css?v=abc123')
            pages = list(Path(tmp).glob('chart-data/*/*.html'))
            self.assertEqual(len(pages), 2)
            self.assertTrue(any('href="/#chart-data-' in page.read_text() for page in pages))
            self.assertTrue(any('href="/moths/#chart-data-' in page.read_text() for page in pages))
            self.assertTrue(all('survey.css?v=abc123' in page.read_text() for page in pages))


if __name__ == '__main__':
    unittest.main()
