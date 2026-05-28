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
    ssh-client.ts            ← SSH接続・バッチ実行・CSV配置・IFファイル転送（新規）
    if-file-builder.ts       ← IFファイル組み立てロジック（新規）
  regression/
    regression-runner.ts     ← オーケストレータ（新規）
    regression.config.ts     ← SSH・実行設定（新規）
  tests/e2e/
    scenario_01_xxx.spec.ts  ← 1ファイル＝1シナリオ（全日程を含む）
    scenario_02_xxx.spec.ts
    ...
  tmp/
    scenario_01_state.json   ← Day 間の状態引き継ぎファイル（実行時生成・gitignore）
    scenario_02_state.json
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
| test 名 | `[MakeIfFile_DayN] 〜` | バッチ後・翌日テスト前に実行する IF ファイル生成ステップ |

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

- ユーザアカウント・顧客コード等をシナリオごとに**固定の別データ**を使用する
- `testdata/` フォルダにシナリオ別のテストデータ定数ファイルを配置する

#### システム採番値（連番 ID・伝票番号等）の扱い

受注番号・請求番号のようなシステムが自動採番する値は事前に確定できない。
「採番された瞬間にキャプチャして後続 Day に引き継ぐ」方針で対処する。

**実装パターン: describe スコープの状態オブジェクト**

`describe.serial` 内はクロージャで状態を共有できる。Day1 で採番値を取得し、Day2 以降がそれを参照する。

```typescript
test.describe.serial('シナリオ01: 受注登録から請求確認まで', () => {

  // シナリオ内で採番値を共有するオブジェクト
  const ctx = {
    受注番号: '',
    請求番号: '',
  };

  test('[Day1] 受注入力・確定', async ({ page }) => {
    // 登録処理後、完了画面または URL から採番値を取得
    ctx.受注番号 = await page.locator('#order-number').textContent() ?? '';
    // URL から取得する場合の例: /orders/12345 → '12345'
    // ctx.受注番号 = new URL(page.url()).pathname.split('/').at(-1)!;
  });

  test('[Day2] 出荷処理・在庫引当', async ({ page }) => {
    // Day1 でキャプチャした採番値で対象レコードを特定
    await orderSearchPage.search(ctx.受注番号);
  });

  test('[Day3] 請求締め・照合確認', async ({ page }) => {
    await billingPage.open(ctx.受注番号);
  });

});
```

**採番値の取得場所（優先順位）**

| 優先度 | 取得場所 | 例 | 備考 |
|---|---|---|---|
| 1 | 登録完了後の URL | `/orders/12345` | 変わりにくく安定 |
| 2 | 完了画面の表示値 | `受注番号: 12345` | ロケータで直接取得 |
| 3 | 固有属性の組み合わせで検索 | 顧客コード＋業務日付 | 採番値が画面に出ない場合の代替 |
| ✗ | 一覧画面の最新行 | 登録直後の先頭行 | 並列実行時に他シナリオの行が混入する恐れがあるため不可 |

**代替: 固有属性の組み合わせで検索する方法**

採番値の取得が困難な場合、シナリオ固有の属性（顧客コード×業務日付など）でレコードを一意に絞り込む。

```typescript
test('[Day2] 出荷処理', async ({ page }) => {
  // 採番値ではなく「顧客コード＋業務日付」で検索して1件に絞り込む
  await orderSearchPage.searchByCustomer(TEST_DATA.顧客コード);
  await orderListPage.clickFirstRow();
});
```

#### マスタデータのシナリオ専有（推奨方針）

顧客・商品などのマスタデータをシナリオごとに専有させることで、採番値への依存を減らしシナリオを単純に保てる。

```
testdata/
  scenario_01.ts  → 顧客: C001, 商品: A001  ← シナリオ01 が専有
  scenario_02.ts  → 顧客: C002, 商品: B001  ← シナリオ02 が専有
  scenario_03.ts  → 顧客: C003, 商品: C001  ← シナリオ03 が専有
```

この分離により「顧客 C001 × 業務日付」でレコードが1件に絞れるため、`ctx` による採番値引き継ぎが不要になる。

**ただし以下のケースでは採番値キャプチャを併用すること**

- 同一シナリオ内で、同じ顧客・商品を**同日に複数回**操作するフローがある場合
  → 固有属性だけでは絞り込めないため `ctx` オブジェクトに採番値を保持する

**新規シナリオ追加時のルール**

1. 他のシナリオが使っていない顧客コード・商品コードを `testdata/` に追加する
2. それらのマスタレコードを DB 初期化データ（`data.sql` 等）に投入する
3. 同一属性を複数シナリオで共有しない

#### Day 間の状態引き継ぎ（JSON ファイル永続化）

`ctx` オブジェクトは**同一 `npx playwright test` 実行内でのみ有効**。
regression-runner が Day ごとに別プロセスを起動するため、`ctx` に格納した採番値は次の Day 実行時には失われる。

Day をまたいで値を引き継ぐ場合は `tmp/scenario_XX_state.json` に書き出す。

```typescript
import * as fs from 'fs';

// Day1 終了時: 採番値を JSON に保存
test('[Day1] 受注入力・確定', async ({ page }) => {
  // ...
  const state = { 受注番号: ctx.受注番号 };
  fs.writeFileSync('tmp/scenario_01_state.json', JSON.stringify(state));
});

// Day2・[MakeIfFile] 開始時: JSON から復元
const state = JSON.parse(fs.readFileSync('tmp/scenario_01_state.json', 'utf-8'));
```

- `tmp/` は `.gitignore` に追加し、実行時生成ファイルとして管理する
- `ctx` オブジェクトは同一 Day 内の step 間共有に引き続き使用できる

#### 対向システム連携 IF ファイルの生成

夜間バッチが出力したファイルを対向システムに送り、翌営業日に IF ファイルが連携されてくるパターンでは、
翌日バッチが取り込む想定の IF ファイルを自動生成する必要がある。

**方針**: バッチ実行後に `[MakeIfFile_DayN]` タグのテストを Playwright で実行し、
バッチ結果確認画面を打鍵して変動値を取得、固定値と合わせて IF ファイルを生成・転送する。

```typescript
test('[MakeIfFile_Day2] Day1→Day2 IF ファイル生成', async ({ page }) => {
  // 状態ファイルから前日の採番値を復元
  const state = JSON.parse(fs.readFileSync('tmp/scenario_01_state.json', 'utf-8'));

  // バッチ処理結果確認画面を打鍵して変動値を取得
  await loginPage.ログイン('user01', 'password');
  await billingResultPage.open(state.受注番号);
  const 請求金額   = await billingResultPage.getBillingAmount();
  const 処理日付   = await billingResultPage.getProcessedDate();

  // 固定値と組み合わせて IF ファイルを組み立て
  const content = buildIfFile({
    顧客コード: TEST_DATA.顧客コード,  // testdata 定数（固定）
    請求金額,                           // 画面から取得（変動）
    処理日付,                           // 画面から取得（変動）
    区分コード: 'A01',                  // 固定値
    フラグ:     '1',                    // 固定値
  });

  // ローカルに書き出し（SSH 転送は regression-runner が行う）
  fs.writeFileSync('tmp/if_scenario_01_day2.csv', content);
});
```

IF ファイルの組み立てロジックは `lib/if-file-builder.ts` に集約する。

```typescript
// lib/if-file-builder.ts
export interface IfFileParams {
  顧客コード: string;
  請求金額:   string;
  処理日付:   string;
  区分コード: string;
  フラグ:     string;
}

export function buildIfFile(params: IfFileParams): string {
  return Object.values(params).join(',') + '\n';
}
```

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
  │                    ↓ 全完了を待つ（各シナリオが tmp/*_state.json を書き出す）
  │
  ├─ SSH: CSV 配置（Day2 用）
  ├─ SSH: 夜間バッチ実行 → 業務日付が Day2 に進む
  ├─ [MakeIfFile_Day2] npx playwright test --grep "\[MakeIfFile_Day2\]"
  │          ├─ scenario_01: バッチ結果確認画面を打鍵 → IF ファイル生成（tmp/ に書き出し）
  │          └─ scenario_02: 同上                                         並列
  ├─ SSH: IF ファイルをバッチサーバに転送（SCP）
  │
  ├─ [Day2] npx playwright test --grep "\[Day2\]"
  │          ├─ scenario_01: [Day2] 出荷処理    ─┐
  │          └─ scenario_02: [Day2] 解約処理    ─┘ 並列
  │                    ↓ 全完了を待つ
  │
  ├─ SSH: CSV 配置（Day3 用）
  ├─ SSH: 夜間バッチ実行 → 業務日付が Day3 に進む
  ├─ [MakeIfFile_Day3] npx playwright test --grep "\[MakeIfFile_Day3\]"（必要な場合）
  ├─ SSH: IF ファイルをバッチサーバに転送（必要な場合）
  │
  └─ [Day3] npx playwright test --grep "\[Day3\]"
             └─ scenario_01: [Day3] 請求確認
```

> `[MakeIfFile_DayN]` ステップは、対向システム連携 IF ファイルが不要なシナリオ構成では省略できる。

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
   - IF ファイル生成（Playwright: `--grep "[MakeIfFile_DayN+1]"`）※対向連携がある場合
   - IF ファイルのバッチサーバへの転送（SSH SCP）※対向連携がある場合
4. 完了後に SSH 切断

### 骨格

```typescript
// regression/regression-runner.ts
import { spawnSync }        from 'child_process';
import { SshClient }        from '../lib/ssh-client';
import { regressionConfig } from './regression.config';

async function main(): Promise<void> {
  const ssh = new SshClient(regressionConfig.ssh);
  await ssh.connect();

  for (let day = 1; day <= regressionConfig.maxDays; day++) {
    // オンライン処理
    spawnSync('npx', ['playwright', 'test', '--grep', `\\[Day${day}\\]`], { stdio: 'inherit' });

    if (day < regressionConfig.maxDays) {
      // 夜間バッチ
      await ssh.placeCsvFiles(day);
      await ssh.runBatch();

      // 対向連携 IF ファイル生成（シナリオに [MakeIfFile_DayN] がある場合のみ実行）
      spawnSync('npx', ['playwright', 'test', '--grep', `\\[MakeIfFile_Day${day + 1}\\]`], { stdio: 'inherit' });
      await ssh.uploadIfFiles(day + 1);
    }
  }

  await ssh.disconnect();
}
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
  ifFileRemoteDir: string;  // IF ファイルの転送先ディレクトリ（バッチサーバ上）
}

export class SshClient {
  constructor(config: SshConfig)
  async connect(): Promise<void>
  async runBatch(): Promise<void>
  async placeCsvFiles(day: number): Promise<void>
  async uploadIfFiles(day: number): Promise<void>  // ローカル tmp/ → バッチサーバに SCP 転送
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

### IF ファイル転送方針

`[MakeIfFile_DayN]` テストがローカルの `tmp/` に生成した IF ファイルを、
`node-ssh` の `putFiles` で一括 SCP 転送する。

```typescript
async uploadIfFiles(day: number): Promise<void> {
  const localFiles = glob.sync(`tmp/if_*_day${day}.csv`);
  await this.ssh.putFiles(
    localFiles.map(local => ({
      local,
      remote: `${this.config.ifFileRemoteDir}/${path.basename(local)}`,
    }))
  );
}
```

- どのファイルをどのディレクトリに転送するかは `ifFileRemoteDir` 設定で管理する
- ファイルの命名規則は `if_{scenario_id}_day{N}.csv` に統一する

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
| `IF_FILE_REMOTE_DIR` | IF ファイルの転送先ディレクトリ（バッチサーバ上） | なし（対向連携がある場合は必須） |
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
| 2 | `lib/ssh-client.ts` 実装（`uploadIfFiles` を含む） |
| 3 | `lib/if-file-builder.ts` 実装 |
| 4 | `regression/regression.config.ts` 実装 |
| 5 | `regression/regression-runner.ts` 実装（`[MakeIfFile_DayN]` ステップを含む） |
| 6 | `playwright.e2e.config.ts` に `workers` 設定追加 |
| 7 | `tests/e2e/` にサンプルシナリオを1件作成して動作確認（Day 間状態引き継ぎ・IF ファイル生成を含む） |
| 8 | `tmp/` を `.gitignore` に追加 |
