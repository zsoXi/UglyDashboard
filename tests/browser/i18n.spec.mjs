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

test('defaults to English, switches to Polish and keeps the working state', async ({ page }) => {
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.locator('#lang-code')).toHaveText('EN');
  await expect(page.locator('#heading')).toHaveText('Operations center');
  await expect(page.locator('.brand .brandtext small')).toHaveText('MISSION CONTROL');

  await goView(page, 'agents');
  await page.locator('#search').fill('fx-docs');
  await page.locator('#view tr[data-inspect="opencode:fx-beta"]').click();
  await expect(page.locator('#inspector')).toHaveAttribute('open', '');

  // The modal inspector blocks pointer events on the topbar; the switch is
  // triggered programmatically to prove it never closes the open dialog.
  await page.evaluate(() => {
    const button = document.getElementById('lang');
    if (button instanceof HTMLButtonElement) button.click();
  });
  await expect(page.locator('html')).toHaveAttribute('lang', 'pl');
  await expect(page.locator('#lang-code')).toHaveText('PL');
  await expect(page.locator('#heading')).toHaveText('Agenci i sesje');
  // Filters, the current view and an open inspector survive the switch.
  await expect(page.locator('#search')).toHaveValue('fx-docs');
  await expect(page.locator('#view')).toContainText('fx-docs');
  await expect(page.locator('#inspector')).toHaveAttribute('open', '');
  await page.locator('#close-inspector').click();
  expect(await page.evaluate(() => localStorage.getItem('mc-lang'))).toBe('pl');

  await page.reload();
  await page.locator('#login').waitFor({ state: 'hidden' });
  await expect(page.locator('html')).toHaveAttribute('lang', 'pl');
  await expect(page.locator('#lang-code')).toHaveText('PL');
  await expect(page.locator('#heading')).toHaveText('Agenci i sesje');

  await page.locator('#lang').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.locator('#lang-code')).toHaveText('EN');
});

test('renders both languages without missing keys', async ({ page }) => {
  await expect(page.locator('#lang-code')).toHaveText('EN');
  await expect
    .poll(async () => page.evaluate(() => window.mcMissingKeys()))
    .toEqual([]);
  for (const view of ['overview', 'projects', 'graph', 'analytics', 'integrations', 'settings']) {
    await goView(page, view);
    expect(await page.evaluate(() => window.mcMissingKeys())).toEqual([]);
  }

  await page.locator('#lang').click();
  await expect(page.locator('#lang-code')).toHaveText('PL');
  for (const view of ['overview', 'projects', 'graph', 'analytics', 'integrations', 'settings']) {
    await goView(page, view);
    expect(await page.evaluate(() => window.mcMissingKeys())).toEqual([]);
  }
});

test('@mobile: language switch keeps the drawer and localized labels', async ({ page }) => {
  await page.locator('#lang').click();
  await expect(page.locator('#lang-code')).toHaveText('PL');
  const toggle = page.locator('#menu-toggle');
  await toggle.click();
  await expect(page.locator('body')).toHaveClass(/nav-open/);
  await expect(page.locator('.sidebar nav button[data-view="overview"]')).toContainText('Przegląd');
  await page.locator('.sidebar nav button[data-view="alerts"]').click();
  await expect(page.locator('body')).not.toHaveClass(/nav-open/);
  await expect(page.locator('#heading')).toHaveText('Wymaga uwagi');
});
