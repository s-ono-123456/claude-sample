# playwright-gen

`ast-analyzer/sample-app`（Spring MVC + MyBatis）を対象とした Playwright E2E テスト基盤。

Neo4j グラフ解析結果をメタデータとして事前収集し、Page Object Model（POM）を自動生成することで、シナリオ作成を効率化する。

---

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [設計方針](docs/design.md) | プロジェクト全体の設計・ディレクトリ構成・メタデータ生成フロー |
| [extract_metadata.py 実装方針](docs/extract_metadata_impl.md) | メタデータ収集スクリプトの実装詳細 |
| [generate_pom.py 実装方針](docs/generate_pom_impl.md) | POM 自動生成スクリプトの実装詳細 |
| [テストデータ自動生成設計](docs/testdata-design.md) | 遷移パス解析によるテストデータ自動生成の設計 |
| [既知の課題](docs/known_issues.md) | 発生した問題と対処の記録 |

---

## ディレクトリ構成

```
playwright-gen/
  collect/                    # 事前収集スクリプト
    extract_metadata.py       # Neo4j + JSP解析 → screens.yaml 生成
    generate_pom.py           # screens.yaml → TypeScript POM ファイル生成
    screens_master.yaml       # URL の正となる手動管理ファイル
    templates/                # Jinja2 テンプレート

  metadata/                   # 生成物（Git 管理）
    screens/                  # 画面ごとのメタデータ YAML
    screens_index.yaml        # 全画面インデックス

  pom/                        # 生成物（Git 管理）
    BasePage.ts               # 手動編集可（初回生成後は上書きしない）
    *Page.ts                  # 各画面の Page Object

  tests/                      # テストシナリオ（手動管理）
    plbl/                     # PL-BL 結合テスト
    integration/              # 連結テスト
    e2e/                      # 総合テスト

  docs/                       # 設計ドキュメント
```

---

## セットアップ

```powershell
cd playwright-gen
npm install
npx playwright install chromium
```

---

## テスト実行

```powershell
# PL-BL 結合テスト
npm run test:plbl

# 連結テスト
npm run test:integration

# 総合テスト（E2E）
npm run test:e2e

# ヘッドあり（ブラウザ表示）で実行
npm run test:headed:plbl

# レポート表示
npm run report
```

---

## メタデータ・POM 再生成

```powershell
# 1. Neo4j グラフからメタデータを収集
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml

# 2. メタデータから POM を生成
uv run python playwright-gen/collect/generate_pom.py
```

> 前提: `ast-analyzer/config.yaml` に Neo4j 接続情報が設定済みであること。
> 対象アプリ（sample-app）が起動済みであること。
