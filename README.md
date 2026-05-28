# Claude Code ツールセット

Claude Code と周辺開発ツールのコレクションです。

## ツール一覧

| ツール | 概要 | ドキュメント |
|--------|------|-------------|
| [security-gate](security-gate/) | Claude Code の `PreToolUse` フックとして動作するルールベースの防御レイヤー。YAML 定義のルール（47 件）で危険なコマンドを即座にブロックする | [README](security-gate/README.md) |
| [mattermost-gate](mattermost-gate/) | Claude Code の `PermissionRequest` フックとして動作するゲートウェイ。ツール使用の承認を Mattermost 経由でオペレーターが制御する | [README](mattermost-gate/README.md) |
| [ast-analyzer](ast-analyzer/) | Spring MVC / MyBatis / JSP / JS アプリを AST 解析し、画面〜DB テーブルの呼び出し連鎖と画面遷移を Neo4j グラフ DB に格納する | [README](ast-analyzer/README.md) |
| [graph-explorer](graph-explorer/) | ast-analyzer が構築した Neo4j グラフを Streamlit + pyvis でブラウザから検索・可視化する | [README](graph-explorer/README.md) |

## Claude Code フック構成

security-gate と mattermost-gate は Claude Code のフックとして連携動作します。

```
Claude Code がツールを呼び出す
    │
    ▼  PreToolUse（全ツール・allowedTools 含む）
security-gate ── YAML ルールで即時判断
    │ block → ツール実行をキャンセル（Mattermost 通知なし）
    │ pass  ↓
    ▼  PermissionRequest（未承認ツールのみ）
mattermost-gate ── Mattermost で人間が承認・拒否
    │ allow ↓
    ▼
ツール実行
```

| | security-gate | mattermost-gate |
|---|---|---|
| フックイベント | `PreToolUse` | `PermissionRequest` |
| 判断方式 | ルールベース（自動・即時） | 人間が Mattermost で判断 |
| 役割 | 明らかに危険な操作をブロック | グレーゾーンを人間が承認 |

## 共通前提条件

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)（パッケージ管理）

## 共通セットアップ

```powershell
uv sync
```

各ツール固有の設定・起動手順は、上記の各 README を参照してください。
