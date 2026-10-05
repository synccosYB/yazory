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
    panel.addEventListener('toggle', async () => {
      if (!panel.open) return;
      try {
        const response = await fetch(panel.dataset.url, {headers: {'Accept': 'application/json'}});
        if (!response.ok) throw new Error();
        show(await response.json());
        result.textContent = '';
      } catch (_) { fields = null; result.textContent = panel.dataset.error; }
    });
    panel.addEventListener('click', async event => {
      const button = event.target.closest('[data-save]');
      if (!button) return;
      if (!fields) {
        button.disabled = true;
        try {
          const response = await fetch(panel.dataset.url, {headers: {'Accept': 'application/json'}});
          if (!response.ok) throw new Error();
          show(await response.json());
          result.textContent = '';
        } catch (_) {
          result.textContent = panel.dataset.error;
          button.disabled = false;
          return;
        }
        button.disabled = false;
      }
      const row = button.closest('[data-verification-field]');
      const field = row.dataset.verificationField;
      const status = row.querySelector('[data-choice]').value;
      const reason = row.querySelector('[data-reason]');
      button.disabled = true;
      try {
        const body = new URLSearchParams({csrf: panel.dataset.csrf, status,
          reason: reason.value, fingerprint: fields[field].fingerprint});
        row.querySelectorAll('[data-edit]').forEach(input => body.set(input.dataset.edit, input.value));
        const response = await fetch(`${panel.dataset.url}/${field}`, {method: 'POST', body,
          headers: {'Accept': 'application/json'}});
        if (!response.ok) throw new Error();
        const saved = await response.json();
        // Do not repaint the whole panel here. Repainting resets the other
        // rows' unsaved dropdown/reason edits, which made their Save buttons
        // appear not to work when reviewing several fields in sequence.
        fields = saved.fields;
        const item = fields[field];
        row.querySelector('[data-status]').textContent =
          panel.querySelector(`[data-status-label="${item.status}"]`).textContent;
        row.querySelector('[data-review]').textContent =
          [item.reviewer, item.date ? new Date(item.date).toLocaleString() : '', item.reason]
            .filter(Boolean).join(' · ');
        row.querySelector('[data-choice]').value = item.status;
        row.querySelector('[data-reason]').value = item.reason;
        const refreshed = await fetch(panel.dataset.url, {headers: {'Accept': 'application/json'}});
        if (refreshed.ok) show(await refreshed.json());
        result.textContent = panel.dataset.saved;
      } catch (_) {result.textContent = panel.dataset.error;}
      finally {button.disabled = false;}
    });
  });
})();
