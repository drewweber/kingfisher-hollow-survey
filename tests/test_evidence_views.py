import unittest
from datetime import date, datetime, timezone
from unittest import mock

import pandas as pd
import report
import natural_history


class EvidenceViewsTests(unittest.TestCase):
    def test_bird_life_list_renders_unknown_history_and_checklist(self):
        life = pd.DataFrame([dict(label='Example bird', taxon_name='Avis example',
              group='Birds', family_name='', taxon_id=-9, list_number=1,
              observations=pd.NA, first_seen=pd.Timestamp('2026-08-01'), first_observed_at=pd.NaT, last_seen=pd.NaT,
              repeat_history_known=False, source='eBird', source_url='https://ebird.org/checklist/S123')])
        html = report.life_list_body(life)
        self.assertIn('https://ebird.org/checklist/S123', html)
        self.assertIn('Life-list date', html)
        self.assertNotIn('>NaT<', html)
        self.assertNotIn('>nan<', html)

    def test_bird_missing_checklist_and_metadata_still_renders(self):
        life = pd.DataFrame([dict(label='Example bird', taxon_name=pd.NA,
              group='Birds', family_name=pd.NA, taxon_id=-9, list_number=1,
              observations=pd.NA, first_seen=pd.Timestamp('2026-08-01'), first_observed_at=pd.NaT, last_seen=pd.NaT,
              repeat_history_known=False, source='eBird', source_url=pd.NA)])
        html = report.life_list_body(life)
        self.assertIn('Example bird', html)
        self.assertNotIn('&lt;NA&gt;', html)

    def test_fungi_dates_and_recent_counts_use_eligible_inventory(self):
        rows = pd.DataFrame([
            dict(id=1,taxon_id=2,taxon_name='Test fungus',iconic_taxon='Fungi',rank='species',captive=0,observed_on='2026-11-02'),
            dict(id=2,taxon_id=3,taxon_name='Cultivated',iconic_taxon='Fungi',rank='species',captive=1,observed_on='2026-11-03'),
            dict(id=3,taxon_id=None,taxon_name='Unresolved',iconic_taxon='Fungi',rank='genus',captive=0,observed_on='2026-11-04'),
        ])
        html = report.fungi_view(rows)
        self.assertIn('Nov 2, 2026', html)
        self.assertIn('Nov 4, 2026', html)
        self.assertNotIn('Cultivated', html)
        empty = pd.DataFrame(columns=['taxon_id'])
        with mock.patch.multiple(report.analyze, **{name: mock.Mock(return_value=empty) for name in
             ('load_butterflies','load_odonates','load_mammals','load_plants','load_amphibians','load_reptiles')}):
            recent = report.taxa_page_recent_species(rows.assign(observed_on=pd.to_datetime(rows.observed_on)), birds=empty,moths=empty,as_of=date(2026,11,11))
        self.assertEqual(recent['fungi'], 1)

    def test_herp_reference_photo_does_not_imply_local_voucher(self):
        found = pd.DataFrame([dict(taxon_id=2,label='Example frog',taxon_name='Example frog',ref_count=1,photo_url='https://example.org/reference.jpg')])
        html = report.amphibian_found_body(found, [dict(id=4,taxon_id=2,quality_grade='needs_id',url='https://www.inaturalist.org/observations/4')])
        self.assertIn('species reference photos', html)
        self.assertIn('1 local records · 0 with photos · 0 research grade', html)
        self.assertIn('https://www.inaturalist.org/observations/4', html)

    def test_missing_bird_export_does_not_create_zero_inventory_or_false_gaps(self):
        with mock.patch.object(report.analyze, 'load_birds', return_value=pd.DataFrame()), mock.patch.object(report.analyze, 'bird_gap_from_ebird_barcharts') as gap:
            html = report.birds_view()
        gap.assert_not_called()
        self.assertIn('Snapshot unavailable', html)
        self.assertIn('local gap candidates cannot be selected', html)
        self.assertNotIn('0 species are recorded', html)

    def test_log_window_label_uses_the_counting_timezone(self):
        totals = {key:1 for key,value in report.VIEW_CONFIG.items() if value.get('taxa_group')}
        html = report.log_taxa_stats_panel(totals, {key:0 for key in totals}, datetime(2026,11,12,2,tzinfo=timezone.utc))
        self.assertIn('Window ends Nov 11, 2026', html)

    def test_valid_no_go_forecast_does_not_look_like_outage(self):
        with mock.patch.object(report.analyze, 'rank_moth_forecast', return_value=[
                dict(date='2026-11-12', rating='Skip', priority_rank=None)]):
            html = report.moth_forecast_body({'nights': [{}]}, {})
        self.assertIn('No suitable nights', html)
        self.assertNotIn('temporarily unavailable', html)

    def test_empty_fungi_view_has_no_invented_record_or_image(self):
        html = report.fungi_view(pd.DataFrame())
        self.assertIn('No fungal records', html)
        self.assertNotIn('<img ', html)

    def test_season_is_calendar_guidance_not_claim_of_recent_observations(self):
        for month, expected in [(1,'winter'), (3,'spring'), (6,'summer'), (9,'autumn'), (12,'winter')]:
            self.assertEqual(natural_history.seasonal_context(date(2026,month,1))['key'], expected)
        html = report.seasonal_body([], set(), date(2026,11,11))
        self.assertIn('November', html)
        self.assertIn('Seasonal guide', html)
        self.assertNotIn('Observed this week', html)


if __name__ == '__main__':
    unittest.main()
