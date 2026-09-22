(() => {
  'use strict';

  document.querySelectorAll('[data-local-select-filter]').forEach((search) => {
    const select = document.getElementById(search.dataset.localSelectFilter);
    if (!select) return;
    const results = document.createElement('div');
    results.className = 'select-search-results';
    results.hidden = true;
    search.after(results);

    const close = () => {
      results.hidden = true;
      search.setAttribute('aria-expanded', 'false');
    };
    const choose = (option) => {
      select.value = option.value;
      select.dispatchEvent(new Event('change', {bubbles: true}));
      search.value = option.value === '__new__' ? '' : option.textContent.trim();
      close();
    };
    const render = () => {
      const query = search.value.trim().toLocaleLowerCase();
      const options = [...select.options].filter((option) =>
        option.value === '__new__' || (!query || option.textContent.toLocaleLowerCase().includes(query)));
      results.replaceChildren(...options.map((option) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = option.textContent.trim();
        button.className = option.value === select.value ? 'selected' : '';
        button.addEventListener('mousedown', (event) => event.preventDefault());
        button.addEventListener('click', () => choose(option));
        return button;
      }));
      results.hidden = false;
      search.setAttribute('aria-expanded', 'true');
    };

    search.setAttribute('role', 'combobox');
    search.setAttribute('aria-autocomplete', 'list');
    search.setAttribute('aria-expanded', 'false');
    search.addEventListener('focus', render);
    search.addEventListener('input', () => { select.value = ''; render(); });
    search.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
    search.addEventListener('blur', () => setTimeout(close, 120));
    select.addEventListener('change', () => {
      const fields = select.closest('[data-person-picker]')?.querySelector('[data-new-person]');
      if (fields) {
        fields.hidden = select.value !== '__new__';
        fields.querySelector('[name="askan_name"]')?.toggleAttribute('required', select.value === '__new__');
      }
    });
    select.closest('[data-person-picker]')?.querySelector('[data-add-new-person]')
      ?.addEventListener('click', () => {
        select.value = '__new__';
        select.dispatchEvent(new Event('change', {bubbles: true}));
        search.value = '';
        close();
        select.closest('[data-person-picker]')
          ?.querySelector('[data-new-person] [name="askan_name"]')?.focus();
      });

    const selected = select.selectedOptions[0];
    if (selected?.value) search.value = selected.textContent.trim();
    select.dispatchEvent(new Event('change'));
  });
})();
