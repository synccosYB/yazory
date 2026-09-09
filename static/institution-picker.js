(() => {
  'use strict';
  const form = document.querySelector('#intake-wizard');
  if (!form) return;

  const labels = {
    gabbais: form.dataset.gabbaisLabel,
    addGabbai: form.dataset.addGabbaiLabel,
    gabbai: form.dataset.gabbaiLabel,
    gabbaiPhone: form.dataset.gabbaiPhoneLabel,
    remove: form.dataset.removeLabel
  };
  const mode = form.querySelector('[data-rabbi-mode]');
  const person = form.querySelector('[data-rabbi-person]');
  const rabbiName = form.querySelector('input[name="rabbi"]');
  const rabbiPhone = form.querySelector('input[name="rabbi_phone"]');
  const shuls = {};
  const directory = {};
  const gabbais = {};
  const pickers = [];

  function suggestedRabbi() {
    const weekday = shuls.weekday_shul && directory[shuls.weekday_shul.value];
    const shabbos = shuls.shabbos_shul && directory[shuls.shabbos_shul.value];
    return (weekday && weekday.name && weekday) ||
      (shabbos && shabbos.name && shabbos) || null;
  }

  function applySuggestion() {
    if (!mode || mode.value !== 'automatic') return;
    const rabbi = suggestedRabbi();
    rabbiName.value = rabbi ? rabbi.name : '';
    rabbiPhone.value = rabbi ? (rabbi.phone || '') : '';
    person.value = '';
  }

  function applyCanonical() {
    if (!person.value) return;
    const option = person.selectedOptions[0];
    rabbiName.value = option.textContent.trim();
    rabbiPhone.value = option.dataset.phone || '';
  }

  function applyMode() {
    const canonical = mode && mode.value === 'canonical';
    if (person) {
      person.closest('label').hidden = !canonical;
      person.disabled = !canonical;
    }
    if (mode && mode.value === 'automatic') applySuggestion();
    if (canonical) applyCanonical();
  }

  function markManual() {
    if (!mode || mode.value !== 'automatic') return;
    mode.value = 'manual';
    if (person) person.value = '';
    applyMode();
  }

  function gabbaiFields(root, select) {
    if (!select.name.endsWith('_shul')) return null;
    const wrap = document.createElement('div');
    wrap.className = 'shul-gabbai-fields';
    const heading = document.createElement('div');
    heading.className = 'section-heading';
    const title = document.createElement('strong');
    title.textContent = labels.gabbais;
    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'small secondary';
    add.textContent = labels.addGabbai;
    heading.append(title, add);
    const rows = document.createElement('div');
    wrap.append(heading, rows);
    root.appendChild(wrap);

    function addRow(data = {}) {
      const row = document.createElement('div');
      row.className = 'form-grid shul-gabbai-row';
      const nameLabel = document.createElement('label');
      nameLabel.textContent = labels.gabbai;
      const name = document.createElement('input');
      name.name = select.name + '_gabbai_name';
      name.maxLength = 160;
      name.value = data.name || '';
      nameLabel.appendChild(name);
      const phoneLabel = document.createElement('label');
      phoneLabel.textContent = labels.gabbaiPhone;
      const phone = document.createElement('input');
      phone.name = select.name + '_gabbai_phone';
      phone.maxLength = 80;
      phone.value = data.phone || '';
      phoneLabel.appendChild(phone);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'small danger';
      remove.textContent = labels.remove;
      remove.addEventListener('click', () => row.remove());
      row.append(nameLabel, phoneLabel, remove);
      rows.appendChild(row);
    }

    add.addEventListener('click', () => addRow());
    return {rows, addRow};
  }

  function fillGabbais(select, fields) {
    if (!fields) return;
    fields.rows.replaceChildren();
    const rows = select.value === '__new__' ? [] : (gabbais[select.value] || []);
    if (rows.length) rows.forEach(fields.addRow);
    else fields.addRow();
  }

  form.querySelectorAll('[data-institution-picker]').forEach(root => {
    const select = root.querySelector('[data-institution-select]');
    const newField = root.querySelector('[data-new-institution]');
    const input = newField.querySelector('input');
    const fields = gabbaiFields(root, select);
    if (select.name === 'weekday_shul' || select.name === 'shabbos_shul') {
      shuls[select.name] = select;
    }
    function update() {
      const adding = select.value === '__new__';
      newField.hidden = !adding;
      input.disabled = !adding;
      input.required = adding;
      if (adding && !input.value) input.focus();
      fillGabbais(select, fields);
      applySuggestion();
    }
    select.addEventListener('change', update);
    pickers.push({select, fields, update});
    update();
  });

  if (mode) mode.addEventListener('change', applyMode);
  if (person) person.addEventListener('change', applyCanonical);
  if (rabbiName) rabbiName.addEventListener('input', markManual);
  if (rabbiPhone) rabbiPhone.addEventListener('input', markManual);
  applyMode();

  Promise.all([
    fetch('/api/shul-rabbis', {headers: {Accept: 'application/json'}})
      .then(response => response.ok ? response.json() : {}),
    fetch('/api/shul-gabbais', {headers: {Accept: 'application/json'}})
      .then(response => response.ok ? response.json() : {})
  ]).then(([rabbis, rows]) => {
    Object.assign(directory, rabbis || {});
    Object.assign(gabbais, rows || {});
    pickers.forEach(item => item.update());
  }).catch(() => {});
})();
