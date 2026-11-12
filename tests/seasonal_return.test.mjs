import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../assets/seasonal-return.js', import.meta.url), 'utf8');
function render(from) {
  const links = [0, 1].map(() => ({hidden: true, href: '/seasons/', textContent: ''}));
  vm.runInNewContext(source, {
    URL, URLSearchParams,
    location: {origin: 'https://survey.example', search: from === null ? '' : `?from=${encodeURIComponent(from)}`},
    document: {querySelectorAll: () => links},
  });
  return links;
}
test('specialist return retains selected season, evidence anchor and known comparison', () => {
  for (const link of render('/seasons/autumn/?compare=years#evidence-sallow')) {
    assert.equal(link.hidden, false);
    assert.equal(link.href, '/seasons/autumn/?compare=years#evidence-sallow');
    assert.equal(link.textContent, '← Back to autumn');
  }
});
test('return context never accepts an external URL or an unrelated internal destination', () => {
  for (const from of [null, 'https://evil.example/seasons/autumn/', '//evil.example/seasons/autumn/', '/api/update', '/seasons/monsoon/', 'javascript:alert(1)']) {
    assert.ok(render(from).every(link => link.hidden));
  }
});
test('unknown parameters and unsafe fragments are discarded', () => {
  const [link] = render('/seasons/winter/?secret=value#<script>');
  assert.equal(link.href, '/seasons/winter/');
});
