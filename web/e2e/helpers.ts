import { expect, type Page } from '@playwright/test';

export async function open(page: Page, path: string, errors: string[]) {
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !/ERR_CERT|net::ERR_/.test(m.text())) errors.push(m.text()); });
  await page.addInitScript(() => { sessionStorage.setItem('qveris.booted', '1'); sessionStorage.setItem('qveris.film', '1'); });
  await page.goto(path);
  await expect(page.locator('main h1').first()).toBeVisible();
}
/** Click through the page without Playwright's actionability waits (heavy WebGL in software rendering). */
export async function jsClick(page: Page, selector: string, text?: string) {
  await page.evaluate(([sel, t]) => {
    const els = [...document.querySelectorAll<HTMLElement>(sel)];
    const el = t ? els.find((e) => e.textContent?.trim().includes(t)) : els[0];
    if (!el) throw new Error(`not found: ${sel} ${t ?? ''}`);
    el.click();
  }, [selector, text ?? ''] as const);
}
