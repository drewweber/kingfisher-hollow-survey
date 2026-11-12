"""Verify the five generated seasonal routes and their local destinations."""
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1] / 'public'


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.assets = []
        self.headings = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            self.ids.append(a['id'])
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag in ('img', 'script') and a.get('src'):
            self.assets.append(a['src'])
        if tag == 'link' and a.get('rel') == 'stylesheet':
            self.assets.append(a['href'])
        if tag == 'h1':
            self.headings += 1


def verify():
    for key in ('', 'spring', 'summer', 'autumn', 'winter'):
        route = '/seasons/' + (key + '/' if key else '')
        file = ROOT / route.strip('/') / 'index.html'
        html = file.read_text()
        doc = Document()
        doc.feed(html)
        assert doc.headings == 1, (route, 'must have one main heading')
        assert len(doc.ids) == len(set(doc.ids)), (route, 'duplicate anchors')
        assert len(file.read_bytes()) < 250_000, (route, 'unexpected page payload')
        for season in ('spring', 'summer', 'autumn', 'winter'):
            assert f'/seasons/{season}/' in doc.links, (route, 'missing seasonal navigation', season)
        if key:
            assert {'evidence', 'next-observation'} <= set(doc.ids), (route, 'incomplete journey')
        for link in doc.links + doc.assets:
            parsed = urlsplit(link)
            assert parsed.scheme not in ('javascript', 'data'), (route, 'unsafe destination')
            if parsed.scheme or parsed.netloc:
                continue
            target = ROOT / parsed.path.lstrip('/') if parsed.path else file
            if parsed.path.endswith('/'):
                target /= 'index.html'
            assert target.is_file(), (route, 'missing local destination', link)
            if parsed.fragment and target.suffix == '.html':
                destination = Document()
                destination.feed(target.read_text())
                assert unquote(parsed.fragment) in destination.ids, (route, 'missing destination anchor', link)
        print(f'{route}: complete navigation, source anchors and assets; {len(file.read_bytes()):,} bytes')

    field = ROOT / 'field'
    worker = (field / 'service-worker.js').read_text()
    manifest = json.loads(re.search(r'const ASSETS = (\[.*?\]);', worker, re.S).group(1))
    for asset in manifest:
        source = field / ('index.html' if asset['path'] == './' else asset['path'])
        assert hashlib.sha256(source.read_bytes()).hexdigest() == asset['sha256'], ('offline asset changed after hashing', asset['path'])
    assert any('seasonal-return.' in asset['path'] for asset in manifest), 'missing offline seasonal return'
    print(f'/field/: all {len(manifest)} offline asset hashes match final bytes')


if __name__ == '__main__':
    verify()
