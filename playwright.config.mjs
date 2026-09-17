import { defineConfig } from '@playwright/test';

/**
 * MUSE-1 browser QA for UglyDashboard v5.
 * The app under test is NOT started here: tests/browser/global-setup.mjs
 * spawns scripts/browser_fixture.py (real Engine + Server, ephemeral data,
 * OS-assigned port) and tests/browser/global-teardown.mjs stops it again.
 * No webServer entry on purpose: the fixture lifecycle is explicit, so a
 * stale dashboard can never be tested by accident.
 */
export default defineConfig({
  testDir: 'tests/browser',
  globalSetup: 'tests/browser/global-setup.mjs',
  globalTeardown: 'tests/browser/global-teardown.mjs',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: 'artifacts/team/muse1/test-results',
  reporter: [
    ['list'],
    ['html', { outputFolder: 'artifacts/team/muse1/playwright-report', open: 'never' }],
  ],
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: 'desktop',
      grepInvert: /@mobile/,
      use: { viewport: { width: 1280, height: 800 } },
    },
    {
      name: 'mobile',
      grep: /@mobile/,
      use: {
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
});
