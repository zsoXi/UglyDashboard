/** Shared helper for the MUSE-1 browser suite (synthetic fixture only). */
import { expect, request as apiRequest } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

export function infoPath() {
  return (
    process.env.MC_FIXTURE_INFO ||
    path.resolve('artifacts/team/muse1/.fixture-info.json')
  );
}

export function fixtureInfo() {
  const file = infoPath();
  if (!existsSync(file)) throw new Error(`browser fixture info missing: ${file}`);
  return JSON.parse(readFileSync(file, 'utf8'));
}

/** Open the dashboard with the ephemeral owner token (fragment auth). */
export async function login(page) {
  const info = fixtureInfo();
  await page.goto(`${info.url}/#access=${encodeURIComponent(info.owner_token)}`);
  await page.locator('#login').waitFor({ state: 'hidden' });
  // Fixture always exposes exactly four synthetic sessions.
  await page.locator('#nav-agents', { hasText: '4' }).waitFor();
  if (page.url().includes('access='))
    throw new Error('owner token fragment was not cleared after login');
  return info;
}

/** Switch to a top-level view via the sidebar nav, opening the mobile drawer
 * first because the nav buttons are off-viewport while it is closed. */
export async function goView(page, name) {
  const mobile = await page.evaluate(() => window.matchMedia('(max-width: 900px)').matches);
  if (mobile) {
    const toggle = page.locator('#menu-toggle');
    if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click();
  }
  await page.locator(`nav button[data-view="${name}"]`).click();
  await page.locator('#view .loading').waitFor({ state: 'detached' }).catch(() => {});
  if (mobile) await expect(page.locator('body')).not.toHaveClass(/nav-open/);
}

/**
 * Attach console/network watchers BEFORE navigation. Call this before login()
 * in beforeEach, then assert with expectQuiet() in afterEach so every normal
 * view test proves: no console errors, no page errors, no failed requests and
 * no unexpected non-OK API responses. `allow` lists URL/text substrings for
 * the explicit error tests only (states.spec, wrong-key login).
 */
export function startWatch(page) {
  const rec = { consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [] };
  page.on('console', (msg) => {
    // Console network errors ("Failed to load resource …") carry the failing
    // resource URL only in the message location, not in the text. Append it so
    // expectQuiet's `allow` substrings can match the same URLs as responses.
    if (msg.type() === 'error') {
      const loc = msg.location();
      rec.consoleErrors.push(`${msg.text()} @ ${loc.url || ''}`);
    }
  });
  page.on('pageerror', (err) => {
    rec.pageErrors.push(String((err && err.message) || err));
  });
  page.on('requestfailed', (req) => {
    rec.failedRequests.push(`${req.url()} :: ${(req.failure() || {}).errorText || 'failed'}`);
  });
  page.on('response', (resp) => {
    if (!resp.ok()) rec.badResponses.push(`${resp.status()} ${resp.url()}`);
  });
  return rec;
}

export function expectQuiet(rec, allow = []) {
  const hit = (s) => allow.some((a) => s.includes(a));
  expect(
    {
      consoleErrors: rec.consoleErrors.filter((s) => !hit(s)),
      pageErrors: rec.pageErrors.filter((s) => !hit(s)),
      failedRequests: rec.failedRequests.filter((s) => !hit(s)),
      badResponses: rec.badResponses.filter((s) => !hit(s)),
    },
    'unexpected console errors, page errors or failed API requests',
  ).toEqual({ consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [] });
}

/** Authenticated APIRequestContext for the ephemeral fixture (Node side).
 * Uses the APIRequest factory from @playwright/test, not the per-test
 * `request` fixture (which is already a context and has no newContext). */
export async function apiScope() {
  const info = fixtureInfo();
  const ctx = await apiRequest.newContext({
    baseURL: info.url,
    extraHTTPHeaders: { Authorization: `Bearer ${info.owner_token}` },
  });
  return { info, ctx };
}
