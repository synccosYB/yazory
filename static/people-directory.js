// Start new directory visits and reloads at the heading. Preserve explicit
// anchors and the browser's back/forward position in a previously viewed list.
(() => {
  const navigation = performance.getEntriesByType('navigation')[0];
  if (location.hash || navigation?.type === 'back_forward') return;
  history.scrollRestoration = 'manual';
  window.addEventListener('pageshow', event => {
    if (event.persisted || location.hash) return;
    requestAnimationFrame(() => window.scrollTo({top: 0, left: 0, behavior: 'instant'}));
  });
})();
