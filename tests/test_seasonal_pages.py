import re
import sys
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import seasonal_pages


def chapter(key='winter'):
    return dict(key=key, label=key.title(), months='December–February', month_numbers=[12, 1, 2],
        route=f'/seasons/{key}/', title='The quiet evidence', intro='Look closely & listen.', framing='Dates describe encounters, not abundance.',
        passages=[dict(id='winter-early', phase='Early winter', phase_month=12, photo_record_id=1, title='Read the branches', body='A <careful> look.', look_for='Keep a dated note.', row_ids=['pine'])],
        rows=[dict(id='pine', taxon_id=1, name='Pine & fir', group='Plants', record_type='Unspecified encounter', interpretation='Two documented winters.', years=['2024–25', '2025–26'], record_count=2, reporting_days=2,
            records=[dict(id=1, date='2024-12-31', period='2024–25', month=12, position=.33, url='https://www.inaturalist.org/observations/1', name='Pine & fir', quality='needs_id', event_type='Unspecified encounter', photo_url='javascript:bad()', photo_credit='x', photo_license='cc-by'),
                dict(id=2, date='2026-01-01', period='2025–26', month=1, position=.34, url='https://www.inaturalist.org/observations/2', name='Pine & fir', quality='research', event_type='Unspecified encounter', photo_url='', photo_credit='', photo_license='')])],
        coverage=[dict(period='2025–26', months=[dict(month=m, label=l, record_count=n, reporting_days=n) for m,l,n in [(12,'December',0),(1,'January',1),(2,'February',0)]])],
        source_years=['2024–25','2025–26'], as_of='2026-01-01', next_observation='Document the whole plant.', sources=[dict(label='Source',url='https://example.org/source')], bird_examples=[])


class Parse(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.ids=[]; self.hrefs=[]; self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a: self.ids.append(a['id'])
        if tag=='a' and 'href' in a: self.hrefs.append(a['href'])


class SeasonalPagesTests(unittest.TestCase):
    def render(self, chapters):
        with tempfile.TemporaryDirectory() as tmp:
            paths=seasonal_pages.write_seasonal_pages(chapters,tmp)
            return {str(p.relative_to(tmp)):p.read_text() for p in paths}
    def test_five_routes_navigation_and_canonical(self):
        pages=self.render({s:chapter(s) for s in ['spring','summer','autumn','winter']})
        self.assertEqual(len(pages),5)
        for s in ['spring','summer','autumn','winter']:
            page=pages[f'seasons/{s}/index.html']
            self.assertIn(f'<link rel="canonical" href="https://survey.kingfisher-hollow.com/seasons/{s}/">',page)
            self.assertIn('aria-current="page"',page)
            for other in ['spring','summer','autumn','winter']: self.assertIn(f'href="/seasons/{other}/"',page)
    def test_escape_safe_sources_and_fingerprint(self):
        c=chapter(); c['intro']='<script>alert(1)</script>'; c['sources'].append(dict(label='bad',url='javascript:bad()'))
        page=self.render({'winter':c})['seasons/winter/index.html']
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('&lt;script&gt;',page); self.assertIn('Pine &amp; fir',page)
        self.assertNotIn('javascript:',page)
        self.assertRegex(page,r'seasonal\.css\?v=[a-f0-9]{12}')
        self.assertRegex(page,r'seasonal\.js\?v=[a-f0-9]{12}')
    def test_winter_evidence_native_fallback_and_context(self):
        page=self.render({'winter':chapter()})['seasons/winter/index.html']
        self.assertIn('2024-12-31',page); self.assertIn('2026-01-01',page)
        self.assertIn('2024–25',page); self.assertIn('2025–26',page)
        self.assertIn('<details class="voucher-appendix" id="evidence">',page)
        self.assertIn('not a sample of the whole community',page)
        self.assertNotIn('class="pooled-calendar"',page)
        self.assertIn('/plants/?from=%2Fseasons%2Fwinter%2F%23evidence-pine',page)
        self.assertIn('/field/?from=%2Fseasons%2Fwinter%2F%23next-observation',page)
        self.assertNotIn('/field-guide/',page)
        p=Parse(page); self.assertEqual(len(p.ids),len(set(p.ids)))
        for href in p.hrefs:
            if href.startswith('#'): self.assertIn(href[1:],p.ids)
    def test_seasonal_photographs_and_local_fonts(self):
        pages=self.render({})
        for key,extension in [('spring','webp'),('summer','webp'),('autumn','jpg'),('winter','jpg')]:
            page=pages[f'seasons/{key}/index.html']
            self.assertIn(f'/assets/seasons/{key}.{extension}?v=',page)
            self.assertNotIn('fonts.googleapis.com',page)
            self.assertIn('/assets/fonts/playfair-display-latin-wght-normal.woff2',page)
        self.assertIn('May 25, 2026',pages['seasons/spring/index.html'])
        self.assertIn('June 24, 2025',pages['seasons/summer/index.html'])
        self.assertIn('Capture date unrecorded',pages['seasons/autumn/index.html'])
        self.assertIn('Capture date unrecorded',pages['seasons/winter/index.html'])
    def test_media_requires_credit_and_license_and_sources_stay_available(self):
        c=chapter(); r=c['rows'][0]['records'][0]
        r.update(photo_url='https://example.org/photo.jpg',photo_credit='',photo_license='cc-by')
        page=self.render({'winter':c})['seasons/winter/index.html']
        self.assertNotIn('https://example.org/photo.jpg',page)
        r['photo_credit']='A photographer'
        page=self.render({'winter':c})['seasons/winter/index.html']
        self.assertIn('https://example.org/photo.jpg',page)
        self.assertIn('A photographer',page)
        self.assertIn('https://www.inaturalist.org/observations/1',page)
        self.assertEqual(seasonal_pages.safe_url('https://[broken'), '')
    def test_passage_illustration_requires_explicit_id_and_matching_observation_month(self):
        c=chapter(); records=c['rows'][0]['records']
        for r in records: r.update(photo_url=f'https://example.org/{r["id"]}.jpg',photo_credit='Photographer',photo_license='cc-by')
        c['passages'][0].update(photo_record_id=2,phase_month=1)
        page=self.render({'winter':c})['seasons/winter/index.html']
        self.assertIn('https://example.org/2.jpg',page)
        self.assertNotIn('https://example.org/1.jpg',page)
        c['passages'][0]['phase_month']=12
        page=self.render({'winter':c})['seasons/winter/index.html']
        self.assertNotIn('https://example.org/2.jpg',page)
        self.assertNotIn('https://example.org/1.jpg',page)
        self.assertIn('2026-01-01',page)
        c['passages'][0]['photo_record_id']=None
        page=self.render({'winter':c})['seasons/winter/index.html']
        self.assertNotIn('class="detail-photo"',page)
    def test_community_summary_has_full_counts_and_secondary_year_coverage(self):
        c=chapter('summer')
        c['community'] = dict(record_count=100, taxa_count=45, reporting_days=8,
            first_date='2025-06-01', as_of='2026-08-31',
            groups=[dict(label='Moths',taxa_count=40,reporting_days=7),dict(label='Plants',taxa_count=5,reporting_days=3)],
            months=[dict(month=6,taxa_count=20,reporting_days=4)],
            periods=[dict(period='2025',taxa_count=20,reporting_days=4,moth_taxa_count=17),dict(period='2026',taxa_count=30,reporting_days=4,moth_taxa_count=27)],
            moths=dict(taxa_count=40,family_count=4,months=[]))
        page=self.render({'summer':c})['seasons/summer/index.html']
        self.assertIn('45 taxa across 2 broad groups',page)
        self.assertIn('40 moth taxa across 4 identified families',page)
        self.assertIn('<details class="community-methods">',page)
        self.assertIn('Species and subspecies may have separate IDs',page)
        self.assertLess(page.index('id="community"'),page.index('id="evidence"'))
        self.assertIn('2025</th>',page);self.assertIn('2026</th>',page)
        self.assertNotIn('class="opening-detail"',page)

    def test_empty_missing_chapters_still_provide_complete_journey(self):
        pages=self.render({})
        self.assertEqual(len(pages),5)
        page=pages['seasons/winter/index.html']
        self.assertIn('No supporting records',page)
        self.assertIn('Continue into spring',page)
        self.assertNotIn('2026-01-01',page)

if __name__=='__main__': unittest.main()
