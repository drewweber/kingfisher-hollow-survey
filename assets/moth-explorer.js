/* Progressive moth timing explorer. Native monthly records remain linked. */
(() => {
  const params = new URLSearchParams(location.search);
  const back = document.getElementById('moth-timing-back');
  if (back) {
    const returnParams = new URLSearchParams();
    for (const key of ['from', 'moth']) if (params.has(key)) returnParams.set(key, params.get(key));
    back.href = '/moths/' + (returnParams.size ? '?' + returnParams : '') + '#' + (back.dataset.returnAnchor || 'moth-timing');
    return;
  }
  const root = document.getElementById('moth-explorer');
  if (!root) return;
  const input = document.getElementById('moth-search');
  const status = document.getElementById('moth-search-status');
  const results = document.getElementById('moth-search-results');
  const output = document.getElementById('moth-timing-result');
  const detail = document.getElementById('moth-timing');
  let data = null;
  let loading = false;
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  function node(tag, text) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function contextLinks() {
    document.querySelectorAll('[data-moth-context]').forEach(link => {
      const url = new URL(link.href, location.origin);
      for (const key of ['from', 'moth']) {
        const value = new URLSearchParams(location.search).get(key);
        if (value) url.searchParams.set(key, value);
        else url.searchParams.delete(key);
      }
      link.href = url.pathname + url.search;
    });
  }
  function select(row, update = true) {
    output.replaceChildren();
    output.append(node('h3', row.common_name || row.scientific_name));
    output.append(node('p', (row.scientific_name || '') + ' · ' + (row.stages.length ? row.stages.join(', ') : 'Stage not supplied')));
    const present = months.filter((_, i) => row.monthly_records[i] > 0);
    output.append(node('p', present.length ? 'Recorded here in ' + present.join(', ') + '.' : 'No dated records available for this moth.'));
    const list = node('dl'); list.className = 'moth-timing-months';
    row.monthly_records.forEach((count, i) => {
      const cell = node('div'); cell.append(node('dt', months[i]), node('dd', count + ' records')); list.append(cell);
    });
    output.append(list);
    const link = node('a', 'View this moth’s records on iNaturalist ↗');
    link.href = 'https://www.inaturalist.org/observations?project_id=kingfisher-hollow-biodiversity-survey&taxon_id=' + row.id;
    link.target = '_blank'; link.rel = 'noopener'; output.append(link);
    input.value = row.common_name || row.scientific_name;
    results.replaceChildren();
    status.textContent = 'Showing monthly records for ' + input.value + '.';
    if (update) {
      const url = new URL(location.href); url.searchParams.set('moth', row.id); url.hash = 'moth-timing';
      history.pushState(null, '', url.pathname + url.search + url.hash);
    }
    contextLinks();
  }
  function search() {
    const term = input.value.trim().toLowerCase(); results.replaceChildren();
    if (!term) { status.textContent = 'Search ' + data.length + ' moth taxa.'; return; }
    const matches = data.filter(row => ((row.common_name || '') + ' ' + (row.scientific_name || '')).toLowerCase().includes(term));
    status.textContent = matches.length + ' matches' + (matches.length > 30 ? '; first 30 shown. Keep typing to narrow the list.' : '.');
    matches.slice(0, 30).forEach(row => {
      const li = node('li'); const button = node('button', (row.common_name || row.scientific_name) + (row.common_name ? ' · ' + row.scientific_name : ''));
      button.type = 'button'; button.addEventListener('click', () => select(row)); li.append(button); results.append(li);
    });
  }
  async function load() {
    if (data || loading) return;
    loading = true;
    try {
      const response = await fetch(root.dataset.src);
      if (!response.ok) throw new Error('unavailable');
      data = await response.json(); input.disabled = false;
      const selected = data.find(row => String(row.id) === new URLSearchParams(location.search).get('moth'));
      if (selected) select(selected, false); else search();
    } catch (_) { status.textContent = 'The searchable list is unavailable. Browse all monthly records using the link below.'; }
    finally { loading = false; }
  }
  input.addEventListener('input', search);
  detail.addEventListener('toggle', () => { if (detail.open) load(); });
  window.addEventListener('popstate', () => {
    const selected = data && data.find(row => String(row.id) === new URLSearchParams(location.search).get('moth'));
    if (selected) select(selected, false);
    else { input.value = ''; output.replaceChildren(); if (data) search(); }
    contextLinks();
  });
  function openHash() {
    const id = location.hash.slice(1);
    const target = document.getElementById(id);
    if (target) {
      if (target.tagName === 'DETAILS') target.open = true;
      let parent = target.parentElement;
      while (parent) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; }
    }
    if (params.has('moth')) detail.open = true;
    if (detail.open) load();
  }
  window.addEventListener('hashchange', openHash);
  contextLinks(); openHash();
})();
