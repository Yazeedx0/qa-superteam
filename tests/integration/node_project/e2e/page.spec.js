import { test, expect } from '@playwright/test';
test.describe('static page', () => {
  test('has title', async ({ page }) => {
    await page.setContent('<title>Hi</title><h1>Hello</h1>');
    await expect(page).toHaveTitle('Hi');
  });
  test('wrong heading', async ({ page }) => {
    await page.setContent('<h1>Hello</h1>');
    await expect(page.locator('h1')).toHaveText('Bye', { timeout: 500 });
  });
});
