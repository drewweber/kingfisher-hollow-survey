/* Optional comparison state. Every dated source remains in the static document. */
(function () {
  'use strict';
  function normalizedComparison(search, periods) {
    const value = new URLSearchParams(search).get('compare');
    return value === 'years' || periods.includes(value) ? value : 'all';
  }
  function comparisonUrl(href, value, periods) {
    const url = new URL(href);
    if (value === 'years' || periods.includes(value)) url.searchParams.set('compare', value);
    else url.searchParams.delete('compare');
    return url.pathname + url.search + url.hash;
  }
  // Export pure state helpers for the same no-dependency tests used by the build.
  if (typeof module !== 'undefined' && module.exports) module.exports = { normalizedComparison, comparisonUrl };
  if (typeof document === 'undefined') return;
  const controls = document.querySelector('.comparison-controls');
  const select = document.querySelector('#comparison-mode');
  if (controls && select) {
    const periods = Array.from(select.options).map(o => o.value).filter(v => v !== 'all' && v !== 'years');
    function apply() {
      const value = normalizedComparison(location.search, periods);
      select.value = value;
      document.querySelectorAll('.pooled-calendar').forEach(el => { el.hidden = value !== 'all'; });
      document.querySelectorAll('.year-calendar').forEach(el => { el.open = value !== 'all'; });
      document.querySelectorAll('.year-band').forEach(el => { el.hidden = value !== 'all' && value !== 'years' && el.dataset.year !== value; });
      document.querySelectorAll('.year-calendar').forEach(calendar => {
        const empty = calendar.querySelector('.year-empty');
        if (empty) empty.hidden = value === 'all' || value === 'years' || Array.from(calendar.querySelectorAll('.year-band')).some(band => band.dataset.year === value);
      });
      const status = document.querySelector('#comparison-status');
      if (status) status.textContent = value === 'all' ? '' : value === 'years' ? 'Calendar marks are separated by seasonal period. All dated records remain available below.' : 'Calendar marks show ' + value + '. All dated records remain available below.';
      // A specialist return keeps the deliberately chosen comparison and its evidence anchor.
      document.querySelectorAll('a[href*="?from="]').forEach(link => {
        const destination = new URL(link.getAttribute('href'), location.href);
        const from = destination.searchParams.get('from');
        if (!from || !/^\/seasons\/(spring|summer|autumn|winter)\//.test(from)) return;
        const local = new URL(from, location.origin);
        destination.searchParams.set('from', comparisonUrl(local.href, value, periods));
        link.setAttribute('href', destination.pathname + destination.search + destination.hash);
      });
    }
    controls.hidden = false;
    select.addEventListener('change', function () {
      history.pushState(null, '', comparisonUrl(location.href, select.value, periods));
      apply();
    });
    const reset = document.querySelector('.reset-comparison');
    if (reset) reset.addEventListener('click', function (event) {
      event.preventDefault();
      history.pushState(null, '', comparisonUrl(location.href, 'all', periods));
      apply();
      select.focus();
    });
    addEventListener('popstate', apply);
    apply();
  }
  // Existing shared voucher links open their native disclosure ancestors.
  function revealAnchor() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    if (!id || !document.getElementById) return;
    const target = document.getElementById(id);
    if (!target) return;
    let ancestor = target;
    while (ancestor) {
      if (ancestor.tagName === 'DETAILS') ancestor.open = true;
      ancestor = ancestor.parentElement;
    }
    if (target.scrollIntoView) target.scrollIntoView({block: 'start'});
  }
  addEventListener('hashchange', revealAnchor);
  revealAnchor();
  document.querySelectorAll('.landscape img, .detail-photo img, .opening-detail img').forEach(img => {
    const unavailable = () => img.parentElement.classList.add('media-unavailable');
    img.addEventListener('error', unavailable);
    if (img.complete && img.naturalWidth === 0) unavailable();
  });
}());
