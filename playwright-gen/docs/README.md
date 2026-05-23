# docs/ — 設計書インデックス

## ファイル一覧

| ファイル | 内容 |
|---|---|
| [design.md](design.md) | 全体設計方針・screens.yaml スキーマ・POM 生成方針・CI フロー |
| [extract_metadata_impl.md](extract_metadata_impl.md) | `extract_metadata.py` の実装詳細（処理フロー・CLI・依存ライブラリ）|
| [generate_pom_impl.md](generate_pom_impl.md) | `generate_pom.py` の実装詳細（処理フロー・Jinja2 テンプレート・CLI）|
| [testdata-design.md](testdata-design.md) | テストデータ自動生成の設計方針（シナリオ YAML・INSERT 文生成）|
| [known_issues.md](known_issues.md) | 既知の課題とその解消状況 |

---

## ユースケース別の読み方

### Playwright シナリオを書きたい

1. `design.md` — 全体像と screens.yaml のスキーマを把握する
2. `metadata/screens_index.yaml` — 対象画面の URL・遷移を確認する
3. `metadata/screens/{画面id}.yaml` — フォーム・セレクタ・バリデーションを確認する
4. `pom/` — 既存 Page Object を使って spec を書く

### `extract_metadata.py` を実装・改修したい

1. `design.md` — 設計方針・screens.yaml スキーマを把握する
2. `extract_metadata_impl.md` — 処理フロー・CLI・依存ライブラリを確認する

### `generate_pom.py` を実装・改修したい

1. `design.md` — POM 実装方針・生成例を把握する
2. `generate_pom_impl.md` — セレクタ解決ルール・Jinja2 テンプレートを確認する

### テストデータを生成したい

1. `testdata-design.md` — 全体の設計と入力フォーマットを把握する

### 動作がおかしいときに原因を調べたい

1. `known_issues.md` — 既知の課題と対処法を確認する
