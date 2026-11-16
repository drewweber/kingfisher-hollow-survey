import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../report.py', import.meta.url), 'utf8');
const script = source.split('LIFE_LIST_SCRIPT = """')[1].split('"""')[0].replaceAll('\\\\', '\\');

function harness() {
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
    ['Wood Duck', 'Aix sponsa', 'Birds', 'Anatidae']].map(([name, sci, group, family]) => {
    const scientific = element({ textContent: sci });
    scientific.classList.toggle('ll-scientific-name', true);
    return element({ dataset: { family }, cells: [{}, {
      lastElementChild: scientific, childNodes: [{ textContent: name }, scientific],
    }, { textContent: group }], querySelector() { return null; } });
  });
  const buttons = ['all', 'Moths', 'Butterflies'].map(group => element({ dataset: { group } }));
  const ids = Object.fromEntries(['ll-search', 'll-count', 'll-select', 'll-taxon-select', 'll-clear']
    .map(id => [id, element()]));
  ids['ll-count'].textContent = '3 species shown';
  let nextTimer = 0;
  const timers = new Map();
  vm.runInNewContext(script, {
    document: { getElementById: id => ids[id],
      querySelectorAll: selector => selector === '.ll-row' ? rows : buttons },
    setTimeout(callback, delay) { assert.equal(delay, 250); timers.set(++nextTimer, callback); return nextTimer; },
    clearTimeout(id) { timers.delete(id); },
  });
  return { rows, buttons, ids, timers, flush() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(fn => fn()); } };
}

test('typing filters immediately but announces only the settled result', () => {
  const h = harness();
  const search = h.ids['ll-search'], count = h.ids['ll-count'];
  search.value = 'luna'; search.dispatch('input');
  assert.equal(h.rows.filter(row => row.style.display !== 'none').length, 1);
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
  assert.equal(h.rows.filter(row => row.style.display !== 'none').length, 3);
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
  assert.equal(h.rows[2].style.display, '');
  assert.equal(h.rows[0].style.display, 'none');
});
