import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { summarizeYardmic } from '../src/yardmic.mjs';

const script = fs.readFileSync(new URL('../assets/yardmic.js', import.meta.url), 'utf8');
const raw = JSON.parse(fs.readFileSync(new URL('fixtures/yardmic-2026-11-15--18.json', import.meta.url)));
const sample = () => summarizeYardmic(raw, { now: '2026-11-18T17:47:57.203Z' });

// A small DOM boundary keeps these behavioral tests independent of browser tooling.
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attributes = {}; this.listeners = {}; this.style = {}; this.value = ''; this.scrollLeft = 0; this.scrollTop = 0; }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.value = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  get lastElementChild() { return this.children.at(-1); }
  get open() { return 'open' in this.attributes; }
  set open(value) { if (value) this.setAttribute('open', ''); else delete this.attributes.open; }
  contains(node) { return descendants(this).includes(node); }
  querySelectorAll(selector) {
    return descendants(this).slice(1).filter(node => selector === '[data-mic-state]'
      ? 'data-mic-state' in node.attributes
      : selector.split(', ').some(part => part === node.tagName || (part.startsWith('.') && hasClass(node, part.slice(1)))));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
}
const descendants = node => [node, ...node.children.flatMap(descendants)];
const hasClass = (node, name) => node.className?.split(' ').includes(name);
const defaultText = node => {
  if (hasClass(node, 'sr-only')) return '';
  const children = node.tagName === 'details' && !('open' in node.attributes)
    ? node.children.filter(child => child.tagName === 'summary') : node.children;
  return [node.value, ...children.map(defaultText)].join(' ');
};
const tableRows = table => descendants(table).filter(node => node.tagName === 'tr' && node.children.some(child => child.attributes.scope === 'row'));
const tableCells = table => descendants(table).filter(node => node.tagName === 'td');
const barWidths = table => descendants(table).filter(node => hasClass(node, 'mic-bar-fill')).map(node => Number.parseFloat(node.style.width));
const assertWidths = (actual, expected) => {
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9, `${value} should equal ${expected[index]}`));
};

async function page(data = sample()) {
  const ids = ['bird-microphone', 'mic-recent-title', 'mic-window', 'mic-recent-content', 'mic-update-status', 'mic-kingfisher-title', 'mic-kingfisher-content', 'mic-pattern-content', 'mic-pattern-coverage'];
  const nodes = Object.fromEntries(ids.map(id => { const node = new Element('div'); node.id = id; return [id, node]; }));
  const refresh = new Element('button');
  nodes['bird-microphone'].querySelector = () => refresh;
  let failed = false;
  let now = Date.parse('2026-11-18T17:47:57.203Z');
  const intervals = new Map();
  const document = {
    activeElement: null,
    getElementById: id => Object.values(nodes).flatMap(descendants).find(node => node.id === id),
    createElement(tag) {
      const node = new Element(tag);
      node.focus = () => { document.activeElement = node; };
      return node;
    },
    addEventListener() {},
  };
  const context = {
    Intl, Date: class extends Date { static now() { return now; } }, AbortController, performance: { now: () => 0 },
    document,
    fetch: async () => { if (failed) throw new Error('offline'); return { ok: true, json: async () => data }; },
    setTimeout: () => 0, clearTimeout() {}, setInterval: (callback, delay) => intervals.set(delay, callback),
  };
  vm.runInNewContext(script, context);
  await new Promise(resolve => setImmediate(resolve));
  return {
    nodes, refresh, document,
    fail: () => { failed = true; },
    recover: () => { failed = false; },
    respondWith: payload => { data = payload; },
    advanceWallClock: milliseconds => { now += milliseconds; },
    tickCounter: () => intervals.get(30000)(),
    find: name => Object.values(nodes).flatMap(descendants).filter(node => hasClass(node, name)),
  };
}

test('recent rows share 60 minute positions and expose the count and times accessibly', async () => {
  const data = sample();
  const ui = await page(data);
  const strips = ui.find('mic-timeline');
  assert.equal(strips.length, data.recentHour.species.length);
  for (const [i, strip] of strips.entries()) {
    const bird = data.recentHour.species[i];
    assert.equal(strip.children.length, 60);
    assert.equal(strip.attributes.role, 'img');
    assert.match(strip.attributes['aria-label'], new RegExp(`${bird.detectedMinutes} detected minute`));
    assert.equal(strip.attributes['aria-describedby'], 'mic-timeline-legend');
    const detected = strip.children.flatMap((node, index) => hasClass(node, 'is-detected') ? [index] : []);
    const first = Math.floor(Date.parse(data.recentHour.end) / 60000) * 60000 - 59 * 60000;
    assert.deepEqual(detected, bird.minuteStarts.map(time => (Date.parse(time) - first) / 60000));
  }
  assert.match(ui.nodes['mic-recent-content'].textContent, /Blank spaces.*silence/);
});

test('reviewed and auto records have no badge; only another displayed status is Unreviewed', async () => {
  const data = sample();
  let ui = await page(data);
  assert.equal(ui.find('mic-badge').length, 0);
  assert.equal(ui.nodes['mic-kingfisher-title'].textContent, 'Last Belted Kingfisher detected');
  data.recentHour.species[0].status = 'pending';
  ui = await page(data);
  assert.deepEqual(ui.find('mic-badge').map(node => node.textContent), ['Unreviewed']);
});

test('failed refresh keeps the original timeline window and marks it delayed', async () => {
  const ui = await page();
  const window = ui.nodes['mic-window'].textContent;
  const strips = ui.find('mic-timeline').map(node => node.attributes['aria-label']);
  ui.fail();
  await ui.refresh.listeners.click();
  assert.equal(ui.nodes['mic-recent-title'].textContent, 'Recently heard');
  assert.equal(ui.nodes['mic-window'].textContent, window);
  assert.deepEqual(ui.find('mic-timeline').map(node => node.attributes['aria-label']), strips);
  assert.match(ui.nodes['mic-update-status'].textContent, /Updates delayed/);
});

test('elapsed hours include sleep after a failed refresh and rebase on the next response', async () => {
  const data = sample();
  data.kingfisher.elapsedMinutes = 120;
  const ui = await page(data);
  const hours = () => ui.document.getElementById('mic-hours').textContent;
  const window = ui.nodes['mic-window'].textContent;
  const strips = ui.find('mic-timeline').map(node => node.attributes['aria-label']);
  assert.equal(hours(), '2.0');
  ui.advanceWallClock(3600000);
  ui.fail();
  await ui.refresh.listeners.click();
  assert.equal(hours(), '3.0');
  assert.equal(ui.nodes['mic-window'].textContent, window);
  assert.deepEqual(ui.find('mic-timeline').map(node => node.attributes['aria-label']), strips);
  ui.recover();
  data.kingfisher.elapsedMinutes = 30;
  await ui.refresh.listeners.click();
  assert.equal(hours(), '0.5');
  ui.advanceWallClock(3600000);
  ui.tickCounter();
  assert.equal(hours(), '1.5');
});

test('an incomplete successful HTTP response preserves the last elapsed-time baseline', async () => {
  const data = sample();
  data.kingfisher.elapsedMinutes = 120;
  const ui = await page(data);
  const window = ui.nodes['mic-window'].textContent;
  ui.advanceWallClock(3600000);
  ui.respondWith({ state: 'available' });
  await ui.refresh.listeners.click();
  assert.equal(ui.document.getElementById('mic-hours').textContent, '3.0');
  assert.equal(ui.nodes['mic-window'].textContent, window);
  assert.match(ui.nodes['mic-update-status'].textContent, /Updates delayed/);
});

test('missing timestamp positions use a text fallback rather than an empty strip', async () => {
  const data = sample();
  delete data.recentHour.species[0].minuteStarts;
  const ui = await page(data);
  assert.equal(ui.find('mic-timeline').length, data.recentHour.species.length - 1);
  assert.match(ui.nodes['mic-recent-content'].textContent, /4 detected minutes.*Timeline unavailable/);
});

test('all eligible species render without a display cap', async () => {
  const data = sample();
  data.recentHour.species = Array.from({ length: 32 }, (_, i) => ({ ...data.recentHour.species[0], code: `bird${i}`, name: `Bird ${i}` }));
  const ui = await page(data);
  assert.equal(ui.find('mic-bird').length, 32);
  assert.equal(ui.find('mic-timeline').length, 32);
  assert.match(ui.nodes['mic-recent-content'].textContent, /32 species/);
});

test('an empty partial window shows missing-data copy rather than an empty activity strip', async () => {
  const data = sample();
  data.recentHour.species = [];
  data.recentHour.state = 'partial';
  const ui = await page(data);
  assert.equal(ui.find('mic-timeline').length, 0);
  assert.match(ui.nodes['mic-recent-content'].textContent, /available portion.*Some records are missing/);
});

test('source cache time stays distinct from fetch time and survives failed refresh', async () => {
  const data = sample();
  data.freshness.recent.sourceCache = { ageSecondsAtRetrieval: 300, cachedAt: '2026-11-18T17:42:57.203Z', maxAgeSeconds: 900 };
  const ui = await page(data);
  const note = ui.nodes['mic-update-status'].textContent;
  assert.match(note, /Data fetched.*12:47 PM EST/);
  assert.match(note, /Estimated YardMic response time:.*12:42 PM EST/);
  assert.match(note, /cached responses as fresh for 15 minutes/);
  ui.fail();
  await ui.refresh.listeners.click();
  assert.match(ui.nodes['mic-update-status'].textContent, /Estimated YardMic response time:.*12:42 PM EST/);
});

test('composition table exposes every species and hour with detection-day values', async () => {
  const data = sample();
  data.patterns.speciesHours = Array.from({ length: 32 }, (_, i) => ({ code: `bird${i}`, name: `Bird ${i}`, detectedDates: 3, peakHour: 6, daysByHour: Array.from({ length: 24 }, (_, hour) => hour === 6 ? 3 : 0) }));
  const ui = await page(data);
  const table = ui.find('mic-composition-table')[0];
  assert.ok(table, 'the species-by-hour table is rendered');
  const nodes = descendants(table);
  const columns = nodes.filter(node => node.tagName === 'th' && node.attributes.scope === 'col');
  const names = nodes.filter(node => node.tagName === 'th' && node.attributes.scope === 'row');
  const cells = nodes.filter(node => node.tagName === 'td');
  assert.equal(columns.length, 25);
  assert.deepEqual(names.map(node => node.textContent), data.patterns.speciesHours.map(bird => bird.name));
  assert.equal(cells.length, 32 * 24);
  assert.equal(cells[6].textContent, '3');
  assert.match(cells[6].attributes['aria-label'], /3 dates with detections/);
  assert.match(cells[0].attributes['aria-label'], /No accepted detection.*coverage unknown/);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /All 32 species/);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /Nov 11–Nov 17/);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /3 of 7 dates returned/);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /Records returned: Nov 15, Nov 16, Nov 17/);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /most frequently detected hour/);
  assert.equal(ui.find('mic-composition-scroll')[0].attributes.tabindex, '0');
});

test('composition replaces the recurring-hour card and preserves After dark evidence', async () => {
  const data = sample();
  data.patterns.speciesHours = [{ code: 'example', name: 'Example bird', daysByHour: Array(24).fill(1), detectedDates: 3, peakHour: 0 }];
  const ui = await page(data);
  const text = ui.nodes['mic-pattern-content'].textContent;
  assert.match(text, /Daily rhythms/);
  assert.doesNotMatch(text, /Black-capped Chickadee, 3 pm/);
  assert.match(text, /After dark, before dawn/);
  for (const bird of data.patterns.overnight.slice(0, 5)) assert.ok(text.includes(bird.name));
  assert.match(text, /calendar date, rather than by complete night/);
  ui.fail();
  await ui.refresh.listeners.click();
  assert.equal(ui.find('mic-composition-table').length, 1);
  assert.match(ui.nodes['mic-pattern-coverage'].textContent, /out of date/);
});

test('empty or unavailable composition stays explicit without implying silence', async () => {
  const data = sample();
  data.patterns.speciesHours = [];
  let ui = await page(data);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /No accepted detections.*does not establish silence/);
  assert.equal(ui.find('mic-composition-table').length, 0);
  delete data.patterns.speciesHours;
  ui = await page(data);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /Hourly composition is unavailable/);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /After dark, before dawn/);
});

test('unchanged pattern refresh preserves the table being read or scrolled', async () => {
  const data = sample();
  data.patterns.speciesHours = [{ code: 'example', name: 'Example bird', daysByHour: Array(24).fill(1), detectedDates: 3, peakHour: 0 }];
  const ui = await page(data);
  const table = ui.find('mic-composition-table')[0];
  await ui.refresh.listeners.click();
  assert.equal(ui.find('mic-composition-table')[0], table);
  ui.fail();
  await ui.refresh.listeners.click();
  assert.equal(ui.find('mic-composition-table')[0], table);
  assert.match(ui.nodes['mic-pattern-coverage'].textContent, /out of date/);
});

function insightSample() {
  const coverage = (start, end, recorded = 4) => {
    const dates = Array.from({ length: 7 }, (_, offset) => {
      const date = new Date(`${start}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + offset);
      return date.toISOString().slice(0, 10);
    });
    return { range: { start, end }, returnedDates: dates, recordedDates: dates.slice(0, recorded), noRecordingDates: dates.slice(recorded), missingDates: [], detectionOnlyDates: [], listeningMinutes: recorded * 600 };
  };
  return {
    weekly: {
      state: 'comparable', minimumRecordedDays: 4,
      weeks: [coverage('2026-10-21','2026-10-27'), coverage('2026-10-28','2026-11-03'), coverage('2026-11-04','2026-11-10'), coverage('2026-11-11','2026-11-17')],
      species: [
        {code:'increase',name:'Increasing Bird',detectedDays:[1,1,1,4],firstDetectedDate:'2026-10-21',change:'more-often',deltaFraction:.75},
        {code:'first',name:'First Record Bird',detectedDays:[0,0,0,3],firstDetectedDate:'2026-11-12',change:'first-in-window',deltaFraction:.75},
        {code:'decrease',name:'Decreasing Bird',detectedDays:[4,4,4,1],firstDetectedDate:'2026-10-21',change:'less-often',deltaFraction:-.75},
      ],
    },
    dayparts: {
      state:'available',minimumRecordedDays:3,coverage:coverage('2026-11-11','2026-11-17',3),
      periods:[{id:'morning',label:'Morning',startHour:6,endHour:10},{id:'midday',label:'Midday',startHour:10,endHour:14},{id:'afternoon',label:'Afternoon',startHour:14,endHour:18}],
      species:[
        {code:'belkin1',name:'Belted Kingfisher',daysByPeriod:[0,1,1],detectedDates:1,group:'mixed'},
        {code:'bkcchi',name:'Black-capped Chickadee',daysByPeriod:[3,3,3],detectedDates:3,group:'all-day'},
        {code:'pileat',name:'Pileated Woodpecker',daysByPeriod:[1,0,3],detectedDates:3,group:'afternoon'},
      ],
    },
  };
}

test('changed patterns preserve open disclosures, chart positions and focus', async () => {
  const data = sample();
  data.insights = insightSample();
  const ui = await page(data);
  const weeklyDetails = () => ui.find('mic-insight-details')[0];
  const daypartDetails = () => ui.find('mic-insight-details')[1];
  const about = () => ui.find('mic-insight-about')[0];
  const chart = () => ui.find('mic-composition-scroll')[0];
  const weeklyChart = () => ui.find('mic-insight-scroll')[0];
  weeklyDetails().open = true;
  about().open = true;
  chart().scrollLeft = 60;
  chart().scrollTop = 25;
  weeklyChart().scrollLeft = 100;
  weeklyChart().focus();
  data.insights.weekly.weeks[0].listeningMinutes += 60;
  await ui.refresh.listeners.click();
  assert.match(about().textContent, /41\.0 reported hours/);
  assert.ok(weeklyDetails().open);
  assert.ok(about().open);
  assert.ok(!daypartDetails().open);
  assert.equal(chart().scrollLeft, 60);
  assert.equal(chart().scrollTop, 25);
  assert.equal(weeklyChart().scrollLeft, 100);
  assert.equal(ui.document.activeElement, weeklyChart());

  about().children[0].focus();
  data.insights.weekly.weeks[0].listeningMinutes += 60;
  await ui.refresh.listeners.click();
  assert.equal(ui.document.activeElement, about().children[0]);

  ui.document.activeElement = ui.refresh;
  data.insights.weekly.weeks[0].listeningMinutes += 60;
  await ui.refresh.listeners.click();
  assert.equal(ui.document.activeElement, ui.refresh);
});

test('focus moves to a heading when a refreshed comparison removes its chart', async () => {
  const data = sample();
  const ui = await page(data);
  ui.find('mic-composition-scroll')[0].focus();
  data.patterns.speciesHours = [];
  await ui.refresh.listeners.click();
  assert.equal(ui.document.activeElement.textContent, 'Daily rhythms');
  assert.equal(ui.document.activeElement.attributes.tabindex, '-1');
});

test('coverage dots describe the exact dates in About this data, including empty weeks', async () => {
  const data = sample();
  data.insights = insightSample();
  const { weekly } = data.insights;
  weekly.state = 'insufficient';
  weekly.weeks[0].recordedDates = ['2026-10-21', '2026-10-24'];
  weekly.weeks[1].recordedDates = [];
  const ui = await page(data);
  const strip = ui.find('mic-history-strip')[0];
  const notes = ui.find('mic-insight-about')[0];
  const description = (strip.attributes['aria-describedby'] ?? '').split(' ').map(id => ui.document.getElementById(id));
  assert.ok(description.every(week => week && notes.contains(week)));
  assert.deepEqual(description.map(week => week.textContent.match(/Recorded dates: (.*)\.$/)?.[1]), [
    'Oct 21, Oct 24', 'none', 'Nov 4, Nov 5, Nov 6, Nov 7', 'Nov 11, Nov 12, Nov 13, Nov 14',
  ]);
  assert.ok(!notes.open);
  assert.doesNotMatch(defaultText(notes), /Recorded dates/);
});

test('weekly trend bars use each week’s recorded-day denominator and retain exact comparisons', async () => {
  const data = sample(); data.insights = insightSample();
  data.insights.weekly.weeks[1].recordedDates = [...data.insights.weekly.weeks[1].returnedDates];
  data.insights.weekly.weeks[1].noRecordingDates = [];
  const ui = await page(data), weekly = ui.find('mic-weekly')[0];
  const text = defaultText(weekly);
  assert.match(text, /Who’s becoming a regular/);
  assert.match(text, /More often/); assert.match(text, /Less often/); assert.match(text, /First in this window/);
  assert.doesNotMatch(text, /arrived|first-ever|abundance increased/i);
  const visual = ui.find('mic-week-trends')[0];
  assert.equal(tableRows(visual).length, 3);
  const increasing = tableRows(visual).find(row => row.children[0].textContent.startsWith('Increasing Bird'));
  assertWidths(barWidths(increasing), [25, 100 / 7, 25, 100]);
  assert.deepEqual(tableCells(increasing).map(cell => cell.textContent), ['1/4', '1/7', '1/4', '4/4']);
  assert.deepEqual(tableCells(increasing).map(cell => cell.attributes['aria-label']), [
    '1 of 4 recorded days with detections', '1 of 7 recorded days with detections',
    '1 of 4 recorded days with detections', '4 of 4 recorded days with detections',
  ]);
  const first = tableRows(visual).find(row => row.children[0].textContent.startsWith('First Record Bird'));
  assert.match(first.children[0].title, /Nov 12.*not an arrival date/);
  const complete = ui.find('mic-weekly-table')[0];
  assert.equal(tableRows(complete).length, 3);
  assert.deepEqual(tableCells(complete).map(cell => cell.textContent), ['1/4','1/7','1/4','4/4','0/4','0/7','0/4','3/4','4/4','4/7','4/4','1/4']);
});

test('sparse weekly history shows actual recorded-date dots and repeats without inventing trends', async () => {
  const data = sample(); data.insights = insightSample();
  const weekly = data.insights.weekly; weekly.state = 'insufficient';
  weekly.weeks.forEach((week, index) => {
    week.recordedDates = index === 3 ? ['2026-11-15', '2026-11-16', '2026-11-17'] : [];
    week.noRecordingDates = week.returnedDates.filter(date => !week.recordedDates.includes(date));
    week.listeningMinutes = week.recordedDates.length * 600;
  });
  weekly.species.forEach(bird => { bird.change = 'insufficient'; bird.detectedDays = [0, 0, 0, Math.min(3, bird.detectedDays[3])]; });
  const ui = await page(data), panel = ui.find('mic-weekly')[0], text = defaultText(panel);
  assert.match(text, /Building history/); assert.match(text, /More recorded days.*before comparing weeks/);
  assert.match(text, /Showing up again/);
  assert.doesNotMatch(text, /More often|Less often|First in this window|reported hours|dates returned|percentage points/);
  assert.equal(ui.find('mic-week-trends').length, 0);
  assert.equal(ui.find('mic-history-dot').length, 28);
  const recorded = ui.find('mic-history-dot').filter(dot => hasClass(dot, 'is-recorded'));
  assert.deepEqual(recorded.map(dot => dot.title), ['Nov 15: recording evidence', 'Nov 16: recording evidence', 'Nov 17: recording evidence']);
  assert.match(ui.find('mic-history-strip')[0].attributes['aria-label'], /Unfilled dots have no recording evidence/);
  assert.deepEqual(ui.find('mic-repeat-count').map(node => node.textContent), ['3/3', '3/3']);
  assert.equal(tableRows(ui.find('mic-weekly-table')[0]).length, weekly.species.length);
  assert.ok(tableCells(ui.find('mic-weekly-table')[0]).some(cell => cell.textContent === '—'));
});

test('daypart visual aligns periods on a shared scale with exact visible and accessible counts', async () => {
  const data = sample(); data.insights = insightSample();
  const ui = await page(data), panel = ui.find('mic-dayparts')[0], text = defaultText(panel);
  assert.match(text, /Days detected.*out of 3 recorded days/);
  assert.match(text, /6 am–10 am/); assert.match(text, /10 am–2 pm/); assert.match(text, /2 pm–6 pm/);
  assert.match(text, /Across all three periods/);
  assert.match(text, /coverage within each period is unknown/);
  assert.equal(ui.find('mic-period-card').length, 0);
  const visual = ui.find('mic-daypart-visual')[0];
  assert.deepEqual(tableRows(visual).map(row => row.children[0].textContent), ['Pileated Woodpecker', 'Black-capped Chickadee']);
  assert.deepEqual(tableCells(visual).map(cell => cell.textContent), ['1', '0', '3', '3', '3', '3']);
  assertWidths(barWidths(visual), [100 / 3, 0, 100, 100, 100, 100]);
  assert.deepEqual(tableCells(visual).slice(0, 3).map(cell => cell.attributes['aria-label']), [
    '1 of 3 recorded days with detections', '0 of 3 recorded days with detections', '3 of 3 recorded days with detections',
  ]);
  assert.equal(tableRows(ui.find('mic-daypart-table')[0]).length, 3);
  assert.match(ui.nodes['mic-pattern-content'].textContent, /After dark, before dawn/);
});

test('daypart highlights are bounded while the complete comparison retains every species', async () => {
  const data = sample(); data.insights = insightSample();
  data.insights.dayparts.species = ['morning', 'midday', 'afternoon', 'all-day'].flatMap((group, index) =>
    Array.from({ length: 3 }, (_, number) => ({
      code: `${group}${number}`, name: `${group} bird ${number + 1}`, group, detectedDates: 3,
      daysByPeriod: group === 'all-day' ? [3, 3, 3] : [0, 1, 2].map(period => period === index ? 3 : 0),
    })));
  const ui = await page(data), visual = ui.find('mic-daypart-visual')[0];
  assert.equal(tableRows(visual).length, 8);
  assert.deepEqual(tableRows(visual).map(row => row.children[0].textContent), [
    'morning bird 1', 'morning bird 2', 'midday bird 1', 'midday bird 2',
    'afternoon bird 1', 'afternoon bird 2', 'all-day bird 1', 'all-day bird 2',
  ]);
  assert.equal(tableRows(ui.find('mic-daypart-table')[0]).length, 12);
});

test('recording details and selection rules live in one closed shared About disclosure', async () => {
  const data = sample(); data.insights = insightSample();
  const ui = await page(data), notes = ui.find('mic-insight-about');
  assert.equal(notes.length, 1);
  assert.equal(notes[0].tagName, 'details');
  assert.equal(notes[0].children[0].textContent, 'About this data');
  assert.equal(notes[0].attributes.open, undefined);
  const defaultPanels = defaultText(ui.find('mic-weekly')[0]) + defaultText(ui.find('mic-dayparts')[0]);
  for (const pattern of [/reported hours/, /dates returned/, /no recording evidence/, /missing/, /percentage points/, /at least 4 recorded days/, /at least half/]) {
    assert.doesNotMatch(defaultPanels, pattern);
    assert.match(notes[0].textContent, pattern);
  }
  const before = ui.find('mic-daypart-visual')[0];
  notes[0].setAttribute('open', '');
  await ui.refresh.listeners.click();
  assert.equal(ui.find('mic-insight-about')[0], notes[0]);
  assert.equal(ui.find('mic-daypart-visual')[0], before);
  assert.equal(notes[0].attributes.open, '');
});

test('insufficient and empty histories do not fabricate contrasts or divide by zero', async () => {
  const data = sample(); data.insights = insightSample();
  data.insights.dayparts.state = 'insufficient';
  data.insights.dayparts.coverage.recordedDates = ['2026-11-15'];
  let ui = await page(data);
  assert.match(defaultText(ui.find('mic-dayparts')[0]), /Building history.*more recorded days/);
  assert.equal(ui.find('mic-daypart-visual').length, 0);
  assert.match(ui.find('mic-insight-about')[0].textContent, /At least 3 recorded days/);
  data.insights.weekly.state = 'insufficient';
  data.insights.weekly.weeks.forEach(week => { week.recordedDates = []; week.noRecordingDates = [...week.returnedDates]; week.listeningMinutes = 0; });
  data.insights.weekly.species = [];
  data.insights.dayparts.coverage.recordedDates = [];
  data.insights.dayparts.species = [];
  ui = await page(data);
  assert.equal(ui.find('mic-history-dot').filter(dot => hasClass(dot, 'is-recorded')).length, 0);
  assert.equal(ui.find('mic-bar-fill').length, 0);
  assert.equal(ui.find('mic-week-trends').length, 0);
  assert.equal(ui.find('mic-daypart-visual').length, 0);
  assert.doesNotMatch(ui.nodes['mic-pattern-content'].textContent, /NaN|Infinity/);
});

test('recent timeline labels its fixed snapshot window rather than the current hour', async () => {
  const data=sample();
  data.recentHour.windowBasis='source-response-estimate';
  data.recentHour.snapshotEstimatedAt=data.recentHour.end;
  const ui=await page(data);
  assert.equal(ui.nodes['mic-recent-title'].textContent,'Recently heard');
  assert.match(ui.nodes['mic-window'].textContent,/estimated time window/);
  assert.match(ui.nodes['mic-update-status'].textContent,/recording coverage is not verified/);
});

test('unknown snapshot time does not invent a window or empty minute bins', async () => {
  const data=sample();
  data.recentHour.windowBasis='unknown';data.recentHour.start=null;data.recentHour.end=null;data.recentHour.species=[];
  const ui=await page(data);
  assert.equal(ui.find('mic-timeline').length,0);
  assert.match(ui.nodes['mic-window'].textContent,/Time range unavailable/);
  assert.match(ui.nodes['mic-recent-content'].textContent,/cannot place these records in a reliable one-hour window/);
  assert.doesNotMatch(ui.nodes['mic-window'].textContent,/1969|1970/);
});

test('retrieval-based window acknowledges source timing uncertainty', async () => {
  const data=sample();data.recentHour.windowBasis='retrieval-estimate';
  const ui=await page(data);
  assert.match(ui.nodes['mic-window'].textContent,/estimated from first retrieval/);
  assert.match(ui.nodes['mic-update-status'].textContent,/Source timing is unavailable/);
});
