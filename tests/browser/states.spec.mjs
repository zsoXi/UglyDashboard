import { expect, test } from '@playwright/test';
import { expectQuiet, fixtureInfo, goView, login, startWatch } from './fixture.mjs';

test('search with no matches shows the empty state', async ({ page }) => {
  const watch = startWatch(page);
  await login(page);
  await goView(page, 'agents');
  await page.locator('#search').fill('zzz-no-such-fixture');
  await expect(page.locator('#view .empty')).toContainText('Brak sesji');
  await page.locator('#reset-filters').click();
  await expect(page.locator('#view table.table')).toBeVisible();
  expectQuiet(watch);
});

test('failed overview request renders an error notice, not a blank page', async ({ page }) => {
  const watch = startWatch(page);
  const info = fixtureInfo();
  await page.route('**/api/overview', (route) => route.abort('failed'));
  await page.goto(`${info.url}/#access=${encodeURIComponent(info.owner_token)}`);
  await expect(page.locator('#view .notice.danger')).toBeVisible();
  await page.unroute('**/api/overview');
  // Explicit expected failure: the aborted request must be the only noise.
  expect(watch.failedRequests.some((s) => s.includes('/api/overview'))).toBe(true);
  expectQuiet(watch, ['/api/overview']);
});

test('failed timeline request surfaces an error toast', async ({ page }) => {
  const watch = startWatch(page);
  await login(page);
  await goView(page, 'timeline');
  await expect(page.locator('#timeline-events .event').first()).toBeVisible();
  await page.route('**/api/timeline*', (route) => route.abort('failed'));
  await page.locator('#timeline-search').click();
  await expect(page.locator('#toasts .toast.error').first()).toBeVisible();
  await page.unroute('**/api/timeline*');
  // Explicit expected failure: the aborted request must be the only noise.
  expect(watch.failedRequests.some((s) => s.includes('/api/timeline'))).toBe(true);
  expectQuiet(watch, ['/api/timeline']);
});
