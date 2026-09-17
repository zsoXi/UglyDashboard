import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { expectQuiet, goView, login, startWatch } from './fixture.mjs';

/**
 * D.2 usage report: period scope, honest costs, presentation-only toggles and
 * a heatmap that separates "no records" from a confirmed zero. Every number
 * asserted here comes from the shared aggregates the API already exposes.
 */

let watch;

test.beforeEach(async ({ page }) => {
  watch = startWatch(page);
  await login(page);
});

test.afterEach(async () => {
  expectQuiet(watch);
});

/** @param {import('@playwright/test').Page} page */
async function openUsage(page) {
  await goView(page, 'analytics');
  await expect(page.locator('#analytics-results .analytics-kpis')).toBeVisible();
}

test('period scope offers today and all history, and keeps the selected filters', async ({
  page,
}) => {
  await openUsage(page);
  const days = page.locator('#days');
  await expect(days.locator('option[value="1"]')).toHaveText('Today');
  await expect(days.locator('option[value="0"]')).toHaveText('All recorded history');
  for (const value of ['7', '30', '90', '365']) {
    await expect(days.locator(`option[value="${value}"]`)).toHaveCount(1);
  }
  await page.locator('#project-filter').selectOption({ label: 'Fixture Alpha' });
  const chosen = await page.locator('#project-filter').inputValue();
  await days.selectOption('30');
  await page.locator('#analytics-apply').click();
  await expect(page.locator('#analytics-results .analytics-kpis')).toBeVisible();
  expect(await page.locator('#project-filter').inputValue()).toBe(chosen);
});

test('presentation toggles never change the measured total', async ({ page }) => {
  await openUsage(page);
  const tokensCard = page.locator('#analytics-results .analytics-kpis [data-total]');
  const total = await tokensCard.getAttribute('data-total');
  expect(total).not.toBeNull();

  await page.locator('#fold-reasoning').click();
  await expect(page.locator('#fold-reasoning')).toHaveClass(/active/);
  await expect(tokensCard).toHaveAttribute('data-total', String(total));

  await page.locator('#chart-percent').click();
  await expect(page.locator('#analytics-results .chart-percent')).toBeVisible();
  await expect(tokensCard).toHaveAttribute('data-total', String(total));
  const shares = await page
    .locator('#analytics-results .chart-percent .statusline .num')
    .allTextContents();
  const sum = shares.reduce((n, text) => n + Number.parseFloat(text), 0);
  expect(shares.length).toBeGreaterThan(0);
  expect(Math.abs(sum - 100)).toBeLessThanOrEqual(1);

  await page.locator('#chart-absolute').click();
  await expect(page.locator('#analytics-results svg.chart')).toBeVisible();
  await expect(tokensCard).toHaveAttribute('data-total', String(total));
});

test('sessions, projects and files stay consistent with the summary', async ({ page }) => {
  await openUsage(page);
  const total = Number(
    await page.locator('#analytics-results .analytics-kpis [data-total]').getAttribute('data-total'),
  );
  const rowsSum = await page
    .locator('#analytics-results tr[data-tokens]')
    .evaluateAll((els) => els.reduce((n, el) => n + Number(el.dataset.tokens || 0), 0));
  expect(rowsSum).toBe(total);

  await expect(page.getByRole('heading', { name: 'Sessions in period' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Projects in period' })).toBeVisible();
  await expect(page.getByText('Unassigned', { exact: true })).toBeVisible();
  await expect(
    page.getByText('Equal-allocation heuristic per session; not a measured per-file cost.'),
  ).toBeVisible();
  const unassigned = await page
    .locator('#analytics-results .statusline')
    .filter({ hasText: 'Unassigned' })
    .locator('.num')
    .innerText();
  expect(Number.parseFloat(unassigned.replace(/[^\d.]/g, ''))).toBeGreaterThan(0);
});

test('heatmap separates missing records from a confirmed zero', async ({ page }) => {
  await openUsage(page);
  await expect(page.getByRole('heading', { name: 'Activity · 52 weeks · global' })).toBeVisible();
  const nodata = page.locator('#analytics-results .heatcell.nodata');
  expect(await nodata.count()).toBeGreaterThan(0);
  await expect(nodata.first()).toHaveAttribute('title', 'no records for this day');
  const confirmed = page.locator('#analytics-results .heatcell:not(.nodata)');
  expect(await confirmed.count()).toBeGreaterThan(0);
});

test('usage report is localized in both languages', async ({ page }) => {
  await openUsage(page);
  await expect(page.getByText('Recorded cost').first()).toBeVisible();
  await page.locator('#lang').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'pl');
  await expect(page.getByRole('heading', { name: 'Sesje w okresie' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Udział (%)' })).toBeVisible();
  await expect(page.getByText('Koszt zapisany').first()).toBeVisible();
  await page.locator('#lang').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
});

test('exports still deliver the selected range', async ({ page }) => {
  await openUsage(page);
  const [json] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('[data-export="json"]').click(),
  ]);
  expect(json.suggestedFilename()).toBe('mission-control.json');
  const [csv] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('[data-export="csv"]').click(),
  ]);
  expect(csv.suggestedFilename()).toBe('mission-control.csv');
  const csvBody = await readFile(await csv.path(), 'utf8');
  expect(csvBody).toContain('# coverage');
  expect(csvBody).toContain('aggregates_complete');
});
