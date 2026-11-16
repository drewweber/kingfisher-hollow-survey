import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../report.py', import.meta.url), 'utf8');
const script = source.split('LIFE_LIST_SCRIPT = """')[1].split('"""')[0].replaceAll('\\\\', '\\');

function harness(href = 'https://survey.example/life-list/', size = 3) {
  function element(extra = {}) {
    const listeners = {}, attrs = {}, classes = new Set();
    return { value: '', textContent: '', dataset: {}, style: {}, ...extra,
      addEventListener(type, callback) { listeners[type] = callback; },
      dispatch(type) { listeners[type]?.(); },
      setAttribute(name, value) { attrs[name] = value; },
      getAttribute(name) { return attrs[name]; },
      focus() { this.focused = true; },
      classList: { contains: c => classes.has(c), remove: c => classes.delete(c),
        toggle(c, on) { on ? classes.add(c) : classes.delete(c); } },
    };
  }
  const rows = [['Luna Moth', 'Actias luna', 'Moths', 'Saturniidae'],
    ['Monarch', 'Danaus plexippus', 'Butterflies', 'Nymphalidae'],
    ['Wood Duck', 'Aix sponsa', 'Birds', 'Anatidae'],
    ...Array.from({length: size - 3}, (_, i) => ['Species ' + i, 'Scientific ' + i, 'Moths', 'Saturniidae'])].map(([name, sci, group, family]) => {
    const scientific = element({ textContent: sci });
    scientific.classList.toggle('ll-scientific-name', true);
    const number = element(), link = element();
    return element({ number, link, dataset: { family }, cells: [{}, {
      lastElementChild: scientific, childNodes: [{ textContent: name }, scientific],
    }, { textContent: group }], querySelector(selector) { return selector === '.ll-number' ? number : link; } });
  });
  const buttons = ['all', 'Moths', 'Butterflies'].map(group => element({ dataset: { group } }));
  const ids = Object.fromEntries(['ll-search', 'll-count', 'll-select', 'll-taxon-select', 'll-clear', 'll-body', 'll-pagination', 'll-previous', 'll-next', 'll-page-label', 'll-table-region']
    .map(id => [id, element()]));
  ids['ll-count'].textContent = size.toLocaleString() + ' species shown';
  ids['ll-body'].children = [...rows];
  ids['ll-body'].replaceChildren = function(...children) { this.children = children; };
  let nextTimer = 0;
  const timers = new Map();
  const listeners = {}, entries = [href];
  let position = 0;
  const window = {
    location: { href },
    addEventListener(type, callback) { listeners[type] = callback; },
    history: {
      state: { unrelated: 'preserved' },
      pushState(state, title, url) {
        assert.equal(state.unrelated, 'preserved');
        entries.splice(++position); entries.push(String(url)); window.location.href = String(url);
      },
      replaceState(state, title, url) {
        assert.equal(state.unrelated, 'preserved');
        entries[position] = String(url); window.location.href = String(url);
      },
    },
  };
  function go(delta) {
    position += delta; assert.ok(position >= 0 && position < entries.length);
    window.location.href = entries[position]; listeners.popstate();
  }
  vm.runInNewContext(script, {
    URL, window,
    document: { getElementById: id => ids[id],
      querySelectorAll: selector => selector === '.ll-row' ? rows : buttons },
    setTimeout(callback, delay) { assert.equal(delay, 250); timers.set(++nextTimer, callback); return nextTimer; },
    clearTimeout(id) { timers.delete(id); },
  });
  return { rows, buttons, ids, timers, window, entries, go, flush() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(fn => fn()); } };
}

test('typing filters immediately but announces only the settled result', () => {
  const h = harness();
  const search = h.ids['ll-search'], count = h.ids['ll-count'];
  search.value = 'luna'; search.dispatch('input');
  assert.equal(h.ids['ll-body'].children.length, 1);
  assert.equal(count.textContent, '3 species shown');
  search.value = 'does not exist'; search.dispatch('input');
  assert.equal(h.timers.size, 1);
  h.flush();
  assert.match(count.textContent, /No species match/);
});

test('clear filters resets query, group, family, pressed state and focus', () => {
  const h = harness();
  h.buttons[1].dispatch('click');
  h.ids['ll-taxon-select'].value = 'Saturniidae'; h.ids['ll-taxon-select'].dispatch('change');
  h.ids['ll-search'].value = 'luna'; h.ids['ll-search'].dispatch('input');
  h.ids['ll-clear'].dispatch('click');
  assert.equal(h.ids['ll-search'].value, '');
  assert.equal(h.ids['ll-select'].value, '');
  assert.equal(h.ids['ll-taxon-select'].value, '');
  assert.equal(h.ids['ll-taxon-select'].disabled, true);
  assert.equal(h.ids['ll-body'].children.length, 3);
  assert.equal(h.buttons[0].getAttribute('aria-pressed'), 'true');
  assert.equal(h.buttons[1].getAttribute('aria-pressed'), 'false');
  assert.equal(h.ids['ll-search'].focused, true);
  h.flush();
  assert.equal(h.ids['ll-count'].textContent, '3 species shown');
});

test('more groups and family filter continue to narrow scientific-name searches', () => {
  const h = harness();
  h.ids['ll-select'].value = 'Birds'; h.ids['ll-select'].dispatch('change');
  h.ids['ll-taxon-select'].value = 'Anatidae'; h.ids['ll-taxon-select'].dispatch('change');
  h.ids['ll-search'].value = 'AIX'; h.ids['ll-search'].dispatch('input');
  h.flush();
  assert.equal(h.ids['ll-count'].textContent, '1 species shown');
  assert.equal(visible(h)[0], h.rows[2]);
});


function visible(h) {
  return h.ids['ll-body'].children;
}

test('deep link and reload restore query, pinned group, family and result count', () => {
  const href = 'https://survey.example/life-list/?from=seasonal&q=LUNA&group=Moths&family=Saturniidae#life-list';
  for (const h of [harness(href), harness(harness(href).window.location.href)]) {
    assert.equal(h.ids['ll-search'].value, 'LUNA');
    assert.equal(h.buttons[1].getAttribute('aria-pressed'), 'true');
    assert.equal(h.ids['ll-select'].value, '');
    assert.equal(h.ids['ll-taxon-select'].value, 'Saturniidae');
    assert.equal(h.ids['ll-taxon-select'].disabled, false);
    assert.equal(visible(h).length, 1);
    assert.equal(h.ids['ll-count'].textContent, '1 species shown');
    assert.equal(h.entries.length, 1);
    assert.equal(h.window.location.href, href);
  }
});

test('more-group deep link restores dropdown rather than a pinned pressed button', () => {
  const h = harness('https://survey.example/life-list/?group=Birds&family=Anatidae');
  assert.equal(h.ids['ll-select'].value, 'Birds');
  assert.ok(h.buttons.every(button => button.getAttribute('aria-pressed') === 'false'));
  assert.equal(h.ids['ll-taxon-select'].value, 'Anatidae');
  assert.equal(visible(h)[0], h.rows[2]);
});

test('unknown groups, unavailable families and duplicate filters normalize in place', () => {
  for (const query of ['group=Unknown&family=Saturniidae', 'family=Saturniidae', 'group=all']) {
    const h = harness('https://survey.example/life-list/?from=seasonal&tag=a&tag=b&' + query + '#life-list');
    assert.equal(h.window.location.href, 'https://survey.example/life-list/?from=seasonal&tag=a&tag=b#life-list');
    assert.equal(h.buttons[0].getAttribute('aria-pressed'), 'true');
    assert.equal(h.ids['ll-taxon-select'].disabled, true);
    assert.equal(visible(h).length, 3);
    assert.equal(h.entries.length, 1);
  }
  const h = harness('https://survey.example/life-list/?group=Moths&group=Birds&family=Anatidae');
  assert.equal(h.window.location.href, 'https://survey.example/life-list/?group=Moths');
  assert.equal(h.ids['ll-taxon-select'].value, '');
  assert.equal(visible(h)[0], h.rows[0]);
});

test('typing has one history entry per editing session; Back/Forward restores query', () => {
  const h = harness();
  for (const value of ['l', 'lu', 'lun', 'luna']) {
    h.ids['ll-search'].value = value; h.ids['ll-search'].dispatch('input');
  }
  assert.equal(h.entries.length, 2);
  assert.equal(new URL(h.window.location.href).searchParams.get('q'), 'luna');
  h.go(-1); h.flush();
  assert.equal(h.ids['ll-search'].value, '');
  assert.equal(visible(h).length, 3);
  h.go(1); h.flush();
  assert.equal(h.ids['ll-search'].value, 'luna');
  assert.equal(visible(h)[0], h.rows[0]);
  h.ids['ll-search'].dispatch('blur');
  h.ids['ll-search'].value = 'duck'; h.ids['ll-search'].dispatch('input');
  assert.equal(h.entries.length, 3);
  h.go(-1);
  assert.equal(h.ids['ll-search'].value, 'luna');
});

test('discrete filters and clear are reversible while preserving unrelated URL state', () => {
  const original = 'https://survey.example/life-list/?from=seasonal&tag=a&tag=b#life-list';
  const h = harness(original);
  h.buttons[1].dispatch('click');
  h.ids['ll-taxon-select'].value = 'Saturniidae'; h.ids['ll-taxon-select'].dispatch('change');
  h.ids['ll-search'].value = 'Actias & luna + ?'; h.ids['ll-search'].dispatch('input');
  assert.equal(new URL(h.window.location.href).searchParams.get('q'), 'Actias & luna + ?');
  h.ids['ll-clear'].dispatch('click');
  assert.equal(h.window.location.href, original);
  assert.equal(h.ids['ll-search'].focused, true);
  h.go(-1); h.flush();
  assert.equal(h.ids['ll-search'].value, 'Actias & luna + ?');
  assert.equal(h.ids['ll-taxon-select'].value, 'Saturniidae');
  assert.equal(h.buttons[1].getAttribute('aria-pressed'), 'true');
  assert.equal(visible(h).length, 0);
  h.go(-1); h.flush();
  assert.equal(h.ids['ll-search'].value, '');
  assert.equal(visible(h).length, 1);
  h.go(-1);
  assert.equal(h.ids['ll-taxon-select'].value, '');
  h.go(-1);
  assert.equal(h.buttons[0].getAttribute('aria-pressed'), 'true');
  h.go(1); h.go(1);
  assert.equal(h.ids['ll-taxon-select'].value, 'Saturniidae');
  assert.equal(new URL(h.window.location.href).searchParams.get('from'), 'seasonal');
  assert.equal(new URL(h.window.location.href).hash, '#life-list');
});

test('reselecting the current group or clearing empty filters adds no history entries', () => {
  const h = harness();
  h.ids['ll-clear'].dispatch('click'); h.buttons[0].dispatch('click');
  assert.equal(h.entries.length, 1);
  h.buttons[1].dispatch('click'); h.buttons[1].dispatch('click');
  assert.equal(h.entries.length, 2);
});


test('returning the more-groups dropdown to its placeholder clears group and family', () => {
  const h = harness('https://survey.example/life-list/?group=Birds&family=Anatidae');
  h.ids['ll-select'].value = ''; h.ids['ll-select'].dispatch('change');
  assert.equal(h.window.location.href, 'https://survey.example/life-list/');
  assert.equal(h.buttons[0].getAttribute('aria-pressed'), 'true');
  assert.equal(h.ids['ll-taxon-select'].disabled, true);
  assert.equal(visible(h).length, 3);
});


test('pagination bounds mounted rows and searches across detached records', () => {
  const h = harness(undefined, 10000);
  assert.equal(visible(h).length, 100);
  assert.equal(h.ids['ll-count'].textContent, 'Showing 1–100 of 10,000 species');
  assert.equal(h.ids['ll-previous'].disabled, true);
  assert.equal(h.ids['ll-next'].disabled, false);
  assert.equal(h.ids['ll-pagination'].hidden, false);
  h.ids['ll-next'].dispatch('click'); h.flush();
  assert.equal(visible(h).length, 100);
  assert.equal(visible(h)[0], h.rows[100]);
  assert.equal(h.rows[100].number.textContent, '9,900');
  assert.equal(h.rows[100].link.focused, true);
  assert.equal(h.ids['ll-count'].textContent, 'Showing 101–200 of 10,000 species');
  assert.equal(new URL(h.window.location.href).searchParams.get('page'), '2');
  h.ids['ll-search'].value = 'Scientific 9996'; h.ids['ll-search'].dispatch('input'); h.flush();
  assert.equal(visible(h).length, 1);
  assert.equal(visible(h)[0], h.rows[9999]);
  assert.equal(h.ids['ll-pagination'].hidden, true);
  assert.equal(new URL(h.window.location.href).searchParams.has('page'), false);
  assert.equal(h.ids['ll-count'].textContent, '1 species shown');
  h.go(-1); h.flush();
  assert.equal(visible(h)[0], h.rows[100]);
  assert.equal(h.ids['ll-page-label'].textContent, 'Page 2 of 100');
  h.go(-1);
  assert.equal(visible(h)[0], h.rows[0]);
  h.go(1);
  assert.equal(visible(h)[0], h.rows[100]);
});

test('page deep links clamp bounds and initial no-match URL detaches every SSR row', () => {
  for (const page of ['-1', '0', '1.5', 'nope', 'Infinity', '9007199254740992']) {
    const h = harness('https://survey.example/life-list/?from=seasonal&page=' + page + '#life-list', 205);
    assert.equal(visible(h)[0], h.rows[0]);
    assert.equal(h.window.location.href, 'https://survey.example/life-list/?from=seasonal#life-list');
  }
  const h = harness('https://survey.example/life-list/?page=999', 205);
  assert.equal(visible(h).length, 5);
  assert.equal(visible(h)[0], h.rows[200]);
  assert.equal(h.ids['ll-next'].disabled, true);
  assert.equal(h.window.location.href, 'https://survey.example/life-list/?page=3');
  assert.equal(h.ids['ll-count'].textContent, 'Showing 201–205 of 205 species');
  h.ids['ll-next'].dispatch('click');
  assert.equal(h.entries.length, 1);
  const empty = harness('https://survey.example/life-list/?q=nothing&page=9', 205);
  assert.equal(visible(empty).length, 0);
  assert.equal(empty.ids['ll-pagination'].hidden, true);
  assert.equal(empty.window.location.href, 'https://survey.example/life-list/?q=nothing');
});

test('group, family and Clear filters reset pagination while Back retains its subset', () => {
  const h = harness('https://survey.example/life-list/?page=2', 305);
  h.buttons[1].dispatch('click');
  assert.equal(h.ids['ll-page-label'].textContent, 'Page 1 of 4');
  assert.equal(visible(h)[0], h.rows[0]);
  h.ids['ll-next'].dispatch('click');
  h.ids['ll-taxon-select'].value = 'Saturniidae'; h.ids['ll-taxon-select'].dispatch('change');
  assert.equal(h.ids['ll-page-label'].textContent, 'Page 1 of 4');
  h.ids['ll-next'].dispatch('click');
  h.ids['ll-clear'].dispatch('click');
  assert.equal(visible(h)[0], h.rows[0]);
  assert.equal(h.ids['ll-search'].focused, true);
  h.go(-1);
  assert.equal(h.ids['ll-page-label'].textContent, 'Page 2 of 4');
  assert.equal(h.ids['ll-taxon-select'].value, 'Saturniidae');
  assert.equal(visible(h)[0], h.rows[102]);
});


test('a last-page unlinked record moves keyboard focus to the table region', () => {
  const h = harness(undefined, 101);
  h.rows[100].querySelector = () => null;
  h.ids['ll-next'].dispatch('click');
  assert.equal(visible(h).length, 1);
  assert.equal(h.ids['ll-next'].disabled, true);
  assert.equal(h.ids['ll-table-region'].focused, true);
});
