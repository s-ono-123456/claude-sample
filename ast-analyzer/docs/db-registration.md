# DB 登録処理の実装詳細

実装ファイル: `graph/neo4j_client.py`

---

## 基本構造

`Neo4jClient` クラスが全 Neo4j 操作を担う。コンテキストマネージャとして使用し、
`with` ブロック終了時に自動でドライバを閉じる。

```python
with Neo4jClient(uri, user, password) as neo4j:
    neo4j.create_constraints()
    neo4j.save_controllers(controllers)
    ...
```

内部の `_run()` がクエリ実行の共通口。1クエリ = 1セッションで発行される。

```python
def _run(self, query: str, **params):
    with self.driver.session() as session:
        return session.run(query, **params)
```

バッチ登録には `_run_unwind()` を使う。空リストは自動スキップされる。

```python
def _run_unwind(self, query: str, items: list, **params):
    if not items:
        return
    with self.driver.session() as session:
        return session.run(query, items=items, **params)
```

---

## ノード登録パターン: UNWIND + MERGE + SET

全ノード登録は `UNWIND` でリストを展開し、`MERGE`（冪等）+ `SET`（プロパティ上書き）で書く。
同一種別のノードを **1クエリ** で一括登録する。

```cypher
-- 例: 全 Controller ノードを一括登録
UNWIND $items AS c
MERGE (ctrl:Controller {className: c.className})
SET ctrl.filePath = c.filePath, ctrl.baseUrl = c.baseUrl
```

クラスとメソッドは **3クエリ** で登録する（クラス数・メソッド数に依存しない）。

```
1. 全クラスノードを UNWIND MERGE
2. 全メソッドノードを UNWIND MERGE（全クラス分フラット展開）
3. 全 HAS_METHOD エッジを UNWIND MERGE（m.className で親を辿る）
```

Controller N クラス × メソッド数合計 M のクエリ数: **3**（旧実装では 1+2M）

---

## エッジ登録パターン: UNWIND + MATCH + MATCH + MERGE

エッジ登録は両端ノードの ID をリストにまとめ、UNWIND で一括 MERGE する。

```cypher
-- 例: Controller → Service の CALLS エッジ（全ペア一括）
UNWIND $items AS p
MATCH (cm:ControllerMethod {id: p.cmId})
MATCH (sm:ServiceMethod    {id: p.smId})
MERGE (cm)-[:CALLS]->(sm)
```

ノードが存在しない場合は `MATCH` が空振りし、エッジは作られずエラーにもならない。
このため **ノードを先に全登録してからエッジを登録する** 順序が必須。

---

## 登録順序（main.py での制御）

```
[Phase 1 ノード]
  save_controllers()  ─┐
  save_services()      ├─ 全ノードを先に登録（各3クエリ）
  save_daos()          │
  save_mappers()      ─┘ （5クエリ）

[Phase 1 エッジ]
  link_all()          ─── Controller→Service→DAO の CALLS エッジ（各1クエリ）

[Phase 2 ノード]
  save_screens()      ─── Screen / Button ノード（3クエリ）

[Phase 2 エッジ]
  link_buttons_submits_to()        ─┐
  link_buttons_navigates_to()      ─┤─ Button → ControllerMethod エッジ（各1クエリ）
  link_controllers_returns_view()  ─┤─ ControllerMethod → Screen エッジ（各1クエリ）
  link_controllers_redirects_to()  ─┘
  link_screens_transitions()       ─── Screen → Screen の TRANSITIONS_TO（2クエリ: Screenノード MERGE + エッジ MERGE/SET）

[Phase 3 ノード]
  save_js_files()     ─── JsFile / JsFunction / AjaxCall ノード（5クエリ）

[Phase 3 エッジ]
  link_buttons_triggers_js()    ─┐
  link_js_calls_js_batch()      ─┤─ JS 関連エッジ（各1クエリ、ただし link_ajax_to_controllers は2クエリ）
  link_ajax_to_controllers()    ─┤
  link_js_navigates_to_batch()  ─┘
```

---

## クエリ数の比較

| フェーズ | 旧実装（クラス数・メソッド数に比例） | 新実装（固定） |
|---|---|---|
| Phase 1 ノード | Σ(1 + 2N) per class | 14 |
| Phase 1 エッジ | Σ(calls) per method | 2 |
| Phase 2 ノード | Σ(1 + 2B) per screen | 3 |
| Phase 2 エッジ | Σ(pairs) | 6 |
| Phase 3 ノード | Σ(1 + 2F + 2A) per file | 5 |
| Phase 3 エッジ | Σ(pairs) | 5 |
| **合計** | **数百〜数千（規模依存）** | **~35（規模非依存）** |

---

## save_mappers の READS / WRITES 分離

SQL 種別（SELECT / INSERT / UPDATE / DELETE）に応じてエッジ種別を分けた **別クエリ** で登録する。

```python
reads  = [{"sqlId": sid, "table": t} for t in stmt.tables if stmt.sql_type == SqlType.SELECT]
writes = [{"sqlId": sid, "table": t} for t in stmt.tables if stmt.sql_type != SqlType.SELECT]
```

- `SELECT` → `SqlStatement -[READS]-> Table`（UNWIND 1クエリ）
- `INSERT` / `UPDATE` / `DELETE` → `SqlStatement -[WRITES]-> Table`（UNWIND 1クエリ）

旧実装で使っていた f-string による動的クエリ生成は廃止。

---

## TRANSITIONS_TO の登録パターン（condition の扱い）

`condition` は `null` になりうるため、MERGE キーに含めず `SET` で後から設定する。

```cypher
UNWIND $items AS p
MATCH (s1:Screen {path: p.fromPath})
MATCH (s2:Screen {path: p.toPath})
MERGE (s1)-[r:TRANSITIONS_TO {trigger: p.trigger}]->(s2)
SET r.condition = p.condition
```

- `condition` が `null` の場合、`SET` によりプロパティが削除される（Neo4j の仕様）
- 同一画面への自己ループ（`fromPath == toPath`）も同じパターンで登録される
- 同一 `(from, to, trigger)` で条件が異なる場合は既存リレーションシップの `condition` が上書きされる

---

## Ajax 解決の2エッジ構造

Ajax 呼び出しが Controller に解決された場合、エッジを2本登録する。

```
JsFunction -[MAKES_AJAX]-> AjaxCall -[RESOLVES_TO]-> ControllerMethod
JsFunction -[AJAX_CALLS]->                           ControllerMethod  ← 短絡エッジ
```

`link_ajax_to_controllers()` が RESOLVES_TO と AJAX_CALLS を各1クエリ（合計2クエリ）で一括登録する。
未解決の Ajax は `RESOLVES_TO` を持たないため `unresolved_ajax_calls()` で検出できる。

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

### `clear_all()`

全ノード・リレーションシップを削除する。`--reset` フラグ付きで `main.py` を実行した際に呼び出される。

```cypher
MATCH (n) DETACH DELETE n
```

制約（インデックス）は削除されないため、再実行時に `create_constraints()` で重複警告が出るが動作に影響はない。

---

### `unresolved_ajax_calls() -> list`

`RESOLVES_TO` エッジを持たない `AjaxCall`（URL解決できなかった Ajax 呼び出し）の一覧を返す。
動的URL生成（変数結合・テンプレートリテラル）が原因で解決できなかったものが該当する。

```cypher
MATCH (a:AjaxCall)
WHERE NOT (a)-[:RESOLVES_TO]->()
RETURN a.url AS url, a.method AS method
ORDER BY a.url
```
