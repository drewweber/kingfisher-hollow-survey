"""Regression coverage for subspecies being counted as extra moth species."""
import sqlite3
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import analyze
import db
import public_api


class InventoryCountsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA)
        self.add_observation(1, 60607, 'Limenitis arthemis', 'species')
        self.add_observation(2, 58585, 'Limenitis arthemis astyanax', 'subspecies')
        self.add_observation(3, 235550, 'Danaus plexippus plexippus', 'subspecies')
        self.add_observation(4, 47916, 'Actias luna', 'species')
        self.conn.executemany(
            'INSERT INTO butterfly_taxa (taxon_id, taxon_name) VALUES (?, ?)',
            [(60607, 'Limenitis arthemis'), (48662, 'Danaus plexippus')])
        self.conn.execute("INSERT INTO moth_taxa (taxon_id, taxon_name) VALUES (47916, 'Actias luna')")
        for tid in (60607, 58585, 235550, 48662, 47916):
            self.conn.execute('INSERT INTO taxon_meta (taxon_id, order_name, order_common) VALUES (?, ?, ?)',
                              (tid, 'Lepidoptera', 'Butterflies and Moths'))
        self.patcher = patch.object(analyze, 'connect', self.connection)
        self.patcher.start()

    @contextmanager
    def connection(self):
        yield self.conn

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def add_observation(self, oid, tid, name, rank):
        self.conn.execute('INSERT INTO property_obs (id,taxon_id,taxon_name,iconic_taxon,rank,observed_on,observed_at,created_at,url) VALUES (?,?,?,?,?,?,?,?,?)',
                          (oid,tid,name,'Insecta',rank,'2026-07-01','2026-07-01T21:00:00-04:00','2026-07-02',f'https://www.inaturalist.org/observations/{oid}'))

    def test_life_list_and_rosters_have_identical_species_membership(self):
        observations = analyze.load_property()
        life = analyze.life_list(observations)
        self.assertEqual(set(life.loc[life.group == 'Moths', 'taxon_id']), {47916})
        self.assertEqual(set(life.loc[life.group == 'Butterflies', 'taxon_id']), {60607, 48662})
        self.assertEqual(analyze.summary(observations)['species'], 3)
        self.assertEqual(len(observations), 4)  # No evidence is discarded.
        self.assertEqual(life.set_index('taxon_id').loc[60607, 'observations'], 2)
        self.assertEqual(observations.loc[observations.id == 2, 'url'].iloc[0], 'https://www.inaturalist.org/observations/2')
        raw = analyze.load_property(species_only=False)
        self.assertEqual(raw.loc[raw.id == 2, 'taxon_id'].iloc[0], 58585)
        self.assertEqual(raw.loc[raw.id == 2, 'rank'].iloc[0], 'subspecies')

    def test_public_summary_uses_the_same_species_identity(self):
        result = public_api.summary_from_connection(self.conn, birds=pd.DataFrame(), updated_at='2026-07-02T00:00:00Z')
        self.assertEqual(result['totalSpecies'], 3)
        self.assertEqual(result['moths'], 1)
        self.assertEqual(result['butterflies'], 2)

    def test_unknown_lepidoptera_is_not_assumed_to_be_a_moth(self):
        label = analyze.group_labeler(set(), set(), {9: 'Butterflies and Moths'})
        self.assertEqual(label(9, 'Insecta'), 'Butterflies and Moths')

    def test_unmatched_subspecies_and_hybrids_remain_separate(self):
        self.add_observation(5, 9, 'Limenitis arthemis × Limenitis archippus', 'hybrid')
        self.add_observation(6, 10, 'Unknown species minor', 'subspecies')
        self.add_observation(7, 11, 'Limenitis arthemisia minor', 'subspecies')
        observations = analyze.load_property()
        self.assertTrue({9, 10, 11}.issubset(set(observations.taxon_id)))
        self.assertEqual(len(observations), 7)

    def test_moth_api_keeps_descendant_observations_under_parent_species(self):
        self.add_observation(5, 100, 'Actias luna minor', 'subspecies')
        self.conn.execute("UPDATE taxon_meta SET family_name='Saturniidae' WHERE taxon_id=47916")
        self.conn.execute("INSERT INTO taxon_meta (taxon_id, order_name, family_name) VALUES (100, 'Lepidoptera', 'Saturniidae')")
        snapshot = public_api.snapshot_from_connection(self.conn)
        self.assertEqual(snapshot['observation_count'], 2)
        self.assertEqual(snapshot['species_count'], 1)
        self.assertEqual({row['taxon_id'] for row in snapshot['observations']}, {47916})
        self.assertEqual({row['observation_id'] for row in snapshot['observations']}, {4, 5})

    def test_build_guard_rejects_equal_counts_with_different_membership(self):
        life = analyze.life_list(analyze.load_property())
        analyze.validate_inventory_counts(life)
        life.loc[life.group == 'Moths', 'taxon_id'] = 999
        with self.assertRaisesRegex(ValueError, 'Moths.*999'):
            analyze.validate_inventory_counts(life)

    def test_build_guard_rejects_api_total_disagreement(self):
        life = analyze.life_list(analyze.load_property())
        with self.assertRaisesRegex(ValueError, 'totalSpecies'):
            analyze.validate_inventory_counts(life, {'totalSpecies': 4, 'moths': 1, 'butterflies': 2})

    def test_ambiguous_parent_name_does_not_merge_identifications(self):
        self.conn.execute("INSERT INTO butterfly_taxa (taxon_id, taxon_name) VALUES (999, 'Limenitis arthemis')")
        observations = analyze.load_property()
        self.assertIn(58585, set(observations.taxon_id))

    def test_parent_without_cached_metadata_keeps_child_family(self):
        self.conn.execute('DELETE FROM taxon_meta WHERE taxon_id=48662')
        self.conn.execute("UPDATE taxon_meta SET family_name='Nymphalidae' WHERE taxon_id=235550")
        life = analyze.life_list(analyze.load_property()).set_index('taxon_id')
        self.assertEqual(life.loc[48662, 'family_name'], 'Nymphalidae')
        self.assertEqual(life.loc[48662, 'group'], 'Butterflies')

    def test_combined_chronology_counts_overlapping_birds_once(self):
        # iNaturalist birds are excluded by the canonical inventory loader,
        # including a name that does not match eBird's current taxonomy.
        self.add_observation(8, 200, 'Hylocichla mustelina', 'species')
        self.add_observation(9, 201, 'Old bird synonym', 'species')
        self.conn.execute("UPDATE property_obs SET iconic_taxon='Aves' WHERE id IN (8,9)")
        birds = pd.DataFrame([
            dict(taxon_order=200, common_name='Wood Thrush', taxon_name='Hylocichla mustelina', date='2026-05-01', sub_id='S1'),
            dict(taxon_order=None, common_name='Unknown order', taxon_name='Unmatched name', date='2026-05-02', sub_id='S2'),
            dict(taxon_order=None, common_name='Undated bird', taxon_name='Another name', date=None, sub_id='S3'),
        ])
        combined = analyze.overview_observations(analyze.load_property(), birds)
        life = analyze.life_list(combined)
        firsts = analyze.firsts_timeline(combined)
        self.assertEqual(len(life), 6)
        self.assertEqual(firsts.cumulative.tolist(), [1, 2, 3, 4, 5])
        self.assertEqual(firsts.source.tolist()[:2], ['eBird', 'eBird'])
        self.assertEqual(firsts.observed_on.iloc[0], pd.Timestamp('2026-05-01'))
        self.assertEqual(set(firsts.taxon_id), set(life.loc[life.first_seen.notna(), 'taxon_id']))
        self.assertNotIn(200, set(firsts.taxon_id))
        self.assertNotIn(201, set(firsts.taxon_id))
        self.assertEqual(firsts.attrs['inventory_species'], 6)
        self.assertEqual(firsts.attrs['undated_species'], 1)

    def test_uniqueness_eligibility_preserves_original_identification_ids(self):
        self.assertEqual(analyze.species_taxon_ids(), {60607, 58585, 235550, 47916})

    def test_child_uniqueness_keeps_its_own_identity_and_photo_evidence(self):
        self.conn.execute("UPDATE property_obs SET photo_url='https://example.org/child.jpg' WHERE taxon_id=235550")
        self.conn.execute("INSERT INTO species_stats (taxon_id,taxon_name,common_name,state_obs_count,county_obs_count,is_county_first) VALUES (235550,'Danaus plexippus plexippus','Monarch subspecies',7,2,1)")
        evidence = analyze.load_property(canonical_species=False)
        stats = analyze.load_stats()
        for finder in (analyze.county_first_showcase, analyze.rarest_finds):
            result = finder(evidence, stats).iloc[0]
            self.assertEqual(result.taxon_id, 235550)
            self.assertEqual(result.taxon_name, 'Danaus plexippus plexippus')
            self.assertEqual(result.photo_url, 'https://example.org/child.jpg')
            self.assertEqual(result.state_obs_count, 7)
        recent = analyze.whats_new(evidence, stats).set_index('taxon_id')
        self.assertEqual(recent.loc[235550, 'state_obs_count'], 7)
        self.assertNotIn(48662, recent.index)

    def test_child_rarity_is_not_reassigned_to_species_in_moth_showcase(self):
        self.add_observation(5, 100, 'Actias luna minor', 'subspecies')
        self.conn.execute("INSERT INTO species_stats (taxon_id,state_obs_count,county_obs_count,is_county_first) VALUES (100,1,1,1)")
        moths = analyze.load_moths()
        result = analyze.moth_highlights(moths, analyze.load_stats(), df=analyze.load_property())
        self.assertTrue(pd.isna(result.iloc[0].state_obs_count))
        self.assertEqual(result.iloc[0].taxon_id, 47916)

    def test_raw_evidence_groups_recognize_known_butterfly_descendants(self):
        evidence = analyze.add_group_column(analyze.load_property(canonical_species=False)).set_index('taxon_id')
        self.assertEqual(evidence.loc[235550, 'group'], 'Butterflies')
        self.assertEqual(evidence.loc[58585, 'group'], 'Butterflies')


if __name__ == '__main__':
    unittest.main()
