/* A specialist inventory can return to the exact seasonal passage it came from. */
(() => {
  const from = new URLSearchParams(location.search).get('from');
  if (!from || !from.startsWith('/') || from.startsWith('//')) return;
  let target;
  try { target = new URL(from, location.origin); } catch { return; }
  if (target.origin !== location.origin) return;
  const match = target.pathname.match(/^\/seasons\/(spring|summer|autumn|winter)\/$/);
  if (!match) return;
  const comparison = target.searchParams.get('compare');
  const search = comparison && /^(years|\d{4}(?:–\d{2})?)$/.test(comparison)
    ? `?${new URLSearchParams({compare: comparison})}` : '';
  const hash = /^#[a-zA-Z0-9_-]+$/.test(target.hash) ? target.hash : '';
  document.querySelectorAll('[data-seasonal-return]').forEach(link => {
    link.href = `${target.pathname}${search}${hash}`;
    link.textContent = `← Back to ${match[1]}`;
    link.hidden = false;
  });
})();
