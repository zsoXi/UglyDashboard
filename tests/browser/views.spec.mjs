import { expect, test } from '@playwright/test';
import { apiScope, expectQuiet, goView, login, startWatch } from './fixture.mjs';

let watch;
test.beforeEach(async ({ page }) => {
  watch = startWatch(page);
  await login(page);
});
test.afterEach(async () => {
  expectQuiet(watch);
});

test('overview renders stats, projects, sessions and event stream', async ({ page }) => {
  await expect(page.locator('#view .kpi')).toHaveCount(4);
  await expect(page.locator('#view .campus')).toHaveCount(2);
  await expect(page.locator('#view')).toContainText('Fixture');
  await expect(page.locator('#overview-events .event').first()).toBeVisible();
  await expect(page.locator('#view table.table tbody tr')).toHaveCount(4);
});

test('projects view shows both fixture spaces', async ({ page }) => {
  await goView(page, 'projects');
  await expect(page.locator('#view .campus')).toHaveCount(2);
  await expect(page.locator('#view')).toContainText('Fixture Alpha');
  await expect(page.locator('#view')).toContainText('Fixture Beta');
});

test('agents view supports table/cards modes and inspector', async ({ page }) => {
  await goView(page, 'agents');
  const rows = page.locator('#view table.table tbody tr');
  await expect(rows).toHaveCount(4);
  await page.locator('#view button[data-mode="cards"]').click();
  await expect(page.locator('#view .agentcard')).toHaveCount(4);
  await page.locator('#view button[data-mode="table"]').click();
  await expect(page.locator('#view table.table')).toBeVisible();

  await page.locator('#view tr[data-inspect="opencode:fx-root"]').click();
  const dialog = page.locator('#inspector');
  await expect(dialog).toHaveAttribute('open', '');
  await expect(page.locator('#inspector-body')).toContainText('fx-root');
  await expect(page.locator('#inspector-body')).toContainText('Fixture prompt for');
  await page.locator('#close-inspector').click();
  await expect(dialog).not.toHaveAttribute('open', '');
});

test('search narrows sessions and project buttons jump to agents', async ({ page }) => {
  await goView(page, 'agents');
  await page.locator('#search').fill('fx-docs');
  await expect(page.locator('#view table.table tbody tr')).toHaveCount(1);
  await expect(page.locator('#view')).toContainText('fx-docs');
  await page.locator('#reset-filters').click();
  await expect(page.locator('#view table.table tbody tr')).toHaveCount(4);

  await goView(page, 'projects');
  await page.locator('#view button[data-project]').first().click();
  await expect(page.locator('#view table.table')).toBeVisible();
});

test('graph draws delegation edges, zooms and opens the inspector from a node', async ({
  page,
}) => {
  await goView(page, 'graph');
  await expect(page.locator('#graph-svg')).toBeVisible();
  await expect(page.locator('#graph-layer [data-inspect="opencode:fx-child"]')).toBeVisible();
  // Real edges, not just nodes: the fixture tree has confirmed parent links.
  expect(await page.locator('#graph-layer path.edge').count()).toBeGreaterThanOrEqual(1);
  await expect(page.locator('#graph-count')).not.toBeEmpty();

  // Zoom control really rescales the layer transform.
  const layer = page.locator('#graph-layer');
  const scaleOf = (t) => Number(/scale\(([^)]+)\)/.exec(t || '')?.[1]);
  const before = scaleOf(await layer.getAttribute('transform'));
  await page.locator('.graph-toolbar button[data-zoom="in"]').click();
  await expect
    .poll(async () => scaleOf(await layer.getAttribute('transform')))
    .toBeGreaterThan(before);

  // Clicking a node opens the session inspector (same contract as table rows).
  await page.locator('#graph-layer [data-inspect="opencode:fx-child"]').click();
  await expect(page.locator('#inspector')).toHaveAttribute('open', '');
  await expect(page.locator('#inspector-body')).toContainText('fx-child');
  await page.locator('#close-inspector').click();
  await expect(page.locator('#inspector')).not.toHaveAttribute('open', '');
});

test('timeline searches and paginates through the more cursor', async ({ page }) => {
  await goView(page, 'timeline');
  const events = page.locator('#timeline-events .event');
  const more = page.locator('#timeline-more');
  // The fixture seeds >100 events, so the first page is full and the cursor
  // button is visible (the 5s auto-refresh never touches this view).
  await expect(events).toHaveCount(100);
  await expect(more).toBeVisible();
  const firstCount = await events.count();
  await more.click();
  // The second page appends older events and exhausts the cursor.
  await expect.poll(async () => events.count()).toBeGreaterThan(firstCount);
  await expect(more).toBeHidden();

  await page.locator('#timeline-query').fill('Fixture prompt sample');
  await page.locator('#timeline-search').click();
  await expect(page.locator('#timeline-events')).toContainText('Fixture prompt sample');
});

test('analytics aggregates fixture token usage', async ({ page }) => {
  await goView(page, 'analytics');
  await expect(page.locator('#analytics-results')).not.toContainText('Calculating', {
    timeout: 15_000,
  });
  await expect(page.locator('#analytics-results')).toContainText('fx-');
});

test('alerts show fixture budget signals and acknowledge works', async ({ page }) => {
  await goView(page, 'alerts');
  const alerts = page.locator('#view .alert');
  await expect(alerts.first()).toBeVisible();
  await expect(page.locator('#view')).toContainText('budget');
  const ack = page.locator('#view .alert .actions button[data-ack]').first();
  await ack.click();
  await expect(page.locator('#toasts .toast')).toContainText('Alert acknowledged');
});

test('integrations show sources and scan results without leaking secrets', async ({ page }) => {
  await goView(page, 'integrations');
  await expect(page.locator('#scan-roots')).toBeVisible();
  await expect(page.locator('#scan-results')).toContainText('fixture', { ignoreCase: true });

  // The secrets panel lists names only; values require an explicit POST.
  const { ctx } = await apiScope();
  try {
    const listed = await ctx.get('/api/integrations');
    expect(listed.ok()).toBe(true);
    const body = await listed.text();
    expect(body).toContain('pairing_key');
    const revealed = await ctx.post('/api/reveal', { data: { name: 'pairing_key' } });
    expect(revealed.ok()).toBe(true);
    const value = (await revealed.json()).value;
    // Length-only assertion: the value itself must never reach test logs.
    expect(typeof value === 'string' ? value.length : 0).toBeGreaterThan(16);
    expect(body.includes(value)).toBe(false);
  } finally {
    await ctx.dispose();
  }
});

test('settings config edit saves, persists across reload and is restored', async ({ page }) => {
  const { ctx } = await apiScope();
  const getConfig = async () => (await (await ctx.get('/api/config')).json());
  const original = await getConfig();
  const editedValue = original.poll_seconds >= 120 ? 59 : original.poll_seconds + 1;
  try {
    await goView(page, 'settings');
    const editor = page.locator('#config-editor');
    await expect(editor).toContainText('token_budget');
    const raw = await editor.inputValue();
    const cfg = JSON.parse(raw);
    cfg.poll_seconds = editedValue;
    await editor.fill(JSON.stringify(cfg, null, 2));
    await page.locator('#config-save').click();
    await expect(page.locator('#config-status')).toContainText('Saved');
    // Server-side persistence, independent of the editor DOM.
    await expect.poll(async () => (await getConfig()).poll_seconds).toBe(editedValue);
    // A full reload proves the value survived a fresh read of config.json.
    await page.reload();
    await page.locator('#login').waitFor({ state: 'hidden' });
    await goView(page, 'settings');
    await expect(page.locator('#config-editor')).toContainText(
      `"poll_seconds": ${editedValue}`,
    );
  } finally {
    const restore = await ctx.post('/api/config', { data: original });
    expect(restore.ok()).toBe(true);
    await expect.poll(async () => (await getConfig()).poll_seconds).toBe(original.poll_seconds);
    await ctx.dispose();
  }
});

const COVERAGE_BASE = {
  scope: { kind: 'snapshot', window_limit: 1000, sessions_loaded: 96 },
  metadata_complete: false,
  aggregates_complete: true,
  history_limited: true,
  breakdowns: { daily: 'partial', model: 'partial', file: 'partial' },
  breakdown_details: { sessions_scored: 96 },
  details_truncated: true,
  detail_events_evicted: 21438,
  catching_up: false,
  source_stale: false,
  read_blocked: false,
  discovered_sessions: 1000,
  processed_sessions: 1000,
  last_successful_read_at: 1737000000000,
};

/** @param {import('@playwright/test').Page} page @param {object} coverage */
async function mockCoverage(page, coverage) {
  await page.route('**/api/overview*', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.coverage = coverage;
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await page.locator('#login').waitFor({ state: 'hidden' });
}

test('complete totals with limited details stay informational, not an alarm', async ({
  page,
}) => {
  await mockCoverage(page, COVERAGE_BASE);
  const notice = page.locator('.coverage-note');
  await expect(notice).toBeVisible();
  await expect(notice).toContainText('Usage totals are complete');
  await expect(notice).toContainText('Detailed history is limited');
  await expect(notice).toContainText('Partial breakdowns');
  await expect(notice).toContainText('Only the newest');
  await expect(notice).not.toHaveClass(/coverage-degraded/);
});

test('incomplete aggregates are marked explicitly, not hidden', async ({ page }) => {
  await mockCoverage(page, {
    ...COVERAGE_BASE,
    aggregates_complete: false,
    catching_up: true,
    processed_sessions: 96,
  });
  const notice = page.locator('.coverage-note');
  await expect(notice).toBeVisible();
  await expect(notice).toContainText('Import is still running');
  await expect(notice).toHaveClass(/coverage-degraded/);
});

test('a blocked source never claims completeness', async ({ page }) => {
  await mockCoverage(page, {
    ...COVERAGE_BASE,
    metadata_complete: null,
    aggregates_complete: false,
    history_limited: false,
    details_truncated: false,
    breakdowns: { daily: 'unknown', model: 'unknown', file: 'unknown' },
    detail_events_evicted: 0,
    read_blocked: true,
    discovered_sessions: null,
    processed_sessions: null,
  });
  const notice = page.locator('.coverage-note');
  await expect(notice).toBeVisible();
  await expect(notice).toContainText('cannot be read right now');
  await expect(notice).toHaveClass(/coverage-degraded/);
  await expect(notice).not.toContainText('Usage totals are complete');
});
