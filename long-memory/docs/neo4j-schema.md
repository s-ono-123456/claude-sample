# Long-Memory Neo4j スキーマ設計

## 1. ノード種別

### Memory ノード

会話から抽出した「記憶の最小単位」。Q&A チャンクではなく、事実・決定・観察を自然文で表現した 1 項目が 1 ノードに対応する。

| プロパティ | 型 | 取りうる値 | 説明 |
|---|---|---|---|
| id | string | UUID v4 | 一意識別子 |
| type | string | `"knowledge"` / `"decision"` / `"tentative"` | 記憶の分類（後述） |
| content | string | 自然文（1〜3 文程度） | 記憶の本文。extractor.py が会話から抽出した事実・決定・観察 |
| content_tokens | string | スペース区切りのトークン列 | `content` を fugashi（MeCab）で形態素解析し、名詞・動詞・形容詞・副詞を抽出してスペース区切りにしたもの。Fulltext インデックス対象 |
| embedding | float[] | 1024 次元の浮動小数点配列 | `content` のテキストを qwen3-embedding:0.6b でベクトル化したもの。ベクトルインデックス対象 |
| session_id | string | UUID（Session.id と対応） | 記憶が生成されたセッション。BELONGS_TO エッジと対応 |
| status | string | `"active"` / `"inactive"` | 初期値は `"active"`（全 type 共通）。`inactive` はユーザーが明示的に無効化した状態。`decision` は後の意思決定で取り消された場合も `inactive` になる |
| created_at | datetime | ISO 8601 datetime | 記憶の生成日時 |
| score | float | 0.0 〜 1.0（初期値 0.5） | アクセス頻度・フィードバックによる重要度。スコアリング式の係数として使用 |

プロジェクトによるフィルタは `Memory -[:BELONGS_TO]-> Session -[:IN_PROJECT]-> Project` のエッジ走査で行う。グラフ DB は index-free adjacency によりホップごとのコストが O(1) のため、プロパティでの非正規化は不要。

#### type の分類基準

| type | 意味 | 時間減衰 | 分類基準 |
|---|---|---|---|
| `knowledge` | 事実・観察・発見 | あり（半減期 90 日） | 客観的事実、作業中の発見、観察結果。「X は Y である」「この API はドキュメントと挙動が違う」 |
| `decision` | 採用・却下が確定した意思決定 | なし（status で管理） | 最終的な採用・却下が確定したもの。上位の問いに従属していない |
| `tentative` | 未確定の検討事項・仮説 | あり（半減期 30 日） | A か B か未決の状態での中間判断、検討中の仮説。上位の問いに従属している間は tentative |

**`decision` と `tentative` の判断基準：** 「この議論はまだ上位の問いに従属しているか？」で判断する。A・B どちらかを選ぶ問いが未解決なら `tentative`。最終的に選んだ時点で新しい `decision` ノードとして保存する（`tentative` ノードの更新ではなく新規作成）。

#### status の有効範囲

| type | status | 説明 |
|---|---|---|
| 全 type | `"active"` | 有効な記憶（初期値） |
| 全 type | `"inactive"` | ユーザーが明示的に無効化した記憶 |
| `decision` | `"inactive"` | 後の意思決定で取り消された場合も `inactive` |

検索時は `WHERE m.status = 'active'` でフィルタして、無効化済みの記憶を除外する。

---

### Entity ノード

Memory の content に登場する固有名詞・技術名・概念。グラフ拡張検索の中継点として機能する。

> **マルチプロジェクト動作:** Entity ノードはプロジェクト横断で共有（グローバル）。プロジェクトフィルタは Entity ではなく Memory レベルで適用する（`Memory -[:BELONGS_TO]-> Session -[:IN_PROJECT]-> Project {path: $project}`）。Entity を経由してグラフ拡張しても、最終的に返す Memory は必ずプロジェクトフィルタを通過した結果のみとなる（search-strategy.md §7.2 の Cypher 参照）。

| プロパティ | 型 | 取りうる値 | 説明 |
|---|---|---|---|
| id | string | UUID v4 | 一意識別子 |
| name | string | 正規化済みエンティティ名 | 大文字小文字・表記揺れを統一した表記（例: `neo4j`、`bge-m3`）。MERGE の照合キー |
| embedding | float[] | 1024 次元の浮動小数点配列 | `name` のテキストを qwen3-embedding:0.6b でベクトル化したもの。Entity レベルのベクトル検索に使用 |
| mention_count | int | 0 以上の整数 | 全 Memory を通じた累積言及回数。保存のたびに加算 |
| last_seen | datetime | ISO 8601 datetime | 最後にこのエンティティが言及された日時 |

---

### Session ノード

Claude Code の 1 会話セッションに対応するコンテナノード。同セッション内の Memory は `BELONGS_TO` エッジを辿ることで一括取得できる。

| プロパティ | 型 | 取りうる値 | 説明 |
|---|---|---|---|
| id | string | UUID（Claude Code が付与する session_id） | 一意識別子。フックの stdin JSON に含まれる値をそのまま使用 |
| started_at | datetime | ISO 8601 datetime | セッション開始時刻 |

---

### Project ノード

プロジェクトルートパスを正規化した識別子。複数セッションをプロジェクト単位でグループ化する。

| プロパティ | 型 | 取りうる値 | 説明 |
|---|---|---|---|
| path | string | 絶対パス（主キー相当） | プロジェクトルートの絶対パス（例: `C:/claude`）。MERGE の照合キー |
| name | string | 任意の文字列 | 人が読みやすいプロジェクト名（例: `claude`） |

---

## 2. リレーションシップ

### MENTIONS

```
(Memory)-[:MENTIONS]->(Entity)
```

プロパティなし。Memory の content に登場するエンティティへのエッジ。グラフ拡張検索における主なトラバーサル経路。逆引き（`<-[:MENTIONS]-`）で「この Entity を言及している Memory 一覧」を取得できる。

---

### BELONGS_TO

```
(Memory)-[:BELONGS_TO]->(Session)
```

プロパティなし。Memory の出自セッションを記録する。同セッション内の全 Memory を一括取得する際に使用（UC3: 評価まとまりの取得）。

---

### IN_PROJECT

```
(Session)-[:IN_PROJECT]->(Project)
```

プロパティなし。Session とプロジェクトの紐付け。

`Memory -[:BELONGS_TO]-> Session -[:IN_PROJECT]-> Project` の 2 ホップで Memory をプロジェクト単位に絞り込める。

---

### CO_OCCURS_WITH

```
(Entity)-[:CO_OCCURS_WITH {count: int, strength: float}]->(Entity)
```

| プロパティ | 型 | 取りうる値 | 説明 |
|---|---|---|---|
| count | int | 1 以上の整数 | 同一 Memory 内で共起した累積回数。共起のたびに加算 |
| strength | float | 0.0 〜 1.0 | count を正規化した強度（`count / max_count` 相当）。スコアリングで使用 |

同一 Memory の content に共起したエンティティ同士を結ぶ。グラフ拡張検索で「関連エンティティ」を芋づる式に辿る際のエッジ。深さ 2 ホップまで展開することで、直接類似しないが関連する Memory を発見できる。

---

## 3. インデックス定義

### 3-1. ベクトルインデックス定義

意味的類似検索に使用する。クエリテキストを Embedding してから近傍 K 件の Memory / Entity を取得する。

> **バージョン要件:** `CREATE VECTOR INDEX` 構文は Neo4j 5.11 以降で使用可能。docker-compose.yml は `neo4j:5.20-community` を使用しているため問題なし。

```cypher
-- Memory ノードのベクトルインデックス
CREATE VECTOR INDEX memory_embedding_index
FOR (m:Memory) ON (m.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

-- Entity ノードのベクトルインデックス
CREATE VECTOR INDEX entity_embedding_index
FOR (e:Entity) ON (e.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};
```

### 3-2. 全文インデックス定義

Apache Lucene ベースの転置インデックス。ベクトル検索は固有名詞・ファイルパス・コマンド名などの文字列一致が苦手なため、補完的に使用する。

**仕組み：**

保存時と検索時の両方で fugashi（MeCab）による形態素解析を通すことで、日英問わず一貫したトークン分割を実現する。

```
保存時: content「Neo4jにベクトルインデックスを作成した」
  → fugashi で形態素解析（名詞・動詞・形容詞・副詞を抽出）
  → content_tokens「Neo4j ベクトルインデックス 作成」
  → standard アナライザー（空白区切り）でインデックス化

検索時: クエリ「Neo4jでできる全文検索の機能を知りたい」
  → 同じ fugashi で形態素解析
  → 「Neo4j 全文検索 機能 知る」
  → Fulltext クエリとして投入 → content_tokens とトークンが一致してヒット
```

**Cypher クエリ例：**

```cypher
-- 'Neo4j' または '全文検索' を含む Memory を取得（OR がデフォルト）
CALL db.index.fulltext.queryNodes('memory_token_index', 'Neo4j 全文検索')
YIELD node AS m, score
WHERE m.status = 'active'
RETURN m.content, score
ORDER BY score DESC
LIMIT 10

-- 両方のキーワードを含む Memory に絞る（AND 検索）
CALL db.index.fulltext.queryNodes('memory_token_index', 'Neo4j AND 全文検索')
YIELD node AS m, score
...
```

```cypher
-- content_tokens に対して standard アナライザーで全文インデックスを作成
-- 保存時に fugashi でスペース区切り済みのため standard アナライザーで十分
CREATE FULLTEXT INDEX memory_token_index
FOR (m:Memory) ON EACH [m.content_tokens];
```

---

## 4. グラフ構造例

```
[Project: path="C:/claude"]
     ↑
     IN_PROJECT
     │
[Session: id="abc-123"]
     ↑
     BELONGS_TO
     │
[Memory: "Neo4j にベクトルインデックスを作成した" (knowledge)]
     │
     ├──MENTIONS──→ [Entity: "Neo4j"]
     │                   │
     │                   └──CO_OCCURS_WITH──→ [Entity: "ベクトルインデックス"]
     │
     └──MENTIONS──→ [Entity: "ベクトルインデックス"]
                         │
                         └──CO_OCCURS_WITH──→ [Entity: "Embedding"]
                                                   │
                                             MENTIONS 逆引き
                                                   ↓
                                        [Memory: "Ollama で qwen3-embedding:0.6b を使った"]
                                        ← ベクトル類似度が低くても関連する記憶として取得できる
```

---

## 5. UC 別：スキーマ設計の対応関係

| UC | 問題 | スキーマ上の解決 |
|---|---|---|
| UC1 知識参照 | Embedding の対象が会話テキスト（事実ではない） | `content` を事実・観察・決定の自然文に限定。extractor.py で抽出してから保存 |
| UC1 知識参照 | チャンク境界と意味的まとまりの不一致 | チャンク化を廃止。1 項目 = 1 Memory ノード |
| UC2 意思決定の想起 | `decision` の自動分類基準が未定義 | `type` を 3 分類に整理し、抽出プロンプトに分類基準を明示 |
| UC2 意思決定の想起 | 意思決定の構造（選択肢・根拠・結論）が分散 | 選択肢・根拠・結論を 1 つの `content` に自然文でまとめる |
| UC2 意思決定の想起 | 時間減衰で永続すべき決定が薄れる | `decision` は時間減衰なし。`status` で競合管理 |
| UC3 評価結果の活用 | 同セッション内の評価をまとめて取得できない | `BELONGS_TO` エッジで Session から同セッションの全 Memory を一括取得 |
| UC3 評価結果の活用 | セッションをまたぐ評価の統合 | Entity ノードから `MENTIONS` 逆引きで複数セッションの Memory を横断取得 |
| UC4 暗黙の技術的文脈 | 検索トリガーがファイル・関数を考慮しない | 能動検索スキルでファイルパス・関数名を明示したクエリを実行（フックの自動 inject は補助的な下地。精度の高い技術的文脈の取得はスキルが担う） |
