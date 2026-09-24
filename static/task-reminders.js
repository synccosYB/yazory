(() => {
  const box = document.getElementById('task-reminder-popup');
  if (!box) return;
  let shown = '';
  async function check() {
    try {
      const response = await fetch('/tasks/reminders/pending', {credentials: 'same-origin'});
      if (!response.ok) return;
      const tasks = await response.json();
      const task = tasks[0];
      if (!task || shown === String(task.id)) return;
      shown = String(task.id);
      box.replaceChildren();
      const heading = document.createElement('strong');
      heading.textContent = box.dataset.title;
      const name = document.createElement('p');
      name.textContent = task.title;
      const link = document.createElement('a');
      link.href = task.url;
      link.textContent = box.dataset.open;
      const dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.textContent = box.dataset.dismiss;
      dismiss.addEventListener('click', async () => {
        const form = new FormData();
        form.append('csrf', box.dataset.csrf);
        const result = await fetch(`/tasks/${task.id}/reminder/dismiss`, {method: 'POST', body: form, credentials: 'same-origin'});
        if (result.ok) { box.hidden = true; shown = ''; check(); }
      });
      box.append(heading, name, link, dismiss);
      box.hidden = false;
    } catch (_) { /* A lost connection can be retried on the next poll. */ }
  }
  check();
  setInterval(check, 60000);
})();
