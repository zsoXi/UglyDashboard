import { expect, test } from '@playwright/test';
import { expectQuiet, goView, login, startWatch } from './fixture.mjs';

let watch;
test.beforeEach(async ({ page }) => {
  watch = startWatch(page);
  await login(page);
});
test.afterEach(async () => {
  expectQuiet(watch);
});

/**
 * Publishable screenshots: the fixture only serves synthetic English/Polish
 * labels, and no secret is ever revealed in this file.
 */
test('desktop dark: overview and agents', async ({ page }) => {
  await expect(page.locator('#view .kpi').first()).toBeVisible();
  await page.screenshot({ path: 'docs/screenshots/overview-dark.png' });
  await page.locator('#lang').click();
  await expect(page.locator('#lang-code')).toHaveText('PL');
  await page.screenshot({ path: 'docs/screenshots/overview-pl-dark.png' });
  await page.locator('#lang').click();
  await expect(page.locator('#lang-code')).toHaveText('EN');
  await goView(page, 'agents');
  await expect(page.locator('#view table.table')).toBeVisible();
  await page.screenshot({
    path: 'artifacts/team/muse1/agents-dark.png',
  });
  await goView(page, 'graph');
  await expect(page.locator('#graph-svg')).toBeVisible();
  await page.screenshot({ path: 'artifacts/team/muse1/graph-dark.png' });
});

test('desktop light: overview', async ({ page }) => {
  await page.locator('#theme').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.locator('#view .kpi').first()).toBeVisible();
  await page.screenshot({ path: 'docs/screenshots/overview-light.png' });
});

test('@mobile: overview and open navigation', async ({ page }) => {
  await expect(page.locator('#view .kpi').first()).toBeVisible();
  await page.screenshot({ path: 'docs/screenshots/overview-mobile.png' });
  await page.locator('#lang').click();
  await expect(page.locator('#lang-code')).toHaveText('PL');
  await page.screenshot({ path: 'docs/screenshots/overview-pl-mobile.png' });
  await page.locator('#lang').click();
  await expect(page.locator('#lang-code')).toHaveText('EN');
  await page.locator('#menu-toggle').click();
  await expect(page.locator('body')).toHaveClass(/nav-open/);
  await page.screenshot({ path: 'artifacts/team/muse1/nav-mobile.png' });
});
