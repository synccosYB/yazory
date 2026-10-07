document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-additional-askan-form]').forEach(form => {
    const input = form.querySelector('[data-additional-askan-search]');
    const results = form.querySelector('[data-additional-askan-results]');
    let timer;
    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = true;
      results.disabled = true;
      if (q.length < 2) return;
      timer = setTimeout(async () => {
        try {
          const response = await fetch(input.dataset.searchUrl + '?q=' + encodeURIComponent(q), {headers: {'Accept': 'application/json'}});
          if (!response.ok) return;
          const people = await response.json();
          people.forEach(person => {
            const option = document.createElement('option');
            option.value = person.id;
            option.textContent = person.name + (person.phone ? ' · ' + person.phone : '') + ' · ID ' + person.id;
            results.appendChild(option);
          });
          if (people.length) {
            results.hidden = false;
            results.disabled = false;
            results.selectedIndex = 0;
          }
        } catch (error) {}
      }, 180);
    });
    results.addEventListener('change', () => {
      if (results.value) input.value = results.options[results.selectedIndex].textContent;
    });
  });
});
