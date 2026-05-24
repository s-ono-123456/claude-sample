# e2e リグレッションテスト 設計書

総合テスト（e2e）レベルでオンライン処理（Playwright）とバッチ処理（SSH）を組み合わせた
多日サイクルのリグレッションテストを自動実行するための設計。

---

## 1. 概要

### 目的

- アプリ改修後のリグレッション検証を手作業なしで実施する
- 1日分のオンライン打鍵 → 夜間バッチ → 翌日打鍵 という業務サイクルを自動で再現する
- 複数シナリオを同じ業務日内で並列実行し、バッチを最小回数（1日1回）に抑えて短時間化する

### 対象テストレベル

`tests/e2e/` に配置する総合テスト（e2e）。

| テストレベル | ディレクトリ | 説明 |
|---|---|---|
| PL-BL 結合テスト | `tests/plbl/` | フロント〜バックエンドの結合（バッチなし） |
| 連結テスト | `tests/integration/` | システム間連携（バッチあり・日次ではない） |
| **総合テスト（本設計）** | **`tests/e2e/`** | **業務サイクル全体（複数日 + 夜間バッチ）** |

### 実行環境

```
開発端末 / CI コンテナ
  │
  ├─ Playwright（ブラウザ自動操作）→ Web アプリ（AP サーバ）
  │
  └─ SSH ──────────────────────────→ バッチサーバ
                                        ├─ 連携 CSV 配置スクリプト
                                        └─ 夜間バッチ実行スクリプト
```

---

## 2. ディレクトリ構成

既存の構成に以下を追加する。

```
playwright-gen/
  lib/
    ssh-client.ts            ← SSH接続・バッチ実行・CSV配置（新規）
  regression/
    regression-runner.ts     ← オーケストレータ（新規）
    regression.config.ts     ← SSH・実行設定（新規）
  tests/e2e/
    scenario_01_xxx.spec.ts  ← 1ファイル＝1シナリオ（全日程を含む）
    scenario_02_xxx.spec.ts
    ...
  docs/
    e2e-regression-design.md ← 本ファイル
```

---

## 3. シナリオファイル設計

### 基本構造

1シナリオにつき1ファイル。全日程（Day1〜DayN）を1ファイルに収める。

```typescript
// tests/e2e/scenario_01_order.spec.ts
import { test } from '@playwright/test';
import { LoginPage }       from '../../pom/LoginPage';
import { OrderListPage }   from '../../pom/OrderListPage';
import { OrderDetailPage } from '../../pom/OrderDetailPage';

test.describe.serial('シナリオ01: 受注登録から請求確認まで', () => {

  test('[Day1] 受注入力・確定', async ({ page }) => { ... });

  test('[Day2] 出荷処理・在庫引当', async ({ page }) => { ... });

  test('[Day3] 請求締め・照合確認', async ({ page }) => { ... });

});
```

### タグ規則

| 要素 | 規則 | 用途 |
|---|---|---|
| describe 名 | `シナリオNN: 〜` | レポート表示・識別 |
| test 名 | `[DayN] 〜`（角括弧必須） | オーケストレータが `--grep` で日別抽出 |

### `describe.serial` の効果

- 同一 describe ブロック内のテストを**順番に実行**する
- Day1 が失敗したら、同シナリオの Day2 以降を**自動スキップ**する
- ファイルをまたいだ並列実行は**この設定の影響を受けない**（Playwright のファイル間並列は維持）

### POM の使い方

既存の `tests/plbl/` と同じパターンで直接インスタンス化する。

```typescript
test('[Day1] 受注入力', async ({ page }) => {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.waitForLoad();
  await loginPage.ログイン('user01', 'password');
  // ...
});
```

### テストデータの独立性（並列実行の前提）

複数シナリオが同じ業務日に並列実行されるため、シナリオ間でテストデータが衝突してはならない。

- ユーザアカウント・顧客コード・受注番号等をシナリオごとに**固定の別データ**を使用する
- `testdata/` フォルダにシナリオ別のテストデータ定数ファイルを配置する

---

## 4. 並列実行の仕組み

### Day 単位の実行フロー

```
npm run regression
  │
  ├─ [Day1] npx playwright test --grep "\[Day1\]"
  │          ├─ scenario_01: [Day1] 受注入力    ─┐
  │          ├─ scenario_02: [Day1] 契約登録    ─┤ ファイル間並列（workers）
  │          └─ scenario_03: [Day1] 入金処理    ─┘
  │                    ↓ 全完了を待つ
  │
  ├─ SSH: CSV 配置（Day2 用）
  ├─ SSH: 夜間バッチ実行 → 業務日付が Day2 に進む
  │
  ├─ [Day2] npx playwright test --grep "\[Day2\]"
  │          ├─ scenario_01: [Day2] 出荷処理    ─┐
  │          └─ scenario_02: [Day2] 解約処理    ─┘ 並列
  │                    ↓ 全完了を待つ
  │
  ├─ SSH: CSV 配置（Day3 用）
  ├─ SSH: 夜間バッチ実行 → 業務日付が Day3 に進む
  │
  └─ [Day3] npx playwright test --grep "\[Day3\]"
             └─ scenario_01: [Day3] 請求確認
```

### Playwright workers の動作

- デフォルト: CPU コア数分のワーカーでファイル間を並列実行
- `describe.serial` はファイル内の順序制御のみ（ファイル間の並列を妨げない）
- `--grep "[Day2]"` でフィルタした場合、各ファイルで該当 test のみ実行される

### シナリオ日数が異なる場合

シナリオによって日数が異なっても動作する。
`[Day3]` が存在しないシナリオは `--grep "[Day3]"` の対象外となり自動的にスキップされる。

---

## 5. オーケストレータ設計

**ファイル**: `regression/regression-runner.ts`

### 責務

1. 設定を読み込む（`regression.config.ts`）
2. SSH クライアントに接続する
3. Day ループ（1〜N）を回す
   - Playwright CLI を同期呼び出し（`--grep "[DayN]"`）
   - バッチ前の CSV 配置（SSH）
   - 夜間バッチ実行（SSH）
4. 完了後に SSH 切断

### 骨格

```typescript
// regression/regression-runner.ts
import { spawnSync }       from 'child_process';
import { SshClient }       from '../lib/ssh-client';
import { regressionConfig } from './regression.config';

async function main(): Promise<void>
```

### 失敗時の挙動

| 状況 | デフォルト挙動 | 環境変数で変更 |
|---|---|---|
| Day N のテストが失敗 | バッチを実行して次の Day へ進む | `FAIL_FAST=true` で中断 |
| バッチ処理が失敗 | エラーを出力してプロセス終了 | 変更不可（整合性のため） |
| SSH 接続失敗 | エラーを出力してプロセス終了 | 変更不可 |

> **デフォルトをバッチ続行にする理由**: バッチが実行されないと業務日付が進まず、
> 後続の手動確認もできなくなるため。テスト失敗はレポートで確認する。

---

## 6. SSH クライアント設計

**ファイル**: `lib/ssh-client.ts`  
**依存パッケージ**: `node-ssh`（npm）

### 骨格

```typescript
// lib/ssh-client.ts
import { NodeSSH } from 'node-ssh';

interface SshConfig {
  host: string;
  port: number;
  username: string;
  privateKeyPath: string;
  batchScript: string;
  csvPlaceScript: string;
}

export class SshClient {
  constructor(config: SshConfig)
  async connect(): Promise<void>
  async runBatch(): Promise<void>
  async placeCsvFiles(day: number): Promise<void>
  async disconnect(): Promise<void>
}
```

### CSV 配置方針

バッチサーバ側のシェルスクリプト（`csvPlaceScript`）に **day 番号** を引数で渡す。
どの CSV をどこに配置するかはシェル側が管理する（クライアント側は関与しない）。

```bash
# バッチサーバ上のシェル例（参考）
/batch/place_csv.sh 2   # Day2 用 CSV を所定ディレクトリに配置
```

### 認証

秘密鍵ファイル（PEM/OpenSSH 形式）を使用。パスワード認証は非推奨。
CI 環境ではシークレットとして管理し、実行時にファイルに書き出して使用する。

---

## 7. 設定設計

**ファイル**: `regression/regression.config.ts`

すべての設定を環境変数から読み込む。`.env` ファイルや CI シークレットで管理する。

| 環境変数 | 説明 | デフォルト |
|---|---|---|
| `BATCH_SSH_HOST` | バッチサーバのホスト名・IP | なし（必須） |
| `BATCH_SSH_PORT` | SSH ポート番号 | `22` |
| `BATCH_SSH_USER` | SSH ユーザ名 | なし（必須） |
| `BATCH_SSH_KEY` | 秘密鍵ファイルのパス | `~/.ssh/id_rsa` |
| `BATCH_SCRIPT` | 夜間バッチ実行シェルのフルパス | なし（必須） |
| `CSV_PLACE_SCRIPT` | CSV 配置シェルのフルパス | なし（必須） |
| `REGRESSION_MAX_DAYS` | テストサイクルの最大日数 | `3` |
| `FAIL_FAST` | Day 失敗時にバッチをスキップするか | `false` |

---

## 8. 実行方法

### package.json に追加するスクリプト

```json
{
  "scripts": {
    "regression": "tsx regression/regression-runner.ts"
  },
  "dependencies": {
    "node-ssh": "^13.x"
  },
  "devDependencies": {
    "tsx": "^4.x"
  }
}
```

- `tsx`: TypeScript をコンパイルなしで直接実行（`ts-node` の後継）
- `node-ssh`: SSH 接続ライブラリ（runtime dependency）

### tsconfig.json への追加

`include` に以下を追加する。

```json
"include": [
  "*.ts",
  "tests/**/*.ts",
  "pom/**/*.ts",
  "lib/**/*.ts",
  "regression/**/*.ts"
]
```

### 実行コマンド

```powershell
# 環境変数を設定して実行
$env:BATCH_SSH_HOST = "batch-server.example.com"
$env:BATCH_SSH_USER = "batchuser"
$env:BATCH_SSH_KEY  = "C:\Users\user\.ssh\id_rsa"
$env:BATCH_SCRIPT   = "/home/batchuser/scripts/run_nightly.sh"
$env:CSV_PLACE_SCRIPT = "/home/batchuser/scripts/place_csv.sh"
$env:REGRESSION_MAX_DAYS = "3"

npm run regression
```

### 個別 Day の手動実行

オーケストレータを使わず特定の Day だけ実行したい場合は Playwright CLI を直接使う。

```powershell
npx playwright test --config playwright.e2e.config.ts --grep "\[Day2\]"
```

---

## 9. レポート

### 日別レポートの分離

オーケストレータが各 Day の Playwright 実行時に `--output-dir` を指定し、日別にレポートを分離する。

```
playwright-report/
  day-1/   ← Day1 の HTML レポート
  day-2/   ← Day2 の HTML レポート
  day-3/   ← Day3 の HTML レポート
```

### 確認方法

```powershell
npx playwright show-report playwright-report/day-1
```

---

## 10. 制約・注意事項

### テスト時間

```
総実行時間 ≈ Σ(各 Day のオンライン処理時間) + バッチ実行時間 × (日数 - 1)
```

バッチ実行時間が支配的になる場合、バッチ側でのチューニングが必要。

### Workers 数の調整

デフォルトは CPU コア数。シナリオ数が多い場合は `playwright.e2e.config.ts` で明示的に設定する。

```typescript
// playwright.e2e.config.ts
export default defineConfig(baseConfig, {
  testDir: './tests/e2e',
  workers: 4,  // 環境に合わせて調整
  use: { baseURL: '...' },
});
```

### CI 環境での SSH 鍵管理

GitHub Actions の場合：

```yaml
- name: Write SSH key
  run: |
    mkdir -p ~/.ssh
    echo "${{ secrets.BATCH_SSH_KEY }}" > ~/.ssh/batch_rsa
    chmod 600 ~/.ssh/batch_rsa
  env:
    BATCH_SSH_KEY: ~/.ssh/batch_rsa
```

### `describe.serial` と grep の組み合わせ

`--grep "[Day2]"` を指定すると、各シナリオの `describe.serial` ブロック内で
Day2 以外のテストはスキップされる。`describe.serial` の「失敗時に後続スキップ」は
**同一実行内でのみ有効**（別 Day の実行には引き継がれない）。

→ Day1 が失敗した場合、Day2 の実行時にデータが揃っていないためテストが失敗することで
   自然に「シナリオが壊れている」と検出できる。

---

## 付録: 実装ロードマップ

設計書作成完了後、以下の順序で実装する。

| フェーズ | 作業内容 |
|---|---|
| 1 | `node-ssh` / `tsx` のインストール。`tsconfig.json` 更新 |
| 2 | `lib/ssh-client.ts` 実装 |
| 3 | `regression/regression.config.ts` 実装 |
| 4 | `regression/regression-runner.ts` 実装 |
| 5 | `playwright.e2e.config.ts` に `workers` 設定追加 |
| 6 | `tests/e2e/` にサンプルシナリオを1件作成して動作確認 |
