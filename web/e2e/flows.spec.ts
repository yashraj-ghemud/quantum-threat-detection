import { test, expect } from '@playwright/test';
import { open, jsClick } from './helpers';

test('studio: sign and verify is accepted by both recipients', async ({ page }) => {
  const errors: string[] = [];
  await open(page, '/studio', errors);
  await jsClick(page, 'button', 'Sign & verify');
  await expect(page.getByText('Skip to verdict')).toBeVisible({ timeout: 60_000 });
  await jsClick(page, 'button', 'Skip to verdict');
  await expect(page.locator('.class-card').first()).toContainText('ACCEPTED');
  await expect(page.getByText('What the engine recorded')).toBeVisible();
  // Try to break it: a real replay and a real late delivery of the same signature are refused.
  await jsClick(page, 'button', 'Replay it');
  const replay = page.locator('.break-row', { hasText: 'Replay the exact signature' });
  await expect(replay).toContainText('REJECTED', { timeout: 30_000 });
  await expect(replay).toContainText('Replay');
  await jsClick(page, 'button', 'Deliver it late');
  const late = page.locator('.break-row', { hasText: 'Deliver it 5 minutes late' });
  await expect(late).toContainText('REJECTED', { timeout: 30_000 });
  await expect(late).toContainText('old; window is');
  expect(errors).toEqual([]);
});

test('attack lab: blind forgery is rejected and classified', async ({ page }) => {
  const errors: string[] = [];
  await open(page, '/attack-lab?attack=forgery.blind&intensity=0.5', errors);
  const res = page.waitForResponse((r) => r.url().includes('/attacks/run') && r.status() === 200, { timeout: 60_000 });
  const btn = page.locator('.hold-btn'); await btn.scrollIntoViewIfNeeded();
  const box = (await btn.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await page.mouse.down(); await page.waitForTimeout(3000); await page.mouse.up();
  const body = await (await res).json();
  expect(body.detected).toBe(true);
  expect(body.detected_category).toBe('FORGERY');
  await expect(page.locator('.run-verdict')).toContainText('Detected');
  await expect(page.locator('.run-verdict')).toContainText('Correctly classified');
  expect(errors).toEqual([]);
});

test('attack lab: dephasing is fingerprinted', async ({ request }) => {
  const r = await request.post('/api/v1/attacks/run', { data: { attack: { attack_id: 'channel.dephase', intensity: 0.6 } } });
  const body = await r.json();
  expect(body.verdict).toBe('COMPROMISED');
  expect(body.detected_subtype).toBe('dephasing');
});

test('playground: teleportation shows four outcomes', async ({ page }) => {
  const errors: string[] = [];
  await open(page, '/playground', errors);
  await jsClick(page, '[role=tab]', 'Teleport');
  await jsClick(page, 'button', 'Teleport the current state');
  await expect(page.locator('.outcome')).toHaveCount(4);
  expect(errors).toEqual([]);
});

test('ledger: verify, tamper, detect, revert', async ({ page, request }) => {
  await request.post('/api/v1/signatures/sign-and-verify', { data: { message: 'e2e ledger' } });
  await request.post('/api/v1/ledger/seal');
  const errors: string[] = [];
  await open(page, '/ledger', errors);
  await jsClick(page, 'button', 'Verify integrity');
  await expect(page.locator('.stat').filter({ hasText: 'Integrity' })).toContainText('valid');
  await jsClick(page, 'button', 'Tamper demo');
  await jsClick(page, '.modal button', 'Rewrite a stored transaction');
  await expect(page.getByText(/Tamper detected in block/)).toBeVisible();
  await jsClick(page, 'button', 'Revert tamper');
  await expect(page.getByText(/Tamper detected in block/)).toBeHidden();
  expect(errors).toEqual([]);
});

test('command: live traffic produces a feed row', async ({ page }) => {
  const errors: string[] = [];
  await open(page, '/command', errors);
  await page.evaluate(() => fetch('/api/v1/traffic/start', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ rate_per_min: 60 }) }));
  await expect(page.locator('.feed-row').first()).toBeVisible({ timeout: 45_000 });
  await page.evaluate(() => fetch('/api/v1/traffic/stop', { method: 'POST' }));
  expect(errors).toEqual([]);
});

test('analytics: threshold design job renders its table', async ({ page, request }) => {
  const job = await (await request.post('/api/v1/analytics/jobs', { data: { kind: 'threshold_design', preset: 'quick' } })).json();
  await expect.poll(async () => (await (await request.get(`/api/v1/analytics/jobs/${job.id}`)).json()).status, { timeout: 60_000 }).toBe('SUCCEEDED');
  const errors: string[] = [];
  await open(page, '/analytics#threshold_design', errors);
  await expect(page.getByRole('heading', { name: 'Design table', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
