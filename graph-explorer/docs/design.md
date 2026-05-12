# Graph Explorer 設計書

## 概要

Neo4j に登録済みのグラフDB（Spring MVC アプリ解析結果）を、ブラウザから検索・可視化する内部ツール。

---

## アーキテクチャ

| レイヤー | 技術 | 備考 |
|---|---|---|
| フロントエンド | Streamlit | Python ワンスタック、追加言語不要 |
| グラフ描画 | pyvis | インタラクティブ（ズーム・ドラッグ対応） |
| DB接続 | neo4j ドライバ | pyproject.toml の既存依存を利用 |
| 設定 | `ast-analyzer/config.yaml` | neo4j.uri / user / password を共用 |

### 起動方法

```powershell
uv run streamlit run graph-explorer/app.py
```

アクセス先: http://localhost:8501

---

## グラフスキーマ

### ノード

| ラベル | 主要プロパティ | 説明 |
|---|---|---|
| Screen | viewName, title | JSP 画面 |
| Button | label, button_type, target_url | フォームボタン / リンク / JS ボタン |
| ControllerMethod | url, httpMethod | Spring MVC エンドポイント |
| ServiceMethod | name, signature | サービス層メソッド |
| DaoMethod | name | DAO メソッド |
| SqlStatement | sqlId, sql_type | MyBatis SQLステートメント |
| Table | name | DB テーブル |
| JsFunction | name, filePath | JavaScript 関数 |

### リレーション

| リレーション | From → To | 意味 |
|---|---|---|
| CONTAINS | Screen → Button | 画面がボタンを持つ |
| SUBMITS_TO | Button → ControllerMethod | フォームサブミット先 |
| NAVIGATES_TO | Button → ControllerMethod | リンク先 |
| TRIGGERS_JS | Button → JsFunction | onclick で JS 関数を呼ぶ |
| AJAX_CALLS | JsFunction → ControllerMethod | AJAX リクエスト先 |
| CALLS | ControllerMethod → ServiceMethod | 呼び出し |
| CALLS | ServiceMethod → DaoMethod | 呼び出し |
| EXECUTES | DaoMethod → SqlStatement | SQL 実行 |
| READS | SqlStatement → Table | SELECT |
| WRITES | SqlStatement → Table | INSERT / UPDATE / DELETE |
| TRANSITIONS_TO | Screen → Screen | 画面遷移 |
| RETURNS_VIEW | ControllerMethod → Screen | ビュー返却 |
| REDIRECTS_TO | ControllerMethod → Screen | リダイレクト |

---

## 機能仕様

### 機能1: 画面遷移グラフ

**目的**: 選択した画面から遷移できる画面をグラフで可視化する。

**UI**
- サイドバー: Screen ノードの viewName をドロップダウンで選択
- サイドバー: 最大ホップ数スライダー（1〜5、デフォルト 3）
- メイン: pyvis インタラクティブグラフ

**Cypher**
```cypher
MATCH path = (s:Screen {viewName: $name})-[:TRANSITIONS_TO*1..$hops]->(e:Screen)
RETURN path
```

**表示仕様**
- Screen ノード: 青色（#4287f5）
- エッジ: リレーション名ラベルなし（矢印のみ）
- 結果なし: 「選択した画面からの遷移が見つかりませんでした」を表示

---

### 機能2: フル呼び出し連鎖グラフ

**目的**: 画面を起点に Controller → Service → DAO → Table までの全経路を可視化する。

**UI**
- サイドバー: Screen ノードの viewName をドロップダウンで選択
- メイン: ノード種別ごとに色分けされた pyvis グラフ

**Cypher（フォーム経路）**
```cypher
MATCH path = (s:Screen {viewName: $name})-[:CONTAINS]->(b:Button)
  -[:SUBMITS_TO]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path
```

**Cypher（JS/AJAX 経路）**
```cypher
MATCH path = (s:Screen {viewName: $name})-[:CONTAINS]->(b:Button)
  -[:TRIGGERS_JS]->(jf:JsFunction)
  -[:AJAX_CALLS]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path
```

フォーム経路と JS 経路の結果を統合して 1 グラフに表示する。

**ノード色定義**

| ノード種別 | 色コード | 色名 |
|---|---|---|
| Screen | #4287f5 | 青 |
| Button | #f5a142 | 橙 |
| ControllerMethod | #a142f5 | 紫 |
| ServiceMethod | #42b883 | 緑 |
| DaoMethod | #c8a060 | 茶 |
| SqlStatement | #909090 | 灰 |
| Table | #f54242 | 赤 |
| JsFunction | #f5e642 | 黄 |

**表示仕様**
- エッジ: リレーション名をラベル表示
- 結果なし: 「呼び出し連鎖が見つかりませんでした」を表示

---

---

### 機能3: 遷移条件一覧

**目的**: 全 `TRANSITIONS_TO` エッジを表形式で俯瞰し、遷移条件を確認する。

**UI**
- サイドバー: 「遷移元」の multiselect フィルタ
- メイン上部: 全遷移のデータフレーム（遷移元 / 遷移先 / トリガー / 条件）
- メイン下部: 「2画面間の経路」セクション
  - From / To を selectbox で選択
  - 「経路を検索」ボタン → pyvis グラフを表示

**Cypher（全遷移取得）**
```cypher
MATCH (s1:Screen)-[r:TRANSITIONS_TO]->(s2:Screen)
RETURN
  coalesce(s1.title, s1.viewName) AS from_screen,
  coalesce(s2.title, s2.viewName) AS to_screen,
  r.trigger AS trigger,
  r.condition AS condition
ORDER BY from_screen, to_screen
```

**Cypher（2画面間の経路）**
```cypher
MATCH path = (s1:Screen {viewName: $from_view})
  -[:TRANSITIONS_TO*1..5]->(s2:Screen {viewName: $to_view})
RETURN path
```

**表示仕様**
- `condition = null` の行は「（条件なし）」と表示
- JS ガード条件は `!(guard_cond)` 形式、AJAX コールバック条件と `&&` で結合

---

## モジュール設計

### `graph-explorer/neo4j_client.py`

```python
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str)
    def close(self)
    def get_all_screens(self) -> dict[str, str]
        # viewName -> title の辞書
    def get_screen_transitions(self, name: str, hops: int) -> list
        # TRANSITIONS_TO パスを返す
    def get_call_chain(self, name: str) -> list
        # フォーム経路 + JS 経路のパスを結合して返す
    def get_all_transitions(self) -> list
        # 全 TRANSITIONS_TO エッジを辞書リストで返す（遷移条件一覧用）
    def get_paths_between(self, from_view: str, to_view: str, max_hops: int) -> list
        # 2画面間の全 TRANSITIONS_TO パスを返す
```

### `graph-explorer/graph_builder.py`

```python
NODE_COLORS: dict[str, str]  # ノード種別 → 色コード

def _smooth_for_parallel(index: int, total: int) -> dict:
    # 同一ノード間の平行エッジを扇形に分散する vis.js smooth 設定を返す
    # total=1 は CW roundness=0.1、複数の場合は CW/CCW を対称に割り当て

def build_pyvis_graph(paths: list, show_edge_labels: bool = True, show_self_loops: bool = True) -> str:
    # 2 パス構成:
    #   第1パス: (from, to) ペアごとのユニークエッジ数を集計
    #   第2パス: ノード・エッジ追加（平行エッジには個別の smooth 設定を付与）
    # ノードの重複を排除（element_id をキーに使用）
    # ノード tooltip にプロパティ情報を表示
```

### `graph-explorer/app.py`

```python
# @st.cache_resource: Neo4jClient をセッション間でキャッシュ
# サイドバー: ページ選択（画面遷移グラフ / フル呼び出し連鎖）
# 画面名ドロップダウン: get_all_screens() の結果を表示
# グラフ埋め込み: st.components.v1.html(html, height=600, scrolling=True)
```

---

## ファイル構成

```
graph-explorer/
├── docs/
│   └── design.md        # 本設計書
├── app.py               # Streamlit エントリポイント
├── neo4j_client.py      # Neo4j クエリ
└── graph_builder.py     # pyvis グラフ構築
```

---

## 依存ライブラリ

`pyproject.toml` に追加：

```toml
"streamlit>=1.35",
"pyvis>=0.3",
```

既存（変更なし）：
- `neo4j>=5.0` — DB 接続
- `pyyaml>=6.0` — config.yaml 読み込み
