import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	testDir: './tests/e2e',
	fullyParallel: true,
	reporter: 'list',
	use: {
		baseURL: 'http://127.0.0.1:5174',
		trace: 'on-first-retry'
	},
	projects: [
		{
			name: 'chromium',
			use: { ...devices['Desktop Chrome'] }
		}
	],
	webServer: {
		command: 'pnpm exec vite dev --host 127.0.0.1 --port 5174',
		url: 'http://127.0.0.1:5174',
		reuseExistingServer: !process.env.CI,
		timeout: 30_000
	}
});
