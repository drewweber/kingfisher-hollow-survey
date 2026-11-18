import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const require = createRequire(import.meta.url);
const api = () => require('../assets/bird-route-map.js');
const data = () => JSON.parse(readFileSync(new URL('../data/bird-route-use-5m.json', import.meta.url)));
const close = (actual, expected, tolerance = 1e-12) => assert.ok(Math.abs(actual - expected) < tolerance, `${actual} differs from ${expected}`);
const script = readFileSync(new URL('../assets/bird-route-map.js', import.meta.url), 'utf8');

function openMap({ hash = '', hasObserver = true } = {}) {
  const status = { textContent: 'Loading route map…' };
  const dataScript = { get textContent() {
    reads += 1;
    return JSON.stringify({
      metadata: { cell_size_m: 5, cell_count: 1, route_count: 2, max_count: 2 },
      geojson: { type: 'FeatureCollection', features: [{
        type: 'Feature', properties: { route_count: 2 },
        geometry: { type: 'Polygon', coordinates: [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]] },
      }] },
    });
  } };
  const cells = { style: {}, replaceChildren(fragment) { this.children = fragment.children; }, addEventListener() {} };
  const svg = { style: {}, addEventListener() {}, setAttribute() {}, getBoundingClientRect: () => ({ width: 800 }) };
  const tiles = { children: [], setAttribute() {}, appendChild(image) { this.children.push(image); } };
  const controls = {
    '[data-map-status]': status, '[data-route-map-svg]': svg, '[data-map-tiles]': tiles,
    '[data-map-cells]': cells, '[data-route-cells]': dataScript,
  };
  const container = Object.assign(new EventTarget(), {
    dataset: {},
    closest: () => section,
    contains: element => element === svg || element === help || element === container,
    querySelector: selector => controls[selector],
    querySelectorAll: () => [],
  });
  const help = {};
  const section = { contains: element => element === section || container.contains(element) };
  const targets = { 'bird-route-use': section, 'bird-route-help': help };
  const frames = [];
  const window = Object.assign(new EventTarget(), { location: { hash } });
  let reads = 0;
  let intersect = () => {};
  let disconnected = false;
  let rootMargin;
  const makeElement = name => ({
    name, children: [],
    appendChild(child) { this.children.push(child); },
    setAttribute() {}, addEventListener() {},
  });
  class Observer {
    constructor(callback, options) {
      rootMargin = options.rootMargin;
      intersect = isIntersecting => callback([{ target: container, isIntersecting }]);
    }
    observe(target) { assert.equal(target, container); }
    disconnect() { disconnected = true; }
  }
  runInNewContext(script, {
    window,
    document: {
      readyState: 'interactive',
      querySelectorAll: () => [container],
      getElementById: id => targets[id] ?? null,
      createElementNS: (_namespace, name) => makeElement(name),
      createDocumentFragment: () => makeElement('#fragment'),
    },
    IntersectionObserver: hasObserver ? Observer : undefined,
    requestAnimationFrame: callback => frames.push(callback),
  });
  return {
    window, container, svg, status, cells, tiles, rootMargin,
    reads: () => reads,
    disconnected: () => disconnected,
    intersect: isIntersecting => intersect(isIntersecting),
    paint: () => frames.splice(0).forEach(callback => callback()),
  };
}

test('offscreen maps defer data parsing, SVG creation, and tile requests until near the viewport', () => {
  const map = openMap();
  map.intersect(false);
  map.paint();
  assert.equal(map.reads(), 0);
  assert.equal(map.cells.children, undefined);
  assert.equal(map.tiles.children.length, 0);
  assert.ok(Number.parseInt(map.rootMargin, 10) > 0);
  map.intersect(true);
  map.paint();
  assert.equal(map.cells.children[0].name, 'polygon');
  assert.ok(map.tiles.children.length > 0);
  assert.ok(map.disconnected());
  map.intersect(true);
  assert.equal(map.reads(), 1);
});

test('focus initializes the map before an offscreen control is used', () => {
  const map = openMap();
  assert.equal(map.reads(), 0);
  map.container.dispatchEvent(new Event('focusin', { bubbles: true }));
  assert.equal(map.cells.children[0].name, 'polygon');
  assert.ok(map.disconnected());
});

test('the route-use section and its nested help text can be opened by fragment', () => {
  for (const hash of ['#bird-route-use', '#bird-route%2Dhelp']) {
    const map = openMap({ hash });
    assert.equal(map.cells.children[0].name, 'polygon');
  }
  const map = openMap({ hash: '#elsewhere' });
  assert.equal(map.reads(), 0);
  map.window.location.hash = '#bird-route-help';
  map.window.dispatchEvent(new Event('hashchange'));
  assert.equal(map.cells.children[0].name, 'polygon');
  assert.ok(map.disconnected());
});

test('the map still renders when IntersectionObserver is unavailable', () => {
  const map = openMap({ hasObserver: false });
  map.paint();
  assert.equal(map.cells.children[0].name, 'polygon');
  assert.ok(map.tiles.children.length > 0);
});

test('Mercator axes and world edges agree with standard raster tiles', () => {
  const { project } = api();
  assert.deepEqual(project([0, 0]), [0.5, 0.5]);
  close(project([-180, 0])[0], 0);
  close(project([180, 0])[0], 1);
  close(project([0, 85.0511287798066])[1], 0);
  assert.ok(project([-76.5, 42])[1] < 0.5);
  assert.throws(() => project([NaN, 2]));
});

test('fit keeps every cell inside 24 pixel padding at narrow and wide widths', () => {
  const { fitBounds } = api();
  const bounds = [0.2, 0.3, 0.2001, 0.3002];
  for (const width of [320, 800, 1400]) {
    const view = fitBounds(bounds, width, 420, 24);
    close(view.w / view.h, width / 420);
    assert.ok((bounds[0] - view.x) / view.w * width > 23.999);
    assert.ok((bounds[1] - view.y) / view.h * 420 > 23.999);
    assert.ok((view.x + view.w - bounds[2]) / view.w * width > 23.999);
    assert.ok((view.y + view.h - bounds[3]) / view.h * 420 > 23.999);
  }
});

test('zoom preserves center and clamps to valid Mercator world and zoom limits', () => {
  const { zoomView, panView, tileRequests } = api();
  const initial = { x: 0.2, y: 0.3, w: 0.1, h: 0.05 };
  const zoomed = zoomView(initial, 0.5, 840, 420);
  close(zoomed.x + zoomed.w / 2, 0.25);
  close(zoomed.y + zoomed.h / 2, 0.325);
  close(zoomed.w, 0.05);
  const world = zoomView(initial, 1e12, 840, 420);
  const moved = panView(world, -100, 100);
  assert.ok(moved.x >= 0 && moved.y >= 0 && moved.x + moved.w <= 1 && moved.y + moved.h <= 1);
  const nearest = zoomView(initial, 1e-12, 840, 420);
  assert.ok(tileRequests(nearest, 840).every(tile => tile.z <= 20));
  close(nearest.w, 840 / (256 * 2 ** 20));
});

test('real aggregate produces only projected cells and a bounded raster tile set', () => {
  const { readCells, fitBounds, tileRequests } = api();
  const snapshot = data();
  const parsed = readCells(snapshot);
  assert.equal(parsed.cells.length, snapshot.metadata.cell_count);
  assert.equal(parsed.maximum, snapshot.metadata.max_count);
  assert.equal(parsed.routeCount, snapshot.metadata.route_count);
  assert.deepEqual(Object.keys(parsed.cells[0]).sort(), ['count', 'points']);
  assert.equal(parsed.cells[0].points.length, 5);
  for (const width of [320, 800, 1400]) {
    const tiles = tileRequests(fitBounds(parsed.bounds, width, 420, 24), width);
    assert.ok(tiles.length > 0 && tiles.length < 60);
    assert.equal(new Set(tiles.map(tile => tile.url)).size, tiles.length);
    for (const tile of tiles) {
      assert.match(tile.url, /^https:\/\/tile\.openstreetmap\.org\/\d+\/\d+\/\d+\.png$/);
      close(tile.size, 1 / 2 ** tile.z);
      assert.ok(tile.x >= 0 && tile.y >= 0 && tile.x + tile.size <= 1 && tile.y + tile.size <= 1);
    }
  }
});

test('malformed data cannot become cells or tile requests', () => {
  const { readCells } = api();
  for (const mutate of [
    d => { d.metadata.cell_size_m = 10; },
    d => { d.metadata.max_count += 1; },
    d => { d.geojson.features[0].properties.route_count = d.metadata.route_count + 1; },
    d => { d.geojson.features[0].geometry.type = 'LineString'; },
    d => { d.geojson.features[0].geometry.coordinates[0][0] = [0, 0]; },
    d => { d.geojson.features[0].geometry.coordinates[0][1][0] = NaN; },
  ]) {
    const document = data();
    mutate(document);
    assert.throws(() => readCells(document));
  }
});

test('logarithmic colors give equal space to equal ratios while preserving endpoints', () => {
  const { cellColor } = api();
  assert.equal(cellColor(1, 100), '#00224e');
  assert.equal(cellColor(10, 100), '#7d7c78');
  assert.equal(cellColor(100, 100), '#fee838');
  assert.equal(cellColor(1, 1), '#00224e');
  assert.equal(cellColor(2, 16), cellColor(10, 10000));
  assert.equal(cellColor(4, 16), cellColor(100, 10000));
});
