# Neo4j グラフ DB スキーマ設計

## ノード一覧

| ノード | 一意キー | 主なプロパティ | 登録フェーズ |
|---|---|---|---|
| `Controller` | `className` | `filePath`, `baseUrl` | Phase 1 |
| `ControllerMethod` | `id` | `name`, `url`, `httpMethod`, `returnView`, `redirectTo`, `className` | Phase 1 |
| `Service` | `className` | `filePath` | Phase 1 |
| `ServiceMethod` | `id` | `name`, `signature`, `className` | Phase 1 |
| `Dao` | `className` | `filePath`, `fqn` | Phase 1 |
| `DaoMethod` | `id` | `name`, `signature`, `className` | Phase 1 |
| `SqlStatement` | `id` | `sqlId`, `sqlType`, `rawSql`, `namespace` | Phase 1 |
| `Table` | `name` | ― | Phase 1 |
| `Screen` | `path` | `viewName`, `title` | Phase 2 |
| `Button` | `uid` | `label`, `buttonType`, `targetUrl`, `httpMethod`, `onclickFn` | Phase 2 |
| `JsFile` | `path` | ― | Phase 3 |
| `JsFunction` | `id` | `name`, `filePath`, `line` | Phase 3 |
| `AjaxCall` | `id` | `url`, `method`, `unresolved` | Phase 3 |

---

## ノード ID 生成ルール

| ノード | ID 形式 | 例 |
|---|---|---|
| `Controller` | `className` | `ProductController` |
| `ControllerMethod` | `ClassName#methodName#/url` | `ProductController#list#/product/list` |
| `ServiceMethod` | `ClassName#methodName` | `ProductServiceImpl#findAll` |
| `DaoMethod` | `ClassName#methodName` | `ProductDao#findAll` |
| `SqlStatement` | `namespace#sqlId` | `com.example.dao.ProductDao#findAll` |
| `Screen` | JSPファイルの絶対パス | `/app/src/.../product/list.jsp` |
| `Button` | `{jspPath}#btn{index}` | `/app/.../list.jsp#btn0` |
| `JsFunction` | `{filePath}#{functionName}` | `/app/js/product.js#submitForm` |
| `AjaxCall` | `{filePath}#{fnName}#{url}#{httpMethod}` | `/app/js/product.js#load#{var}#GET` |

---

## エッジ一覧

### Phase 1 エッジ

| エッジ | 起点 → 終点 | 意味 |
|---|---|---|
| `HAS_METHOD` | `Controller` → `ControllerMethod` | クラスとメソッドの所属関係 |
| `HAS_METHOD` | `Service` → `ServiceMethod` | 同上 |
| `HAS_METHOD` | `Dao` → `DaoMethod` | 同上 |
| `CALLS` | `ControllerMethod` → `ServiceMethod` | Controller からの Service 呼び出し |
| `CALLS` | `ServiceMethod` → `DaoMethod` | Service からの DAO 呼び出し |
| `EXECUTES` | `DaoMethod` → `SqlStatement` | MyBatis の sqlId 照合 |
| `READS` | `SqlStatement` → `Table` | SELECT 文によるテーブル参照 |
| `WRITES` | `SqlStatement` → `Table` | INSERT / UPDATE / DELETE によるテーブル更新 |

### Phase 2 エッジ

| エッジ | 起点 → 終点 | 意味 |
|---|---|---|
| `CONTAINS` | `Screen` → `Button` | JSP とボタンの所属関係 |
| `SUBMITS_TO` | `Button` → `ControllerMethod` | フォームの submit 先 |
| `NAVIGATES_TO` | `Button` → `ControllerMethod` | `<a href>` によるリンク遷移 |
| `RETURNS_VIEW` | `ControllerMethod` → `Screen` | `return "viewName"` によるView返却 |
| `REDIRECTS_TO` | `ControllerMethod` → `Screen` | `return "redirect:/path"` によるリダイレクト |
| `TRANSITIONS_TO` | `Screen` → `Screen` | 画面遷移の直接エッジ（`trigger`: ボタンラベル、`condition`: 分岐条件式、同一画面への自己ループも含む） |

### Phase 3 エッジ

| エッジ | 起点 → 終点 | 意味 |
|---|---|---|
| `CONTAINS` | `JsFile` → `JsFunction` | JSファイルと関数の所属関係 |
| `MAKES_AJAX` | `JsFunction` → `AjaxCall` | 関数内の Ajax 呼び出し |
| `RESOLVES_TO` | `AjaxCall` → `ControllerMethod` | Ajax URL から Controller への解決 |
| `AJAX_CALLS` | `JsFunction` → `ControllerMethod` | Ajax 呼び出しの短絡エッジ |
| `CALLS` | `JsFunction` → `JsFunction` | JS 関数間の呼び出し |
| `TRIGGERS_JS` | `Button` → `JsFunction` | `onclick` によるJS関数起動 |
| `NAVIGATES_TO` | `JsFunction` → `ControllerMethod` | `window.location.href` による遷移 |

---

## UNIQUE 制約一覧

`create_constraints()` で初回起動時に全制約を `IF NOT EXISTS` で作成する。

```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Screen)           REQUIRE n.path IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Button)           REQUIRE n.uid IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Controller)       REQUIRE n.className IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ControllerMethod) REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Service)          REQUIRE n.className IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:ServiceMethod)    REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Dao)              REQUIRE n.className IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:DaoMethod)        REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:SqlStatement)     REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Table)            REQUIRE n.name IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:JsFile)           REQUIRE n.path IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:JsFunction)       REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:AjaxCall)         REQUIRE n.id IS UNIQUE
```

---

## グラフ全体の構造イメージ

```
Screen -[CONTAINS]-> Button
                       │
          ┌────────────┼──────────────────┐
          │            │                  │
     SUBMITS_TO   NAVIGATES_TO      TRIGGERS_JS
          │            │                  │
          ▼            ▼                  ▼
   ControllerMethod ◄──┘           JsFunction
          │                         │       │
       CALLS                  AJAX_CALLS  CALLS
          │                         │       │
          ▼                         ▼       ▼
   ServiceMethod           ControllerMethod JsFunction
          │
       CALLS
          │
          ▼
     DaoMethod
          │
       EXECUTES
          │
          ▼
     SqlStatement
          │
    READS / WRITES
          │
          ▼
        Table

ControllerMethod -[RETURNS_VIEW / REDIRECTS_TO]-> Screen
Screen           -[TRANSITIONS_TO]->              Screen
```

---

## 代表的な Cypher クエリ

### 画面→テーブルの全呼び出し連鎖

```cypher
MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
  -[:SUBMITS_TO]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path
```

### 画面遷移フロー（最大5ホップ、自己ループを含む）

```cypher
MATCH path = (s:Screen {viewName: $name})-[:TRANSITIONS_TO*1..5]->(e:Screen)
RETURN path
```

同一画面への自己ループ（例: ログイン失敗→ログイン再表示）も含まれる。
`condition` プロパティがある場合は分岐条件式（例: `"user == null"`）が格納されている。

### 特定テーブルを参照している画面を逆引き

```cypher
MATCH path = (t:Table {name: 'ORDERS'})<-[:READS|WRITES]-(sql)
  <-[:EXECUTES]-(dm:DaoMethod)
  <-[:CALLS]-(sm:ServiceMethod)
  <-[:CALLS]-(cm:ControllerMethod)
  <-[:SUBMITS_TO|AJAX_CALLS]-(b)
  <-[:CONTAINS]-(s:Screen)
RETURN path
```

### 未解決 AjaxCall 一覧

```cypher
MATCH (a:AjaxCall)
WHERE NOT (a)-[:RESOLVES_TO]->()
RETURN a.url AS url, a.method AS method
ORDER BY a.url
```

### グラフ統計

```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count
```
