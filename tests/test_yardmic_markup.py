import unittest
from html.parser import HTMLParser
from unittest import mock
import pandas as pd
import report


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.elements = []; self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class YardMicMarkupTests(unittest.TestCase):
    def test_microphone_leads_birds_page_without_replacing_ebird_inventory(self):
        with mock.patch.object(report.analyze, 'load_birds', return_value=pd.DataFrame()), mock.patch.object(report.bird_routes, 'load', return_value=None), mock.patch.object(report, 'bird_route_use_body', return_value=''):
            html = report.birds_view()
        nodes = Elements(html).elements
        ids = [attrs['id'] for _, attrs in nodes if 'id' in attrs]
        self.assertIn('bird-microphone', ids)
        self.assertLess(ids.index('bird-microphone'), ids.index('bird-inventory'))
        self.assertIn('Recently heard', html)
        self.assertIn('Last Belted Kingfisher detected', html)
        self.assertNotIn('One fixed microphone', html)
        self.assertIn('Patterns at the', html)
        self.assertIn('eBird', html)
        self.assertIn('<noscript>', html)
        self.assertNotIn('YARDMIC_API_KEY', html)
        self.assertNotIn('10:56', html)
        self.assertTrue(any(tag == 'button' and 'data-yardmic-refresh' in attrs for tag, attrs in nodes))

    def test_microphone_script_only_loads_on_birds_route(self):
        self.assertIn('/assets/yardmic.js', report.scripts('birds'))
        for mode in report.VIEW_CONFIG:
            if mode != 'birds':
                self.assertNotIn('/assets/yardmic.js', report.scripts(mode))

    def test_navigation_names_microphone_patterns_and_ebird_separately(self):
        links = dict(report.VIEW_CONFIG['birds']['links'])
        self.assertIn('#bird-microphone-patterns', links)
        self.assertIn('#bird-inventory', links)


if __name__ == '__main__':
    unittest.main()
