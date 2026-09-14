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
      await page.goto(path);
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
    await expect(page.locator('.profile-record-actions')).toBeVisible();
    await expect(page.locator('.profile-summary')).toBeVisible();
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: testInfo.outputPath(`${locale}-mobile-family-profile.png`), fullPage: true });
  });
}

test('communications search filters rendered supporter rows', async ({ page }) => {
  await page.goto('/communications');
  const rows = page.locator('#communications-supporters-table tbody tr');
  const initial = await rows.count();
  test.skip(initial < 2, 'Demo data needs at least two supporters for this interaction check.');
  await page.getByRole('searchbox', { name: /search supporters/i }).fill('__no_match__');
  await expect(page.locator('#communications-supporters-table tbody tr:visible')).toHaveCount(0);
});
