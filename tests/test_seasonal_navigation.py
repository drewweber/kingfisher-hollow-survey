import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import report


class SeasonalJourneyNavigationTests(unittest.TestCase):
    def test_overview_seasons_open_matching_chapters(self):
        html = report.seasonal_body([], set(), date(2026, 11, 11))
        for season in ('spring', 'summer', 'autumn', 'winter'):
            self.assertIn(f'href="/seasons/{season}/"', html)
        self.assertIn('href="/seasons/"', html)
        self.assertNotIn('href="/fungi/"', html)
        self.assertNotIn('href="/herps/"', html)
        self.assertNotIn('different season than', html)

    def test_every_specialist_page_offers_seasons_and_contextual_return(self):
        for mode in report.VIEW_CONFIG:
            html = report.nav(mode)
            self.assertIn('href="/seasons/"', html)
            self.assertIn('id="seasonal-return"', html)


if __name__ == '__main__':
    unittest.main()
