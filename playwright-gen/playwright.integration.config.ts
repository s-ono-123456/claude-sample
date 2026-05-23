import { defineConfig } from '@playwright/test';
import { baseConfig } from './playwright.base.config';

export default defineConfig(baseConfig, {
  testDir: './tests/integration',
  use: {
    // TODO: 連結テスト環境のURLを設定する
    baseURL: 'http://localhost:8080',
  },
});
