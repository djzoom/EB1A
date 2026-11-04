const { defineConfig } = require('@playwright/test')

module.exports = defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.js',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173/site/',
    browserName: 'chromium',
    timezoneId: 'UTC',
    reducedMotion: 'reduce',
    viewport: { width: 390, height: 844 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  webServer: {
    // CI 已构建并检查同一份产物；本地 npm test 仍自动完整构建。
    command: (process.env.GCTIME_PREBUILT === '1' ? '' : 'npm run build && ') +
      'python3 -m http.server 4173 --bind 127.0.0.1 --directory dist',
    url: 'http://127.0.0.1:4173/site/',
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  }
})
