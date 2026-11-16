"""Confirmed property evidence must agree across inventory and gap views."""
import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
import analyze
import db
import public_api
import report
import curated_observations as curated
import inventory
import stats


class CuratedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache_path = Path(self.temp.name) / 'cache.json'
        manifest_path = Path(self.temp.name) / 'manifest.json'
        manifest_path.write_text((ROOT / 'data/reference/confirmed-property-observations.json').read_text())
        manifest_patch = patch.object(curated, 'MANIFEST_PATH', manifest_path)
        manifest_patch.start()
        self.addCleanup(manifest_patch.stop)
        cache_patch = patch.object(curated, 'CACHE_PATH', self.cache_path)
        cache_patch.start()
        self.addCleanup(cache_patch.stop)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA)
        self.conn.execute(
            "INSERT INTO region_reptile_taxa (taxon_id,taxon_name,common_name,region_count) "
            "VALUES (39865,'Glyptemys insculpta','Wood Turtle',106)")
        self.addCleanup(self.conn.close)
        self.patcher = patch.object(analyze, 'connect', self.connection)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    @contextmanager
    def connection(self):
        yield self.conn

    def test_confirmed_record_reaches_inventory_roster_api_csv_and_accumulation(self):
        observations = analyze.load_property()
        self.assertEqual(observations['taxon_id'].tolist(), [39865])
        life = analyze.life_list(observations)
        self.assertEqual(life['label'].tolist(), ['Wood Turtle'])
        self.assertEqual(life.iloc[0]['source'], 'iNaturalist')
        self.assertEqual(life.iloc[0]['source_url'], 'https://www.inaturalist.org/observations/371959757')
        self.assertEqual(life.iloc[0]['observations'], 1)
        self.assertEqual(life.iloc[0]['family_name'], 'Emydidae')
        self.assertEqual(analyze.summary(observations)['species'], 1)
        self.assertEqual(analyze.firsts_timeline(observations)['cumulative'].tolist(), [1])
        reptiles = analyze.load_reptiles()
        self.assertEqual(reptiles['taxon_id'].tolist(), [39865])
        self.assertTrue(analyze.reptile_gap(reptiles)['missing'].empty)
        summary = public_api.summary_from_connection(
            self.conn, birds=pd.DataFrame(), updated_at='2026-11-16T00:00:00Z')
        self.assertEqual(summary['totalSpecies'], 1)
        rows = list(csv.DictReader(io.StringIO(report.life_list_csv(life))))
        self.assertEqual(rows[0]['Name'], 'Wood Turtle')
        self.assertEqual(rows[0]['Source URL'], life.iloc[0]['source_url'])
        self.assertEqual(rows[0]['Property evidence'], 'Confirmed by property owner')
        self.assertIn('Wood Turtle', report.reptile_found_body(analyze.reptile_found(observations, reptiles)))
        self.assertTrue(analyze.load_stats().empty)

    def add_project_record(self, oid=371959757, tid=39865):
        self.conn.execute(
            'INSERT INTO property_obs (id,taxon_id,taxon_name,common_name,iconic_taxon,rank,'
            'observed_on,created_at,observed_at,url,latitude,longitude) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (oid, tid, 'Glyptemys insculpta', 'Wood Turtle', 'Reptilia', 'species',
             '2026-06-15', '2026-06-15', '2026-06-15T08:24:55-04:00',
             f'https://www.inaturalist.org/observations/{oid}', 42.1, -76.1))

    def test_upstream_overlap_deduplicates_records_and_roster_counts_and_removes_coordinates(self):
        self.add_project_record()
        self.conn.execute("INSERT INTO reptile_taxa (taxon_id,taxon_name,common_name,obs_count) VALUES (39865,'Glyptemys insculpta','Wood Turtle',1)")
        observations = analyze.load_property()
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[['latitude', 'longitude']].isna().all().all())
        self.assertEqual(analyze.life_list(observations).iloc[0]['observations'], 1)
        self.assertEqual(analyze.load_reptiles().iloc[0]['obs_count'], 1)
        self.assertEqual(public_api.summary_from_connection(self.conn, birds=pd.DataFrame(), updated_at='2026-11-16T00:00:00Z')['totalSpecies'], 1)

    def test_project_rows_keep_source_and_history_when_combined_with_confirmation(self):
        self.add_project_record(11, 39682)
        rows = analyze.load_property()
        self.assertTrue(rows['repeat_history_known'].all())
        self.assertEqual(rows['source'].tolist(), ['iNaturalist', 'iNaturalist'])
        self.assertEqual(rows['source_url'].nunique(), 2)
        self.assertEqual(analyze.summary(rows)['observations'], 2)

    def test_cached_deletion_does_not_restore_offline_snapshot_or_stale_project_row(self):
        self.add_project_record()
        self.conn.execute("INSERT INTO reptile_taxa (taxon_id,taxon_name,obs_count) VALUES (39865,'Glyptemys insculpta',1)")
        with patch.object(curated.inat_api, 'fetch_observations', return_value=[]), \
                patch.object(curated.inat_api, 'fetch_taxa', return_value=[]):
            curated.refresh()
        self.assertTrue(analyze.load_property().empty)
        self.assertTrue(analyze.load_reptiles().empty)
        self.assertEqual(analyze.reptile_gap(analyze.load_reptiles())['missing']['taxon_id'].tolist(), [39865])

    def test_latest_coarse_identification_cannot_resurrect_species(self):
        old = dict(curated.manifest()[0]['snapshot'])
        old.update(taxon_id=39863, taxon_name='Glyptemys', common_name=None, rank='genus')
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': old}}))
        self.assertTrue(analyze.load_property().empty)
        self.assertTrue(analyze.load_reptiles().empty)
        self.assertEqual(analyze.load_property(species_only=False).iloc[0]['rank'], 'genus')

    def test_finer_identification_uses_same_canonical_species_in_roster_and_inventory(self):
        self.add_project_record()
        self.conn.execute("INSERT INTO reptile_taxa (taxon_id,taxon_name,obs_count) VALUES (39865,'Glyptemys insculpta',1)")
        newer = dict(curated.manifest()[0]['snapshot'])
        newer.update(taxon_id=999, taxon_name='Glyptemys insculpta example', rank='subspecies')
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': newer}}))
        self.assertEqual(analyze.load_property()['taxon_id'].tolist(), [39865])
        self.assertEqual(analyze.load_reptiles()['taxon_id'].tolist(), [39865])
        self.assertTrue(analyze.reptile_gap(analyze.load_reptiles())['missing'].empty)

    def test_captive_correction_withdraws_confirmed_wild_property_record_consistently(self):
        newer = dict(curated.manifest()[0]['snapshot'], captive=True)
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': newer}}))
        self.assertTrue(analyze.load_property().empty)
        self.assertTrue(analyze.load_reptiles().empty)
        summary = public_api.summary_from_connection(self.conn, birds=pd.DataFrame(), updated_at='2026-11-16T00:00:00Z')
        self.assertEqual(summary['totalSpecies'], 0)

    def test_newer_manifest_snapshot_supersedes_older_restored_cache_status(self):
        self.cache_path.write_text(json.dumps({'371959757': {'checked_at':'2020-01-01T00:00:00Z','snapshot':None}}))
        self.assertEqual(analyze.load_property()['taxon_id'].tolist(), [39865])

    def test_refresh_and_cache_allowlist_strip_all_location_fields(self):
        public = {
            'id': 371959757, 'location': 'sensitive', 'latitude': 42.1,
            'longitude': -76.1, 'private_location': 'secret',
            'description': 'private address', 'place_guess': 'private address',
            'geojson': {'coordinates': [-76.1, 42.1]},
            'taxon': {'id': 39865, 'name': 'Glyptemys insculpta', 'rank': 'species'},
        }
        safe = curated.sanitize(public)
        for key in ('location', 'latitude', 'longitude', 'private_location', 'description', 'place_guess', 'geojson'):
            self.assertNotIn(key, safe)
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': {**safe, **{'latitude':42.1, 'private_location':'secret'}}}}))
        loaded = curated.records()[371959757]
        self.assertNotIn('latitude', loaded)
        self.assertNotIn('private_location', loaded)

    def test_transport_failure_preserves_latest_cached_status(self):
        import requests
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': None}}))
        with patch.object(curated.inat_api, 'fetch_observations', side_effect=requests.ConnectionError('offline')):
            with self.assertRaises(requests.ConnectionError):
                curated.refresh()
        self.assertIsNone(curated.records()[371959757])

    def test_removing_confirmation_removes_offline_supplement(self):
        with patch.object(curated, 'manifest', return_value=[]):
            self.assertTrue(analyze.load_property().empty)
            self.assertTrue(analyze.load_reptiles().empty)

    def test_withdrawn_supplement_preserves_independent_project_evidence(self):
        self.add_project_record(12)
        self.conn.execute("INSERT INTO reptile_taxa (taxon_id,taxon_name,obs_count) VALUES (39865,'Glyptemys insculpta',1)")
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': None}}))
        self.assertEqual(analyze.load_property()['id'].tolist(), [12])
        self.assertEqual(analyze.load_reptiles()['taxon_id'].tolist(), [39865])
        self.assertTrue(analyze.reptile_gap(analyze.load_reptiles())['missing'].empty)

    def test_finer_record_without_project_parent_uses_public_species_ancestor(self):
        newer = dict(curated.manifest()[0]['snapshot'])
        newer.update(taxon_id=999, taxon_name='Glyptemys insculpta example', rank='subspecies')
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': newer}}))
        self.assertEqual(analyze.load_property()['taxon_id'].tolist(), [39865])
        self.assertEqual(analyze.load_reptiles()['taxon_id'].tolist(), [39865])
        self.assertEqual(analyze.life_list(analyze.load_property()).iloc[0]['family_name'], 'Emydidae')

    def test_finer_identification_in_both_sources_does_not_double_roster_count(self):
        self.add_project_record()
        self.conn.execute("UPDATE property_obs SET taxon_id=999, taxon_name='Glyptemys insculpta example', rank='subspecies'")
        self.conn.execute("INSERT INTO reptile_taxa (taxon_id,taxon_name,obs_count) VALUES (39865,'Glyptemys insculpta',1)")
        newer = dict(curated.manifest()[0]['snapshot'])
        newer.update(taxon_id=999, taxon_name='Glyptemys insculpta example', rank='subspecies')
        self.cache_path.write_text(json.dumps({'371959757': {'snapshot': newer}}))
        self.assertEqual(analyze.load_reptiles().iloc[0]['obs_count'], 1)
        self.assertEqual(len(analyze.load_property()), 1)

    def test_curated_species_does_not_inherit_old_comparison_claims(self):
        self.conn.execute("INSERT INTO species_stats (taxon_id,is_county_first,state_obs_count) VALUES (39865,1,1)")
        self.assertTrue(analyze.load_stats().empty)
        self.assertEqual(stats._stale_or_missing(self.conn), [])

    def test_other_confirmed_group_uses_same_roster_and_public_summary(self):
        mammal = dict(curated.records()[371959757])
        mammal.update(id=123, taxon_id=456, taxon_name='Example mammal', iconic_taxon='Mammalia', ancestor_ids=[40151])
        with patch.object(curated, 'records', return_value={123: mammal}):
            self.assertEqual(analyze.load_mammals()['taxon_id'].tolist(), [456])
            summary = public_api.summary_from_connection(self.conn, birds=pd.DataFrame(), updated_at='2026-11-16T00:00:00Z')
            self.assertEqual(summary['mammals'], 1)
            self.assertEqual(summary['totalSpecies'], 1)


if __name__ == '__main__':
    unittest.main()
