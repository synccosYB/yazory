document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.donation-person-search').forEach(input => {
    const form = input.closest('form');
    const results = form.querySelector('.donation-person-results');
    const contacts = form.querySelector('.donation-contact-select');
    const addButton = form.querySelector('.donation-person-add');
    const newBox = form.querySelector('.donation-person-new');
    const newName = form.querySelector('.donation-new-name');
    const newPhone = form.querySelector('.donation-new-phone');
    const createButton = form.querySelector('.donation-person-create');
    const createMessage = form.querySelector('.donation-person-create-message');
    let timer;

    addButton.addEventListener('click', () => {
      newBox.hidden = !newBox.hidden;
      if (!newBox.hidden) {
        newName.value = input.value.trim();
        newName.focus();
      }
    });

    createButton.addEventListener('click', async () => {
      createMessage.textContent = '';
      const name = newName.value.trim();
      if (!name) {
        createMessage.textContent = 'Enter the person’s name.';
        return;
      }
      const body = new FormData();
      body.append('csrf', form.querySelector('[name="csrf"]').value);
      body.append('name', name);
      body.append('phone', newPhone.value.trim());
      try {
        const response = await fetch(addButton.dataset.createUrl, {
          method: 'POST', body, headers: {'Accept': 'application/json'}
        });
        const data = await response.json();
        if (response.status === 409 && data.matches) {
          createMessage.textContent = 'Possible duplicate. Choose the existing person from the search results instead.';
          input.value = name;
          input.dispatchEvent(new Event('input'));
          return;
        }
        if (!response.ok) {
          createMessage.textContent = data.error || 'Could not add person.';
          return;
        }
        results.replaceChildren();
        const option = document.createElement('option');
        option.value = data.id;
        option.textContent = data.name + (data.phone ? ' · ' + data.phone : '') + ' · ID ' + data.id;
        option.selected = true;
        results.appendChild(option);
        results.disabled = false;
        results.hidden = false;
        contacts.value = '';
        input.value = option.textContent;
        newBox.hidden = true;
      } catch (error) {
        createMessage.textContent = 'Could not add person.';
      }
    });

    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      results.disabled = true;
      results.hidden = true;
      results.replaceChildren();
      if (q.length < 2) return;
      timer = setTimeout(async () => {
        try {
          const response = await fetch(input.dataset.searchUrl + '?q=' + encodeURIComponent(q), {
            headers: {'Accept': 'application/json'}
          });
          if (!response.ok) return;
          const people = await response.json();
          people.forEach(person => {
            const option = document.createElement('option');
            option.value = person.id;
            option.textContent = person.name + (person.phone ? ' · ' + person.phone : '') + ' · ID ' + person.id;
            results.appendChild(option);
          });
          if (people.length) {
            results.disabled = false;
            results.hidden = false;
          }
        } catch (error) {}
      }, 180);
    });

    results.addEventListener('change', () => {
      if (results.value) {
        contacts.value = '';
        input.value = results.options[results.selectedIndex].textContent;
      }
    });
    results.addEventListener('dblclick', () => {
      if (results.value) form.requestSubmit();
    });
    contacts.addEventListener('change', () => {
      if (contacts.value) {
        results.disabled = true;
        results.hidden = true;
        results.replaceChildren();
        input.value = '';
      }
    });
  });
});
