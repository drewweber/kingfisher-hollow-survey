import csv
import io
import unittest

import pandas as pd

import report


class InventoryExportTests(unittest.TestCase):
    def inventory(self, count=205):
        return pd.DataFrame([dict(
            label=f'Species {i}', taxon_name=f'Scientific {i}', group='Moths',
            family_name='Saturniidae', taxon_id=i + 1, observations=2,
            first_seen=pd.Timestamp('2026-08-01'), first_observed_at=pd.NaT,
            last_seen=pd.Timestamp('2026-08-03'), source='iNaturalist',
            source_url=f'https://www.inaturalist.org/observations/{i + 1}',
            repeat_history_known=True,
        ) for i in range(count)])

    def test_complete_ssr_and_export_include_every_record_past_the_first_page(self):
        life = self.inventory()
        html = report.life_list_body(life)
        content = report.life_list_csv(life)
        rows = list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(205, html.count('class="ll-row"'))
        self.assertEqual(205, len(rows))
        self.assertEqual('Species 204', rows[0]['Name'])
        self.assertEqual('Species 0', rows[-1]['Name'])
        self.assertEqual('1', rows[-1]['List number'])
        self.assertEqual('https://www.inaturalist.org/observations/1', rows[-1]['Source URL'])
        self.assertEqual('Saturniidae', rows[-1]['Family'])
        self.assertEqual('2026-08-03', rows[-1]['Last seen'])
        self.assertIn(f'/life-list/{report.inventory_csv_filename(content)}', html)
        self.assertIn('id="ll-pagination" aria-label="Inventory pages" hidden', html)
        self.assertEqual(205, html.count('class="ll-mobile-details"'))

    def test_export_quotes_names_and_preserves_unknown_bird_history(self):
        life = self.inventory(2)
        life.loc[0, 'label'] = 'A "quoted",\nname'
        life.loc[1, ['label', 'taxon_name', 'source', 'source_url', 'repeat_history_known']] = [
            '=HYPERLINK("unsafe")', 'Bird', 'eBird', 'https://ebird.org/checklist/S123', False]
        life.loc[1, 'observations'] = pd.NA
        life.loc[1, 'last_seen'] = pd.NaT
        rows = list(csv.DictReader(io.StringIO(report.life_list_csv(life))))
        self.assertEqual('A "quoted",\nname', rows[1]['Name'])
        self.assertEqual('\'=HYPERLINK("unsafe")', rows[0]['Name'])
        self.assertEqual('', rows[0]['Records'])
        self.assertEqual('', rows[0]['Last seen'])
        self.assertEqual('False', rows[0]['Repeat history known'])
        self.assertEqual('eBird', rows[0]['Source'])
        self.assertEqual('https://ebird.org/checklist/S123', rows[0]['Source URL'])
        self.assertEqual('2026-08-01', rows[0]['Record date'])

    def test_export_fingerprint_changes_with_data_and_neutralizes_formula_prefixes(self):
        life = self.inventory(6)
        names = ['=name', '+name', '-name', '@name', '\tname', '  =name']
        life['label'] = names
        first = report.life_list_csv(life)
        rows = list(csv.DictReader(io.StringIO(first)))
        self.assertTrue(all(row['Name'].startswith("'") for row in rows))
        life.loc[0, 'label'] = 'Changed name'
        second = report.life_list_csv(life)
        self.assertNotEqual(report.inventory_csv_filename(first), report.inventory_csv_filename(second))
        self.assertEqual(report.inventory_csv_filename(first), report.inventory_csv_filename(first))


    def test_missing_bird_source_links_never_become_synthetic_inaturalist_urls(self):
        life = self.inventory(3)
        life.loc[0, ['taxon_id', 'source', 'source_url', 'repeat_history_known']] = [-900001701, 'eBird', None, False]
        life.loc[1, ['source', 'source_url', 'repeat_history_known']] = ['eBird', None, False]
        life.loc[2, 'source_url'] = None
        rows = {row['Name']: row for row in csv.DictReader(io.StringIO(report.life_list_csv(life)))}
        self.assertEqual('', rows['Species 0']['Source URL'])
        self.assertEqual('', rows['Species 1']['Source URL'])
        self.assertEqual('https://www.inaturalist.org/taxa/3', rows['Species 2']['Source URL'])
