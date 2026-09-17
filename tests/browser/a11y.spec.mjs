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

const VIEWS = [
  'overview',
  'projects',
  'agents',
  'graph',
  'timeline',
  'analytics',
  'alerts',
  'integrations',
  'settings',
];

test('theme toggle persists across reload without a flash default', async ({ page }) => {
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.locator('#theme').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.reload();
  await page.locator('#login').waitFor({ state: 'hidden' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(await page.evaluate(() => localStorage.getItem('mc-theme'))).toBe('light');
  await page.locator('#theme').click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('keyboard: slash focuses search, Enter opens the inspector', async ({ page }) => {
  await goView(page, 'agents');
  await page.keyboard.press('/');
  await expect(page.locator('#search')).toBeFocused();
  await page.keyboard.press('Escape');
  await page.locator('#view tr[data-inspect="opencode:fx-child"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#inspector')).toHaveAttribute('open', '');
  await expect(page.locator('#inspector-body')).toContainText('fx-child');
  await page.keyboard.press('Escape');
  await expect(page.locator('#inspector')).not.toHaveAttribute('open', '');
});

test('inspector moves focus inside the dialog', async ({ page }) => {
  await goView(page, 'agents');
  await page.locator('#view tr[data-inspect="opencode:fx-root"]').click();
  await expect(page.locator('#inspector')).toHaveAttribute('open', '');
  const inside = await page.evaluate(() =>
    document.getElementById('inspector').contains(document.activeElement),
  );
  expect(inside).toBe(true);
  await page.locator('#close-inspector').click();
});

test('no horizontal clipping on any desktop view', async ({ page }) => {
  for (const view of VIEWS) {
    await goView(page, view);
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      inner: window.innerWidth,
    }));
    expect(overflow.scroll, `${view}: scrollWidth=${overflow.scroll}`).toBeLessThanOrEqual(
      overflow.inner,
    );
  }
});

test('@mobile: navigation drawer opens, traps Escape and closes on navigate', async ({
  page,
}) => {
  const toggle = page.locator('#menu-toggle');
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(page.locator('body')).toHaveClass(/nav-open/);
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(page.locator('body')).not.toHaveClass(/nav-open/);
  await toggle.click();
  await page.locator('.sidebar nav button[data-view="alerts"]').click();
  await expect(page.locator('body')).not.toHaveClass(/nav-open/);
  await expect(page.locator('#view .alert').first()).toBeVisible();
});

test('@mobile: no horizontal clipping on key views', async ({ page }) => {
  for (const view of ['overview', 'agents', 'timeline', 'settings']) {
    await goView(page, view);
    const overflow = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      inner: window.innerWidth,
    }));
    expect(overflow.scroll, `${view}: scrollWidth=${overflow.scroll}`).toBeLessThanOrEqual(
      overflow.inner,
    );
  }
});
