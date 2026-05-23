# CLAUDE.md — playwright-gen

Playwright テスト基盤のサブプロジェクト。設計・構成の詳細は [README.md](README.md) と [docs/](docs/) を参照。

---

## プロジェクト構造の要点

- **`metadata/screens_index.yaml`** — シナリオ作成時に最初に読む。全画面のURL・遷移・フォーム要素が一覧化されている。
- **`metadata/screens/*.yaml`** — 画面ごとの詳細メタデータ（セレクタ・バリデーション・SQL情報を含む）。
- **`pom/*.ts`** — 自動生成された Page Object。`BasePage.ts` のみ手動編集可（再生成で上書きされない）。
- **`tests/plbl/`** — PL-BL 結合テストのシナリオ置き場。新しいシナリオはここに追加する。

---

## シナリオ作成の手順

1. `metadata/screens_index.yaml` を読んで対象画面と遷移パスを確認する
2. 対象画面の `metadata/screens/*.yaml` を読んでセレクタ・バリデーションを把握する
3. `pom/` の対応 Page Object を使ってシナリオを実装する
4. テストデータが必要な場合は [docs/testdata-design.md](docs/testdata-design.md) の方針に従う

---

## 注意事項

- `pom/BasePage.ts` は手動編集されている可能性があるため、`generate_pom.py` は上書きしない設計になっている。
- `playwright.base.config.ts` に共通設定（タイムアウト・リトライ・レポーター）がある。環境固有の設定は各 `playwright.*.config.ts` に記載する。
- テスト用 DB は `ast-analyzer/sample-app/src/main/resources/schema.sql` と `data.sql` で管理されている。
