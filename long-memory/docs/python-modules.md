# Python モジュール概要

各スクリプトの役割・入出力・処理の流れをまとめる。

---

## hooks/memory_save.py

**役割:** SessionEnd / PreCompact フック。会話トランスクリプトから記憶を抽出して Neo4j に保存する。

**入力:** stdin から Claude Code が渡す JSON（`cwd`, `session_id`, `transcript_path` を含む）

**処理の流れ:**

1. `transcript_path` からトランスクリプトテキストを読み込む
2. `extractor.py` で LLM 呼び出し → 事実・決定・観察を `[{type, content}]` リストとして抽出
3. `ollama_client.py` で各 content の Embedding を生成
4. `entity_extractor.py` でエンティティ（固有名詞・技術名・概念）を抽出
5. fugashi（MeCab）で `content` を形態素解析し `content_tokens`（スペース区切り）を生成
6. `neo4j_client.py` で Neo4j に書き込み:
   - Session ノードを MERGE（session_id で統合）
   - Project ノードを MERGE（cwd で統合）、Session に IN_PROJECT エッジを作成
   - Memory ノードを INSERT（重複は定期整理スキルで別途管理）、Session に BELONGS_TO エッジを作成
   - Entity ノードを MERGE（name 正規化で統合）
   - MENTIONS エッジを作成
   - 同一 Memory 内の Entity 間に CO_OCCURS_WITH エッジを作成（count 加算）

---

## hooks/memory_inject.py

**役割:** SessionStart / PostCompact フック。現在の会話コンテキストに関連する過去の記憶を検索し、システムプロンプトに注入する。

**入力:** stdin から Claude Code が渡す JSON（`cwd`, `messages` を含む）

**処理の流れ:**

1. フックイベントに応じてクエリを生成
   - `SessionStart`: 初回メッセージをそのままクエリとして使用（文脈理解なし）
   - `PostCompact`: 圧縮後の直近メッセージを結合してクエリを生成
2. `ollama_client.py` でクエリ Embedding を生成
3. `neo4j_client.py` でグラフ拡張検索を実行（[search-strategy.md](search-strategy.md) §7 の Cypher）
   - プロジェクトフィルタ: `cwd` で Project ノードを特定
4. `scorer.py` でスコアリング（ベクトル類似度 + グラフ近接度 + 時間減衰 + 重要度）
5. 上位 10 件を以下フォーマットで stdout に出力（Claude Code がシステムプロンプトに自動注入）

**出力フォーマット:**

```
## 関連する過去の記憶

- [2026-05-10] Neo4j のベクトルインデックスは cosine 類似度を使用した
- [2026-05-12] qwen3-embedding:0.6b の Embedding 次元数は 1024
```

---

## hooks/memory_search.py

**役割:** 能動検索スキルから呼び出される検索エンドポイント。クエリ文字列を受け取り、ハイブリッド検索（ベクトル + 全文 + グラフ拡張）を実行して結果を stdout に出力する。

**入力:** stdin から JSON（`query`, `cwd` を含む）

**処理の流れ:**

1. `query` と `cwd` を読み込む
2. `ollama_client.py` でクエリ Embedding を生成
3. fugashi（MeCab）でクエリを形態素解析してトークンを生成
4. `neo4j_client.py` でハイブリッド検索を実行（ベクトル + 全文 + グラフ拡張）
   - プロジェクトフィルタ: `cwd` で Project ノードを特定
5. `scorer.py` でスコアリング
6. 結果を stdout に出力（`memory_inject.py` と同形式）

**出力フォーマット:** `memory_inject.py` と同じ（`## 関連する過去の記憶` 形式）

---

## lib/neo4j_client.py

**役割:** Neo4j への接続管理および全 CRUD・検索操作のラッパー。

**主な機能:**

- bolt URI / 認証情報（`config.json` から読み込み）でドライバーを初期化
- Memory ノードの INSERT（重複は定期整理スキルで別途管理）
- Entity ノードの MERGE（`name` 正規化済みの値で統合）
- MENTIONS / BELONGS_TO / IN_PROJECT / CO_OCCURS_WITH エッジの作成・count 加算
- ベクトル検索: `db.index.vector.queryNodes('memory_embedding_index', K, embedding)`
- 全文検索: `db.index.fulltext.queryNodes('memory_token_index', queryTokens)`
- グラフ拡張検索: MENTIONS → CO_OCCURS_WITH → MENTIONS 逆引きの Cypher を実行

---

## lib/ollama_client.py

**役割:** Ollama の `/api/embed` エンドポイントを叩いてテキストをベクトルに変換する。

**入力:** テキスト文字列またはリスト（バッチ対応）

**処理:**

1. `config.json` から `base_url` / `embed_model` / `timeout` を読み込み
2. `POST /api/embed` に `{"model": "qwen3-embedding:0.6b", "input": [...]}` を送信
3. レスポンスから `embeddings` を取り出して返す

**出力:** 1024 次元の `float` リスト（バッチ時はリストのリスト）

---

## lib/extractor.py

**役割:** トランスクリプトテキストを LLM に渡し、保存すべき事実・決定・観察を抽出する。

**入力:** 会話トランスクリプト文字列

**処理:**

1. 抽出プロンプトを組み立てて LLM を呼び出す
   - 抽出レベル: Lv3（事実・決定・発見・観察）を基本とし、Lv4（検討事項・却下した選択肢）は `tentative` として保存
   - 「迷ったら書く」方針: プロンプトに「重要かどうか判断に迷う場合は含めてください」と明記
   - type 分類基準: 「最終的な採用・却下が確定したものだけ decision とする」と明示
   - 出力形式: JSON Schema で強制（Structured Output）
2. LLM のレスポンスをパースして `[{type, content}]` リストに変換
   - `knowledge`: 客観的事実・観察結果（例:「X は Y である」）
   - `decision`: 採用・却下が確定した意思決定（上位の問いに従属していないもの）
   - `tentative`: 未確定の検討事項・仮説・却下した選択肢

**出力:** `[{"type": "knowledge"|"decision"|"tentative", "content": "..."}]`

---

## lib/entity_extractor.py

**役割:** Memory の `content` 文字列から固有名詞・技術名・概念を抽出し、Neo4j の Entity ノード作成に使用する。

**入力:** `content` 文字列

**処理:**

1. LLM または NER モデルでエンティティ候補を抽出
2. name 正規化（小文字化・表記揺れ統一）を適用
3. 重複を排除して返す

**出力:** 正規化済みエンティティ名のリスト（例: `["neo4j", "bge-m3", "embedding"]`）

---

## lib/scorer.py

**役割:** 検索結果の Memory リストに対してスコアを計算し、注入する上位件数に絞り込む。

**入力:** Memory リスト（各要素にベクトルスコア・グラフ距離・作成日時・重要度スコアを付与済み）

**処理:**

スコア計算式（重みは `config.json` から読み込み）:

```
finalScore = α × ベクトル類似度
           + β × グラフ近接度（最短パス長の逆数）
           + γ × 時間スコア（type 別指数減衰）
           + δ × 重要度（Memory.score）

α=0.5, β=0.2, γ=0.2, δ=0.1（初期値）
```

type 別時間スコア:

| type | 減衰方式 |
|---|---|
| `decision` | 減衰なし（`status` で競合管理） |
| `knowledge` | 指数減衰（半減期 90 日） |
| `tentative` | 指数減衰（半減期 30 日） |

**出力:** スコア降順にソートされた Memory リスト

---

## scripts/memory_cleanup.py

**役割:** Memory の重複・競合を検出し、Haiku で「類似 / 競合 / 無関係」を判定して Neo4j を整理する。手動スキルから呼び出す。

**使用方法（2ステップ）:**

```
# Step1: LLM 判定 → 計画を JSON に保存して表示（Neo4j への書き込みなし）
uv run python long-memory/scripts/memory_cleanup.py \
  --project <cwd> --plan-output cleanup_plan.json [--cosine-threshold 0.7]

# Step2: JSON を確認後、同一結果で適用（LLM 呼び出しなし）
uv run python long-memory/scripts/memory_cleanup.py --apply cleanup_plan.json
```

**オプション:**

| オプション | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `--project <path>` | Step1 のみ ○ | — | 整理対象のプロジェクトルートパス（Project.path に対応） |
| `--plan-output <file>` | Step1 のみ ○ | — | LLM 判定結果を書き出す JSON ファイルパス |
| `--apply <file>` | Step2 のみ ○ | — | 保存済み計画 JSON を適用する |
| `--cosine-threshold <float>` | — | 0.7 | 類似ペア候補の Embedding cosine 閾値（Step1 のみ有効） |

**処理の流れ（Step1: --project + --plan-output）:**

1. 対象 Project の全 Memory を取得（`status = 'active'`）
2. Embedding cosine ≥ threshold の Memory ペアを列挙（`neo4j_client.py` を利用）
3. 各ペアの共通 Entity 数を計算（直接 MENTIONS している Entity に加え、CO_OCCURS_WITH で接続された隣接 Entity も含む）し、共通 Entity が多い順にソート
4. Haiku に候補ペアを渡して「類似 / 競合 / 無関係」を分類
5. 判定結果を JSON ファイルに保存し、内容を stdout に表示して終了

**処理の流れ（Step2: --apply）:**

1. JSON ファイルを読み込む
2. LLM を呼び出さず、JSON に記録された判定結果をそのまま適用:
   - 類似 → 情報が豊富な方の `content` に統合し、もう一方を物理削除
   - 競合 → 最新を `status='active'` に残し、古いものを `status='inactive'` に更新
   - 無関係 → スキップ
3. 変更件数を stdout にレポート出力
4. JSON ファイルを削除（適用済みの計画が残留して再適用される事故を防ぐ）

**Step1 の出力例:**

```
[類似] 統合候補:
  (削除) 「Neo4j のベクトルインデックスは cosine 類似度を使用した」 [2026-05-10]
  (残す) 「Neo4j のベクトルインデックスは cosine 類似度を使用する（デフォルト設定）」 [2026-05-15]

[競合] superseded 候補:
  (inactive)   「埋め込みモデルは bge-m3 を採用した」 [2026-05-01]
  (active)     「埋め込みモデルは qwen3-embedding:0.6b を採用した」 [2026-05-31]

スキップ: 12 件
計画を cleanup_plan.json に保存しました。内容を確認後、--apply cleanup_plan.json で適用してください。
```

---

## scripts/analyze_memory.py

**役割:** Neo4j 上の記憶統計を集計・表示するデバッグ / チューニング用スクリプト。

**使用方法:** `uv run python long-memory/scripts/analyze_memory.py`

**出力内容:**

- Memory 総数・type 別件数（knowledge / decision / tentative）
- Entity 総数・上位出現エンティティ一覧
- 最近保存された Memory 一覧（直近 20 件）
- CO_OCCURS_WITH の強いエンティティペア一覧
- 未使用（アクセス回数 0）の Memory 一覧
