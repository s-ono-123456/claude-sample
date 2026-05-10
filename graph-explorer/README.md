# graph-explorer

## なぜ作ったか

ast-analyzer が構築した Neo4j グラフを直接 Cypher クエリで探索するのは、開発者全員にとって敷居が高いです。

このツールは Streamlit + pyvis によるブラウザ UI を提供し、
**Cypher を書かずにノード検索・グラフ可視化**ができるようにします。
影響範囲の確認・画面遷移の把握を、チームの誰でも手軽に行えることが目的です。

## 主な機能

- **ノード検索** — ラベル・プロパティ条件でノードをフィルタリング
- **グラフ可視化** — pyvis によるインタラクティブな関係グラフ表示（ズーム・ドラッグ対応）
- **自己ループ・条件ラベル表示** — 条件分岐による同一画面遷移や `TRANSITIONS_TO` の条件ラベルを描画

## 前提条件

- Python 3.12 以上 / [uv](https://docs.astral.sh/uv/)
- Neo4j 5.x（ast-analyzer でグラフ構築済みのもの）
- `ast-analyzer/config.yaml`（Neo4j 接続情報を共用）

## クイックスタート

```powershell
uv run streamlit run graph-explorer/app.py
```

ブラウザで http://localhost:8501 を開くとグラフ検索画面が表示されます。

## ディレクトリ構成

```
graph-explorer/
├── app.py                  # Streamlit アプリ（エントリーポイント）
├── graph_builder.py        # pyvis グラフ構築ロジック
├── neo4j_client_graph.py   # Neo4j クエリクライアント（graph-explorer 専用）
└── docs/
    └── design.md           # 設計書
```

## 設計書

| ドキュメント | 内容 |
|---|---|
| [設計書](docs/design.md) | アーキテクチャ・グラフスキーマ・画面仕様 |

## トラブルシューティング

**起動時に Neo4j 接続エラーが出る**
`ast-analyzer/config.yaml` の Neo4j 接続情報を確認し、Neo4j が起動しているか確認してください。

**グラフが空で何も表示されない**
ast-analyzer でグラフを構築してから起動してください。

```powershell
.venv\Scripts\python.exe ast-analyzer\main.py --config ast-analyzer\config.yaml
```
