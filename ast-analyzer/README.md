# ast-analyzer

## なぜ作ったか

大規模な Spring MVC / MyBatis アプリケーションでは、ある画面のボタンを押したときにどの DB テーブルが更新されるかを手動で追跡するのは非常に困難です。
Controller → Service → DAO → SQL → テーブルという呼び出し連鎖が複数ファイルにまたがるためです。

このツールはソースコードを AST 解析し、**画面から DB テーブルまでの全呼び出し連鎖と画面遷移を Neo4j グラフ DB に格納**します。
改修時の影響範囲把握・テスト対象の特定を自動化することが目的です。

## 主な機能

- **3 フェーズ解析** — Java/MyBatis → JSP → JavaScript を順番に解析し、グラフを構築
- **呼び出し連鎖の可視化** — 画面ボタン → Controller → Service → DAO → SQL → テーブルまでの全連鎖をグラフで表現
- **画面遷移の抽出** — フォーム送信・リンク・JS 遷移・リダイレクトをまとめて `TRANSITIONS_TO` エッジとして記録
- **dry-run モード** — Neo4j への書き込みなしで解析結果のみ確認可能

## 前提条件

- Python 3.12 以上 / [uv](https://docs.astral.sh/uv/)（パッケージ管理）
- Neo4j 5.x（ローカルまたはリモート）

## クイックスタート

```powershell
# 1. 依存関係インストール
uv sync

# 2. 設定ファイル作成
Copy-Item ast-analyzer\config.yaml.example ast-analyzer\config.yaml
# config.yaml を開き source_root / neo4j 接続情報を設定

# 3. dry-run で解析結果を確認（Neo4j への書き込みなし）
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml --dry-run

# 動作を確認できたら本実行
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml
```

## セットアップ

### 1. 依存関係のインストール

```powershell
uv sync
```

### 2. 設定ファイルの作成

```powershell
Copy-Item ast-analyzer\config.yaml.example ast-analyzer\config.yaml
```

`ast-analyzer\config.yaml` を開き、ソースパスと Neo4j 接続情報を設定します。

```yaml
source_root: path/to/src/main/java
mapper_root: path/to/src/main/resources/mapper
jsp_root:    path/to/src/main/webapp
neo4j:
  uri:      bolt://localhost:7687
  user:     neo4j
  password: your-password
```

> `config.yaml` は `.gitignore` で除外されています。機密情報をコミットしないよう注意してください。

## 実行方法

```powershell
# Phase 3 まで全実行（デフォルト）
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml

# dry-run: Neo4j 書き込みなし（動作確認に便利）
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml --dry-run

# フェーズ指定（1=Java/MyBatis のみ、2=+JSP、3=+JS）
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml --phase 2

# グラフ統計と未解決 AjaxCall を表示
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml --summary

# Neo4j の全データを削除してから再登録（グラフをリセットしたい場合）
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml --reset
```

## 設定リファレンス

`ast-analyzer/config.yaml` で指定できるフィールド一覧です。

| フィールド | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `source_root` | ✅ | — | Java ソースルート（`.java` ファイルを再帰スキャン） |
| `mapper_root` | | `source_root` と同じ | MyBatis mapper XML ルート |
| `jsp_root` | | — | JSP ファイルルート（Phase 2 以降で使用） |
| `js_root` | | `jsp_root` と同じ | JS ファイルルート（Phase 3 で使用） |
| `view_prefix` | | `/WEB-INF/views/` | Spring ViewResolver プレフィックス |
| `view_suffix` | | `.jsp` | Spring ViewResolver サフィックス |
| `context_path` | | `""` | Web アプリのコンテキストパス（例: `/app`） |
| `neo4j.uri` | ✅ | — | Neo4j 接続 URI（例: `bolt://localhost:7687`） |
| `neo4j.user` | ✅ | — | Neo4j ユーザー名 |
| `neo4j.password` | ✅ | — | Neo4j パスワード |

## 実行フェーズ

| フェーズ | 解析対象 | 生成ノード / エッジ |
|---|---|---|
| Phase 1 | Java (Controller / Service / DAO) + MyBatis XML | Controller, Service, DAO, Mapper, SqlStatement, Table, CALLS, EXECUTES, READS/WRITES |
| Phase 2 | JSP (Screen / Button) | Screen, Button, CONTAINS, SUBMITS_TO, NAVIGATES_TO, RETURNS_VIEW, REDIRECTS_TO, TRANSITIONS_TO |
| Phase 3 | JavaScript | JsFile, JsFunction, AjaxCall, TRIGGERS_JS, AJAX_CALLS, NAVIGATES_TO, CALLS |

## グラフスキーマ

```
Screen           -[CONTAINS]->        Button
Button           -[TRIGGERS_JS]->     JsFunction
Button           -[SUBMITS_TO]->      ControllerMethod
Button           -[NAVIGATES_TO]->    ControllerMethod
JsFunction       -[AJAX_CALLS]->      ControllerMethod
JsFunction       -[CALLS]->           JsFunction
ControllerMethod -[CALLS]->           ServiceMethod
ControllerMethod -[RETURNS_VIEW]->    Screen
ControllerMethod -[REDIRECTS_TO]->    Screen
ServiceMethod    -[CALLS]->           DaoMethod
DaoMethod        -[EXECUTES]->        SqlStatement
SqlStatement     -[READS|WRITES]->    Table
Screen           -[TRANSITIONS_TO]->  Screen
```

## ディレクトリ構成

```
ast-analyzer/
├── config.yaml.example      # 設定ファイルテンプレート
├── config.yaml              # 実際の設定（.gitignore 済み）
├── main.py                  # エントリーポイント
├── queries.cypher           # 代表 Cypher クエリ集
├── parsers/
│   ├── java_controller_parser.py
│   ├── java_service_parser.py
│   ├── java_dao_parser.py
│   ├── mybatis_xml_parser.py
│   ├── jsp_parser.py
│   └── js_parser.py
├── linker/
│   ├── method_call_linker.py
│   ├── url_linker.py
│   ├── view_linker.py
│   └── js_linker.py
├── graph/
│   ├── schema.py
│   └── neo4j_client.py
└── model/
    └── ir.py
```

## 代表 Cypher クエリ

よく使う分析クエリは `ast-analyzer/queries.cypher` に収録されています。

```cypher
-- 画面 → ボタン → Controller → Service → DAO → テーブルの全連鎖
MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
  -[:SUBMITS_TO]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path

-- 特定テーブルを参照している画面を逆引き
MATCH path = (t:Table {name: 'ORDERS'})<-[:READS|WRITES]-(sql:SqlStatement)
  <-[:EXECUTES]-(dm:DaoMethod)
  <-[:CALLS]-(sm:ServiceMethod)
  <-[:CALLS]-(cm:ControllerMethod)
  <-[:SUBMITS_TO|AJAX_CALLS]-(b)
  <-[:CONTAINS]-(s:Screen)
RETURN path

-- 画面遷移フロー（最大 5 ホップ）
MATCH path = (s:Screen)-[:TRANSITIONS_TO*1..5]->(e:Screen)
RETURN path
```

## 設計書

| ドキュメント | 内容 |
|---|---|
| [全体設計方針](docs/ast-graph-analyzer-design.md) | AST 解析〜グラフ DB 格納の全体フローと設計方針 |
| [グラフ DB スキーマ](docs/neo4j-schema.md) | ノード・リレーションの一覧とプロパティ定義 |
| [処理フロー](docs/processing-flow.md) | Phase 1〜3 の詳細な処理フロー |
| [DB 登録処理](docs/db-registration.md) | `Neo4jClient` の実装詳細・クエリ構造 |

## トラブルシューティング

**Neo4j に接続できない**
Neo4j が起動しているか確認し、`config.yaml` の `neo4j.uri` / `user` / `password` が正しいか確認してください。
Neo4j Desktop では "Start" ボタンで起動後、`bolt://localhost:7687` で接続できます。

**Java ファイルのパースエラーが出る**
`--dry-run` で実行するとパースエラーの詳細が表示されます。
未対応の構文が含まれる場合は、該当ファイルを `source_root` のスコープ外に置くか、パーサーを拡張してください。

**グラフを最初からやり直したい**
`--reset` フラグを付けて実行すると Neo4j の全データを削除してから再登録します。

```powershell
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml --reset
```
