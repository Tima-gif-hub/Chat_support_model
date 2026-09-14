import { test, expect } from '@playwright/test';

for (const viewport of [{ name: 'desktop', width: 1440, height: 900 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`${viewport.name} catalog citations and complaint states`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto('/customer/?fixture=catalog');
    await expect(page.getByText('Public portfolio interface')).toBeVisible();
    await expect(page.getByRole('button', { name: /S1/ })).toBeVisible();
    await page.getByRole('button', { name: /S1/ }).click();
    await expect(page.getByText(/Solid oak top/)).toBeVisible();
    await page.getByLabel('Demo state').selectOption('confirmation');
    await expect(page.getByRole('button', { name: 'Confirm and submit' })).toBeVisible();
  });
}

test('stored markup is displayed as text', async ({ page }) => {
  await page.goto('/customer/');
  await page.getByLabel('Message').fill('<img src=x onerror=window.pwned=true>');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(await page.evaluate(() => window.pwned)).toBeUndefined();
});

test('message requests preserve JSON content type while overriding Accept', async ({ page }) => {
  let messageContentType = '';
  await page.route('**/api/v1/conversations', async (route) => {
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ conversation_id: 'cnv_test_headers' }) });
  });
  await page.route('**/api/v1/conversations/*/messages', async (route) => {
    messageContentType = route.request().headers()['content-type'] || '';
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: token\ndata: {"text":"ok"}\n\n' });
  });
  await page.goto('/customer/');
  await page.getByLabel('Message').fill('What material is the Alder dining table made from?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect.poll(() => messageContentType).toBe('application/json');
});
