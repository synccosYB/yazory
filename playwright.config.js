const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/visual',
  fullyParallel: false,
  retries: 1,
  reporter: [['line'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    storageState: process.env.VISUAL_STORAGE_STATE || undefined,
    baseURL: process.env.VISUAL_BASE_URL || 'http://127.0.0.1:5010',
    browserName: 'chromium',
    launchOptions: process.env.VISUAL_BROWSER_EXECUTABLE ? {
      executablePath: process.env.VISUAL_BROWSER_EXECUTABLE,
      args: ['--no-sandbox', '--disable-dev-shm-usage']
    } : {},
    colorScheme: 'light',
    locale: 'en-US',
    timezoneId: 'America/New_York'
  }
});
