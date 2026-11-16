import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
const source = await readFile(new URL('../field-guide/app/browser-navigation.js', import.meta.url), 'utf8');
function harness({ standalone = false, ios = false, legacy = false, enhanced = true } = {}) {
  const listeners = {};
  const values = {};
  const root = { dataset: {}, style: { setProperty: (k,v) => values[k] = v } };
  const media = { matches: standalone };
  media[legacy ? 'addListener' : 'addEventListener'] = (...args) => listeners.mode = args.at(-1);
  let ready = false, focused = false, closed = false, focusInNav = false;
  const wrapper = { getBoundingClientRect: () => ({ height: 122 }), contains: () => focusInNav };
  const menu = { hasAttribute: () => true, matches: () => true, hidePopover: () => closed = true };
  const document = { documentElement: root, getElementById: id => !ready ? null : ({
    'field-browser-navigation': wrapper, 'survey-menu': menu,
    'navbar': { classList: { contains: () => enhanced } },
    'results-heading': { focus: () => focused = true },
  })[id], addEventListener: (type, cb) => listeners[type] = cb };
  const window = { matchMedia: () => media, addEventListener: (type, cb) => listeners[type] = cb };
  vm.runInNewContext(source, { document, window, navigator: { standalone: ios } });
  return { root, values, media, listeners,
    ready() { ready = true; listeners.DOMContentLoaded(); },
    focusNav() { focusInNav = true; },
    get focused() { return focused; }, get closed() { return closed; } };
}
test('regular browser gets navigation before paint and sticky filters clear its height', () => {
  const h = harness();
  assert.equal(h.root.dataset.fieldDisplay, 'browser');
  h.ready();
  assert.equal(h.values['--field-browser-nav-height'], '122px');
});
test('standalone display hides browser navigation before DOM is ready', () => {
  const h = harness({ standalone: true });
  assert.equal(h.root.dataset.fieldDisplay, 'standalone');
  h.ready();
  assert.equal(h.values['--field-browser-nav-height'], '0px');
});
test('iOS home screen fallback uses the standalone shell', () => {
  const h = harness({ ios: true });
  assert.equal(h.root.dataset.fieldDisplay, 'standalone');
});
test('display changes close an open menu, move focus, and restore browser navigation', () => {
  const h = harness({ legacy: true }); h.ready(); h.focusNav();
  h.media.matches = true; h.listeners.mode();
  assert.equal(h.closed, true); assert.equal(h.focused, true);
  assert.equal(h.values['--field-browser-nav-height'], '0px');
  h.media.matches = false; h.listeners.mode();
  assert.equal(h.root.dataset.fieldDisplay, 'browser');
  assert.equal(h.values['--field-browser-nav-height'], '122px');
});

test('expanded fallback navigation scrolls away without a sticky filter offset', () => {
  const h = harness({ enhanced: false }); h.ready();
  assert.equal(h.root.dataset.fieldNavEnhanced, 'false');
  assert.equal(h.values['--field-browser-nav-height'], '0px');
});
