import { defineConfig } from '@playwright/test';
import { baseConfig } from './playwright.base.config';

export default defineConfig(baseConfig, {
  testDir: './tests/e2e',
  use: {
    // TODO: 総合テスト環境のURLを設定する
    baseURL: 'http://localhost:8080',
  },
});
