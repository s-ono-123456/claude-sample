# アプリ改修時のテスト管理フロー

アプリケーションを改修した場合に、POM・テストケースをどう維持するかの方針を定める。

---

## 改修の種類と影響範囲

改修の種類によってフローが異なる。まず改修を以下の3種に分類する。

| 改修の種類 | screens.yaml | POM | 既存テスト | 新規テスト |
|---|---|---|---|---|
| **A: DOM 変更**（セレクタ・フォーム・遷移変更） | 変化あり | 変化あり | 修正が必要な場合あり | 基本不要 |
| **B: 新機能追加**（新画面・新入力項目追加） | 変化あり（新ファイル/追記） | 変化あり（新ファイル/追記） | 影響なし | **新規シナリオ作成が必要** |
| **C: バックエンドのみ変更**（DOM 無変化） | 変化なし | 変化なし | 影響なし（期待値の手動確認を推奨） | 基本不要 |

---

## フロー A: 既存テスト修正（DOM 変更・遷移変更）

### トリガー

`collect/extract_metadata.py` + `collect/generate_pom.py` の再実行後、
**`metadata/screens/*.yaml` または `pom/*.ts` に差分が出たとき**。

### ステップ

```
1. TypeScript コンパイルチェック（機械的フィルタ）
   tsc --noEmit
   └─ コンパイルエラーあり → エラー箇所が修正対象（LLM へのヒントにする）
   └─ コンパイルエラーなし → LLM での意味的判断へ進む

2. LLM による影響判断
   入力：
     - screens.yaml diff（YAML。なぜ変わったかの意味的文脈）
     - pom/*.ts diff（TypeScript。テストが直接依存する変更点）
     - tests/ の既存テストファイル（修正箇所を特定するため）
   判断基準：
     - セレクタ変更 → 対応する Locator を使っているテストを特定
     - メソッド引数変更 → 呼び出し箇所をすべて修正
     - 遷移先変更（transition_to / waitForLoad の URL） → アサーション更新
     - waitForLoad() の内容変更 → 直接呼び出しているすべてのシナリオを確認

3. LLM によるテスト修正
   変更対象：tests/ 以下のファイルのみ
   変更禁止：pom/*.ts（手動編集禁止。再生成で上書きされる）

4. CI 検証
   tsc --noEmit → Playwright テスト実行（修正されたシナリオを含むスイート）

5. PR 作成 → 人間レビュー → マージ
```

### LLM が判断すべきケースと不要なケース

| 変更の種類 | LLM 判断の要否 | 理由 |
|---|---|---|
| メソッド削除・シグネチャ変更 | **不要**（TypeScript が検出） | コンパイルエラーで即判明 |
| セレクタ変更（#id → [name=...]） | **必要** | コンパイルは通るが実行時に失敗する可能性 |
| 遷移先 URL 変更 | **必要** | `expect(page).toHaveURL(...)` のアサーションがずれる |
| waitForLoad() 内の title 変更 | **必要** | 動的タイトル対応など挙動が変わる |
| 新規入力項目追加（既存フォームに追加） | **必要** | 既存テストは通るが、新項目を含むテストケースの追加を検討すべき |

---

## フロー B: 新規シナリオ作成（新画面・新機能追加）

### トリガー

POM の**新ファイルが追加されたとき**（`pom/XxxPage.ts` が新たに生成された場合）。

> 注意: 既存テストはコンパイルエラーにも実行エラーにもならないため、
> 差分ベースの「修正不要」判定に引っかからない。新ファイル検出を別途行う。

### ステップ

```
1. 新規 POM ファイルの検出
   git diff --name-only | grep "^pom/.*\.ts$" | grep -v "BasePage.ts"
   └─ 新しい *.ts が含まれているか確認

2. 対応する screens.yaml を読む
   metadata/screens/{画面id}.yaml を参照して
   フォーム・遷移・アサーション情報を把握

3. LLM によるシナリオ設計依頼（Claude Code）
   「{画面名}の正常系シナリオを作って」のように依頼する
   シナリオ作成の詳細手順は CLAUDE.md を参照

4. PR 作成 → 人間レビュー → マージ
```

---

## フロー C: バックエンド変更のみ（DOM 無変化）

POM に変化がないため、テスト修正フロー（A/B）は発動しない。

ただし、**業務ロジックの変更**（金額計算・状態遷移のルール変更など）によって
テストの期待値が実態とずれるケースがある。

対応方針：
- テスト内の値アサーション（`expect(total).toBe(1000)` 等）は仕様変更時に手動で見直す
- バックエンド変更の PR に「テスト期待値の確認」をレビューチェックリストとして含める

---

## LLM への入力と制約

### LLM に渡す情報

| 情報 | 理由 |
|---|---|
| `metadata/screens/*.yaml` の差分 | なぜ変わったかの意味的文脈（LLM の判断精度向上） |
| `pom/*.ts` の差分 | テストが直接依存している変更点 |
| `tests/` の既存テストファイル | 修正対象の特定・文脈理解のため |
| TypeScript コンパイルエラー出力（あれば） | エラー箇所を修正ヒントとして使う |

### 変更禁止領域

```
pom/*.ts       ← 手動編集禁止（generate_pom.py の再実行で上書きされる）
collect/       ← 生成スクリプト（テスト管理フローでは触らない）
metadata/      ← 自動生成物（テスト管理フローでは触らない）
```

**LLM が修正してよいのは `tests/` 以下のみ。**

---

## CI パイプライン例（GitHub Actions）

```yaml
# .github/workflows/test-maintenance.yml
on:
  pull_request:
    paths:
      - 'playwright-gen/pom/**'
      - 'playwright-gen/metadata/**'

jobs:
  check-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # diff 取得のため

      # TypeScript コンパイルチェック（フロー A の前段フィルタ）
      - name: TypeScript compile check
        run: |
          cd playwright-gen
          npm ci
          npx tsc --noEmit

      # POM 差分・screens.yaml 差分を取得して LLM へ渡す処理（実装は別途）
      # - name: Analyze impact with LLM
      #   run: ...

      # テスト実行（LLM が修正した後、または手動修正後）
      - name: Run Playwright tests
        run: |
          cd playwright-gen
          npx playwright test --config playwright.plbl.config.ts
```

> CI の LLM 呼び出し部分の実装は別途検討。
> まずは TypeScript チェック + テスト実行を自動化し、
> LLM による修正案の生成は Claude Code セッションで手動実行する運用から始めることを推奨する。

---

## まとめ：方針の全体像

```
アプリ改修
  ├─ DOM 変更あり
  │    ├─ extract_metadata.py + generate_pom.py 実行
  │    ├─ tsc --noEmit（コンパイルエラーを機械的に検出）
  │    ├─ LLM に screens.yaml diff + POM diff + tests/ を渡して影響判断
  │    ├─ LLM が tests/ を修正（pom/ は触らない）
  │    ├─ CI 検証（tsc + Playwright）
  │    └─ PR → 人間レビュー → マージ
  │
  ├─ 新画面・新機能追加
  │    ├─ 新 POM ファイル検出
  │    ├─ Claude Code に「{画面名}のシナリオを作って」と依頼
  │    └─ PR → 人間レビュー → マージ
  │
  └─ バックエンドのみ変更
       ├─ POM 変化なし → テスト修正フロー発動しない
       └─ 値アサーションを手動で確認（PR レビューチェックリストに含める）
```
