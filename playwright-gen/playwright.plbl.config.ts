import { defineConfig } from '@playwright/test';
import { baseConfig } from './playwright.base.config';

export default defineConfig(baseConfig, {
  testDir: './tests/plbl',
  use: {
    // TODO: PL-BL結合テスト環境のURLを設定する
    baseURL: 'http://localhost:8080',
  },
});
