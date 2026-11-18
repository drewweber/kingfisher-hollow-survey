/* Same-origin, public summaries only. All upstream labels become text nodes. */
(() => {
  'use strict';
  const root = document.getElementById('bird-microphone');
  if (!root) return;
  const byId = id => document.getElementById(id);
  const refresh = root.querySelector('[data-yardmic-refresh]');
  const zone = 'America/New_York';
  const clock = new Intl.DateTimeFormat('en-US', { timeZone: zone, hour: 'numeric', minute: '2-digit' });
  const stamp = new Intl.DateTimeFormat('en-US', { timeZone: zone, month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  const statusStamp = new Intl.DateTimeFormat('en-US', { timeZone: zone, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  const shortDate = new Intl.DateTimeFormat('en-US', { timeZone: zone, month: 'short', day: 'numeric' });
  const retentionMs = 30 * 86400000;
  const saved = { recent: null, history: null, kingfisher: null };
  let busy = false;
  let patternSignature = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  const dateLabel = date => shortDate.format(new Date(`${date}T12:00:00Z`));
  const plural = (n, singular, multiple = `${singular}s`) => `${n} ${n === 1 ? singular : multiple}`;
  const hourLabel = hour => `${hour % 12 || 12} ${hour < 12 ? 'am' : 'pm'}`;
  const badge = status => ['reviewed', 'auto'].includes(status) ? null : el('span', 'mic-badge', 'Unreviewed');

  function minuteTimeline(bird, recent) {
    const start = Date.parse(recent.start);
    const end = Date.parse(recent.end);
    const firstMinute = Math.floor(end / 60000) * 60000 - 59 * 60000;
    const detected = new Set((bird.minuteStarts ?? []).map(Date.parse)
      .filter(time => Number.isFinite(time) && time % 60000 === 0 && time > start && time <= end));
    if (!Array.isArray(bird.minuteStarts) || detected.size !== bird.detectedMinutes) {
      return el('p', 'mic-timeline-fallback', `${plural(bird.detectedMinutes, 'detected minute')} · Timeline unavailable`);
    }
    const strip = el('div', 'mic-timeline');
    strip.setAttribute('role', 'img');
    strip.setAttribute('aria-label', `${bird.name}: ${plural(detected.size, 'detected minute')}. ${stamp.format(new Date(firstMinute))} to ${stamp.format(new Date(end))}. Detected at ${[...detected].sort((a, b) => a - b).map(time => clock.format(new Date(time))).join(', ')}.`);
    strip.setAttribute('aria-describedby', 'mic-timeline-legend');
    for (let index = 0; index < 60; index += 1) {
      const time = firstMinute + index * 60000;
      const mark = el('span', `mic-minute${detected.has(time) ? ' is-detected' : ''}`);
      mark.setAttribute('aria-hidden', 'true');
      if (detected.has(time)) mark.title = `Detected at ${clock.format(new Date(time))}`;
      strip.append(mark);
    }
    return strip;
  }

  function renderCounter() {
    const hours = byId('mic-hours');
    if (!hours || !saved.kingfisher) return;
    const { elapsedMinutes, receivedAt } = saved.kingfisher;
    const minutes = Math.max(0, elapsedMinutes + (Date.now() - receivedAt) / 60000);
    hours.textContent = (minutes / 60).toFixed(1);
  }

  function kingfisherContent(data) {
    const target = el('div');
    const bird = data.kingfisher;
    const number = el('p', 'mic-counter');
    number.id = 'mic-hours';
    target.append(number, el('p', 'mic-counter-label', 'hours since this detection'));
    const when = el('time', 'mic-caption', stamp.format(new Date(bird.latestAt)));
    when.dateTime = bird.latestAt;
    target.append(when);
    const reviewBadge = badge(bird.status);
    if (reviewBadge) target.append(reviewBadge);
    if (data.range.returnedDates.length < 31) target.append(el('p', 'mic-caption', `History includes ${data.range.returnedDates.length} of 31 requested dates.`));
    return target;
  }

  function recentContent(data) {
    const recent = data.recentHour;
    const windowLabel = `${stamp.format(new Date(recent.start))} – ${stamp.format(new Date(recent.end))} · ${recent.windowBasis === 'retrieval-estimate' ? 'estimated from first retrieval' : 'estimated time window'}`;
    const target = el('div');
    if (!recent.species.length) {
      target.append(el('p', 'mic-empty', recent.state === 'partial'
        ? 'No accepted detections in the available portion of this hour. Some records are missing.'
        : 'No accepted detections in the returned records for this hour. This does not establish silence or absence.'));
    } else {
      const legend = el('p', 'mic-caption mic-timeline-legend', 'Each tall mark is one minute with a detection. Blank spaces do not establish silence or recording coverage.');
      legend.id = 'mic-timeline-legend';
      const axis = el('div', 'mic-timeline-header');
      axis.setAttribute('aria-hidden', 'true');
      const scale = el('div', 'mic-timeline-scale');
      const firstMinute = Math.floor(Date.parse(recent.end) / 60000) * 60000 - 59 * 60000;
      scale.append(el('span', '', clock.format(new Date(firstMinute))), el('span', '', clock.format(new Date(recent.end))));
      axis.append(el('span', '', `${plural(recent.species.length, 'species', 'species')}`), scale, el('span', 'mic-bird-time', 'Latest'));
      const list = el('ul', 'mic-birds');
      list.setAttribute('role', 'list');
      for (const bird of recent.species) {
        const row = el('li', 'mic-bird');
        const detail = el('div');
        detail.append(el('p', 'mic-bird-name', bird.name));
        const reviewBadge = badge(bird.status);
        if (reviewBadge) detail.append(reviewBadge);
        const last = el('div', 'mic-bird-time');
        const time = el('time', '', clock.format(new Date(bird.latestAt)));
        time.dateTime = bird.latestAt;
        last.append(el('span', 'sr-only', 'Latest detection: '), time);
        row.append(detail, minuteTimeline(bird, recent), last);
        list.append(row);
      }
      target.append(legend, axis, list);
      if (recent.state === 'partial') target.append(el('p', 'mic-caption', 'Some records for this hour are missing; this list covers the available portion.'));
    }
    if (recent.ambiguous) target.append(el('p', 'mic-caption', 'Detections with ambiguous repeated-clock times are omitted from this hour.'));
    const retrieved = data.freshness.recent.retrievedAt;
    const freshness = retrieved ? `Data fetched ${stamp.format(new Date(retrieved))}.` : 'Fetch time unavailable.';
    const sourceCache = data.freshness.recent.sourceCache;
    const cached = sourceCache?.cachedAt ? ` Estimated YardMic response time: ${stamp.format(new Date(sourceCache.cachedAt))}.` : '';
    const cacheLimit = sourceCache?.maxAgeSeconds > 0 ? ` YardMic treats cached responses as fresh for ${plural(Math.ceil(sourceCache.maxAgeSeconds / 60), 'minute')}.` : '';
    const latest = data.latestDetectionAt ? ` Latest accepted detection: ${stamp.format(new Date(data.latestDetectionAt))}.` : '';
    const windowNote = recent.windowBasis === 'retrieval-estimate'
      ? ' Source timing is unavailable; the window uses the first retrieval of these records. Recording coverage is not verified.'
      : ' The window follows an estimated source response; recording coverage is not verified.';
    return { target, windowLabel, detail: `${freshness}${cached}${cacheLimit}${latest}${windowNote}` };
  }

  function retainPatternState(node, id, fallbackId = '') {
    node.id = id;
    node.setAttribute('data-mic-state', fallbackId);
    return node;
  }

  function compositionPattern(patterns) {
    const panel = el('article', 'mic-pattern mic-composition');
    const heading = el('h3', '', 'Daily rhythms');
    heading.id = 'mic-composition-title';
    panel.append(heading);
    const birds = patterns.speciesHours;
    if (!birds.length) {
      panel.append(el('p', 'mic-pattern-lead', 'No accepted detections in these returned dates. This does not establish silence or absence. Try again as more records arrive.'));
      return panel;
    }
    panel.append(el('p', 'mic-pattern-lead', 'A brighter square means this species was detected in that hour on more dates. Each date counts once, however many calls were recorded.'));
    const metric = el('p', 'mic-caption', `${dateLabel(patterns.range.start)}–${dateLabel(patterns.range.end)} · ${patterns.dates.length} of 7 dates returned · Eastern time`);
    if (patterns.dates.length < 7) metric.append(el('span', 'mic-returned-dates', `Records returned: ${patterns.dates.map(dateLabel).join(', ')}.`));
    const legend = el('div', 'mic-composition-legend');
    legend.append(el('span', '', 'Dates with detections'));
    for (let days = 0; days <= 7; days += 1) {
      legend.append(el('span', `mic-heat-value mic-heat-${days}`, String(days)));
    }
    const order = el('p', 'mic-caption', `All ${plural(birds.length, 'species', 'species')}, ordered by their most frequently detected hour; ties use the earlier hour.`);
    const hint = el('p', 'mic-caption mic-composition-hint', `Scroll within the chart for all ${birds.length} species and 24 hours. Names and hour labels stay in view.`);
    hint.id = 'mic-composition-hint';
    const caveat = el('p', 'mic-caption', 'A dot means no accepted detection in the returned records. Hourly recording coverage is unknown; these are detection-day counts, not bird counts or continuous song.');
    caveat.id = 'mic-composition-note';
    const scroll = retainPatternState(el('div', 'mic-composition-scroll'), 'mic-composition-scroll', heading.id);
    scroll.setAttribute('tabindex', '0');
    scroll.setAttribute('role', 'region');
    scroll.setAttribute('aria-labelledby', heading.id);
    scroll.setAttribute('aria-describedby', `${hint.id} ${caveat.id}`);
    const table = el('table', 'mic-composition-table');
    table.append(el('caption', 'sr-only', `Species by hour: dates with accepted detections, ${dateLabel(patterns.range.start)}–${dateLabel(patterns.range.end)}. ${patterns.dates.length} of 7 dates returned. All times Eastern.`));
    const head = el('thead');
    const headRow = el('tr');
    const speciesHeader = el('th', '', 'Species');
    speciesHeader.setAttribute('scope', 'col');
    headRow.append(speciesHeader);
    for (let hour = 0; hour < 24; hour += 1) {
      const cell = el('th');
      cell.setAttribute('scope', 'col');
      cell.setAttribute('aria-label', `${hourLabel(hour)}–${hourLabel((hour + 1) % 24)} Eastern time`);
      cell.append(el('span', '', String(hour % 12 || 12)), el('span', 'mic-hour-period', hour < 12 ? 'am' : 'pm'));
      headRow.append(cell);
    }
    head.append(headRow);
    const body = el('tbody');
    for (const bird of birds) {
      const row = el('tr');
      const name = el('th', '', bird.name);
      name.setAttribute('scope', 'row');
      row.append(name);
      bird.daysByHour.forEach((days, hour) => {
        const cell = el('td', `mic-heat-value mic-heat-${days}`, days ? String(days) : '·');
        const value = days ? `${plural(days, 'date')} with detections` : 'No accepted detection; recording coverage unknown';
        cell.setAttribute('aria-label', value);
        cell.title = `${bird.name}, ${hourLabel(hour)}–${hourLabel((hour + 1) % 24)}: ${value}`;
        row.append(cell);
      });
      body.append(row);
    }
    table.append(head, body);
    scroll.append(table);
    panel.append(metric, legend, order, hint, scroll, caveat);
    return panel;
  }

  const rangeLabel = range => `${dateLabel(range.start)}–${dateLabel(range.end)}`;
  const occurrence = (count, recorded) => recorded ? `${count}/${recorded}` : '—';

  function comparisonTable(title, className, columns, rows, headingId) {
    const details = retainPatternState(el('details', 'mic-insight-details'), `${className}-disclosure`);
    const summary = retainPatternState(el('summary', '', title), `${className}-summary`, headingId);
    details.append(summary);
    const scroll = retainPatternState(el('div', 'mic-insight-scroll'), `${className}-scroll`, headingId);
    scroll.setAttribute('tabindex', '0');
    scroll.setAttribute('role', 'region');
    scroll.setAttribute('aria-label', title);
    const table = el('table', `mic-insight-table ${className}`);
    table.append(el('caption', 'sr-only', `${title}. Values are dates with detections divided by recorded dates; a dash means no recording evidence.`));
    const head = el('thead');
    const headings = el('tr');
    for (const label of ['Species', ...columns]) {
      const th = el('th', '', label); th.setAttribute('scope', 'col'); headings.append(th);
    }
    head.append(headings);
    const body = el('tbody');
    for (const row of rows) {
      const tr = el('tr');
      const name = el('th', '', row.name); name.setAttribute('scope', 'row'); tr.append(name);
      row.values.forEach(([count, recorded]) => {
        const td = el('td', '', occurrence(count, recorded));
        td.setAttribute('aria-label', recorded ? `${count} dates with detections out of ${recorded} recorded dates` : 'No recording evidence for this window');
        tr.append(td);
      });
      body.append(tr);
    }
    table.append(head, body); scroll.append(table); details.append(scroll);
    return details;
  }

  function occurrenceCell(count, total, className = '', fraction = false) {
    const cell = el('td', `mic-occurrence-cell ${className}`);
    const label = total ? `${count} of ${total} recorded days with detections` : 'No recording evidence';
    cell.setAttribute('aria-label', label); cell.title = label;
    const value = el('span', 'mic-occurrence-value'); value.setAttribute('aria-hidden', 'true');
    const track = el('span', 'mic-bar-track');
    const fill = el('span', 'mic-bar-fill');
    fill.style.width = `${total ? Math.min(100, Math.max(0, count / total * 100)) : 0}%`;
    track.append(fill);
    value.append(track, el('span', 'mic-bar-number', fraction ? occurrence(count, total) : total ? String(count) : '—'));
    cell.append(value);
    return cell;
  }

  const recordedDatesId = index => `mic-week-${index + 1}-recorded-dates`;

  function historyStrip(weeks) {
    const figure = el('figure', 'mic-history-figure');
    const strip = el('div', 'mic-history-strip');
    strip.setAttribute('role', 'img');
    strip.setAttribute('aria-label', `Recording evidence across four weeks. ${weeks.map(week => `${rangeLabel(week.range)}: ${week.recordedDates.length} of 7 days`).join('; ')}. Unfilled dots have no recording evidence.`);
    strip.setAttribute('aria-describedby', weeks.map((_, index) => recordedDatesId(index)).join(' '));
    for (const week of weeks) {
      const group = el('span', 'mic-history-week'); group.setAttribute('aria-hidden', 'true');
      for (let index = 0; index < 7; index += 1) {
        const date = new Date(`${week.range.start}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + index);
        const key = date.toISOString().slice(0, 10);
        const recorded = week.recordedDates.includes(key);
        const dot = el('span', `mic-history-dot${recorded ? ' is-recorded' : ''}`);
        dot.title = `${dateLabel(key)}: ${recorded ? 'recording evidence' : 'no recording evidence'}`;
        group.append(dot);
      }
      strip.append(group);
    }
    figure.append(strip, el('figcaption', '', `${dateLabel(weeks[0].range.start)}–${dateLabel(weeks.at(-1).range.end)} · filled dots = recorded days`));
    return figure;
  }

  function weeklyPattern(weekly) {
    const panel = el('article', 'mic-pattern mic-insight mic-weekly'); panel.id = 'mic-weekly-insight';
    const heading = el('h3', '', 'Who’s becoming a regular');
    heading.id = 'mic-weekly-title';
    panel.append(heading);
    const weeks = weekly.weeks, latest = weeks.at(-1);
    if (weekly.state !== 'comparable') {
      const state = el('div', 'mic-history-state');
      const message = el('div');
      message.append(el('p', 'mic-history-label', 'Building history'), el('p', 'mic-caption', 'More recorded days are needed before comparing weeks.'));
      state.append(message, historyStrip(weeks)); panel.append(state);
      const repeats = weekly.species.filter(bird => bird.detectedDays.at(-1) >= 2).slice(0, 3);
      if (repeats.length) {
        const repeat = el('div', 'mic-repeat-summary');
        repeat.append(el('h4', '', `Showing up again · ${rangeLabel(latest.range)} · days detected / recorded`));
        const list = el('ul', 'mic-repeat-chips'); list.setAttribute('role', 'list');
        for (const bird of repeats) {
          const item = el('li');
          item.append(el('span', '', bird.name), el('span', 'mic-repeat-count', occurrence(bird.detectedDays.at(-1), latest.recordedDates.length)));
          item.title = `${bird.name}: ${bird.detectedDays.at(-1)} of ${latest.recordedDates.length} recorded days`;
          list.append(item);
        }
        repeat.append(list, el('span', 'sr-only', 'Fractions are days detected out of recorded days in the latest week.')); panel.append(repeat);
      }
    } else {
      const labels = { 'first-in-window': 'First in this window', 'more-often': 'More often', 'less-often': 'Less often' };
      const changes = weekly.species.filter(bird => labels[bird.change]).sort((a, b) => Math.abs(b.deltaFraction) - Math.abs(a.deltaFraction) || b.detectedDays.at(-1) - a.detectedDays.at(-1) || a.name.localeCompare(b.name)).slice(0, 6);
      panel.append(el('p', 'mic-visual-caption', 'Days detected / recorded days · four completed weeks'));
      if (changes.length) {
        const table = el('table', 'mic-visual-table mic-week-trends');
        table.append(el('caption', 'sr-only', 'Selected weekly changes. Bar length is the share of recorded days with detections; fractions give exact counts.'));
        const head = el('thead'), headings = el('tr');
        for (const text of ['Species', ...weeks.map(week => rangeLabel(week.range))]) { const th = el('th', '', text); th.setAttribute('scope', 'col'); headings.append(th); }
        head.append(headings); const body = el('tbody');
        for (const bird of changes) {
          const row = el('tr'), name = el('th', '', bird.name); name.setAttribute('scope', 'row');
          name.append(el('span', 'mic-trend-label', labels[bird.change]));
          if (bird.change === 'first-in-window') name.title = `First available record ${dateLabel(bird.firstDetectedDate)}; not an arrival date.`;
          row.append(name);
          bird.detectedDays.forEach((count, index) => row.append(occurrenceCell(count, weeks[index].recordedDates.length, index === 3 ? 'is-latest' : '', true)));
          body.append(row);
        }
        table.append(head, body); panel.append(table);
      } else panel.append(el('p', 'mic-caption', 'No clear week-to-week changes yet.'));
    }
    if (weekly.species.length) panel.append(comparisonTable(`Compare all ${weekly.species.length} species across weeks`, 'mic-weekly-table', weeks.map(week => rangeLabel(week.range)), weekly.species.map(bird => ({ name: bird.name, values: bird.detectedDays.map((count, i) => [count, weeks[i].recordedDates.length]) })), heading.id));
    return panel;
  }

  function daypartPattern(dayparts) {
    const panel = el('article', 'mic-pattern mic-insight mic-dayparts'); panel.id = 'mic-daypart-insight';
    const heading = el('h3', '', 'Morning, midday & afternoon');
    heading.id = 'mic-daypart-title';
    panel.append(heading);
    const cover = dayparts.coverage, total = cover.recordedDates.length;
    panel.append(el('p', 'mic-visual-caption', `Days detected · out of ${plural(total, 'recorded day')} · ${rangeLabel(cover.range)}`));
    if (dayparts.state !== 'available') {
      panel.append(el('p', 'mic-caption', 'Building history — more recorded days are needed to compare times of day.'));
    } else {
      const contrasts = dayparts.periods.flatMap((period, index) => dayparts.species.filter(bird => bird.group === period.id).sort((a, b) => {
        const margin = bird => bird.daysByPeriod[index] - Math.max(...bird.daysByPeriod.filter((_, i) => i !== index));
        return margin(b) - margin(a) || b.daysByPeriod[index] - a.daysByPeriod[index] || a.name.localeCompare(b.name);
      }).slice(0, 2));
      const across = dayparts.species.filter(bird => bird.group === 'all-day').sort((a, b) => Math.min(...b.daysByPeriod) - Math.min(...a.daysByPeriod) || b.detectedDates - a.detectedDates || a.name.localeCompare(b.name)).slice(0, 2);
      if (contrasts.length || across.length) {
        const table = el('table', 'mic-visual-table mic-daypart-visual');
        table.append(el('caption', 'sr-only', `Selected species by time of day. Days detected out of ${total} recorded days. All times Eastern; recording coverage within each period is unknown.`));
        const head = el('thead'), headings = el('tr');
        const species = el('th', '', 'Species'); species.setAttribute('scope', 'col'); headings.append(species);
        for (const [index, period] of dayparts.periods.entries()) {
          const th = el('th', `mic-period-${index}`, period.label); th.setAttribute('scope', 'col');
          th.append(el('span', 'mic-period-time', `${hourLabel(period.startHour)}–${hourLabel(period.endHour)}`)); headings.append(th);
        }
        head.append(headings); table.append(head);
        for (const [group, birds] of [['contrasts', contrasts], ['all', across]]) {
          if (!birds.length) continue;
          const body = el('tbody', `mic-daypart-${group}`);
          if (group === 'all') {
            const groupRow = el('tr'), label = el('th', 'mic-chart-group', 'Across all three periods'); label.setAttribute('colspan', '4'); label.setAttribute('scope', 'rowgroup'); groupRow.append(label); body.append(groupRow);
          }
          for (const bird of birds) {
            const row = el('tr'), name = el('th', '', bird.name); name.setAttribute('scope', 'row'); row.append(name);
            bird.daysByPeriod.forEach((count, index) => row.append(occurrenceCell(count, total, `mic-period-${index}`))); body.append(row);
          }
          table.append(body);
        }
        panel.append(table, el('p', 'mic-visual-caveat', 'Eastern time · coverage within each period is unknown.'));
      } else panel.append(el('p', 'mic-caption', dayparts.species.length ? 'No recurring contrasts yet. Explore every species below.' : 'No accepted daytime detections in these records.'));
    }
    if (dayparts.species.length) panel.append(comparisonTable(`Compare all ${dayparts.species.length} daytime species`, 'mic-daypart-table', dayparts.periods.map(period => `${period.label} ${hourLabel(period.startHour)}–${hourLabel(period.endHour)}`), dayparts.species.map(bird => ({ name: bird.name, values: bird.daysByPeriod.map(count => [count, total]) })), heading.id));
    return panel;
  }

  function insightDataNotes(insights) {
    const notes = retainPatternState(el('details', 'mic-insight-details mic-insight-about'), 'mic-insight-about');
    notes.append(retainPatternState(el('summary', '', 'About this data'), 'mic-insight-about-summary'));
    const body = el('div', 'mic-data-notes');
    body.append(el('p', '', 'Recently heard shows the displayed hour of available records. Its end is estimated from the source report’s time, or from our first retrieval when that is unknown. It is not a verified recording endpoint; waiting for an update does not extend the hour.'));
    body.append(el('p', '', 'A recorded day has reported listening time or an accepted detection. Dates without recording evidence are excluded, not counted as a bird’s absence. Only reviewed and automatically accepted detections contribute. Unequal listening time and vocal behavior affect these comparisons; they do not measure abundance.'));
    if (insights.weekly) {
      const weekly = insights.weekly;
      body.append(el('h4', '', 'Weekly comparisons'), el('p', '', `Four completed seven-day windows. Comparisons need at least ${weekly.minimumRecordedDays} recorded days in each of the latest two windows. More/less often requires a change of at least two detection dates and 25 percentage points in the same direction. Up to six largest supported changes are shown. “First in this window” means no accepted detections in the three earlier windows; it does not establish an arrival or first-ever record. Repeat examples are the first three species with detections on at least two dates in the latest window, ordered by detection days then name.`));
      const coverage = el('ul', 'mic-data-coverage');
      for (const [index, week] of weekly.weeks.entries()) {
        const row = el('li');
        const dates = el('span', '', `${rangeLabel(week.range)}. Recorded dates: ${week.recordedDates.map(dateLabel).join(', ') || 'none'}.`);
        dates.id = recordedDatesId(index);
        row.append(dates, el('span', '', ` ${week.recordedDates.length}/7 recorded days; ${(week.listeningMinutes / 60).toFixed(1)} reported hours; ${week.returnedDates.length} dates returned, ${week.noRecordingDates.length} with no recording evidence, ${week.missingDates.length} missing; ${week.detectionOnlyDates.length} dates with detections but no reported listening time.`));
        coverage.append(row);
      }
      body.append(coverage);
    }
    if (insights.dayparts) {
      const part = insights.dayparts, cover = part.coverage, total = cover.recordedDates.length;
      body.append(el('h4', '', 'Times of day'), el('p', '', `Morning is 6–10 am, midday 10 am–2 pm, afternoon 2–6 pm, Eastern time. Counts are distinct dates with detections, using ${total} recorded days as context, not verified coverage in each period. At least ${part.minimumRecordedDays} recorded days are needed for recurring contrasts. Up to two examples per period are selected by the largest margin over the other periods, then detection days and name. Each needs detections on at least two dates, more dates than either other period, and at least half of its summed period-date counts. Across-all-period examples occur in every period on at least ${Math.max(2, Math.ceil(total / 2))} dates; the two with the highest minimum period count are shown, then total detection dates and name.`));
      body.append(el('p', '', `${rangeLabel(cover.range)}: ${total}/7 recorded days; ${(cover.listeningMinutes / 60).toFixed(1)} reported hours; ${cover.returnedDates.length} dates returned, ${cover.noRecordingDates.length} with no recording evidence, ${cover.missingDates.length} missing; ${cover.detectionOnlyDates.length} dates with detections but no reported listening time. Recorded dates: ${cover.recordedDates.map(dateLabel).join(', ') || 'none'}.`));
    }
    notes.append(body); return notes;
  }

  function renderPatternContent(patterns, insights, hasHourlyEvidence) {
    const target = el('div');
    const grid = el('div', 'mic-pattern-grid');
    if (insights?.weekly) grid.append(weeklyPattern(insights.weekly));
    if (insights?.dayparts) grid.append(daypartPattern(insights.dayparts));
    if (insights?.weekly || insights?.dayparts) grid.append(insightDataNotes(insights));
    target.append(grid);
    if (!hasHourlyEvidence) return target;
    if (Array.isArray(patterns.speciesHours)) grid.append(compositionPattern(patterns));
    if (!patterns.overnight.length) return target;
    const night = el('article', 'mic-pattern');
    night.append(el('h3', '', 'After dark, before dawn'), el('p', 'mic-caption', '8 pm–6 am · Eastern time'));
    const list = el('ul', 'mic-pattern-list');
    for (const bird of patterns.overnight.slice(0, 5)) {
      const item = el('li');
      item.append(el('span', '', bird.name), el('small', '', `${plural(bird.detectedMinutes, 'detected minute')} · ${plural(bird.dates, 'date')}`));
      list.append(item);
    }
    night.append(list, el('p', 'mic-caption', 'Species detected on at least two dates. Counts group detections by calendar date, rather than by complete night.'));
    grid.append(night);
    return target;
  }

  function installPatterns({ content, signature, coverage }) {
    if (signature !== patternSignature) {
      const target = byId('mic-pattern-content');
      const focused = document.activeElement;
      const hadFocus = target.contains(focused) && focused !== target;
      const state = Array.from(target.querySelectorAll('[data-mic-state]'), node => ({
        id: node.id, open: node.open, left: node.scrollLeft, top: node.scrollTop,
      }));
      target.replaceChildren(...content.children);
      for (const { id, open, left, top } of state) {
        const node = byId(id);
        if (!node) continue;
        if (open) node.open = true;
        node.scrollLeft = left;
        node.scrollTop = top;
      }
      if (hadFocus) {
        const replacement = focused.id && byId(focused.id);
        const fallbackId = focused.getAttribute('data-mic-state');
        const next = replacement || (fallbackId && byId(fallbackId)) || target.querySelector('h3, .mic-empty');
        if (next) {
          if (!replacement || focused.getAttribute('tabindex') === '-1') next.setAttribute('tabindex', '-1');
          next.focus({ preventScroll: true });
        }
      }
      patternSignature = signature;
    }
    byId('mic-pattern-coverage').textContent = coverage;
  }

  function evidenceTime(segment) {
    if (!['fresh', 'stale'].includes(segment.state)) return null;
    const time = Date.parse(segment.snapshot?.estimatedAt || segment.retrievedAt);
    return Number.isFinite(time) && Date.now() - time <= retentionMs ? time : null;
  }

  function datedEvidence(data, date, freshOnly = false) {
    if (!data.range.returnedDates.includes(date)) return null;
    if (data.range.dateEvidence) {
      const day = data.range.dateEvidence.find(entry => entry.date === date);
      if (!day || (freshOnly && day.retained)) return null;
      const time = Date.parse(day.estimatedAt);
      return Date.now() - time <= retentionMs ? time : null;
    }
    const times = [];
    for (const name of ['recent', 'history']) {
      const part = data.freshness[name];
      const time = evidenceTime(part);
      if (time === null || (freshOnly && part.state !== 'fresh')) continue;
      if (part.range && (part.range.start > date || part.range.end < date)) continue;
      if (part.dateEvidence) {
        const day = part.dateEvidence.find(entry => entry.date === date);
        if (day && (!freshOnly || !day.retained)) times.push(Date.parse(day.estimatedAt));
      } else if (part.returnedDates ? part.returnedDates.includes(date) : !freshOnly || data.kingfisher.complete) {
        times.push(time);
      }
    }
    const newest = Math.max(...times.filter(Number.isFinite));
    return Date.now() - newest <= retentionMs ? newest : null;
  }

  function historyExpiry(data, patterns, insights, historyTime) {
    const displayed = new Set(patterns.dates);
    for (const week of insights.weekly?.weeks ?? []) {
      for (const date of week.returnedDates) displayed.add(date);
    }
    for (const date of insights.dayparts?.coverage.returnedDates ?? []) displayed.add(date);
    // Merged dates identify the winning source. Frozen history may extend beyond
    // the current range, in which case its own per-date provenance still applies.
    const dates = new Map();
    for (const day of [...(data.freshness.history.dateEvidence ?? []), ...(data.range.dateEvidence ?? [])]) {
      dates.set(day.date, Date.parse(day.estimatedAt));
    }
    let oldest = historyTime;
    for (const date of displayed) oldest = Math.min(oldest, dates.get(date) ?? historyTime);
    return oldest + retentionMs;
  }

  // Build candidate panels offscreen. A malformed response cannot clear good content.
  function prepare(data) {
    if (!['available', 'partial'].includes(data.state) || !Number.isFinite(Date.parse(data.generatedAt))) {
      throw new Error('Invalid microphone summary');
    }
    const recentTime = evidenceTime(data.freshness.recent);
    const historyTime = evidenceTime(data.freshness.history);
    const next = {};
    const hour = data.recentHour;
    if (recentTime !== null && recentTime >= (saved.recent?.time ?? -Infinity) && ['available', 'partial'].includes(hour.state)
        && hour.windowBasis !== 'unknown' && Number.isFinite(Date.parse(hour.start))
        && Number.isFinite(Date.parse(hour.end)) && Array.isArray(hour.species)) {
      next.recent = { ...recentContent(data), time: recentTime };
    }
    if (historyTime !== null && historyTime >= (saved.history?.time ?? -Infinity)) {
      const patterns = data.patterns;
      const weekly = data.insights?.weekly;
      const dayparts = data.insights?.dayparts;
      const insights = {
        weekly: weekly?.weeks.some(week => week.recordedDates.length) ? weekly : null,
        dayparts: dayparts?.coverage.recordedDates.length ? dayparts : null,
      };
      const minutes = (patterns.dailyEffort ?? data.dailyEffort).filter(day => patterns.dates.includes(day.date))
        .reduce((sum, day) => sum + day.listeningMinutes, 0);
      const hasHourlyEvidence = patterns.dates.length > 0 && (minutes > 0 || !!patterns.speciesHours?.length || patterns.overnight.length > 0);
      const expiresAt = historyExpiry(data, patterns, insights, historyTime);
      if (Date.now() <= expiresAt && (hasHourlyEvidence || insights.weekly || insights.dayparts)) {
        const signature = JSON.stringify([patterns, insights, hasHourlyEvidence]);
        const content = signature === patternSignature ? null : renderPatternContent(patterns, insights, hasHourlyEvidence);
        const coverage = patterns.dates.length ? `${dateLabel(patterns.range.start)}–${dateLabel(patterns.range.end)}: ${plural(patterns.dates.length, 'date')} returned of 7 requested; ${minutes.toLocaleString('en-US')} reported listening minutes.` : '';
        next.history = { signature, content, coverage, time: historyTime, expiresAt };
      }
    }
    const bird = data.kingfisher;
    const previous = saved.kingfisher;
    const correction = previous && datedEvidence(data, previous.date, true);
    const canReplace = previous && correction !== null && correction >= previous.time;
    if (bird.state === 'detected' && Number.isFinite(Date.parse(bird.latestAt)) && Number.isFinite(bird.elapsedMinutes)) {
      const date = bird.latestLocal.slice(0, 10);
      const time = bird.evidenceEstimatedAt ? Date.parse(bird.evidenceEstimatedAt) : datedEvidence(data, date);
      const detectedAt = Date.parse(bird.latestAt);
      if (time !== null && Date.now() - time <= retentionMs && (!previous || detectedAt >= previous.detectedAt || canReplace)) {
        next.kingfisher = { target: kingfisherContent(data), time, date, detectedAt,
          elapsedMinutes: bird.elapsedMinutes, receivedAt: Date.parse(data.generatedAt) };
      }
    } else if (bird.state === 'no-match' && canReplace) next.clearKingfisher = true;
    return next;
  }

  function show(id, visible) {
    const panel = byId(id);
    if (!visible && panel.contains(document.activeElement)) refresh.focus({ preventScroll: true });
    panel.hidden = !visible;
  }

  function display(next, freshness) {
    if (next.clearKingfisher) saved.kingfisher = null;
    for (const key of Object.keys(saved)) {
      if (next[key]) saved[key] = next[key];
      else if (saved[key] && Date.now() > (saved[key].expiresAt ?? saved[key].time + retentionMs)) saved[key] = null;
    }
    if (next.recent) {
      byId('mic-window').textContent = next.recent.windowLabel;
      byId('mic-recent-content').replaceChildren(...next.recent.target.children);
      byId('mic-source-detail').textContent = next.recent.detail;
    } else if (!saved.recent) byId('mic-source-detail').textContent = '';
    if (next.history) installPatterns(next.history);
    if (next.kingfisher) byId('mic-kingfisher-content').replaceChildren(...next.kingfisher.target.children);
    const delayed = !freshness || freshness.recent.state !== 'fresh' || freshness.history.state !== 'fresh'
      || (saved.recent && !next.recent) || (saved.history && !next.history) || (saved.kingfisher && !next.kingfisher);
    byId('mic-kingfisher-title').textContent = delayed ? 'Last known Belted Kingfisher detection' : 'Last Belted Kingfisher detected';
    let status = 'Microphone records are temporarily unavailable.';
    if (Object.values(saved).some(Boolean)) {
      const times = [];
      if (saved.recent) times.push(`recent records ${statusStamp.format(saved.recent.time)}`);
      if (saved.history) times.push(`history ${statusStamp.format(saved.history.time)}`);
      if (!times.length && saved.kingfisher) times.push(`kingfisher record ${statusStamp.format(saved.kingfisher.time)}`);
      status = delayed ? `Updates delayed · ${times.join(' · ')}.${saved.kingfisher ? ' A newer detection may exist.' : ''}`
        : `Last updated ${statusStamp.format(Math.max(...Object.values(saved).filter(Boolean).map(item => item.time)))}.`;
    }
    if (byId('mic-update-status').textContent !== status) byId('mic-update-status').textContent = status;
    show('mic-recent-panel', !!saved.recent);
    show('mic-kingfisher-panel', !!saved.kingfisher);
    show('bird-microphone-patterns', !!saved.history);
    if (!saved.recent) byId('mic-recent-content').replaceChildren();
    if (!saved.kingfisher) byId('mic-kingfisher-content').replaceChildren();
    if (!saved.history) {
      byId('mic-pattern-content').replaceChildren();
      byId('mic-pattern-coverage').textContent = '';
      patternSignature = null;
    }
    for (const link of document.querySelectorAll('a[href="#bird-microphone-patterns"]')) {
      if (!saved.history && document.activeElement === link) refresh.focus({ preventScroll: true });
      link.hidden = !saved.history;
    }
    renderCounter();
  }

  async function load() {
    if (busy) return;
    busy = true;
    refresh.setAttribute('aria-disabled', 'true');
    refresh.textContent = 'Checking…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/yardmic', { cache: 'no-store', signal: controller.signal, headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('Feed unavailable');
      const data = await response.json();
      display(prepare(data), data.freshness);
    } catch (_) {
      display({}, null);
    } finally {
      clearTimeout(timeout);
      busy = false;
      refresh.setAttribute('aria-disabled', 'false');
      refresh.textContent = 'Refresh';
    }
    renderCounter();
  }
  refresh.addEventListener('click', load);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  setInterval(() => { if (!document.hidden) load(); }, 120000);
  setInterval(renderCounter, 30000);
  load();
})();
