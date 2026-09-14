import { test, expect } from '@playwright/test';

for (const viewport of [{ name: 'desktop', width: 1440, height: 900 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`${viewport.name} queue filters and actions`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto('/manager/?fixture=queue');
    await expect(page.getByText('Public portfolio interface')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Delivery Damage' })).toBeVisible();
    await expect(page.getByText('Explicit request')).toBeVisible();
    await page.getByLabel('Subtype').selectOption('delivery_delay');
    await expect(page.getByRole('button', { name: /Delivery Delay/ })).toBeVisible();
  });
}

test('manager can acknowledge and add a note in deterministic fixture mode', async ({ page }) => {
  await page.goto('/manager/?fixture=queue');
  await page.getByRole('button', { name: 'Acknowledge', exact: true }).click();
  await expect(page.locator('.detail-grid dd', { hasText: 'Acknowledged' })).toBeVisible();
  await page.getByLabel('Visible to managers only').fill('<script>not markup</script>');
  await page.getByRole('button', { name: 'Save note' }).click();
  await expect(page.getByRole('status')).toContainText('Saved');
  await expect(page.locator('.notes script')).toHaveCount(0);
});
