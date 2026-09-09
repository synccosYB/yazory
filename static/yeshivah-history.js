document.addEventListener('DOMContentLoaded', () => {
  const list = document.querySelector('[data-yeshivah-history]');
  const add = document.querySelector('[data-add-yeshivah]');
  const template = document.getElementById('yeshivah-history-template');
  if (!list || !add || !template) return;

  const addRow = () => {
    list.appendChild(template.content.cloneNode(true));
    list.lastElementChild?.querySelector('input')?.focus();
  };
  add.addEventListener('click', addRow);
  list.addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove-yeshivah]');
    if (!button) return;
    button.closest('.yeshivah-history-row')?.remove();
  });
});
