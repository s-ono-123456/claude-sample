# Claude Code ツールセット

Claude Code と周辺開発ツールのコレクションです。

## ツール一覧

| ツール | 概要 | ドキュメント |
|--------|------|-------------|
| [mattermost-gate](mattermost-gate/) | Claude Code の `PermissionRequest` フックとして動作するゲートウェイ。ツール使用の承認を Mattermost 経由でオペレーターが制御する | [README](mattermost-gate/README.md) |
| [ast-analyzer](ast-analyzer/) | Spring MVC / MyBatis / JSP / JS アプリを AST 解析し、画面〜DB テーブルの呼び出し連鎖と画面遷移を Neo4j グラフ DB に格納する | [README](ast-analyzer/README.md) |
| [graph-explorer](graph-explorer/) | ast-analyzer が構築した Neo4j グラフを Streamlit + pyvis でブラウザから検索・可視化する | [README](graph-explorer/README.md) |

## 共通前提条件

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)（パッケージ管理）

## 共通セットアップ

```powershell
uv sync
```

各ツール固有の設定・起動手順は、上記の各 README を参照してください。
