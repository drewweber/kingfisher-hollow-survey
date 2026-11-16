"""Navigation contracts shared by rendered survey and seasonal pages."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import unittest

import report
import seasonal_pages


class Navigation(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.elements = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.links.append(attrs)
        if 'id' in attrs:
            self.elements[attrs['id']] = attrs


class NavigationAccessTests(unittest.TestCase):
    def test_every_survey_route_has_one_complete_navigation_tree(self):
        for mode, config in report.VIEW_CONFIG.items():
            with self.subTest(mode=mode):
                nav = Navigation(report.nav(mode))
                hrefs = [link['href'] for link in nav.links]
                for destination in ['/life-list/', '/field/', '/moths/', '/plants/']:
                    self.assertEqual(hrefs.count(destination), 1)
                for href, _ in config['links']:
                    # The skip link also points at the first section.
                    self.assertIn(href, hrefs)
                current = [link['href'] for link in nav.links if link.get('aria-current') == 'page']
                self.assertEqual(current, [config['route']])

    def test_no_script_and_older_browsers_start_with_visible_links(self):
        nav = Navigation(report.nav())
        menu = nav.elements['survey-menu']
        self.assertNotIn('hidden', menu)
        self.assertNotIn('hidden', menu['class'].split())
        self.assertNotIn('aria-hidden', menu)
        self.assertNotIn('popover', menu)
        self.assertIn('hidden', nav.elements['survey-menu-button'])
        self.assertEqual(nav.elements['survey-menu-button']['popovertarget'], 'survey-menu')

    def test_primary_destinations_keep_seasonal_return_context(self):
        for season in ['', *seasonal_pages.SEASONS]:
            nav = Navigation(seasonal_pages.nav(season, '/'))
            for destination in ['/life-list/', '/field/']:
                hrefs = [link['href'] for link in nav.links if urlsplit(link['href']).path == destination]
                self.assertEqual(len(hrefs), 1)
                expected = {'from': [f'/seasons/{season}/']} if season else {}
                self.assertEqual(parse_qs(urlsplit(hrefs[0]).query), expected)

    def test_nonmodal_index_does_not_lock_page_scrolling(self):
        styles = (Path(report.__file__).parent / 'src/styles.css').read_text()
        self.assertNotIn('body.survey-menu-open', styles)
        self.assertIn('100dvh - var(--survey-nav-bottom', styles)
        script = report.scripts('all')
        self.assertIn("'popover' in HTMLElement.prototype", script)
        self.assertIn("addEventListener('focusout'", script)
        self.assertNotIn("min-width: 1536px", script)


if __name__ == '__main__':
    unittest.main()
