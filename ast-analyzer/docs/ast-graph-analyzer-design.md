# JSP/JS/Spring/MyBatis AST解析 → グラフDB設計方針

## 概要

JSP・JavaScript・Spring MVC・MyBatisで構成されたWebアプリケーションをAST解析し、
画面からDBテーブルまでの呼び出し連鎖と画面遷移をNeo4jグラフDBに格納する。

---

## 全体フロー

```
JSP / JS / Java / MyBatis XML
        ↓
   各言語ASTパーサー
        ↓
   中間表現 (JSON/Dict)
        ↓
   URLマッチング・メソッド呼び出し解決（リンカー）
        ↓
   Neo4j グラフDB投入
```

---

## グラフDBスキーマ設計（Neo4j）

### ノード種別

| ノード | プロパティ例 |
|---|---|
| `Screen` | path, title |
| `Button` | label, type(submit/link/js) |
| `JsFile` | path |
| `JsFunction` | name, filePath |
| `AjaxCall` | url, method(GET/POST) |
| `Controller` | className, baseUrl |
| `ControllerMethod` | name, url, httpMethod |
| `Service` | className |
| `ServiceMethod` | name, signature |
| `Dao` | className |
| `DaoMethod` | name, sqlId |
| `SqlStatement` | type(SELECT/INSERT/UPDATE/DELETE), raw |
| `Table` | name |

### エッジ種別

```
Screen           -[CONTAINS]->        Button
Button           -[TRIGGERS_JS]->     JsFunction
Button           -[SUBMITS_TO]->      ControllerMethod   (form action)
Button           -[NAVIGATES_TO]->    Screen              (href/forward)
JsFunction       -[AJAX_CALLS]->      ControllerMethod
JsFunction       -[CALLS]->           JsFunction
ControllerMethod -[CALLS]->           ServiceMethod
ServiceMethod    -[CALLS]->           DaoMethod
DaoMethod        -[EXECUTES]->        SqlStatement
SqlStatement     -[READS|WRITES]->    Table
Screen           -[TRANSITIONS_TO]->  Screen             (画面遷移、自己ループ含む、trigger/conditionプロパティ付き)
ControllerMethod -[RETURNS_VIEW]->    Screen
ControllerMethod -[REDIRECTS_TO]->    Screen
```

---

## 技術スタック

| 用途      | ライブラリ                                              |
| ------- | -------------------------------------------------- |
| 実装言語    | Python 3.11+                                       |
| Javaパース | tree-sitter + tree-sitter-java（または javalang）       |
| JSパース   | tree-sitter + tree-sitter-javascript               |
| JSPパース  | BeautifulSoup4（HTML部）+ tree-sitter-java（スクリプトレット部） |
| XMLパース  | lxml（MyBatis mapper XML）                           |
| SQL解析   | sqlparse（テーブル名抽出）                                  |
| グラフDB   | Neo4j 5.x + neo4j Python driver                    |

---

## ディレクトリ構成

```
ast-analyzer/
├── config.yaml                      # 対象ディレクトリ、DB接続情報
├── main.py                          # エントリーポイント
├── parsers/
│   ├── jsp_parser.py                # JSP → Screen/Button/URL参照
│   ├── js_parser.py                 # JS → JsFunction/AjaxCall
│   ├── java_controller_parser.py
│   ├── java_service_parser.py
│   ├── java_dao_parser.py
│   ├── mybatis_xml_parser.py        # Mapper XML → SQL/Table
│   └── utils.py                     # アノテーション値取得・ASTウォーク共通処理
├── linker/
│   ├── url_linker.py                # URL文字列でJSP/JS↔Controller紐付け
│   ├── method_call_linker.py        # メソッド呼び出し連鎖を解決
│   ├── view_linker.py               # return "viewName" → Screen紐付け
│   └── js_linker.py                 # JS関連リンク解決（Button→JS / Ajax→Controller）
├── graph/
│   ├── schema.py                    # ノード/エッジ定数定義
│   └── neo4j_client.py              # Neo4j CRUD
├── model/
│   └── ir.py                        # 中間表現データクラス
└── docs/                            # 設計資料
```

---

## 各パーサーの抽出対象

### JSPパーサー

- `<form action="/search">` → SUBMITS_TO
- `<a href="/detail">` → NAVIGATES_TO
- `<button onclick="fn()">` → TRIGGERS_JS
- インラインJSの `$.ajax({ url: '...' })` → AjaxCall
- `<jsp:forward page="...">` → NAVIGATES_TO
- スクリプトレット内の `response.sendRedirect(...)` → NAVIGATES_TO

### JSパーサー

- `$.ajax({ url: '/api/search', type: 'POST' })`
- `$.get('/api/search', ...)`
- `fetch('/api/search', { method: 'POST' })`
- `axios.post('/api/search')`
- `window.location.href = '/screen'`
- function定義と関数呼び出し関係

### Javaコントローラーパーサー

- `@Controller` / `@RestController` クラス検出
- `@RequestMapping` / `@GetMapping` / `@PostMapping` メソッドとURLパターン
- `@Autowired` フィールド（Serviceの注入先）
- メソッド内の `service.methodName()` 呼び出し
- `return "viewName"` / `return "redirect:/path"`
- `ModelAndView` のview名
- `IfStatement` の条件式（`user == null` など）を `conditional_returns` に格納し、分岐ごとに遷移先と条件をペアで保持

### MyBatis XMLパーサー

- `namespace` → Daoクラス名との対応
- `<select id="findById">` → DaoMethod.sqlId との紐付け
- SQL文の `FROM` / `JOIN` / `INTO` / `UPDATE` 句からテーブル名抽出（sqlparse使用）

---

## URLマッチング（リンカー）

JSPの `action="/search"` とControllerの `@RequestMapping("/search")` を紐付ける。

```python
class UrlLinker:
    def link(self, buttons, controller_methods):
        for btn in buttons:
            for method in controller_methods:
                # パスパラメータ {id} を正規表現に変換して照合
                pattern = re.compile(
                    re.escape(method.url).replace(r'\{[^}]+\}', '[^/]+')
                )
                if pattern.fullmatch(btn.target_url):
                    yield (btn, method)
```

**コンテキストパス対応**: `config.yaml` にコンテキストパス（例: `/app`）を設定し、照合前に除去する。

---

## 画面遷移の抽出パターン

| パターン | 種別 |
|---|---|
| `<form action="/search">` のsubmit | フォーム送信 |
| `<a href="/detail">` | リンク遷移 |
| `<jsp:forward page="detail.jsp">` | サーバー内転送 |
| Controller `return "redirect:/detail"` | リダイレクト |
| Controller `return "detail"` | ViewResolver経由 |
| `response.sendRedirect("/detail")` | サーブレットリダイレクト |
| JS `window.location.href = '/detail'` | JS遷移 |

すべて `Screen -[TRANSITIONS_TO {trigger: "buttonLabel", condition: "条件式"}]-> Screen` として記録する。

- `condition` は `IfStatement` 直前の条件式（例: `"user == null"`）。無条件 return の場合はプロパティなし
- 同一画面への自己ループ（例: ログイン失敗→ログイン再表示）も記録される
- 条件分岐で複数の遷移先を持つ場合、それぞれ別エッジとして登録される

---

## 代表的なCypherクエリ

```cypher
-- 画面→ボタン→コントローラー→サービス→DAO→テーブルの全連鎖
MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
  -[:SUBMITS_TO]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path

-- 画面遷移フロー（最大5ホップ）
MATCH path = (s:Screen)-[:TRANSITIONS_TO*1..5]->(e:Screen)
RETURN path

-- 特定テーブルを参照している画面を逆引き
MATCH path = (t:Table {name: 'ORDERS'})<-[:READS|WRITES]-(sql)
  <-[:EXECUTES]-(dm:DaoMethod)
  <-[:CALLS]-(sm:ServiceMethod)
  <-[:CALLS]-(cm:ControllerMethod)
  <-[:SUBMITS_TO|AJAX_CALLS]-(b)
  <-[:CONTAINS]-(s:Screen)
RETURN path
```

---

## 実装フェーズ

| フェーズ | 内容 | 難易度 |
|---|---|---|
| 1 | JavaパーサーでController/Service/DAO/Mapper解析 | 中 |
| 2 | JSPパーサーでScreen/Button/URL抽出 | 中 |
| 3 | JSパーサーでAjaxCall/JsFunction抽出 | 中 |
| 4 | URLリンカーでJSP/JS↔Controller紐付け | 高 |
| 5 | メソッド呼び出し連鎖の解決 | 高 |
| 6 | Neo4j投入とCypherクエリ整備 | 低 |

---

## 限界と対処方針

| 課題 | 対処 |
|---|---|
| 動的URL生成（変数結合・テンプレートリテラル） | `unresolved=true` フラグでノードマーク、手動補完 |
| リフレクション・動的メソッド呼び出し | 対応範囲外として除外 |
| JSの複雑なクロージャ | 関数スコープ内のAjaxCallのみ記録 |
| Springの親クラス継承 | 継承チェーンを追ってRequestMappingを解決 |
| コンテキストパスの差異 | config.yamlで設定して照合時に正規化 |
