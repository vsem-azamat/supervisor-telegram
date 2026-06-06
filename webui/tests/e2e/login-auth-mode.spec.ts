import { expect, test } from '@playwright/test';

test('magic-link auth mode does not load Telegram Login Widget', async ({ page }) => {
	let telegramWidgetRequested = false;

	await page.route('**/api/auth/config', async (route) => {
		await route.fulfill({
			contentType: 'application/json',
			body: JSON.stringify({
				auth_mode: 'magic_link',
				bot_username: 'dynamic_bot',
				bot_start_url: 'https://t.me/dynamic_bot?start=admin_login_dev'
			})
		});
	});
	await page.route('**/api/auth/me', async (route) => {
		await route.fulfill({
			status: 401,
			contentType: 'application/json',
			body: JSON.stringify({ detail: 'not authenticated' })
		});
	});
	await page.route('https://telegram.org/**', async (route) => {
		telegramWidgetRequested = true;
		await route.abort();
	});

	await page.goto('/login');

	await expect(page.getByRole('heading', { name: 'Konnekt Admin' })).toBeVisible();
	await expect(page.getByText('Open the magic link from Telegram to continue.')).toBeVisible();
	await expect(page.getByRole('link', { name: 'Open Telegram bot' })).toHaveAttribute(
		'href',
		'https://t.me/dynamic_bot?start=admin_login_dev'
	);
	await expect(page.getByText('Bot domain invalid')).toHaveCount(0);
	expect(telegramWidgetRequested).toBe(false);
});
