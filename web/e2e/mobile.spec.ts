import { test, expect } from '@playwright/test';
import { open, jsClick } from './helpers';

test('bottom nav navigates and the More sheet opens', async ({ page }, info) => {
  test.skip(info.project.name !== 'mobile', 'mobile only');
  const errors: string[] = [];
  await open(page, '/command', errors);
  await expect(page.locator('.bottomnav')).toBeVisible();
  await jsClick(page, '.bottomnav a', 'Studio');
  await expect(page.locator('main h1').first()).toHaveText(/Signature Studio/);
  await jsClick(page, '.bottomnav button', 'More');
  await expect(page.getByRole('dialog', { name: 'More' })).toBeVisible();
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(sw).toBeLessThanOrEqual(390);
  expect(errors).toEqual([]);
});
