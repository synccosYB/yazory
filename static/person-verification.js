(() => {
  document.querySelectorAll('[data-person-verification]').forEach(panel => {
    if (panel.dataset.initialized) return;
    panel.dataset.initialized = 'yes';
    let fields;
    const result = panel.querySelector('[data-result]');
    const show = data => {
      fields = data.fields;
      if (data.history) {
        const history = panel.querySelector('[data-history]');
        history.replaceChildren();
        data.history.forEach(item => {
          const row = panel.querySelector(`[data-verification-field="${item.field}"]`);
          if (!row) return;
          const entry = document.createElement('p');
          entry.textContent = [row.querySelector('[data-field-label]').textContent,
            panel.querySelector(`[data-status-label="${item.status}"]`).textContent,
            item.expired ? panel.dataset.expired : '', item.reviewer, new Date(item.date).toLocaleString(), item.reason].filter(Boolean).join(' · ');
          history.append(entry);
        });
      }
      Object.entries(fields).forEach(([field, item]) => {
        const row = panel.querySelector(`[data-verification-field="${field}"]`);
        if (!row) return;
        row.querySelector('[data-status]').textContent = panel.querySelector(`[data-status-label="${item.status}"]`).textContent;
        row.querySelector('[data-review]').textContent = [item.reviewer, item.date ? new Date(item.date).toLocaleString() : '', item.reason].filter(Boolean).join(' · ');
        const select = row.querySelector('[data-choice]');
        if (select) {
          select.value = item.status;
          row.querySelector('[data-reason]').value = item.reason;
        }
        if (data.values && field !== 'identity') {
          const flatten = value => typeof value === 'object' && value !== null ? Object.values(value).flatMap(flatten) : [value];
          const value = data.values[field];
          row.querySelector('[data-value]').textContent = flatten(value).filter(Boolean).join(' · ');
          const editors = row.querySelectorAll('[data-edit]');
          if (field === 'name') {
            const vals = Array.isArray(value) ? value : [];
            editors.forEach(input => input.value = input.dataset.edit === 'english_name' ? (vals[0] || '') : (vals[1] || ''));
          } else if (field === 'home_address') {
            const vals = Array.isArray(value) ? value : [];
            const extra = vals[4] || {};
            const mapped = {street: vals[0] || '', city: vals[1] || '', state: vals[2] || '',
              zip_code: vals[3] || '', unit: extra.unit || '', country: extra.country || ''};
            editors.forEach(input => input.value = mapped[input.dataset.edit] || '');
          } else if (field === 'work_address') {
            const vals = value || {};
            editors.forEach(input => input.value = vals[input.dataset.edit] || '');
          } else {
            editors.forEach(input => input.value = value || '');
          }
        }
      });
    };
    const form = panel.querySelector('[data-profile-form]');
    const fieldset = panel.querySelector('[data-profile-fields]');
    const button = panel.querySelector('[data-save]');
    let baseline = {};
    const snapshot = row => ({status: row.querySelector('[data-choice]')?.value,
      reason: row.querySelector('[data-reason]')?.value || '',
      edits: Object.fromEntries(Array.from(row.querySelectorAll('[data-edit]')).map(input => [input.dataset.edit, input.value]))});
    const remember = () => {
      baseline = {};
      panel.querySelectorAll('[data-verification-field]').forEach(row => {
        baseline[row.dataset.verificationField] = snapshot(row);
      });
      const phoneRow = panel.querySelector('[data-verification-field="phone"]');
      const phone = phoneRow.querySelector('[data-edit]')?.value || phoneRow.querySelector('[data-value]').textContent || '';
      const normalize = value => value.replace(/\D/g, '');
      const otherPhones = ['home_phone', 'cell_phone'].map(field =>
        panel.querySelector(`[data-verification-field="${field}"] [data-edit]`)?.value || panel.querySelector(`[data-verification-field="${field}"] [data-value]`).textContent || '');
      // Keep a distinct legacy number visible; omit empty or duplicate aliases.
      phoneRow.hidden = !phone || otherPhones.some(value => value && normalize(value) === normalize(phone));
    };
    form.addEventListener('input', event => {
      if (!event.target.matches('[data-edit]')) return;
      const row = event.target.closest('[data-verification-field]');
      row.querySelector('[data-choice]').value = 'unverified';
      row.querySelector('[data-reason]').value = '';
      row.querySelector('[data-status]').textContent = panel.querySelector('[data-status-label="unverified"]').textContent;
    });
    form.addEventListener('change', event => {
      if (!event.target.matches('[data-choice]')) return;
      event.target.closest('[data-verification-field]').querySelector('[data-status]').textContent =
        panel.querySelector(`[data-status-label="${event.target.value}"]`).textContent;
    });
    let loading = false;
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const response = await fetch(panel.dataset.url, {headers: {'Accept': 'application/json'}});
        if (!response.ok) throw new Error();
        show(await response.json());
        remember();
        fieldset.disabled = false;
        if (button) button.disabled = false;
      } catch (_) { result.textContent = panel.dataset.error; }
      finally { loading = false; }
    };
    panel.addEventListener('toggle', () => { if (panel.open && !fields) load(); });
    if (button) button.disabled = true;
    if (panel.open) load();
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!fields || !button) return;
      const changes = {};
      panel.querySelectorAll('[data-verification-field]').forEach(row => {
        const field = row.dataset.verificationField;
        const item = snapshot(row);
        if (JSON.stringify(item) !== JSON.stringify(baseline[field])) {
          changes[field] = {...item, fingerprint: fields[field].fingerprint};
        }
      });
      if (!Object.keys(changes).length) { result.textContent = panel.dataset.saved; return; }
      fieldset.disabled = true;
      button.disabled = true;
      try {
        const body = new URLSearchParams({csrf: panel.dataset.csrf, changes: JSON.stringify(changes)});
        const response = await fetch(panel.dataset.url, {method: 'POST', body,
          headers: {'Accept': 'application/json'}});
        if (response.status === 409) {
          const detail = await response.json().catch(() => ({}));
          result.textContent = detail.error || panel.dataset.conflict; return;
        }
        if (!response.ok) throw new Error();
        show(await response.json());
        remember();
        result.textContent = panel.dataset.saved;
      } catch (_) { result.textContent = panel.dataset.error; }
      finally { fieldset.disabled = false; button.disabled = false; }
    });
  });
})();
