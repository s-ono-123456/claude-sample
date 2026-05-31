# Long-Memory システム 設計方針

| トピック | ドキュメント |
|---|---|
| システム概要・アーキテクチャ | [overview.md](overview.md) |
| Neo4j スキーマ設計 | [neo4j-schema.md](neo4j-schema.md) |
| Embedding モデル選定 | [embedding-model.md](embedding-model.md) |
| データライフサイクル戦略 | [search-strategy.md](search-strategy.md) |
| Docker Compose 設計 | [docker-compose.md](docker-compose.md) |
| Python モジュール概要 | [python-modules.md](python-modules.md) |

---

## 1. Claude Code フック設計

### settings.json へのフック登録

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python C:/claude/long-memory/hooks/memory_save.py"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python C:/claude/long-memory/hooks/memory_save.py"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python C:/claude/long-memory/hooks/memory_inject.py"
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "uv run python C:/claude/long-memory/hooks/memory_inject.py"
          }
        ]
      }
    ]
  }
}
```

各スクリプトの処理概要は [python-modules.md](python-modules.md) を参照。

---

## 2. ディレクトリ構成（予定）

```
long-memory/
  docs/
    design.md              ← 本ドキュメント
    overview.md            ← システム概要・アーキテクチャ
    neo4j-schema.md        ← Neo4j スキーマ設計
    embedding-model.md     ← Embedding モデル選定
    search-strategy.md     ← 検索戦略
    docker-compose.md      ← Docker Compose 設計
    python-modules.md      ← Python モジュール概要
  docker/
    docker-compose.yml
    neo4j/conf/
  hooks/
    memory_save.py         # SessionEnd / PreCompact フック: 記憶保存
    memory_inject.py       # SessionStart / PostCompact フック: 記憶検索・注入
    memory_search.py       # 能動検索スキル用: クエリを受け取りハイブリッド検索して結果を返す
  lib/
    neo4j_client.py        # Neo4j 接続・CRUD・検索
    ollama_client.py       # Ollama Embedding API クライアント
    extractor.py           # トランスクリプト → 事実・決定・観察の抽出
    entity_extractor.py    # エンティティ抽出
    scorer.py              # スコアリング（ベクトル + グラフ + 時間）
  scripts/
    init_schema.cypher     # インデックス・制約の初期化
    analyze_memory.py      # 記憶統計・デバッグ用
    memory_cleanup.py      # 記憶整理スキル: 重複・競合 Memory を Haiku で分類して統合・無効化
  config.json.sample       # Neo4j 接続情報・Ollama URL テンプレート
```

---

## 3. 設定ファイル仕様

### config.json

```json
{
  "neo4j": {
    "uri": "bolt://localhost:7687",
    "username": "neo4j",
    "password": "longmemory"
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "embed_model": "qwen3-embedding:0.6b",
    "embed_timeout_seconds": 30
  },
  "memory": {
    "top_k_vector": 20,
    "top_k_graph_expand": 30,
    "top_k_inject": 10,
    "graph_depth": 2,
    "decay_half_life_days": {
      "knowledge": 90,
      "tentative": 30,
      "decision": null
    },
    "score_weights": {
      "vector": 0.5,
      "graph": 0.2,
      "time": 0.2,
      "importance": 0.1
    }
  }
}
```

> **注意:** `score_weights` の4値（vector + graph + time + importance）の合計は必ず **1.0** にすること。実装側での自動正規化は行わない。

---

## 4. 実装ロードマップ

| フェーズ | 内容 | 成果物 |
|---|---|---|
| **P0: 基盤構築** | Docker Compose 起動・Neo4j インデックス初期化・Ollama qwen3-embedding:0.6b セットアップ | `docker/`, `scripts/init_schema.cypher` |
| **P1: コアライブラリ** | `ollama_client.py`・`neo4j_client.py` 実装とユニットテスト | `lib/` |
| **P2: 保存フック** | トランスクリプト抽出・エンティティ抽出・Neo4j 書き込み | `hooks/memory_save.py` |
| **P3: 検索フック** | グラフ拡張検索・スコアリング・プロンプト注入 | `hooks/memory_inject.py` |
| **P4: チューニング** | スコア重み調整・エンティティ抽出精度改善 | config 更新 |
| **P5: 能動検索スキル** | `hooks/memory_search.py` 実装・CLAUDE.md 追記・スキル定義ファイル作成（`~/.claude/skills/long-memory.md`） | `hooks/memory_search.py`、スキル定義ファイル |

---

## 5. 技術選定の根拠まとめ

| 決定 | 選定内容 | 理由 |
|---|---|---|
| Embedding モデル | qwen3-embedding:0.6b | Ollama 公式サポート・日本語対応・32768 トークン長文対応・bge-m3 より MTEB 多言語スコア優位 |
| ベクトル DB | Neo4j 組み込み | グラフ構造と一元管理・追加 DB 不要 |
| グラフ拡張 | CO_OCCURS_WITH 2ホップ | 直接類似しない関連記憶の発見に必要十分な深さ |
| 時間減衰 | 指数減衰（knowledge: 90 日・tentative: 30 日・decision: なし） | 古い記憶を完全に捨てず、type 別に重要度に応じた減衰速度を設定 |
| フック種別 | SessionEnd + PreCompact | 保存は会話終了後（SessionEnd）・コンテキスト圧縮直前（PreCompact）が最適タイミング |
| 記憶保存方式 | LLM 抽出ベース | チャンク化ではなく事実・決定・観察を自然文で抽出してから保存 |
