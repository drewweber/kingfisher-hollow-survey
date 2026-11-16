"""Observer comparisons preserve totals, low counts, and every contributor."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import analyze
from src import viz


class ObserverComparisonTests(unittest.TestCase):
    def chart(self, board):
        with patch.object(viz, '_html', return_value='<plot>') as render:
            html = viz.leaderboard(board)
        return render.call_args.args[0], html

    def test_total_species_include_shared_species_and_ignore_repeat_records(self):
        records = pd.DataFrame([
            dict(id=1, user_login='alice', user_name='Alice', taxon_id=10),
            dict(id=2, user_login='alice', user_name='Alice', taxon_id=10),
            dict(id=3, user_login='alice', user_name='Alice', taxon_id=20),
            dict(id=4, user_login='bob', user_name='Bob', taxon_id=10),
        ])
        board = analyze.observer_leaderboard(records)
        alice = board.set_index('user_login').loc['alice']
        self.assertEqual((alice.observations, alice.species, alice.unique_species), (3, 2, 1))
        fig, html = self.chart(board)
        self.assertEqual(list(fig.data[0].x), [2, 1])
        self.assertEqual(list(fig.data[1].x), [3, 1])
        self.assertIn('Total species', html)
        self.assertIn('Species recorded only by this observer', html)

    def test_all_observers_keep_exact_counts_and_readable_names(self):
        board = pd.DataFrame([dict(display_name=None, user_login=f'user{i:02}', observations=1000000 if i == 0 else 1, species=1, unique_species=0) for i in range(20)])
        fig, html = self.chart(board)
        self.assertEqual(len(fig.data[0].x), 20)
        self.assertEqual(len(fig.data[1].x), 20)
        self.assertIn('user19', html)
        labels = ''.join(fig.layout.yaxis.ticktext)
        self.assertIn('1,000,000 observations', labels)
        self.assertIn('1 species', labels)
        self.assertEqual(fig.layout.xaxis.type, 'log')
        self.assertTrue(all(trace.type == 'scatter' and trace.mode == 'markers' for trace in fig.data))
        self.assertNotEqual(fig.data[0].marker.symbol, fig.data[1].marker.symbol)
        self.assertIn('logarithmic', html)

    def test_zero_is_not_plotted_as_one_and_duplicate_names_keep_separate_rows(self):
        board = pd.DataFrame([
            dict(display_name='Same <name>', user_login='z', observations=10, species=0, unique_species=0),
            dict(display_name='Same <name>', user_login='a', observations=1, species=1, unique_species=0),
        ])
        fig, html = self.chart(board)
        self.assertEqual(list(fig.data[0].x), [1, None])
        self.assertEqual(len(set(fig.layout.yaxis.tickvals)), 2)
        self.assertIn('0 species', ''.join(fig.layout.yaxis.ticktext))
        self.assertIn('Same &lt;name&gt;', html)
        self.assertIn('Zero counts', html)
        self.assertIn('not plotted', html)

    def test_empty_and_all_zero_counts_have_valid_fallbacks(self):
        self.assertIn('No observers', viz.leaderboard(pd.DataFrame()))
        board = pd.DataFrame([dict(display_name='Zero', user_login='zero', observations=0, species=0, unique_species=0)])
        fig, html = self.chart(board)
        self.assertEqual(list(fig.data[0].x), [None])
        self.assertEqual(list(fig.data[1].x), [None])
        self.assertLess(fig.layout.xaxis.range[0], fig.layout.xaxis.range[1])
        self.assertIn('0 observations', ''.join(fig.layout.yaxis.ticktext))


if __name__ == '__main__':
    unittest.main()
