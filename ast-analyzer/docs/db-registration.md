# DB 登録処理の実装詳細

実装ファイル: `graph/neo4j_client.py`

---

## 基本構造

`Neo4jClient` クラスが全 Neo4j 操作を担う。コンテキストマネージャとして使用し、
`with` ブロック終了時に自動でドライバを閉じる。

```python
with Neo4jClient(uri, user, password) as neo4j:
    neo4j.create_constraints()
    neo4j.save_controller(ctrl)
    ...
```

内部の `_run()` がクエリ実行の共通口。**1クエリ = 1セッション** で発行される。
バッチ処理・トランザクションのまとめ実行は行っていない。

```python
def _run(self, query: str, **params):
    with self.driver.session() as session:
        return session.run(query, **params)
```

---

## ノード登録パターン: MERGE + SET

全ノード登録は `MERGE`（存在すれば一致、なければ新規作成）+ `SET`（プロパティ上書き）で冪等に書く。
再実行しても重複ノードは生まれず、プロパティのみ更新される。

```cypher
-- 例: Controller ノード
MERGE (c:Controller {className: $cn})
SET c.filePath = $fp, c.baseUrl = $bu
```

クラスとメソッドは **2ステップ** に分けて登録する。

```
1. クラスノードを MERGE
2. メソッドノードを MERGE（メソッド数分ループ）
3. HAS_METHOD エッジを MERGE（メソッド数分ループ）
```

Controller 1クラスあたりのクエリ数: **1 + 2N**（N = メソッド数）

---

## エッジ登録パターン: MATCH + MATCH + MERGE

エッジ登録は必ず両端のノードを `MATCH` してから `MERGE` でエッジを作る。
ノードが存在しない場合は `MATCH` が空振りし、エッジは作られずにエラーにもならない。

```cypher
-- 例: Controller → Service の CALLS エッジ
MATCH (cm:ControllerMethod {id: $cmId})
MATCH (sm:ServiceMethod    {id: $smId})
MERGE (cm)-[:CALLS]->(sm)
```

このため **ノードを先に全登録してからエッジを登録する** 順序が必須。

---

## 登録順序（main.py での制御）

```
[Phase 1 ノード]
  save_controller()   ─┐
  save_service()       ├─ 全ノードを先に登録
  save_dao()           │
  save_mapper()       ─┘

[Phase 1 エッジ]
  link_all()          ─── Controller→Service→DAO の CALLS エッジ

[Phase 2 ノード]
  save_screen()       ─── Screen / Button ノード

[Phase 2 エッジ]
  link_button_submits_to()      ─┐
  link_button_navigates_to()    ─┤─ Button → ControllerMethod エッジ
  link_controller_returns_view() ─┤─ ControllerMethod → Screen エッジ
  link_controller_redirects_to() ─┘
  _build_screen_transitions()  ─── Screen → Screen の TRANSITIONS_TO エッジ

[Phase 3 ノード]
  save_js_file()      ─── JsFile / JsFunction / AjaxCall ノード

[Phase 3 エッジ]
  link_button_triggers_js()    ─┐
  link_js_calls_js()           ─┤─ JS 関連エッジ
  link_ajax_to_controller()    ─┤
  link_js_navigates_to()       ─┘
```

---

## save_mapper の READS / WRITES 分岐

SQL 種別（SELECT / INSERT / UPDATE / DELETE）に応じてエッジ種別を動的に切り替える。

```python
rel = "READS" if stmt.sql_type == SqlType.SELECT else "WRITES"
```

- `SELECT` → `SqlStatement -[READS]-> Table`
- `INSERT` / `UPDATE` / `DELETE` → `SqlStatement -[WRITES]-> Table`

`MERGE` ではなく f-string でエッジ種別を埋め込んだクエリを `_run()` に渡している。

---

## Ajax 解決の2エッジ構造

Ajax 呼び出しが Controller に解決された場合、エッジを2本登録する。

```
JsFunction -[MAKES_AJAX]-> AjaxCall -[RESOLVES_TO]-> ControllerMethod
JsFunction -[AJAX_CALLS]->                           ControllerMethod  ← 短絡エッジ
```

`AJAX_CALLS` は `AjaxCall` ノードを経由せずに直接 Controller へ辿るための短絡エッジ。
未解決の Ajax は `RESOLVES_TO` を持たないため `unresolved_ajax_calls()` で検出できる。

---

## 現状の課題

| 課題 | 内容 |
|---|---|
| 1クエリ = 1セッション | ノードやエッジを1件ずつ個別に発行しているため、大規模アプリでは登録が遅くなる |
| バッチ処理なし | `UNWIND` を使ったリスト一括登録は未実装 |

### 改善案（未実装）

`UNWIND` でリストを渡すことで1クエリで複数ノードを一括登録できる。

```cypher
UNWIND $methods AS m
MERGE (cm:ControllerMethod {id: m.id})
SET cm.name = m.name, cm.url = m.url, cm.httpMethod = m.httpMethod
```

---

## 診断用メソッド

### `summary() -> dict`

グラフ内の全ノード・エッジ種別ごとのカウントを返す。`--summary` オプションで呼び出される。

```cypher
MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS cnt
MATCH ()-[r]->() RETURN type(r) AS lbl, count(r) AS cnt
```

戻り値例:
```python
{
  "node:Controller": 3,
  "node:ControllerMethod": 12,
  "edge:CALLS": 20,
  ...
}
```

### `unresolved_ajax_calls() -> list`

`RESOLVES_TO` エッジを持たない `AjaxCall`（URL解決できなかった Ajax 呼び出し）の一覧を返す。
動的URL生成（変数結合・テンプレートリテラル）が原因で解決できなかったものが該当する。

```cypher
MATCH (a:AjaxCall)
WHERE NOT (a)-[:RESOLVES_TO]->()
RETURN a.url AS url, a.method AS method
ORDER BY a.url
```
