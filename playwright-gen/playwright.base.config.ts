import { defineConfig } from '@playwright/test';

export const baseConfig = defineConfig({
  timeout: 30_000,
  retries: 0,
  reporter: 'html',
  use: {
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
