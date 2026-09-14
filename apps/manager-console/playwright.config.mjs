import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.mjs',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4174',
    headless: true,
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
  },
  webServer: {
    command: 'python ../../scripts/serve_frontend.py --directory src --prefix manager --port 4174',
    url: 'http://127.0.0.1:4174/manager/',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
