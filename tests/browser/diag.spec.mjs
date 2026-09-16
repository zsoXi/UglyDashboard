import { expect, test } from '@playwright/test';
import { login } from './fixture.mjs';

/** Fails loudly with the first console/page/network error, for diagnosis. */
test('overview boots without console, page or network errors', async ({ page }) => {
  const problems = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`console: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${(err && err.stack) || err}`));
  page.on('response', async (res) => {
    if (!res.ok()) {
      let body = '';
      try {
        body = await res.text();
      } catch {
        // ignore body read failures
      }
      problems.push(`http ${res.status()} ${res.url()} :: ${body.slice(0, 400)}`);
    }
  });
  await login(page);
  expect(problems).toEqual([]);
});
