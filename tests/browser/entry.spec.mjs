import { expect, test } from '@playwright/test';
import { expectQuiet, fixtureInfo, login, startWatch } from './fixture.mjs';

test('login cover requires an owner key', async ({ page }) => {
  const watch = startWatch(page);
  const info = fixtureInfo();
  await page.goto(info.url);
  const login = page.locator('#login');
  await expect(login).toBeVisible();
  await expect(login).toContainText('Owner key');
  await page.locator('#login-token').fill('wrong-key');
  await page.locator('#login-form button[type="submit"]').click();
  await expect(page.locator('#login-error')).toContainText('key', { ignoreCase: true });
  await expect(login).toBeVisible();
  // The wrong key must actually hit the API and be rejected there (explicit
  // expected failure: non-OK /api/overview is allowed in this test only).
  expect(watch.badResponses.some((s) => s.includes('/api/overview'))).toBe(true);
  expectQuiet(watch, ['/api/overview']);
});

let watch;
test.beforeEach(async ({ page }, testInfo) => {
  if (testInfo.title === 'login cover requires an owner key') return;
  watch = startWatch(page);
  await login(page);
});
test.afterEach(async ({}, testInfo) => {
  if (testInfo.title === 'login cover requires an owner key') return;
  expectQuiet(watch);
});

test('owner key via #access fragment logs in and clears the fragment', async ({ page }) => {
  await login(page);
  await expect(page.locator('#view')).not.toContainText('Reading your sources');
  await expect(page.locator('.kpi .value').first()).toBeVisible();
});

test('owner can reveal the pairing key explicitly', async ({ page }) => {
  await login(page);
  await page.locator('nav button[data-view="integrations"]').click();
  const button = page.locator('button[data-reveal="pairing_key"]');
  await expect(button).toBeVisible();
  const output = page.locator('output[data-reveal-out="pairing_key"]');
  await expect(output).toBeEmpty();
  await button.click();
  await expect(output).not.toBeEmpty();
  await expect(page.locator('#toasts .toast')).toContainText('pairing_key');
});
