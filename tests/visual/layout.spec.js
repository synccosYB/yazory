const { test, expect } = require('@playwright/test');

const pages = ['/', '/families', '/families/1', '/communications', '/operations'];
const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
  // A 720-CSS-pixel viewport exercises the layout seen at 200% zoom on a
  // common 1440-pixel desktop without depending on browser-specific zoom APIs.
  { name: 'zoom-200', width: 720, height: 800 }
];

for (const viewport of viewports) {
  for (const path of pages) {
    test(`${viewport.name} ${path} has no page-level clipping`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      expect((await page.goto(path)).status()).toBe(200);
      await expect(page.locator('main')).toBeVisible();
      await page.waitForLoadState('networkidle');

      const overflow = await page.evaluate(() => ({
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth
      }));
      expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth + 1);

      await page.screenshot({
        path: testInfo.outputPath(`${viewport.name}-${path === '/' ? 'overview' : path.slice(1)}.png`),
        fullPage: true
      });
    });
  }
}

for (const locale of ['he', 'yi']) {
  test(`${locale} communications is RTL and unclipped`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/language/${locale}?next=/communications`);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: testInfo.outputPath(`${locale}-mobile-communications.png`), fullPage: true });
  });
}

for (const locale of ['he', 'yi']) {
  test(`${locale} family profile keeps its operational controls`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/language/${locale}?next=/families/1`);
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('.case-workspace-actions')).toBeVisible();
    await expect(page.locator('.case-status-card')).toBeVisible();
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: testInfo.outputPath(`${locale}-mobile-family-profile.png`), fullPage: true });
  });
}

test('communications search filters rendered supporter rows', async ({ page }) => {
  expect((await page.goto('/communications')).status()).toBe(200);
  await page.locator('.mailbox-tools-link').click();
  if (await page.locator('#outreach-workflow').evaluate(element => !element.open)) {
    await page.locator('#outreach-workflow > summary').click();
  }
  const rows = page.locator('#communications-supporters-list .communication-accordion-item');
  const initial = await rows.count();
  expect(initial).toBeGreaterThan(0);
  await page.getByRole('searchbox', { name: /search supporters/i }).fill('__no_match__');
  await expect(page.locator('#communications-supporters-list .communication-accordion-item:visible')).toHaveCount(0);
});

for (const target of ['expense-requests', 'provider-expenses', 'financial-pledges']) {
  test(`case deep link reveals every parent tab: ${target}`, async ({ page }) => {
    await page.goto(`/families/1#${target}`);
    await expect(page.locator(`#${target}`)).toBeAttached();
    expect(await page.locator(`#${target}`).evaluate(element => {
      for (let parent = element; parent; parent = parent.parentElement) {
        if (parent.hidden) return false;
      }
      return true;
    })).toBe(true);
    await page.locator('[data-case-tab="overview"]').click();
    await page.locator('a[href="#expense-requests"]').first().click();
    await expect(page.locator('#expense-requests')).toBeVisible();
  });
}


test('applicant reply destination opens the applicant folder', async ({ page }) => {
  await page.goto('/communications?folder=applicants#mailbox-inbox');
  await expect(page.locator('[data-mailbox-folder="applicants"]')).toHaveClass(/selected/);
  await expect(page.locator('.mailbox-list-fold')).toHaveAttribute('open', '');
});


test('person editor saves through the browser and persists after reopening', async ({ page }) => {
  await page.goto('/supporter-directory');
  const destination = await page.locator('a[href^="/supporter-directory/"][href$="/edit"]').first().getAttribute('href');
  expect(destination).toBeTruthy();
  await page.goto(destination);
  const panel = page.locator('[data-person-verification]');
  const notes = panel.locator('[data-verification-field="notes"] [data-edit]');
  await expect(notes).toBeEnabled();
  const previous = await notes.inputValue();
  const marker = `Browser audit ${Date.now()}`;
  try {
    await notes.fill(marker);
    await panel.locator('[data-save]').click();
    await expect(panel.locator('[data-result]')).toHaveText('Person saved');
    await page.reload();
    await expect(notes).toHaveValue(marker);
  } finally {
    await notes.fill(previous);
    await panel.locator('[data-save]').click();
    await expect(panel.locator('[data-result]')).toHaveText('Person saved');
  }
});


test('household child actions reveal working add and edit forms', async ({ page }) => {
  await page.goto('/families/1#add-child-record');
  await expect(page.locator('.add-child-record form')).toBeVisible();
  await expect(page.locator('.add-child-record form')).toHaveAttribute('action', '/families/1/children');
  const record = page.locator('.child-record').first();
  const target = await record.getAttribute('id');
  expect(target).toBeTruthy();
  await page.goto(`/families/1#${target}`);
  await expect(record.locator('form')).toBeVisible();
});


for (const locale of ['en', 'he', 'yi']) {
  for (const width of [1440, 390]) {
    test(`askan editor save stays reachable and persists: ${locale} ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/language/${locale}?next=/partner-network`);
      const csrf = await page.locator('input[name="csrf"]').first().inputValue();
      const created = await page.request.post('/partner-network/askonim', { form: {
        csrf, name: `Save audit ${locale} ${width} ${Date.now()}`, phone: ''
      }});
      expect(created.ok()).toBeTruthy();
      await page.goto(created.url());
      const form = page.locator('.askan-edit-form');
      const save = form.locator('button[type="submit"]');
      await expect(save).toBeInViewport();
      const cell = `845${String(Date.now()).slice(-7)}`;
      await form.locator('[name="cell_phone"]').fill(cell);
      await form.locator('[name="notes"]').fill('Askan save regression');
      await expect(save).toBeInViewport();
      await save.click();
      await expect(form.locator('[name="cell_phone"]')).toHaveValue(cell);
      await page.reload();
      await expect(form.locator('[name="cell_phone"]')).toHaveValue(cell);
      await expect(form.locator('[name="notes"]')).toHaveValue('Askan save regression');
    });
  }
}
