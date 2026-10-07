(() => {
  const workspace = document.querySelector('[data-person-workspace]');
  if (!workspace) return;
  const tabs = [...workspace.querySelectorAll('[data-person-tab]')];
  const activate = () => {
    const id = location.hash.slice(1);
    const selected = tabs.find(tab => tab.dataset.personTab === id) || tabs[0];
    tabs.forEach(tab => {
      const active = tab === selected;
      tab.setAttribute('aria-current', active ? 'page' : 'false');
      const section = document.getElementById(tab.dataset.personTab);
      section.hidden = !active;
      if (active && section.tagName === 'DETAILS') section.open = true;
    });
    const book = document.getElementById('book-details');
    if (book) book.hidden = selected.dataset.personTab !== 'family-connections';
  };
  window.addEventListener('hashchange', activate);
  activate();
})();
