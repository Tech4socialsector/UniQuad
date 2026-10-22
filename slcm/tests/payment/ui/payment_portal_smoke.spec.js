// Payment portal UI smoke tests (certification layer — no Razorpay charge)
const { test, expect } = require('@playwright/test');

test.describe('Payment portal pages load', () => {
	test('admission login page', async ({ page }) => {
		const response = await page.goto('/nlsatadmissions/login', { waitUntil: 'domcontentloaded' });
		expect(response?.status()).toBeLessThan(400);
		await expect(page.locator('input[type="email"], input[name="email"], #login_email').first()).toBeVisible({
			timeout: 15_000,
		});
	});

	test('PACE login page', async ({ page }) => {
		const response = await page.goto('/paceadmissions/login', { waitUntil: 'domcontentloaded' });
		expect(response?.status()).toBeLessThan(400);
		await expect(page.locator('input[type="email"], input[name="email"], #login_email').first()).toBeVisible({
			timeout: 15_000,
		});
	});

	test('PACE application form redirects guests to login', async ({ page }) => {
		await page.goto('/paceadmissions/application-form', { waitUntil: 'domcontentloaded' });
		await page.waitForURL(/\/pace\/login/, { timeout: 20_000 });
		expect(page.url()).toContain('/paceadmissions/login');
	});

	test('/login redirects to admission portal login', async ({ page }) => {
		await page.goto('/login', { waitUntil: 'domcontentloaded' });
		await page.waitForURL(/\/nlsatadmissions\/login/, { timeout: 20_000 });
		await expect(page.locator('input[type="email"], input[name="email"], #login_email').first()).toBeVisible({
			timeout: 15_000,
		});
	});
});

test.describe('Payment UI assets', () => {
	test('applicant portal stylesheet is served', async ({ request }) => {
		const res = await request.get('/assets/slcm/css/applicant_portal.css');
		expect(res.status()).toBeLessThan(400);
	});
});
