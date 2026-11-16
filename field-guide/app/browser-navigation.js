// Select the shell by how this window is running, not whether an app is installed.
(function () {
  const root = document.documentElement;
  const standalone = window.matchMedia('(display-mode: standalone)');
  function syncShell() {
    const isStandalone = standalone.matches || navigator.standalone === true;
    root.dataset.fieldDisplay = isStandalone ? 'standalone' : 'browser';
    const wrapper = document.getElementById('field-browser-navigation');
    if (!wrapper) return;
    if (isStandalone) {
      const menu = document.getElementById('survey-menu');
      if (menu && menu.hasAttribute('popover') && menu.matches(':popover-open')) menu.hidePopover();
      if (wrapper.contains(document.activeElement)) document.getElementById('results-heading')?.focus();
    }
    // The expanded fallback index must scroll away on short/narrow screens.
    const enhanced = !isStandalone && document.getElementById('navbar')?.classList.contains('survey-nav-enhanced');
    root.dataset.fieldNavEnhanced = String(!!enhanced);
    root.style.setProperty('--field-browser-nav-height', enhanced ? wrapper.getBoundingClientRect().height + 'px' : '0px');
  }
  syncShell();
  if (standalone.addEventListener) standalone.addEventListener('change', syncShell);
  else standalone.addListener(syncShell);
  window.addEventListener('pageshow', syncShell);
  window.addEventListener('resize', syncShell, { passive: true });
  document.addEventListener('DOMContentLoaded', () => {
    syncShell();
    const wrapper = document.getElementById('field-browser-navigation');
    if (wrapper && 'ResizeObserver' in window) new ResizeObserver(syncShell).observe(wrapper);
  });
})();
