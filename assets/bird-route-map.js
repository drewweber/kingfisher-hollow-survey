/* Public aggregate cells over raster map tiles; no WebGL or map library. */
(function () {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const HEIGHT = 420;
  const MAX_LATITUDE = 85.0511287798066;
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

  function project(coordinate) {
    if (!Array.isArray(coordinate) || coordinate.length !== 2 || !coordinate.every(Number.isFinite)
        || Math.abs(coordinate[0]) > 180 || Math.abs(coordinate[1]) > MAX_LATITUDE + 1e-10) {
      throw new Error('Invalid map coordinate');
    }
    const sine = Math.sin(coordinate[1] * Math.PI / 180);
    return [(coordinate[0] + 180) / 360, clamp(0.5 - Math.log((1 + sine) / (1 - sine)) / (4 * Math.PI), 0, 1)];
  }

  function panView(view, dx, dy) {
    return { x: clamp(view.x + dx, 0, 1 - view.w), y: clamp(view.y + dy, 0, 1 - view.h), w: view.w, h: view.h };
  }

  function centeredView(cx, cy, requestedWidth, pixelWidth, pixelHeight) {
    const ratio = pixelWidth / pixelHeight;
    const w = clamp(requestedWidth, pixelWidth / (256 * 2 ** 20), Math.min(1, ratio));
    const h = w / ratio;
    return panView({ x: cx - w / 2, y: cy - h / 2, w, h }, 0, 0);
  }

  function fitBounds(bounds, width, height = HEIGHT, padding = 24) {
    if (!(width > padding * 2 && height > padding * 2)) throw new Error('Map container is too small');
    const [left, top, right, bottom] = bounds;
    const scale = Math.max((right - left) / (width - 2 * padding), (bottom - top) / (height - 2 * padding));
    return centeredView((left + right) / 2, (top + bottom) / 2, scale * width, width, height);
  }

  function zoomView(view, factor, width, height = HEIGHT) {
    return centeredView(view.x + view.w / 2, view.y + view.h / 2, view.w * factor, width, height);
  }

  function tileRequests(view, width) {
    let z = clamp(Math.floor(Math.log2(width / (256 * view.w))), 0, 20);
    let ranges;
    // Keep both network traffic and DOM size bounded even on unusually wide displays.
    do {
      const n = 2 ** z;
      ranges = [clamp(Math.floor(view.x * n), 0, n - 1), clamp(Math.floor(view.y * n), 0, n - 1),
        clamp(Math.floor((view.x + view.w) * n), 0, n - 1), clamp(Math.floor((view.y + view.h) * n), 0, n - 1)];
      if ((ranges[2] - ranges[0] + 1) * (ranges[3] - ranges[1] + 1) < 60 || z === 0) break;
      z -= 1;
    } while (z >= 0);
    const size = 1 / 2 ** z;
    const tiles = [];
    for (let x = ranges[0]; x <= ranges[2]; x += 1) {
      for (let y = ranges[1]; y <= ranges[3]; y += 1) {
        tiles.push({ z, x: x * size, y: y * size, size,
          url: `https://tile.openstreetmap.org/${z}/${x}/${y}.png` });
      }
    }
    return tiles;
  }

  function cellColor(count, maximum) {
    const fraction = maximum > 1 ? clamp(Math.log(Math.max(1, count)) / Math.log(maximum), 0, 1) : 0;
    const colors = [[0, 34, 78], [125, 124, 120], [254, 232, 56]];
    const segment = fraction <= 0.5 ? 0 : 1;
    const weight = fraction * 2 - segment;
    return '#' + colors[segment].map((channel, index) => Math.round(channel + (colors[segment + 1][index] - channel) * weight)
      .toString(16).padStart(2, '0')).join('');
  }

  function readCells(document) {
    const metadata = document && document.metadata;
    const collection = document && document.geojson;
    if (!metadata || metadata.cell_size_m !== 5 || !Number.isInteger(metadata.route_count) || metadata.route_count < 1
        || !collection || collection.type !== 'FeatureCollection' || !Array.isArray(collection.features)
        || !collection.features.length || collection.features.length !== metadata.cell_count) {
      throw new Error('Missing or invalid aggregate map data');
    }
    const bounds = [Infinity, Infinity, -Infinity, -Infinity];
    let maximum = 0;
    const cells = collection.features.map(feature => {
      const count = feature.properties && feature.properties.route_count;
      const geometry = feature.geometry;
      if (feature.type !== 'Feature' || !Number.isInteger(count) || count < 1 || count > metadata.route_count
          || !geometry || geometry.type !== 'Polygon' || !Array.isArray(geometry.coordinates)
          || geometry.coordinates.length !== 1 || !Array.isArray(geometry.coordinates[0]) || geometry.coordinates[0].length !== 5) {
        throw new Error('Invalid aggregate map cell');
      }
      const points = geometry.coordinates[0].map(project);
      if (points[0][0] !== points[4][0] || points[0][1] !== points[4][1]) throw new Error('Map cell is not closed');
      points.forEach(([x, y]) => {
        bounds[0] = Math.min(bounds[0], x); bounds[1] = Math.min(bounds[1], y);
        bounds[2] = Math.max(bounds[2], x); bounds[3] = Math.max(bounds[3], y);
      });
      maximum = Math.max(maximum, count);
      return { count, points };
    });
    if (maximum !== metadata.max_count || bounds[0] === bounds[2] || bounds[1] === bounds[3]) {
      throw new Error('Aggregate map summary disagrees with its cells');
    }
    return { cells, bounds, maximum, routeCount: metadata.route_count };
  }

  function initialize(container) {
    if (container.dataset.mapInitialized) return;
    container.dataset.mapInitialized = 'true';
    const status = container.querySelector('[data-map-status]');
    const svg = container.querySelector('[data-route-map-svg]');
    const tilesGroup = container.querySelector('[data-map-tiles]');
    const cellsGroup = container.querySelector('[data-map-cells]');
    const dataScript = container.querySelector('[data-route-cells]');
    let parsed;
    try {
      if (!svg || !tilesGroup || !cellsGroup || !dataScript || !status) throw new Error('Map elements are missing');
      parsed = readCells(JSON.parse(dataScript.textContent));
    } catch (_error) {
      if (status) status.textContent = 'The route map could not load. Aggregate coverage figures remain available above.';
      container.querySelectorAll('button, input').forEach(control => { control.disabled = true; });
      return;
    }

    const makeSvg = (name, attributes = {}) => {
      const element = document.createElementNS(SVG_NS, name);
      Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
      return element;
    };
    // Local SVG units avoid subpixel rounding of tiny normalized-world polygons.
    // Map math stays in Mercator; tiles, cells and viewport share this transform.
    const svgScale = 2 ** 24;
    const svgX = x => (x - parsed.bounds[0]) * svgScale;
    const svgY = y => (y - parsed.bounds[1]) * svgScale;
    const fragment = document.createDocumentFragment();
    parsed.cells.forEach(cell => {
      const polygon = makeSvg('polygon', {
        points: cell.points.map(([x, y]) => `${svgX(x)},${svgY(y)}`).join(' '),
        fill: cellColor(cell.count, parsed.maximum), 'fill-opacity': 0.85, 'data-count': cell.count,
      });
      const title = makeSvg('title');
      title.textContent = `${cell.count} checklist routes · 5 m × 5 m`;
      polygon.appendChild(title);
      fragment.appendChild(polygon);
    });
    cellsGroup.replaceChildren(fragment);
    tilesGroup.setAttribute('aria-hidden', 'true');
    tilesGroup.setAttribute('pointer-events', 'none');
    svg.style.width = '100%';
    svg.style.height = `${HEIGHT}px`;
    svg.style.display = 'block';
    svg.style.touchAction = 'none';
    svg.style.userSelect = 'none';
    svg.style.webkitUserSelect = 'none';
    svg.style.cursor = 'grab';
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    const tiles = new Map();
    let view;
    let width = 0;
    let drag = null;
    let frame = 0;
    let hoverTimer = 0;
    let announcementTimer = 0;
    let tileFailure = false;
    const summary = `${parsed.cells.length.toLocaleString()} cells from ${parsed.routeCount.toLocaleString()} checklist routes.`;
    const say = text => {
      const message = text + (tileFailure ? ' Base map tiles could not load; route cells remain visible.' : '');
      if (status.textContent !== message) status.textContent = message;
    };
    const announceMovement = text => {
      clearTimeout(announcementTimer);
      announcementTimer = setTimeout(() => say(text), 180);
    };
    const render = () => {
      frame = 0;
      if (!view) return;
      svg.setAttribute('viewBox', `${svgX(view.x)} ${svgY(view.y)} ${view.w * svgScale} ${view.h * svgScale}`);
      const wanted = tileRequests(view, width);
      const urls = new Set(wanted.map(tile => tile.url));
      tiles.forEach((image, url) => {
        if (!urls.has(url)) { image.remove(); tiles.delete(url); }
      });
      wanted.forEach(tile => {
        if (tiles.has(tile.url)) return;
        const image = makeSvg('image', { x: svgX(tile.x), y: svgY(tile.y), width: tile.size * svgScale, height: tile.size * svgScale,
          preserveAspectRatio: 'none', href: tile.url });
        image.addEventListener('error', () => {
          if (!tileFailure) { tileFailure = true; say(summary); }
        }, { once: true });
        tilesGroup.appendChild(image);
        tiles.set(tile.url, image);
      });
    };
    const scheduleRender = () => {
      if (!frame) frame = requestAnimationFrame(render);
    };
    const reset = () => {
      if (!width) return;
      view = fitBounds(parsed.bounds, width, HEIGHT, 24);
      scheduleRender();
    };
    const resize = () => {
      const measured = svg.getBoundingClientRect().width;
      if (measured <= 48 || Math.abs(measured - width) < 0.5) return;
      width = measured;
      reset();
    };
    const directions = { north: [0, -0.2], south: [0, 0.2], west: [-0.2, 0], east: [0.2, 0] };
    const act = action => {
      if (!view) return;
      if (action === 'reset') { reset(); announceMovement(`Map reset. ${summary}`); return; }
      if (action === 'in' || action === 'out') {
        view = zoomView(view, action === 'in' ? 0.5 : 2, width, HEIGHT);
        announceMovement(`Map zoomed ${action}.`);
      } else if (directions[action]) {
        const [dx, dy] = directions[action];
        view = panView(view, dx * view.w, dy * view.h);
        announceMovement(`Map moved ${action}.`);
      } else return;
      scheduleRender();
    };
    container.querySelectorAll('[data-map-action]').forEach(button => {
      button.addEventListener('click', () => act(button.dataset.mapAction));
    });
    const overlay = container.querySelector('[data-map-overlay]');
    if (overlay) {
      const updateOverlay = () => {
        cellsGroup.style.visibility = overlay.checked ? 'visible' : 'hidden';
        clearTimeout(hoverTimer);
        say(overlay.checked ? `Route cells shown. ${summary}` : 'Route cells hidden. Base map remains visible.');
      };
      overlay.addEventListener('change', updateOverlay);
      cellsGroup.style.visibility = overlay.checked ? 'visible' : 'hidden';
    }
    svg.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const actions = { ArrowUp: 'north', ArrowDown: 'south', ArrowLeft: 'west', ArrowRight: 'east',
        '+': 'in', '=': 'in', '-': 'out', _: 'out', Home: 'reset' };
      if (actions[event.key]) { event.preventDefault(); act(actions[event.key]); }
    });
    const countAt = target => target && target.closest ? target.closest('[data-count]')?.getAttribute('data-count') : null;
    const showCount = count => {
      clearTimeout(announcementTimer);
      say(`${count} checklist routes crossed this 5 m × 5 m cell.`);
    };
    cellsGroup.addEventListener('pointerover', event => {
      if (drag) return;
      clearTimeout(hoverTimer);
      const count = countAt(event.target);
      if (count) hoverTimer = setTimeout(() => showCount(count), 250);
    });
    svg.addEventListener('pointerleave', () => clearTimeout(hoverTimer));
    svg.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !event.isPrimary || !view) return;
      clearTimeout(hoverTimer);
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, view: { ...view },
        count: countAt(event.target), moved: false };
      svg.setPointerCapture(event.pointerId);
      svg.style.cursor = 'grabbing';
    });
    svg.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (Math.hypot(dx, dy) > 4) drag.moved = true;
      if (!drag.moved) return;
      view = panView(drag.view, -dx / width * drag.view.w, -dy / HEIGHT * drag.view.h);
      scheduleRender();
    });
    svg.addEventListener('pointerup', event => {
      if (!drag || event.pointerId !== drag.id) return;
      if (!drag.moved && drag.count) showCount(drag.count);
      else if (drag.moved) announceMovement('Map moved. Use Reset view to show all route cells.');
      drag = null;
      if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
      svg.style.cursor = 'grab';
    });
    const endDrag = () => { drag = null; svg.style.cursor = 'grab'; };
    svg.addEventListener('pointercancel', endDrag);
    svg.addEventListener('lostpointercapture', endDrag);
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(resize).observe(svg);
    else window.addEventListener('resize', resize);
    resize();
    say(summary);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { project, fitBounds, zoomView, panView, tileRequests, cellColor, readCells, initialize };
  }
  if (typeof document !== 'undefined') {
    const start = () => document.querySelectorAll('[data-bird-route-map]').forEach(initialize);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
  }
})();
