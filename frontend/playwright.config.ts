import { defineConfig, devices } from '@playwright/test'

const port = Number(process.env.E2E_PORT || 4173)
const baseURL = `http://127.0.0.1:${port}`

/**
 * Default PR-gate suite uses Chromium + Playwright route-level fake Provider/backend
 * (see e2e/fixtures/fakeBackend.ts). Each test gets an isolated in-memory store.
 *
 * Optional real Provider/channel suite: --project=manual-real-provider
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  outputDir: 'test-results',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      VITE_E2E_FAKE: '1',
    },
  },
  projects: [
    {
      name: 'chromium',
      testIgnore: ['**/manual/**'],
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'manual-real-provider',
      testMatch: ['**/manual/**'],
      use: { ...devices['Desktop Chrome'] },
      // No webServer override: operators point E2E_REAL_BASE_URL at a live stack.
      dependencies: [],
    },
  ],
})
