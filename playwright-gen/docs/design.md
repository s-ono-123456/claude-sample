# Playwright 自動打鍵スクリプト作成 設計方針

## 概要

ast-analyzer で構築した Neo4j グラフと JSP 解析結果を活用し、
ソースコードを毎回読み直すことなく Playwright シナリオを効率的に生成するための基盤を整備する。

対象アプリ: `ast-analyzer/sample-app`（Spring MVC + MyBatis）

---

## ディレクトリ構成

```
playwright-gen/
  collect/                    # 事前収集スクリプト（CI で自動実行）
    extract_metadata.py       # Neo4j + JSP解析 → screens.yaml 生成
    generate_pom.py           # screens.yaml → TypeScript POM ファイル生成
    screens_master.yaml       # URL の正となる手動管理ファイル
    transitions_query.cypher  # Neo4j クエリ（遷移グラフ取得）
    templates/                # Jinja2 テンプレート
      page.ts.j2              # POM クラス用テンプレート
      base_page.ts.j2         # BasePage 用テンプレート（初回のみ生成）

  metadata/                   # 生成物（Git にコミット）
    screens/                  # 画面ごとに1ファイル
      login.yaml
      user_register.yaml
      mypage.yaml
      product_list.yaml
      product_detail.yaml
      product_edit.yaml
      order_list.yaml
      order_detail.yaml
    screens_index.yaml        # 全画面のインデックス（Claude が最初に読む）

  pom/                        # 生成物（Git にコミット）
    BasePage.ts               # 手動編集可（初回生成後は上書きしない）
    LoginPage.ts
    UserRegisterPage.ts
    MypagePage.ts
    ProductListPage.ts
    ProductDetailPage.ts
    ProductEditPage.ts
    OrderListPage.ts
    OrderDetailPage.ts

  tests/                      # Claude が生成するシナリオ（手動管理）
    plbl/                     # PL-BL結合テスト
      scenario_01_order.spec.ts
      scenario_02_order_history.spec.ts
    integration/              # 連結テスト
    e2e/                      # 総合テスト

  docs/                       # 設計ドキュメント
    design.md                 # 本ファイル（全体設計方針・スキーマ定義）
    extract_metadata_impl.md  # extract_metadata.py 実装方針
    generate_pom_impl.md      # generate_pom.py 実装方針
    testdata-design.md        # テストデータ自動生成設計
    known_issues.md           # 既知の課題

  playwright.base.config.ts        # 共通設定
  playwright.plbl.config.ts        # PL-BL結合テスト（TODO: baseURL を設定）
  playwright.integration.config.ts # 連結テスト（TODO: baseURL を設定）
  playwright.e2e.config.ts         # 総合テスト（TODO: baseURL を設定）
```

---

## 整備する情報の3層構成

### Layer 1：screens.yaml（事前収集の核）

Claude がシナリオを作る際に最初に読む情報。JSP の DOM 構造から決定論的に生成できる。

#### screens.yaml のスキーマ設計

「どのフォームにどの input があり、どのボタンがあるか」をフォーム単位で整理する。
フォームの境界が明確であれば、「このボタンを押す前に何を入力すべきか」が確定できる。

```
画面 (screen)
 ├─ forms[]                  ← <form>要素1つが1エントリ
 │    ├─ inputs[]            ← フォーム内の input/select/textarea
 │    └─ buttons[]           ← フォーム内の submit ボタン
 ├─ standalone_inputs[]      ← フォームに属さないが JS から参照される input
 ├─ js_actions[]             ← フォームに属さない JS ボタン
 │    └─ reads_inputs[]      ← 参照する standalone_inputs の id
 └─ nav_links[]              ← <a> タグによるナビゲーション
```

#### 画面ごとのフォーム境界

| 画面 | `<form>` の単位 | フォーム外 input |
|---|---|---|
| ログイン | `#loginForm`（username, password → loginBtn） | なし |
| 新規登録 | `#registerForm`（username, email → registerBtn） | なし |
| マイページ | `#userForm`（id(hidden), email → updateBtn） | なし |
| 商品一覧 | 検索フォーム（categorySelect → searchBtn） | なし |
| 商品詳細 | 削除フォーム（なし → btn-danger） | `#quantity`（JS から参照） |
| 商品編集 | `#productForm`（name, description, price, stock, category → saveBtn） | なし |
| 注文履歴 | キャンセルフォーム × N（行ごと動的生成、PENDING のみ） | なし |
| 注文詳細 | なし | なし |

#### ファイル構成と記述例

1画面1ファイルで管理する。PR の差分が画面単位に閉じるため、レビューしやすくなる。

**screens_index.yaml**（Claude がシナリオ作成時に最初に読む軽量インデックス）：

```yaml
# metadata/screens_index.yaml
screens:
  - { id: login,          title: ログイン,        url: /user/login,     jsp: user/login.jsp }
  - { id: user_register,  title: 新規ユーザー登録, url: /user/register,  jsp: user/register.jsp }
  - { id: mypage,         title: マイページ,       url: /user/mypage,    jsp: user/mypage.jsp }
  - { id: product_list,   title: 商品一覧,         url: /product/list,   jsp: product/list.jsp }
  - { id: product_detail, title: 商品詳細,         url: /product/detail, jsp: product/detail.jsp }
  - { id: product_edit,   title: 商品編集,         url: /product/edit,   jsp: product/edit.jsp }
  - { id: order_list,     title: 注文一覧,         url: /order/list,     jsp: order/list.jsp }
  - { id: order_detail,   title: 注文詳細,         url: /order/detail,   jsp: order/detail.jsp }
```

**screens/login.yaml**（個別画面ファイルの例）：

```yaml
# metadata/screens/login.yaml
id: login
title: ログイン
url: /user/login
jsp: user/login.jsp
assertions:
  on_load:
    - { type: title, value: ログイン }
    - { type: h1,    value: ログイン }
    - { type: url,   value: /user/login }
forms:
  - id: loginForm
    action: /user/login
    method: post
    inputs:
      - { id: username, name: username, type: text,     label: ユーザー名, required: true }
      - { id: password, name: password, type: password, label: パスワード, required: true }
    buttons:
      - { id: loginBtn, label: ログイン, type: submit }
    transition_to: login
standalone_inputs: []
nav_links:
  - { text: 新規登録はこちら, href: /user/register, transition_to: user_register }
js_actions: []
```

> **URL の情報源について**  
> `assertions.on_load` の URL パターンは JSP ファイルのパスから推測できるが、  
> 実際のマッピングはコントローラの `@RequestMapping` に依存するため、コード由来の値が仕様と食い違うリスクがある。  
> そのため URL は画面一覧 CSV または MD ファイル（設計書）を正とし、`extract_metadata.py` がそこから読み込む方式とする。  
> title・h1 は JSP の DOM から直接取得するため、ソースコード由来のままでよい。

**screens/product_list.yaml**（フォーム + JS アクション混在の例）：

```yaml
# metadata/screens/product_list.yaml
id: product_list
title: 商品一覧
url: /product/list
jsp: product/list.jsp
assertions:
  on_load:
    - { type: title, value: 商品一覧 }
    - { type: h1,    value: 商品一覧 }
    - { type: url,   value: /product/list }
forms:
  - id: null
    action: /product/list
    method: get
    inputs:
      - id: categorySelect
        name: category
        type: select
        options:
          - { value: "",          label: すべてのカテゴリ }
          - { value: electronics, label: 電子機器 }
          - { value: clothing,    label: 衣類 }
          - { value: food,        label: 食品 }
    buttons:
      - { id: searchBtn, label: 検索, type: submit }
    transition_to: product_list
standalone_inputs: []
nav_links:
  - { text: マイページ, href: /user/mypage,  transition_to: mypage }
  - { text: 注文履歴,  href: /order/list,   transition_to: order_list }
  - { text: ログアウト, href: /user/logout }
js_actions:
  - js_fn: placeOrder
    id: placeOrderBtn
    transitions:
      - { url_suffix: /order/detail/, transition_to: order_detail, unresolved: false }
      - { url_suffix: /user/login,    transition_to: login,        unresolved: false }
```

**screens/product_detail.yaml**（standalone_inputs の例）：

```yaml
# metadata/screens/product_detail.yaml
id: product_detail
title: 商品詳細
url: /product/detail
jsp: product/detail.jsp
assertions:
  on_load:
    - { type: title, value: 商品詳細 - }
    - { type: h1,    value: 商品詳細 }
    - { type: url,   value: /product/detail }
forms:
  - id: null
    action: /product/delete/
    method: post
    inputs: []
    buttons:
      - { selector: .btn-danger, label: 削除, type: submit }
standalone_inputs:
  - { id: quantity, name: quantity, type: number, label: 数量 }
nav_links:
  - { text: 商品一覧に戻る, href: /product/list,  transition_to: product_list }
  - { text: 編集,          href: /product/edit/, transition_to: product_edit }
js_actions:
  - js_fn: addToCartWithQuantity
    id: addCartBtn
    reads_inputs: [quantity]
  - js_fn: buyNow
    id: buyNowBtn
    reads_inputs: [quantity]
    transitions:
      - { url_suffix: /order/detail/, transition_to: order_detail, unresolved: false }
```

残りの画面（product_edit / order_list / order_detail / register / mypage）も同じスキーマで個別ファイルに記述する。

---

#### screens.yaml の作成手順

##### 自動生成（extract_metadata.py）

JSP DOM パース・JS 静的解析・Neo4j クエリを組み合わせて `metadata/screens/*.yaml` を生成する。  
フィールドごとの情報源・処理フロー・実行コマンドの詳細は [extract_metadata_impl.md](extract_metadata_impl.md) を参照。

##### 手動作成の手順（スクリプトなしで1から書く場合）

1. **screens_index.yaml に画面を登録する**
   - `id`（スネークケース）, `title`, `url`（設計書参照）, `jsp`（`WEB-INF/views/` 以下の相対パス）を記述

2. **JSP を開いてフォームを特定する**
   - `<form id="..." action="..." method="...">` を確認
   - フォーム内の `<input>`, `<select>`, `<textarea>` を `inputs[]` に転記
   - フォーム内の submit ボタンを `buttons[]` に転記
   - `transition_to` は `screens_index.yaml` の url と照合して画面 id を設定

3. **フォーム外の input を特定する**
   - JS から `getElementById("...")` で参照されている input を `standalone_inputs[]` に記述

4. **JS アクションを特定する**
   - `onclick` 属性や `addEventListener` で呼ばれる関数名を `js_fn` に記述
   - 関数ボディを確認し、参照している input の id を `reads_inputs[]` に記述
   - `window.location.href` の遷移先が判明すれば `transition_to` を設定（不明なら Neo4j で確認）
   - ランタイム状態に依存する前提条件（例: 「カートに商品が入っていること」）は `preconditions[]` に自然言語で記述

5. **ナビゲーションリンクを抽出する**
   - `<a href="...">` を `nav_links[]` に転記し `transition_to` を設定

6. **アサーションを記述する**
   - `<title>`, `<h1>` の内容と url パターンを `assertions.on_load` に記述

##### 手動補完が必要なフィールド一覧

| フィールド | 理由 | 対処 |
|---|---|---|
| `url` | `@RequestMapping` の実装に依存し、ソース由来では食い違うリスクあり | 設計書 CSV/MD を正として手動管理 |
| `js_actions[].preconditions` | JS のランタイム状態（カート変数等）は静的解析不可 | 自然言語で手動記述 |
| `js_actions[].transition_to` | `window.location.href` が変数の場合は静的解析不可（`unresolved` フラグ付き） | Neo4j で解決できなければ手動補完 |
| `forms[].buttons[].confirm_dialog` | `confirm()` の検出漏れが起きる場合がある | 漏れがあれば手動追記 |
| `assertions.conditional_elements` | 条件表示（ログイン状態等）はランタイム依存 | テスト設計者が手動記述 |

---

#### screens.yaml の記述例（バリデーション突き合わせあり）

バリデーション突き合わせが行われた場合、個別ファイルに `bound_class`・`required_sources`・`validation_discrepancies` が追加される。

```yaml
# metadata/screens/user_register.yaml（バリデーション突き合わせ後の例）
id: user_register
title: 新規ユーザー登録
url: /user/register
jsp: user/register.jsp
forms:
  - id: registerForm
    action: /user/register
    method: post
    bound_class: com.example.sampleapp.model.User   # @ModelAttribute の型
    validation_discrepancies:                         # 不一致があれば列挙
      - field: username
        issue: "HTML に required あり、Java に @NotEmpty なし"
    inputs:
      - id: username
        name: username
        type: text
        label: ユーザー名
        required: true
        required_sources: [html]        # html のみ（Java アノテーションなし）
        constraints: []
      - id: email
        name: email
        type: email
        label: メールアドレス
        required: true
        required_sources: [html, java]  # 両方一致（@NotEmpty + HTML required）
        constraints:
          - { annotation: NotEmpty, source: java }
          - { annotation: Email,    source: java }
    buttons:
      - { id: registerBtn, label: 登録, type: submit, transition_to: login }
standalone_inputs: []
js_actions: []
nav_links:
  - { label: ログインページへ戻る, href: /user/login, transition_to: login }
```

---

### ボタンとインプットの対応関係：取得可否の整理

フォーム境界を基準にすると、対応付けの精度が明確に分類できる。

| パターン | 判定方法 | 精度 | 例 |
|---|---|---|---|
| フォーム内の submit ボタン | `<form>` の DOM 親子関係から自動取得 | 高 | searchBtn ← categorySelect |
| JS ボタンが `getElementById` 等でDOMを直接読む | JS 関数ボディの正規表現解析で追跡 | 中 | buyNowBtn ← quantity |
| JS ボタンが JS 変数（ランタイム状態）を読む | 静的解析では取得不可。`preconditions` に人が記述 | 手動 | placeOrderBtn ← cart変数 |

---

### バリデーション情報の突き合わせ（HTML属性 vs Java アノテーション）

#### 問題

HTML の `required` 属性はフロントエンドのみの制約であり、サーバーサイドの Bean Validation（`@NotNull`、`@NotEmpty` 等）と必ずしも一致しない。
実プロジェクトでは Java アノテーションが正とみなされることが多く、両者を突き合わせて不一致を検出する必要がある。

#### 突き合わせの流れ

```
JSP の <form action="/user/register" method="post">
  ↓ ① form action + method で Controller メソッドを特定
      （Neo4j グラフ: URL → ControllerMethod ノード）

UserController.java: @PostMapping("/register")
  public String register(@ModelAttribute User user)
  ↓ ② @ModelAttribute のクラス型を抽出

User.java（モデルクラス）
  ↓ ③ フィールドの Bean Validation アノテーションを抽出

JSP の <input name="username" required>
  ↓ ④ JSP の name 属性 = Java フィールド名 で突き合わせ

screens.yaml に統合（一致・不一致を記録）
```

> 実装詳細（正規表現・モジュール構成）は [extract_metadata_impl.md](extract_metadata_impl.md) を参照。

#### Java アノテーション → 制約のマッピング

| Bean Validation アノテーション | screens.yaml への反映 |
|---|---|
| `@NotNull` | `required: true`（ただし空文字は通過する点に注意） |
| `@NotEmpty` | `required: true` |
| `@NotBlank` | `required: true` |
| `@Size(min=N, max=M)` | `minlength: N`、`maxlength: M` |
| `@Min(N)` | `min: N`（number 型） |
| `@Max(N)` | `max: N`（number 型） |
| `@Email` | `format: email` |
| `@Pattern(regexp=...)` | `pattern: ...` |

#### 不一致パターンと対処

| パターン | 意味 | 対処 |
|---|---|---|
| HTML `required` あり、Java アノテーションなし | クライアントのみの制約（バイパス可能） | `validation_discrepancies` に記録し警告 |
| Java `@NotEmpty` あり、HTML `required` なし | サーバー側でしか弾かれない | 同上（UX 上の問題）|
| HTML `min="0"`、Java `@Min(0)` あり | 一致（正常） | `required_sources: [html, java]` |
| HTML `type="email"`、Java `@Email` あり | 一致（正常） | 同上 |

`validation_discrepancies` が空でない画面は、Playwright テストでバリデーションバイパスのケースを追加するかどうかをシナリオ作成者が判断する材料になる。

---

### Layer 2：TypeScript POM（自動生成）

> **テスト工程における位置づけ**  
> POM が提供するセレクタ・操作手順（`fill` / `click` の組み合わせ）は、画面の DOM 構造に従った操作を記述するものであり、  
> 「操作が正しく動くか」は単体テストで検証される。したがって POM をソースコード（JSP）から自動生成することは、  
> 単体テストで担保された情報を再利用しているに過ぎず、テスト品質上の問題はない。

#### POM 実装方針

| 項目 | 方針 |
|---|---|
| 生成ツール | `generate_pom.py`（Jinja2 テンプレート）が `screens/*.yaml` から出力 |
| 手動編集 | 不可。再生成で上書きされる。カスタマイズが必要な場合は継承クラスで対応 |
| 基底クラス | `BasePage`（`page` フィールドと共通ユーティリティを保持） |
| インタラクション | `forms` の inputs を引数に取り fill → click するメソッドを生成 |
| 定型アサーション | `assertions.on_load` から `waitForLoad()` を生成（URL・title・h1 を確認） |
| データ検証 | POM には含めない。シナリオ固有のアサーションは spec 側で記述 |
| セレクタ優先順位 | `id` → `#id` / `class` → `.class` / `name` → `[name="..."]` の順で解決 |
| メソッド命名 | js_fn 名を camelCase 化 / フォーム submit はボタンラベルから命名 |

#### 生成例：LoginPage.ts

```typescript
// pom/LoginPage.ts  ← generate_pom.py が自動生成
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class LoginPage extends BasePage {
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginBtn: Locator;

  constructor(page: Page) {
    super(page);
    this.usernameInput = page.locator('#username');
    this.passwordInput = page.locator('#password');
    this.loginBtn      = page.locator('#loginBtn');
  }

  async goto() { await this.page.goto('/user/login'); }

  // assertions.on_load から生成
  async waitForLoad() {
    await expect(this.page).toHaveURL(/\/user\/login/);
    await expect(this.page).toHaveTitle('ログイン');
    await expect(this.page.locator('h1')).toHaveText('ログイン');
  }

  // form inputs（username, password）を引数化して fill → click
  async login(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.loginBtn.click();
  }
}
```

#### 生成例：ProductDetailPage.ts

```typescript
// pom/ProductDetailPage.ts  ← generate_pom.py が自動生成
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class ProductDetailPage extends BasePage {
  readonly quantityInput: Locator;  // standalone_inputs
  readonly addCartBtn: Locator;     // js_actions
  readonly buyNowBtn: Locator;
  readonly deleteBtn: Locator;      // forms

  constructor(page: Page) {
    super(page);
    this.quantityInput = page.locator('#quantity');
    this.addCartBtn    = page.locator('#addCartBtn');
    this.buyNowBtn     = page.locator('#buyNowBtn');
    this.deleteBtn     = page.locator('.btn-danger');
  }

  async goto(id: number) { await this.page.goto(`/product/detail/${id}`); }

  // assertions.on_load から生成
  async waitForLoad() {
    await expect(this.page).toHaveURL(/\/product\/detail\//);
    await expect(this.page.locator('h1')).toHaveText('商品詳細');
  }

  // reads_inputs: [quantity] → quantity を引数化して fill → click
  async addToCartWithQuantity(quantity: number) {
    await this.quantityInput.fill(String(quantity));
    await this.addCartBtn.click();
  }

  async buyNow(quantity: number) {
    await this.quantityInput.fill(String(quantity));
    await this.buyNowBtn.click();
  }

  // form submit（inputs なし → 引数なし）
  async deleteProduct() {
    await this.deleteBtn.click();
  }
}
```

---

#### TypeScript POM の生成手順

セレクタ解決ルール・メソッド命名規則・型推論ルール・Jinja2 テンプレート・実行コマンドの詳細は  
[generate_pom_impl.md](generate_pom_impl.md) を参照。

##### カスタマイズが必要な場合

`pom/` 以下のファイルは**手動編集禁止**（次回の再生成で上書きされる）。

| ケース | 対処方法 |
|---|---|
| 特定画面に操作メソッドを追加したい | 継承クラス（例: `extensions/LoginPageExt.ts`）を `pom/` 外に作成する |
| 生成ルールを全画面に変更したい | `collect/templates/page.ts.j2` テンプレートを修正する |
| 特定画面を生成対象から除外したい | `screens_index.yaml` の当該エントリに `skip_pom: true` を追加する |
| `confirm_dialog` のハンドリングを共通化したい | `BasePage` に共通メソッドを追加し、テンプレートから呼び出す形にする |

---

### Layer 3：シナリオ spec（Claude が生成）

> **シナリオの情報源と品質保証**  
> シナリオ spec は人間が記述するか、設計書（画面遷移図・業務フロー定義）を元に Claude Code に生成させる。  
> 「どの操作をどの順番で行うか」「何をアサートするか」の根拠を設計書に置くことで、  
> コードが仕様から外れていた場合にテストがそれを検知できる。  
> POM はあくまで「操作の手段」を提供するに過ぎず、「何を確認するか」はシナリオ側の責務である。

Claude は `screens.yaml` を読み、シナリオ記述を受け取って spec を生成する。
フォーム境界が明示されているため「どのフィールドを入力してからボタンを押すか」を自動で判断できる。

実際のシナリオ一覧・テストケース・実行コマンドは [tests/plbl/README.md](../tests/plbl/README.md) を参照。

```typescript
// tests/scenario_01_order.spec.ts
import { test, expect } from '@playwright/test';
import { LoginPage }       from '../pom/LoginPage';
import { ProductListPage } from '../pom/ProductListPage';
import { OrderDetailPage } from '../pom/OrderDetailPage';

test.describe('シナリオ1: 商品検索して注文', () => {
  test('カテゴリ検索 → カート追加 → 注文', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.waitForLoad();                       // ← POM自動生成（URL・title・h1）
    await login.login('testuser', 'password');

    const products = new ProductListPage(page);
    await products.waitForLoad();                    // ← ログイン成功の確認を兼ねる
    await products.searchByCategory('electronics');
    await products.waitForLoad();                    // ← 検索後も同画面に留まることを確認

    await page.locator('.btn-cart').first().click();
    await products.placeOrder();

    // transition_to: order_detail → specでURL確認（動的IDを含むためspec側で記述）
    await expect(page).toHaveURL(/\/order\/detail\//);
    const orderDetail = new OrderDetailPage(page);
    await orderDetail.waitForLoad();                 // ← 注文詳細画面の定型確認
  });
});
```

---

## CI パイプライン（PR 時自動更新）

`extract_metadata.py` は Neo4j を使う。ast-analyzer の実行が前提である以上、
Neo4j は「追加の依存」ではなく「すでにある依存」のため。
JS アクションの `transition_to`（`window.location.href` 解析）は
ast-analyzer が生成した `TRANSITIONS_TO` エッジをそのまま利用し、再実装しない。

```
PR がオープンされる
  ↓
① Neo4j 起動（CI では Docker サービスとして起動）
  ↓
② ast-analyzer 実行（Neo4j グラフ更新）
  ↓
③ playwright-gen/collect/extract_metadata.py
   - JSP を DOM パース → forms / standalone_inputs / js_actions / assertions を抽出
   - Java ソースをパース → @ModelAttribute クラス・Bean Validation アノテーションを抽出
   - Neo4j から TRANSITIONS_TO エッジをクエリ → js_actions の transition_to を補完
   - JS 関数ボディを解析 → reads_inputs を補完（getElementById 等）
   → metadata/screens/*.yaml と screens_index.yaml を更新
  ↓
④ playwright-gen/collect/generate_pom.py
   - screens/*.yaml → pom/*.ts を再生成
  ↓
⑤ 差分を PR にコミット（自動）
```

GitHub Actions での Neo4j 起動例：

```yaml
services:
  neo4j:
    image: neo4j:5
    env:
      NEO4J_AUTH: neo4j/password
    ports:
      - 7687:7687
```

---

## Claude Code でのシナリオ作成フロー（実運用）

```
ユーザー: 「商品を検索して注文するシナリオを作って」
  ↓
Claude: screens_index.yaml で全画面を把握 → 必要な画面の screens/*.yaml を読む
  ↓
Claude: ログイン → 商品一覧（検索フォーム） → 注文する（js_action + precondition）
        → 注文詳細 の遷移を確認
  ↓
Claude: 既存 POM をインポートして spec.ts を生成
  ↓（ソースコードを一切読まずに完了）
```

---

## 実装スコープと優先順位

| 優先度 | 対象 | 概要 | 作業量 |
|---|---|---|---|
| ① 高 | `extract_metadata.py` | JSP DOM パース → screens.yaml 生成 | 中 |
| ② 高 | `generate_pom.py` | screens.yaml → POM 自動生成 | 小 |
| ③ 中 | CI 設定 | GitHub Actions または PowerShell フック | 小 |
| ④ 低 | シナリオ spec | Claude が随時生成（都度対応） | ほぼゼロ |

---

## 未決定事項（実装前に確認が必要）

- POM の自動更新を PR に自動コミットする方式か、アーティファクトとして添付してレビューする方式か？
