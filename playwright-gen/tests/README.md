# tests/ — テストシナリオ概要

## テスト工程の3層構成

| ディレクトリ | 工程 | 目的 | 設定ファイル |
|---|---|---|---|
| [plbl/](plbl/README.md) | PL-BL 結合テスト | 画面操作〜業務ロジックの結合動作を確認する | `playwright.plbl.config.ts` |
| integration/ | 連結テスト | 複数サブシステムをまたぐ連携を確認する | `playwright.integration.config.ts` |
| e2e/ | 総合テスト | システム全体を本番に近い環境で検証する | `playwright.e2e.config.ts` |

現時点でシナリオが存在するのは `plbl/` のみ。

---

## 実行コマンド

```powershell
# PL-BL 結合テストのみ実行
npx playwright test --config playwright.plbl.config.ts

# 全テストを実行（全設定ファイル）
npx playwright test

# ヘッドあり（ブラウザ表示）で実行
npx playwright test --config playwright.plbl.config.ts --headed

# 特定シナリオのみ実行
npx playwright test tests/plbl/scenario_01_order.spec.ts --config playwright.plbl.config.ts
```

---

## 前提条件

- サンプルアプリが起動していること（`ast-analyzer/sample-app/up.bat` または Docker Compose）
- `playwright.plbl.config.ts` の `baseURL` がアプリの URL に設定されていること
- DB に `schema.sql` + `data.sql` が適用されていること
