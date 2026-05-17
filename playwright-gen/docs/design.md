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
    transitions_query.cypher  # Neo4j クエリ（遷移グラフ取得）

  metadata/                   # 生成物（Git にコミット）
    screens/                  # 画面ごとに1ファイル
      login.yaml
      product_list.yaml
      product_detail.yaml
      product_edit.yaml
      order_list.yaml
      order_detail.yaml
      register.yaml
      mypage.yaml
    screens_index.yaml        # 全画面のインデックス（Claude が最初に読む）
    transitions.yaml          # 画面遷移グラフ（横断的なので1ファイル）

  pom/                        # 生成物（Git にコミット）
    BasePage.ts
    LoginPage.ts
    ProductListPage.ts
    ProductDetailPage.ts
    OrderListPage.ts
    OrderDetailPage.ts

  tests/                      # Claude が生成するシナリオ（手動管理）
    scenario_01_order.spec.ts
    scenario_02_order_history.spec.ts

  docs/                       # 設計ドキュメント
    design.md                 # 本ファイル

  playwright.config.ts
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
  - { id: login,          title: ログイン,           url: /user/login,          file: screens/login.yaml }
  - { id: register,       title: 新規ユーザー登録,    url: /user/register,       file: screens/register.yaml }
  - { id: mypage,         title: マイページ,          url: /user/mypage,         file: screens/mypage.yaml }
  - { id: product_list,   title: 商品一覧,            url: /product/list,        file: screens/product_list.yaml }
  - { id: product_detail, title: 商品詳細,            url: /product/detail/{id}, file: screens/product_detail.yaml }
  - { id: product_edit,   title: 商品編集/新規登録,   url: /product/edit/{id},   file: screens/product_edit.yaml }
  - { id: order_list,     title: 注文履歴,            url: /order/list,          file: screens/order_list.yaml }
  - { id: order_detail,   title: 注文詳細,            url: /order/detail/{id},   file: screens/order_detail.yaml }
```

**screens/login.yaml**（個別画面ファイルの例）：

```yaml
# metadata/screens/login.yaml
id: login
title: ログイン
url: /user/login
view_file: WEB-INF/views/user/login.jsp
forms:
  - form_id: loginForm
    action: /user/login
    method: post
    inputs:
      - { id: username, name: username, type: text,     label: ユーザー名, required: true }
      - { id: password, name: password, type: password, label: パスワード, required: true }
    buttons:
      - { id: loginBtn, label: ログイン, type: submit, transition_to: product_list }
standalone_inputs: []
js_actions: []
nav_links:
  - { label: 新規登録はこちら, href: /user/register, transition_to: register }
assertions:
  on_load:
    - { type: url,   pattern: "/user/login" }
    - { type: title, text: ログイン }         # JSP <title> から取得
    - { type: h1,    text: ログイン }          # JSP <h1> から取得
  conditional_elements: []
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
view_file: WEB-INF/views/product/list.jsp
forms:
  - form_id: null
    action: /product/list
    method: get
    inputs:
      - id: categorySelect
        name: category
        type: select
        label: カテゴリ
        options:
          - { value: "",           label: すべてのカテゴリ }
          - { value: electronics,  label: 電子機器 }
          - { value: clothing,     label: 衣類 }
          - { value: food,         label: 食品 }
    buttons:
      - { id: searchBtn, label: 検索, type: submit }
standalone_inputs: []
js_actions:
  - selector: ".btn-cart"
    label: カートに追加
    js_fn: addToCart
    reads_inputs: []
    preconditions: []
  - id: placeOrderBtn
    label: 注文する
    js_fn: placeOrder
    reads_inputs: []
    preconditions:
      - "カートに1件以上の商品が追加済みであること（addToCart を先に呼ぶ）"
    transition_to: order_detail
nav_links:
  - { label: マイページ,  href: /user/mypage,  transition_to: mypage }
  - { label: 注文履歴,   href: /order/list,   transition_to: order_list }
  - { label: ログアウト,  href: /user/logout }
assertions:
  on_load:
    - { type: url,   pattern: "/product/list" }
    - { type: title, text: 商品一覧 }
    - { type: h1,    text: 商品一覧 }
  conditional_elements: []
```

**screens/product_detail.yaml**（standalone_inputs の例）：

```yaml
# metadata/screens/product_detail.yaml
id: product_detail
title: 商品詳細
url: /product/detail/{id}
view_file: WEB-INF/views/product/detail.jsp
forms:
  - form_id: null
    action: /product/delete/{id}
    method: post
    inputs: []
    buttons:
      - { class: btn-danger, label: 削除, type: submit,
          confirm_dialog: "削除してよろしいですか？", transition_to: product_list }
standalone_inputs:
  - { id: quantity, name: quantity, type: number, label: 数量, min: 1, max: "{product.stock}" }
js_actions:
  - id: addCartBtn
    label: カートに追加
    js_fn: addToCartWithQuantity
    reads_inputs: [quantity]
    preconditions: []
  - id: buyNowBtn
    label: 今すぐ購入
    js_fn: buyNow
    reads_inputs: [quantity]
    preconditions: []
    transition_to: order_detail
nav_links:
  - { label: 商品一覧に戻る, href: /product/list, transition_to: product_list }
assertions:
  on_load:
    - { type: url,   pattern: "/product/detail/" }
    - { type: title, text: 商品詳細 }
    - { type: h1,    text: 商品詳細 }
  conditional_elements: []
```

残りの画面（product_edit / order_list / order_detail / register / mypage）も同じスキーマで個別ファイルに記述する。

---

#### screens.yaml の作成手順

screens.yaml は `extract_metadata.py` によって自動生成されるが、
各フィールドの情報源と生成ロジックを把握しておくことが手動補完・トラブルシュートに不可欠である。

##### 情報ソース対応表

| フィールド | 情報源 | 取得方法 |
|---|---|---|
| `id` | screens_index.yaml（または命名規則） | JSP ファイルパスから推測（手動定義も可）|
| `title` | JSP `<title>` タグ | DOM パース |
| `url` | 設計書 CSV / MD | 手動管理（Controller の `@RequestMapping` 依存のため）|
| `view_file` | JSP ファイルパス | ファイルシステムからそのまま取得 |
| `forms[].form_id` | JSP `<form id="...">` | DOM パース |
| `forms[].action` | JSP `<form action="...">` | DOM パース |
| `forms[].method` | JSP `<form method="...">` | DOM パース |
| `forms[].inputs[]` | JSP `<input>`, `<select>`, `<textarea>` | DOM パース |
| `forms[].buttons[]` | JSP `<button type="submit">`, `<input type="submit">` | DOM パース |
| `standalone_inputs[]` | JSP 内で `<form>` 外に存在する `<input>` | DOM パース（form 外判定）|
| `js_actions[]` | JSP 内の `onclick` 等 JS 呼び出し | JS パース / Neo4j `JsFunction` ノード |
| `js_actions[].transition_to` | Neo4j `TRANSITIONS_TO` エッジ | Neo4j クエリ（`transitions_query.cypher`）|
| `js_actions[].reads_inputs` | JS 関数ボディの `getElementById` 等 | JS 正規表現解析 |
| `nav_links[]` | JSP `<a href="...">` | DOM パース |
| `assertions.on_load` | JSP `<title>`, `<h1>` + URL（設計書） | DOM パース + 設計書 |
| `bound_class` | Controller の `@ModelAttribute` 型 | Java ソースパース / Neo4j |
| `validation_discrepancies` | JSP HTML 属性 vs Java Bean Validation | 突き合わせロジック（後述）|

##### 自動生成の流れ詳細（extract_metadata.py）

```
① 対象 JSP ファイルの列挙
   - config.yaml の view_dir（例: WEB-INF/views/）以下の *.jsp を再帰列挙
   - screens_index.yaml に登録済みの画面のみ処理する

② JSP の DOM パース（BeautifulSoup）
   フォーム抽出:
     - soup.find_all('form') → form_id, action, method を取得
     - 各 form 内の input/select/textarea を抽出 → inputs[]
       * select の場合: option タグを展開し options[] を生成
       * label タグの for 属性または隣接テキストを label に設定
     - form 内の button[type=submit] / input[type=submit] を抽出 → buttons[]
       * data-confirm 属性または onclick="confirm(...)" → confirm_dialog に設定

   standalone_inputs 抽出:
     - soup.find_all('input') から form 内のものを除外
     - id 属性を持つものを対象とする（JS から getElementById で参照される前提）

   nav_links 抽出:
     - soup.find_all('a', href=True) を列挙
     - 外部リンク（http:// / https:// 始まり）は除外
     - href の URL を screens_index.yaml の url と照合 → transition_to を解決

   assertions 抽出:
     - soup.find('title').text → on_load[type=title]
     - soup.find('h1').text   → on_load[type=h1]
     - URL パターンは screens_index.yaml から転記

③ JS 解析（正規表現）
   - JSP 内 <script> タグおよび src 属性で読み込む外部 .js ファイルを処理
   - onclick="foo()" 等から呼び出し関数名を抽出 → js_fn
   - 関数ボディを正規表現で解析:
       document\.getElementById\(['"](\w+)['"]\)  → reads_inputs に id を追加
       window\.location\.href\s*=\s*['"]([^'"]+)  → 仮 transition_to（④で補完）

④ Neo4j クエリ（遷移情報補完）
   - transitions_query.cypher を実行:
       MATCH (b:Button)-[:TRANSITIONS_TO]->(s:Screen) RETURN b, s
       MATCH (j:JsFunction)-[:TRANSITIONS_TO]->(s:Screen) RETURN j, s
   - unresolved フラグが付いている transition_to を Neo4j の結果で上書き
   - Neo4j でも解決不能な場合は transition_to: null（手動補完対象）

⑤ Java ソース解析（バリデーション突き合わせ）
   - form の action + method で ControllerMethod ノードを Neo4j から特定
   - @ModelAttribute の型クラス名を取得 → bound_class
   - モデルクラスの Java ファイルを直接パースしフィールドのアノテーションを抽出
   - JSP の input name 属性 = Java フィールド名 で突き合わせ
   - 差異を validation_discrepancies に記録

⑥ screens/*.yaml へ出力
   - 画面ごとに個別ファイルへ書き込み（既存ファイルは上書き）
   - screens_index.yaml も更新（新規画面が追加された場合のみ差分）
```

##### 実行コマンド

```powershell
# screens.yaml を全画面生成
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml

# 特定画面のみ再生成
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml --screen login

# dry-run（ファイル書き込みなし、stdout で確認）
uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml --dry-run
```

> **前提**: `extract_metadata.py` を実行する前に `ast-analyzer` が Neo4j グラフを構築済みであること。
> グラフが古い場合は `uv run python ast-analyzer/main.py --config ast-analyzer/config.yaml` を先に実行する。

##### 手動作成の手順（スクリプトなしで1から書く場合）

1. **screens_index.yaml に画面を登録する**
   - `id`（スネークケース）, `title`, `url`（設計書参照）, `file`（`screens/{id}.yaml`）を記述

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
# metadata/screens/register.yaml（バリデーション突き合わせ後の例）
id: register
title: 新規ユーザー登録
url: /user/register
view_file: WEB-INF/views/user/register.jsp
forms:
  - form_id: registerForm
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

##### screens.yaml → TypeScript 対応表

| screens.yaml のフィールド | 生成される TypeScript コード |
|---|---|
| `forms[].inputs[].id` | `readonly {id}Input: Locator` + `page.locator('#{id}')` |
| `standalone_inputs[].id` | `readonly {id}Input: Locator` + `page.locator('#{id}')` |
| `forms[].buttons[].id` | `readonly {id}: Locator` + `page.locator('#{id}')` |
| `forms[].buttons[].class` | `readonly {camelCase}Btn: Locator` + `page.locator('.{class}')` |
| `js_actions[].id` | `readonly {id}: Locator` + `page.locator('#{id}')` |
| `js_actions[].selector` | `readonly {camelCase(label)}Btn: Locator` + `page.locator('{selector}')` |
| `url`（パスパラメータなし）| `async goto() { await this.page.goto('{url}') }` |
| `url`（`{id}` 等を含む）| `async goto(id: number) { await this.page.goto(\`{url}\`) }` |
| `assertions.on_load[type=url]` | `await expect(this.page).toHaveURL(/{pattern}/)` |
| `assertions.on_load[type=title]` | `await expect(this.page).toHaveTitle('{text}')` |
| `assertions.on_load[type=h1]` | `await expect(this.page.locator('h1')).toHaveText('{text}')` |
| `forms[].inputs[]` + submit ボタン | `async {メソッド名}({inputs を引数化})` — fill × N → click |
| `js_actions[].js_fn` + `reads_inputs[]` | `async {js_fn}({reads_inputs を引数化})` — fill × N → click |

##### セレクタ解決ルール（優先順位順）

| screens.yaml の指定 | 生成されるセレクタ |
|---|---|
| `id: foo` あり | `page.locator('#foo')` |
| `id` なし・`class: btn-danger` あり | `page.locator('.btn-danger')` |
| `id` なし・`class` なし・`name: username` あり | `page.locator('[name="username"]')` |
| `selector: ".btn-cart"` 直接指定 | `page.locator('.btn-cart')` |

##### メソッド命名規則

| 対象 | 命名規則 | 例 |
|---|---|---|
| フォーム submit メソッド | submit ボタンの `label` をキャメルケース化 | `login()`, `search()`, `save()` |
| JS アクション メソッド | `js_fn` をそのままキャメルケースで使用 | `addToCartWithQuantity()`, `buyNow()` |
| input 系 Locator フィールド | `{id}Input` | `usernameInput`, `quantityInput` |
| ボタン系 Locator フィールド（id あり） | `{id}` | `loginBtn`, `addCartBtn` |
| ボタン系 Locator フィールド（id なし） | `{camelCase(class)}Btn` | `dangerBtn` |

##### メソッド引数の型推論

| input の type | TypeScript 引数の型 |
|---|---|
| `text` / `password` / `email` / `textarea` | `string` |
| `number` | `number` |
| `select` | `string`（option の value） |
| `hidden` | 引数に含めない（固定値のため） |

##### generate_pom.py の処理フロー

```
① screens_index.yaml を読み込み、対象画面の一覧を取得

② 画面ごとに screens/{id}.yaml を読み込む

③ Locator フィールドの列挙（constructor 用）
   - forms[].inputs[]       → {id}Input: Locator
   - standalone_inputs[]    → {id}Input: Locator
   - forms[].buttons[]      → セレクタ解決ルールに従い Locator 名を決定
   - js_actions[]           → {id}: Locator または {camelCase(label)}Btn: Locator

④ セレクタ文字列の解決
   - id あり     → '#id'
   - class あり  → '.class'
   - name あり   → '[name="name"]'
   - selector 指定あり → そのまま使用

⑤ goto() メソッドの生成
   - url にパスパラメータ（{id} 等）がある場合 → 引数付きに変換
     /product/detail/{id} → async goto(id: number) { ...`/product/detail/${id}` }
   - パスパラメータなし → 引数なし

⑥ waitForLoad() メソッドの生成
   - assertions.on_load を順番に展開
     type: url   → toHaveURL(/パターン/)
     type: title → toHaveTitle('テキスト')
     type: h1    → page.locator('h1').toHaveText('テキスト')

⑦ フォームアクションメソッドの生成
   - forms[] を列挙
   - inputs[]（hidden 除く）を引数として列挙し型を推論
   - fill(String(引数)) → click() の順で展開
   - buttons[].confirm_dialog がある場合:
     → page.on('dialog', dialog => dialog.accept()) を click() の前に挿入

⑧ JS アクションメソッドの生成
   - js_actions[] を列挙
   - reads_inputs[] を standalone_inputs の type から型推論して引数化
   - 各 input を fill(String(引数)) → click() の順で展開

⑨ Jinja2 テンプレートに変数を渡し .ts ファイルとして出力
   - 出力ファイル名: pom/{PascalCase(id)}Page.ts
   - 既存ファイルは無条件上書き（手動編集は次回再生成で失われる）
```

##### Jinja2 テンプレートの構造（概略）

```jinja
{# collect/templates/page.ts.j2 #}
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class {{ screen.id | pascal_case }}Page extends BasePage {
  {% for loc in locators %}
  readonly {{ loc.name }}: Locator;
  {% endfor %}

  constructor(page: Page) {
    super(page);
    {% for loc in locators %}
    this.{{ loc.name }} = page.locator('{{ loc.selector }}');
    {% endfor %}
  }

  async goto({{ goto_args }}) {
    await this.page.goto(`{{ screen.url | to_js_template }}`);
  }

  async waitForLoad() {
    {% for a in screen.assertions.on_load %}
    {{ a | to_expect_stmt }};
    {% endfor %}
  }

  {% for method in methods %}
  {{ method | render_method }}

  {% endfor %}
}
```

##### 実行コマンド

```powershell
# screens/*.yaml から pom/*.ts を全画面生成
uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml

# 特定画面のみ再生成
uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml --screen login

# dry-run（stdout で確認、ファイル書き込みなし）
uv run python playwright-gen/collect/generate_pom.py --config ast-analyzer/config.yaml --dry-run
```

> 通常は `extract_metadata.py` の直後に続けて実行する。
> CI パイプラインでは両スクリプトをシーケンシャルに実行するため手動実行は不要。

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
