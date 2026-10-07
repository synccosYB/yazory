const { test, expect } = require('@playwright/test');

for (const locale of ['en', 'he', 'yi']) {
  test(`${locale} person save exits editing and validation preserves edits`, async ({ page }) => {
    await page.goto(`/language/${locale}?next=/supporter-directory`);
    const link = page.locator('a[href^="/supporter-directory/"][href$="/edit"]').first();
    await expect(link).toBeVisible();
    await link.click();
    const panel = page.locator('[data-person-verification]');
    await expect(panel).toHaveAttribute('data-profile-mode', 'view');
    const input = panel.locator('[data-verification-field="cell_phone"] [data-edit]');
    await expect(input).toBeHidden();
    await panel.locator('[data-person-mode="edit"]').click();
    await expect(input).toBeEnabled();
    const original = await input.inputValue();
    await input.fill('9175550199');
    await panel.locator('[data-save]').click();
    await expect(panel).toHaveAttribute('data-profile-mode', 'view');
    await expect(input).toBeHidden();
    await expect(panel.locator('[data-verification-field="cell_phone"] [data-value]')).toContainText('9175550199');
    await page.reload();
    await expect(panel).toHaveAttribute('data-profile-mode', 'view');
    await expect(panel.locator('[data-verification-field="cell_phone"] [data-value]')).toContainText('9175550199');
    await panel.locator('[data-person-mode="edit"]').click();
    await input.fill(original);
    await page.route('**/verification', async route => {
      if (route.request().method() === 'POST') await route.fulfill({status: 400, contentType: 'application/json', body: JSON.stringify({error: 'Check the phone'})});
      else await route.continue();
    });
    await panel.locator('[data-save]').click();
    await expect(panel.locator('[data-result]')).toHaveText('Check the phone');
    await expect(panel).toHaveAttribute('data-profile-mode', 'edit');
    await expect(input).toHaveValue(original);
    await page.unroute('**/verification');
    await panel.locator('[data-save]').click();
    await expect(panel).toHaveAttribute('data-profile-mode', 'view');
    await page.locator('[data-person-tab="case-connections"]').click();
    await expect(page.locator('#case-connections')).toBeVisible();
    await expect(page.locator('#identity')).toBeHidden();
  });
}
