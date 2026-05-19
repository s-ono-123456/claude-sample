# Playwright テストデータ自動生成 設計方針

## 概要

Playwright シナリオは「ログイン画面から対象画面まで」の遷移全体をスクリプト化するため、
途中の全画面で表示エラーが出ないテストデータを事前に用意する必要がある。

毎回ソースコードを読んでデータを手作りするのではなく、
**遷移パス上の各画面が実行するSQLのWHERE条件を静的解析で収集し、
整合性のあるINSERT文を自動生成する**。

対象アプリ: `ast-analyzer/sample-app`（Spring MVC + MyBatis）

---

## 問題の構造

```
遷移パス: login → order/list → order/detail/{id}

各画面で実行されるSQL               必要なデータ
──────────────────────────────────────────────────────
login:
  findByUsername(username)      →  users に username が存在すること

order/list:
  findByUserId(userId)          →  orders に user_id = ログインユーザのIDが存在すること

order/detail/{id}:
  findById(id)                  →  orders に id = URLパラメータの値が存在すること
  findItemsByOrderId(orderId)   →  order_items に order_id = 上記IDが存在すること
──────────────────────────────────────────────────────
```

SQLのパラメータは3種類の経路で渡ってくる。
この3種類を正しく追跡することが、整合性のあるテストデータ生成の核心である。

| 経路 | 例 | 自動化可否 |
|---|---|---|
| URLパラメータ (`@PathVariable`) | `/order/detail/{id}` の `id` | ○ シナリオYAMLで直接指定 |
| リクエストパラメータ (`@RequestParam`) | 検索フォームの `category` | ○ フォーム入力値と1対1 |
| セッション値 (`session.getAttribute`) | `loginUser.getId()` → SQL の `userId` | △ バインディング宣言が必要 |

---

## ディレクトリ構成

```
playwright-gen/
  testdata/
    generate_testdata.py      # メインスクリプト（CLI エントリーポイント）
    collect_sql.py            # Neo4j クエリ → 遷移パス上のSQL収集
    parse_mybatis.py          # MyBatis XML → SQL条件抽出
    resolve_params.py         # パラメータ値の解決と整合性チェック
    generate_inserts.py       # INSERT文生成（FK順序制御）
    scenario_sample.yaml      # シナリオ定義ファイルの記述例

  docs/
    design.md                 # screens.yaml・POM 生成設計
    testdata-design.md        # 本ファイル（テストデータ生成設計）
```

---

## 処理フロー

```
① シナリオYAML を読み込む
   遷移パス・URLパラメータ・フォーム入力値・テストユーザ情報を取得
        │
        ▼
② 遷移パス上のSQL文を収集 (collect_sql.py)
   Neo4j グラフから各画面の ControllerMethod → SQL文チェーンを取得
   ※ Neo4j 未使用時（--no-neo4j）: シナリオYAML内の mapper_methods を使用
        │
        ▼
③ WHERE条件を抽出 (parse_mybatis.py)
   MyBatis XMLマッパーをパースし、#{パラメータ名} と対応カラムを取り出す
   動的WHERE句（<if test="...">）はシナリオYAMLの有効フラグで切り替え
        │
        ▼
④ パラメータ値を解決 (resolve_params.py)
   URLパラメータ    → シナリオYAMLの params から直接取得
   リクエストパラメータ → シナリオYAMLの inputs から取得
   セッション値     → session_bindings 宣言を参照して解決
   FK引き継ぎ値    → 前段INSERTの確定値から命名規則で推論
        │
        ▼
⑤ INSERT文を生成 (generate_inserts.py)
   テーブルの外部キー依存順（親テーブルを先に）でソート
   解決済みパラメータ値を使い、整合性のある具体値でINSERT文を生成
   → output/testdata_{scenario_name}.sql に出力
```

---

## 入力：シナリオYAMLフォーマット

```yaml
# playwright-gen/testdata/scenario_sample.yaml
scenario:
  name: 注文詳細確認

  # ─── テストユーザ ──────────────────────────────────────────
  test_user:
    id: 1
    username: testuser
    password: password
    email: test@example.com
    role: USER

  # ─── セッションバインディング宣言 ──────────────────────────
  # session.getAttribute("loginUser") がSQLのどのパラメータに対応するか。
  # アプリの実装が変わらない限り共通ファイルとして使い回せる。
  session_bindings:
    loginUser:
      java_type: com.example.sampleapp.model.User
      field_to_param:
        id:       userId    # SQL の #{userId} = session.loginUser.id
        username: username  # SQL の #{username} = session.loginUser.username

  # ─── 遷移パス ──────────────────────────────────────────────
  # 各エントリは「この画面に到達し、このボタンを押して次へ進む」を表す。
  # action.button は最後の画面（目的地）以外は必須。
  # button の識別子は screens.yaml の buttons[].id に合わせる。
  nav_path:
    - screen: login
      action:
        button: loginBtn              # 必須（最後以外）
        inputs:                       # そのボタンが属するフォームの入力値
          username: "{{ test_user.username }}"
          password: "{{ test_user.password }}"

    - screen: order_list
      action:
        button: orderDetailLink_100   # order/detail/100 への詳細リンク
        # フォーム入力なし（リンク遷移のため）
        # セッションのloginUser.idを使うSQLはsession_bindingsで自動解決

    - screen: order_detail            # 目的地 → action 不要
      params:
        id: 100    # URLパラメータ /order/detail/{id}

  # ─── 動的WHERE句の有効フラグ ──────────────────────────────
  # MyBatisの <if test="category != null"> 等を有効にするかどうか。
  # 省略時は全条件を有効として扱う。
  dynamic_where:
    - mapper: ProductMapper
      method: findByCategory
      enabled: true    # false にすると findAll にフォールバック

  # ─── 補足データ ────────────────────────────────────────────
  # SQLで参照されるがパスからは解決できないテーブルの行を明示する。
  # 例: order_items.product_id が参照する products の行
  additional_data:
    - table: products
      rows:
        - id: 10
          name: テスト商品A
          description: テスト用商品
          price: 2500
          stock: 10
          category: electronics
```

### シナリオYAMLフィールド一覧

| フィールド | 必須 | 説明 |
|---|---|---|
| `scenario.name` | ○ | 出力ファイル名のサフィックスに使用 |
| `test_user` | ○ | ログインユーザの具体値。全フィールドを明示する |
| `session_bindings` | △ | セッション値をSQLパラメータに対応付ける宣言。アプリ固定のため共通ファイル化を推奨 |
| `nav_path[].screen` | ○ | `screens_index.yaml` の `id` を指定 |
| `nav_path[].params` | △ | URLパラメータ（`@PathVariable`）の値。パスに `{id}` 等があれば必須 |
| `nav_path[].action.button` | ○ | 次の画面へ遷移するボタンの `id`（`screens.yaml` の `buttons[].id`）。**最後の画面以外は必須** |
| `nav_path[].action.inputs` | △ | そのボタンが属するフォームの入力値（`@RequestParam`）。入力が必要なフォームのみ指定 |
| `nav_path[].mapper_methods` | △ | Stage 1（Neo4j不使用時）のみ必要。`on_load` と `on_action` に分けて列挙 |
| `dynamic_where` | △ | 動的WHERE句の有効・無効を制御。省略時は全条件有効 |
| `additional_data` | △ | FK参照先など、パスから解決できないテーブルの補足データ |

---

## 出力：INSERT文フォーマット

```sql
-- ============================================================
-- Playwright テストデータ
-- シナリオ: 注文詳細確認
-- 生成日時: 2026-05-19 12:00:00
-- 遷移パス: login → order_list → order_detail
-- ============================================================

-- [1/4] login: UserMapper.findByUsername
--   WHERE username = #{username}  →  'testuser'  (nav_path.inputs)
INSERT INTO users (id, username, email, role)
VALUES (1, 'testuser', 'test@example.com', 'USER');

-- [2/4] order_list: OrderMapper.findByUserId
--   WHERE user_id = #{userId}  →  1  (session_bindings: loginUser.id → test_user.id)
INSERT INTO orders (id, user_id, order_date, status, total_amount)
VALUES (100, 1, '2026-05-19 00:00:00', 'PENDING', 5000);

-- [3/4] order_detail: OrderMapper.findById
--   WHERE id = #{id}  →  100  (nav_path.params.id)
--   ※ [2/4] のINSERTで対象行を作成済み（重複排除）

-- products: additional_data より（order_items.product_id の参照先）
INSERT INTO products (id, name, description, price, stock, category)
VALUES (10, 'テスト商品A', 'テスト用商品', 2500, 10, 'electronics');

-- [4/4] order_detail: OrderMapper.findItemsByOrderId
--   WHERE order_id = #{orderId}  →  100  (FK推論: orders.id = 100)
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price)
VALUES (1, 100, 10, 2, 2500);
```

---

## 各コンポーネントの詳細設計

### collect_sql.py — 遷移パス上のSQL収集（Stage 2）

画面のSQLは「画面ロード時（GET表示）」と「ボタン押下時（アクション）」の2フェーズで収集する。
ボタンIDを明示することで、同一画面の複数ボタンのうち該当するアクションのSQLだけを絞り込む。

#### フェーズ1：画面ロードSQL（各画面を表示するGETリクエスト）

```cypher
-- 画面ロードSQL（transitions_query.cypher に定義）
MATCH (s:Screen {id: $screen_id})
      <-[:RETURNS_VIEW]-(cm:ControllerMethod {httpMethod: 'GET'})
      -[:CALLS*1..3]->(sql:SqlStatement)
RETURN cm.url           AS url,
       sql.raw          AS sql_text,
       sql.type         AS sql_type,
       sql.method_name  AS mapper_method,
       sql.table        AS table_name
```

#### フェーズ2：ボタンアクションSQL（指定ボタン押下時のリクエスト）

```cypher
-- ボタンアクションSQL（action.button の id で絞り込む）
MATCH (s:Screen {id: $screen_id})
      -[:CONTAINS]->(b:Button {id: $button_id})
      -[:SUBMITS_TO]->(cm:ControllerMethod)
      -[:CALLS*1..3]->(sql:SqlStatement)
RETURN b.id             AS button_id,
       cm.url           AS url,
       sql.raw          AS sql_text,
       sql.type         AS sql_type,
       sql.method_name  AS mapper_method,
       sql.table        AS table_name
```

最後の画面（目的地）はフェーズ1のみ実行し、フェーズ2はスキップする。

Neo4jグラフに登録されていない画面については、シナリオYAMLの `mapper_methods` 指定に
フォールバックし、`parse_mybatis.py` が直接XMLを解析して補完する。

---

### parse_mybatis.py — MyBatis XML WHERE条件の抽出

MyBatis XMLマッパーファイルをパースし、各メソッドのWHERE条件とパラメータ名を抽出する。

#### 入力と出力

```xml
<!-- 入力: OrderMapper.xml -->
<select id="findByUserId" parameterType="int" resultMap="orderResultMap">
    SELECT id, user_id, order_date, status, total_amount
    FROM orders
    WHERE user_id = #{userId}
    ORDER BY order_date DESC
</select>
```

```python
# 出力（Pythonデータ構造）
{
    "mapper":  "OrderMapper",
    "method":  "findByUserId",
    "sql_type": "SELECT",
    "table":   "orders",
    "where_params": [
        {
            "column":     "user_id",
            "param_name": "userId",
            "operator":   "=",
            "is_dynamic": False    # <if test="..."> 内でない
        }
    ]
}
```

#### 動的WHERE句の扱い

```xml
<!-- 動的WHERE句の例 -->
<select id="findByCategory" parameterType="string" resultMap="productResultMap">
    SELECT id, name, description, price, stock, category
    FROM products
    <where>
        <if test="category != null and category != ''">
            AND category = #{category}
        </if>
    </where>
    ORDER BY id
</select>
```

```python
# is_dynamic: True でフラグを立てる
{
    "where_params": [
        {
            "column":         "category",
            "param_name":     "category",
            "operator":       "=",
            "is_dynamic":     True,
            "condition_expr": "category != null and category != ''"
        }
    ]
}
# シナリオYAMLの dynamic_where[enabled] が False の場合、このパラメータを無視する
```

---

### resolve_params.py — パラメータ値の解決

各SQLの `#{パラメータ名}` に対して具体値を対応付ける。

#### 解決の優先順位

```
パラメータ名 #{userId} を解決する場合:

① URLパラメータ照合
   nav_path[].params に "userId" があれば → その値を使用

② リクエストパラメータ照合
   nav_path[].action.inputs に "userId" があれば → その値を使用

③ セッションバインディング照合
   session_bindings の field_to_param に "userId" がマッピングされていれば
   → test_user の対応フィールド値を使用
   例: session_bindings.loginUser.field_to_param.id = "userId"
       → test_user.id = 1 を使用

④ FK引き継ぎ推論
   前段で INSERT した orders.id = 100 が確定している状態で
   #{orderId} を解決 → "orderId" が "{テーブル名の単数形}Id" にマッチ
   → orders.id = 100 を使用

⑤ additional_data 照合
   additional_data に当該テーブルの行が明示されていれば → その値を使用

⑥ 解決不能
   警告を出力し、スタブ値（例: 999）を仮置きしてコメントで "-- UNRESOLVED" と明示
```

#### FK引き継ぎ推論のロジック

```
前段で確定: INSERT INTO orders (id, ...) VALUES (100, ...)

次のSQL: WHERE order_id = #{orderId}
  → パラメータ名 "orderId" を分解: "order" + "Id"
  → "order" がテーブル名 "orders" の単数形にマッチ
  → orders.id = 100 を候補として採用

命名規則にマッチしない場合 → additional_data での明示指定にフォールバック
```

---

### generate_inserts.py — INSERT文生成

#### FK依存順序の解決

テーブル間の依存グラフを構築し、トポロジカルソートで挿入順を決定する。

```
users        ← 依存なし（最初に挿入）
  ↓
orders       ← user_id は users.id を参照
  ↓
products     ← 依存なし（order_items の前に挿入）
  ↓
order_items  ← order_id は orders.id、product_id は products.id を参照
```

外部キー情報の取得元（優先順位順）：

1. DDLファイル（`CREATE TABLE` の `FOREIGN KEY` 句）
2. MyBatis `resultMap` の `<association>` / `<collection>` 定義
3. 命名規則ヒューリスティック（`{table}_id` パターン）

#### 重複INSERTの排除

同じテーブルの同じ主キーに対するINSERTが複数の画面で重複した場合、
最初の1件だけを出力し、以降はコメントで「前段で挿入済み（重複排除）」と注記する。

#### NULL許可カラムの補完

WHERE条件に含まれないカラムは以下のルールで補完し、`-- auto-filled` とコメントする。

| カラム型 | 補完値 |
|---|---|
| `VARCHAR` / `TEXT` | `'dummy'` |
| `INT` / `BIGINT` | `0` |
| `DECIMAL` / `NUMERIC` | `0.0` |
| `DATETIME` / `TIMESTAMP` | `NOW()` |
| `BOOLEAN` / `TINYINT(1)` | `0` |

---

## コマンドライン

```powershell
# シナリオYAMLを指定してINSERT文を生成
uv run python playwright-gen/testdata/generate_testdata.py `
    --config ast-analyzer/config.yaml `
    --scenario playwright-gen/testdata/scenario_sample.yaml

# 出力先を明示指定
uv run python playwright-gen/testdata/generate_testdata.py `
    --config ast-analyzer/config.yaml `
    --scenario playwright-gen/testdata/scenario_sample.yaml `
    --output playwright-gen/testdata/output/testdata_order_detail.sql

# dry-run（収集したSQL条件一覧を確認、ファイル書き込みなし）
uv run python playwright-gen/testdata/generate_testdata.py `
    --config ast-analyzer/config.yaml `
    --scenario playwright-gen/testdata/scenario_sample.yaml `
    --dry-run

# Neo4jを使わずMyBatis XMLの直接パースのみで動作（Stage 1 モード）
uv run python playwright-gen/testdata/generate_testdata.py `
    --config ast-analyzer/config.yaml `
    --scenario playwright-gen/testdata/scenario_sample.yaml `
    --no-neo4j
```

### dry-run 出力例

```
=== SQL収集結果 ===

[1] login → UserMapper.findByUsername
    TABLE : users
    WHERE : username = #{username}
    解決   : username → 'testuser'  (nav_path.inputs)

[2] order_list → OrderMapper.findByUserId
    TABLE : orders
    WHERE : user_id = #{userId}
    解決   : userId → 1  (session_bindings: loginUser.id → test_user.id)

[3] order_detail → OrderMapper.findById
    TABLE : orders
    WHERE : id = #{id}
    解決   : id → 100  (nav_path.params.id)
    備考   : [2] のINSERTで対象行を作成済み（重複排除）

[4] order_detail → OrderMapper.findItemsByOrderId
    TABLE : order_items
    WHERE : order_id = #{orderId}
    解決   : orderId → 100  (FK推論: orders.id = 100)

=== 未解決パラメータ ===
なし

=== 生成予定INSERT数 ===
users: 1行 / orders: 1行 / products: 1行（additional_data）/ order_items: 1行
```

---

## サンプルアプリでの適用例

### 全画面・SQL対応表

| 画面 | Controller | SQLメソッド | WHERE条件 | パラメータ経路 |
|---|---|---|---|---|
| ログイン | `UserController.login` | `findByUsername` | `username = #{username}` | フォーム入力 |
| マイページ | `UserController.mypage` | `findById` | `id = #{id}` | セッション `loginUser.id` |
| 商品一覧 | `ProductController.list` | `findAll` | なし | — |
| 商品一覧（絞込） | `ProductController.list` | `findByCategory` | `category = #{category}` | リクエストパラメータ |
| 商品詳細 | `ProductController.detail` | `findById` | `id = #{id}` | URLパラメータ |
| 商品編集 | `ProductController.edit` | `findById` | `id = #{id}` | URLパラメータ |
| 注文履歴 | `OrderController.list` | `findByUserId` | `user_id = #{userId}` | セッション `loginUser.id` |
| 注文詳細 | `OrderController.detail` | `findById` | `id = #{id}` | URLパラメータ |
| 注文詳細 | `OrderController.detail` | `findItemsByOrderId` | `order_id = #{orderId}` | FK推論 |

### 代表的なシナリオとデータ要件

**シナリオA: 注文詳細確認**
```
遷移:    login → order/list → order/detail/100
必要DB:  users(1行) + orders(1行, user_id一致) + order_items(1行以上) + products(order_items分)
```

**シナリオB: カテゴリ検索 → 商品詳細**
```
遷移:    login → product/list?category=electronics → product/detail/10
必要DB:  users(1行) + products(1行以上, category='electronics' を含む)
```

**シナリオC: 商品購入 → 注文確認**
```
遷移:    login → product/detail/10 → (POST /order/place) → order/detail/{new_id}
必要DB:  users(1行) + products(1行, stock > 0)
備考:    POST後に自動生成される orders・order_items は additional_data 不要。
         ただし Playwright シナリオ側で生成後のIDを取得する操作が別途必要。
```

---

## 手動補完が必要な箇所

| 箇所 | 理由 | 対処 |
|---|---|---|
| `session_bindings` の初回宣言 | `session.getAttribute` → フィールド名の対応はJavaコードを読まないと取れない | アプリごとに1回だけ手動で記述。変わらない限り共通ファイルとして再利用 |
| `additional_data` | FK参照先テーブルの値がパスから解決できない場合 | シナリオ作成時に必要行だけ追記 |
| `dynamic_where` の有効フラグ | `<if test="...">` の条件式は静的解析で評価不可 | テストケースに応じてシナリオYAMLで指定 |
| POST後に自動生成される行 | INSERTは不要だが後続画面で参照するIDが実行時まで不明 | Playwrightシナリオ側でIDを取得する操作を別途記述 |

---

## 2段階実装プラン

### Stage 1 — Neo4j不要・MyBatis XML直接パース（先行実装）

Neo4jグラフへの依存をなくし、MyBatis XMLを直接読むだけで動作する軽量版を先に作る。
遷移パスのSQL収集は「シナリオYAMLに mapper_methods を列挙する」方式で代替する。

```yaml
# Stage 1 用シナリオYAML（mapper_methodsを手動列挙）
nav_path:
  - screen: login
    action:
      button: loginBtn
      inputs: { username: testuser, password: password }
    mapper_methods:
      on_load:   []
      on_action: [{ mapper: UserMapper, method: findByUsername }]

  - screen: order_list
    action:
      button: orderDetailLink_100
    mapper_methods:
      on_load:   [{ mapper: OrderMapper, method: findByUserId }]
      on_action: []    # リンク遷移（GET）のため on_load と同一扱い

  - screen: order_detail    # 目的地 → action 不要
    params: { id: 100 }
    mapper_methods:
      on_load:   [{ mapper: OrderMapper, method: findById },
                  { mapper: OrderMapper, method: findItemsByOrderId }]
```

Stage 1 で対応するコンポーネント: `parse_mybatis.py` / `resolve_params.py` / `generate_inserts.py` / `generate_testdata.py`

### Stage 2 — Neo4j連携による自動収集

`collect_sql.py` を追加し、`mapper_methods` の手動列挙をNeo4jクエリで自動化する。
`nav_path` から `mapper_methods` フィールドを省略できるようになる。

前提: `ast-analyzer` による Neo4j グラフ構築が完了していること。

---

## 実装スコープと優先順位

| 優先度 | コンポーネント | 概要 | 作業量 |
|---|---|---|---|
| ① 高 | `parse_mybatis.py` | MyBatis XMLのWHERE条件・パラメータ抽出 | 小 |
| ② 高 | `resolve_params.py` | URL / セッション / FK からのパラメータ値解決 | 中 |
| ③ 高 | `generate_inserts.py` | FK順序制御・INSERT文生成 | 中 |
| ④ 高 | `generate_testdata.py` | CLIエントリーポイント・dry-run | 小 |
| ⑤ 中 | `collect_sql.py` | Neo4j連携による自動SQL収集（Stage 2） | 中 |

---

## 未決定事項

- **DDL取得方法**: `CREATE TABLE` DDLファイルをconfig.yamlに設定するか、Javaエンティティクラスから推論するか
- **解決不能パラメータのポリシー**: スタブ値で続行（警告のみ）にするか、エラーで停止するか
