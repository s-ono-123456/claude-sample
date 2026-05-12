# ast-analyzer 処理フロー

## 概要

Spring MVC + MyBatis + JSP + JS で構成された Java Web アプリケーションを静的解析し、
「画面ボタン → Controller → Service → DAO → SQL → テーブル」という呼び出し連鎖と
画面遷移フローを Neo4j グラフ DB に構築するツール。

---

## 全体フロー

```
ソースコード (Java / XML / JSP / JS)
        │
        ▼
  ┌─────────────┐
  │  Phase 1    │  Java (Controller / Service / DAO) + MyBatis XML を解析
  └─────────────┘
        │ controllers, services, daos, mappers
        ▼
  ┌─────────────┐
  │  Phase 2    │  JSP (Screen / Button) を解析 + URL照合 + View照合
  └─────────────┘
        │ screens, btn_ctrl_pairs, returns_view, redirects_to
        ▼
  ┌─────────────┐
  │  Phase 3    │  JS (JsFunction / AjaxCall) を解析 + リンク解決
  └─────────────┘
        │
        ▼
  Neo4j グラフ DB への書き込み
```

エントリーポイント: `main.py`

---

## Phase 1: Java / MyBatis 解析

**入力**: `source_root` 配下の `*.java`、`mapper_root` 配下の `*.xml`

### パーサー一覧

| パーサー | ファイル | 判定条件 | 抽出内容 |
|---|---|---|---|
| `java_controller_parser.py` | `*.java` | `@Controller` / `@RestController` | クラス名・ベースURL・メソッドのURLマッピング・return値・サービス呼び出し |
| `java_service_parser.py` | `*.java` | `@Service` | クラス名・メソッド一覧・DAO呼び出し・implements インターフェース名 |
| `java_dao_parser.py` | `*.java` | `@Repository` / Mapper インターフェース | クラス名・FQN・メソッド一覧 |
| `mybatis_xml_parser.py` | `*.xml` | `namespace` 属性 | SQL文・SQL種別・テーブル名（sqlparse で FROM/JOIN/INTO/UPDATE 句から抽出） |

ライブラリ: `javalang`（Java ASTパース）、`lxml`（XML）、`sqlparse`（テーブル名抽出）

### Controller パーサーの動作

1. ファイルを読み込み、`@Controller` / `@RestController` が含まれなければ即スキップ（高速プリフィルタ）
2. `javalang.parse.parse()` で AST を構築
3. クラスレベルの `@RequestMapping` からベース URL を取得
4. `@Autowired` / `@Inject` / `@Resource` フィールドを収集（フィールド名 → 型名）
5. `@GetMapping` / `@PostMapping` 等のアノテーション付きメソッドを走査
6. メソッド本体から `MethodInvocation` ノードを再帰的に収集し、`fieldName.methodName()` 形式の呼び出しを抽出
7. `return` 文から view名または `redirect:/path` を抽出（`return_view` / `redirect_to`）
8. `IfStatement` を再帰的に走査し、各 `return` 文に直近の条件式を対応付けて `conditional_returns` に格納

   例: `if (user == null) { return "user/login"; } return "redirect:/product/list";`
   → `ConditionalReturn(value="user/login", condition="user == null")` と
     `ConditionalReturn(value="redirect:/product/list", condition=None)` の2件を生成

   条件式は `_serialize_expr` で文字列化（`BinaryOperation`, `MethodInvocation`, `MemberReference` 等に対応、
   複雑な式は `"..."` にフォールバック）。else 分岐の条件は `!(元の条件)` 形式。

### Phase 1 終了後のメソッド呼び出し連鎖解決 (`method_call_linker.py`)

1. Controller の `@Autowired` フィールド名 → 型名を解決
2. Controller メソッド内の `service.methodName()` → ServiceMethod に `CALLS` エッジ
3. Service メソッド内の `dao.methodName()` → DaoMethod に `CALLS` エッジ
4. Mapper の `namespace` → DAO の FQN を照合して DaoMethod → SqlStatement に `EXECUTES` エッジ

インターフェース注入（`UserService` → `UserServiceImpl`）にも対応。
実装クラス名・インターフェース名の両方で検索できるよう `service_map` に双方向登録する。

---

## Phase 2: JSP 解析 + URL / View 照合

**入力**: Phase 1 の `controllers` + `jsp_root` 配下の `*.jsp`

### JSP パーサー (`jsp_parser.py`)

ライブラリ: BeautifulSoup4

| 抽出対象 | 生成する ButtonType |
|---|---|
| `<form action="/path">` のsubmitボタン | `SUBMIT` |
| `<a href="/path">` | `LINK` |
| `<button onclick="fn()">` / `onclick` 属性付き要素 | `JS_BUTTON` |

追加で以下も抽出:
- ページタイトル（`<title>` タグ）
- `<jsp:forward page="...">` → `server_redirects`
- スクリプトレット内 `response.sendRedirect(...)` → `server_redirects`

Button の `uid` は `"{jspPath}#btn{index}"` 形式で一意に生成。

view_name はファイルパスから `view_prefix` / `view_suffix` を除いた文字列
（例: `/WEB-INF/views/product/list.jsp` → `product/list`）。

### URL照合 (`url_linker.py`)

Button の `targetUrl` と Controller の `@RequestMapping` URL をマッチング。

- パスパラメータ `{id}` は正規表現 `[^/]+` に変換して柔軟に照合
- `config.yaml` の `context_path`（例: `/app`）を照合前に除去

### View照合 (`view_linker.py`)

Controller メソッドの `conditional_returns` → Screen の `view_name` を照合し、条件情報を保持する。

- `RETURNS_VIEW`: `return "viewName"` → 対応 Screen（`condition` 付き）
- `REDIRECTS_TO`: `return "redirect:/path"` → URL から view_name を逆引き（`condition` 付き）

戻り値は `(ctrl_class, cm, screen, condition)` の4要素タプル。
`conditional_returns` が空の場合は従来の `return_view` / `redirect_to` にフォールバック（`condition=None`）。

### 画面遷移エッジの自動生成 (`_build_screen_transitions`)

```
Button → ControllerMethod → [Screen1, Screen2, ...]
```
の連鎖から `Screen -[TRANSITIONS_TO {trigger: "buttonLabel", condition: "条件式"}]-> Screen` を直接生成。

- 1メソッドが複数 return 値を持つ場合（条件分岐）、全遷移先に対してエッジを生成する
- 同一画面への自己ループ（例: ログイン失敗→ログイン再表示）も含む
- `condition=None` の場合は Neo4j の `SET` でプロパティなしとして扱われる

---

## Phase 3: JS 解析 + リンク解決

**入力**: Phase 2 の `screens` + Phase 1 の `controllers` + `js_root` 配下の `*.js`

### JS パーサー (`js_parser.py`)

ライブラリ: tree-sitter + tree-sitter-javascript

| 抽出対象 | 格納先 |
|---|---|
| `function fn() {}` の定義 | `JsFunctionInfo` |
| `$.ajax({ url, type })` / `$.get` / `fetch` / `axios.post` | `AjaxCallInfo` |
| 関数内の関数呼び出し | `JsFunctionInfo.fn_calls` |
| `window.location.href = '/path'` | `JsFunctionInfo.location_hrefs` |

動的URL（変数結合・テンプレートリテラル）は `unresolved=True` フラグでマーク。

#### ガード条件の抽出（`_extract_top_level_guards`）

関数ボディのトップレベル（depth=1、ネストしていない直下）に存在する
「早期リターンガード」の条件を抽出する機能。

**対象パターン**:

```js
if (cart.length === 0) {   // ← ガード条件 (cart.length === 0)
    showMessage('...');
    return;                // ← 早期リターンで後続のナビゲーションをブロック
}
window.location.href = '/order/detail/' + id;
```

**動作**:
1. ブレース深度を逐次追跡し、depth=1 の `if (cond)` を検出
2. `if` ボディに `return` を含み、`window.location` を含まないものをガードと判定
3. `_extract_location_hrefs` で各ナビゲーションの condition に `!(guard)` を付加

**結果の例**（`placeOrder()` の `window.location.href = .../order/detail/...`）:
- 変更前: `condition = "response.success"`
- 変更後: `condition = "!(cart.length === 0) && response.success"`

### JS リンカー (`js_linker.py`)

| 処理 | 内容 |
|---|---|
| `link_buttons_to_js_functions` | Button の `onclick_fn` 名 → 同名 JsFunction にリンク |
| `link_js_function_calls` | `fn_calls` の関数名 → 同ファイル内の JsFunction 定義にリンク |
| `link_ajax_to_controllers` | AjaxCall の URL → Controller の URL と照合してリンク |
| `link_hrefs_to_controllers` | `location_hrefs` の URL → Controller の URL と照合してリンク |

---

## 実行オプション

| オプション | 説明 |
|---|---|
| `--config <path>` | 設定ファイルパス（デフォルト: `config.yaml`） |
| `--phase 1\|2\|3` | 実行フェーズ上限（デフォルト: 3） |
| `--dry-run` | 解析・リンク解決のみ実施、Neo4j への書き込みをスキップ |
| `--reset` | Neo4j の全ノード・リレーションシップを削除してから登録し直す（スキーマ変更後に使用） |
| `--summary` | Neo4j グラフの統計と未解決 AjaxCall を表示して終了 |

`--phase 1` は Java/MyBatis のみ、`--phase 2` は JSP を含む、`--phase 3` は JS も含む。
`--reset` は `MATCH (n) DETACH DELETE n` を実行してから再登録するため、制約定義はそのまま残る。

---

## ディレクトリ構成

```
ast-analyzer/
├── main.py                          # エントリーポイント・フェーズ制御
├── config.yaml                      # 対象ディレクトリ・DB接続情報
├── parsers/
│   ├── java_controller_parser.py
│   ├── java_service_parser.py
│   ├── java_dao_parser.py
│   ├── mybatis_xml_parser.py
│   ├── jsp_parser.py
│   ├── js_parser.py
│   └── utils.py                     # アノテーション値取得・ASTウォーク共通処理
├── linker/
│   ├── method_call_linker.py        # Controller→Service→DAO の呼び出し連鎖解決
│   ├── url_linker.py                # Button.targetUrl ↔ ControllerMethod.url 照合
│   ├── view_linker.py               # ControllerMethod.return_view ↔ Screen 照合
│   └── js_linker.py                 # JS関連リンク解決
├── graph/
│   ├── schema.py                    # ノード/エッジ定数定義
│   └── neo4j_client.py              # Neo4j CRUD
├── model/
│   └── ir.py                        # 中間表現データクラス（IR）
└── docs/                            # 設計資料（本ファイル群）
```
