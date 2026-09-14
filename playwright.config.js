const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/visual',
  fullyParallel: false,
  retries: 1,
  reporter: [['line'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: process.env.VISUAL_BASE_URL || 'http://127.0.0.1:5010',
    browserName: 'chromium',
    colorScheme: 'light',
    locale: 'en-US',
    timezoneId: 'America/New_York'
  }
});
