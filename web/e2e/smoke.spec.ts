import { test, expect } from '@playwright/test';
import { open } from './helpers';

const ROUTES: [string, RegExp][] = [
  ['/command', /Command Center/], ['/studio', /Signature Studio/], ['/attack-lab', /Attack Lab/], ['/playground', /Quantum Playground/],
  ['/analytics', /Analytics/], ['/ledger', /Audit ledger/], ['/incidents', /Incidents/], ['/method', /How QVeris defends/], ['/nope', /State collapsed/],
];

for (const [path, title] of ROUTES) {
  test(`renders ${path} without console errors`, async ({ page }, info) => {
    const errors: string[] = [];
    await open(page, path, errors);
    await expect(page.locator('main h1').first()).toHaveText(title);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `e2e/artifacts/${info.project.name}${path.replace(/\//g, '_')}.png` });
    expect(errors).toEqual([]);
  });
}

test('overview mounts the original story scene', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.addInitScript(() => { sessionStorage.setItem('qveris.booted', '1'); sessionStorage.setItem('qveris.film', '1'); });
  await page.goto('/');
  await expect(page.locator('iframe.legacy-scene')).toBeAttached();
  await expect(page.getByText('The live system')).toBeVisible();
  expect(errors).toEqual([]);
});
