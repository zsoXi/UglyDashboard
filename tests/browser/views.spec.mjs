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
  await expect(page.locator('#analytics-results')).not.toContainText('Obliczanie', {
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
  await expect(page.locator('#toasts .toast')).toContainText('Przyjęto alert');
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
    await expect(page.locator('#config-status')).toContainText('Zapisano');
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

test('incomplete large-history coverage is marked explicitly, not hidden', async ({ page }) => {
  await page.route('**/api/overview*', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.coverage = [
      {
        label: 'OpenCode SQLite',
        total_sessions: 1000,
        loaded_sessions: 96,
        parts_loaded: 95808,
        truncated: true,
        deadline_exceeded: true,
      },
    ];
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  await page.locator('#login').waitFor({ state: 'hidden' });
  const notice = page.locator('.coverage-note');
  await expect(notice).toBeVisible();
  await expect(notice).toContainText('Statystyki niepełne');
  await expect(notice).toContainText('96 z 1000 sesji');
});
