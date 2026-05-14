# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Rules

ファイルを修正する可能性が高いと判断した時点で、早めに以下の手順を踏むこと：

> **Plan モードに入るタイミング**: 設計方針の確認・機能追加・バグ修正など、実装に向かう可能性が少しでもある議論が始まったら、ファイル編集の前に Plan モードに入ること。

1. **Plan モードで実行計画を立てる** — `EnterPlanMode` を使い、変更内容・対象ファイル・手順を明示する
   - 計画にはテスト方法（実行コマンド・確認ポイント）を必ず含めること
2. **ユーザの承認を得る** — 計画をユーザに提示し、「進めてよいか」確認してから実装に移る
3. **実装後にテストを実施する** — 計画で定めたテスト方法に従い、実際に動作確認を行うこと
4. **設計書を更新する** — ソースコードを修正した場合、必ず関連する設計書を更新すること
   - 設計書は各階層の `docs/` フォルダに配置されている

## Project Overview

このリポジトリは3つのサブプロジェクトで構成される：

| プロジェクト | 役割 |
|---|---|
| `ast-analyzer/` | Java/JSP/JS の静的解析 → Neo4j グラフ構築 |
| `mattermost-gate/` | Claude Code フック：ツール操作を Mattermost 経由で承認制御 |
| `graph-explorer/` | Neo4j グラフを Streamlit で可視化する Web UI |

## Setup

```powershell
uv sync
# ast-analyzer: config.yaml.example をコピーして Neo4j 接続情報を設定
Copy-Item ast-analyzer\config.yaml.example ast-analyzer\config.yaml
# mattermost-gate: config.json.sample をコピーして Mattermost 設定を記入
Copy-Item mattermost-gate\config.json.sample mattermost-gate\config.json
```

## Commands

### ast-analyzer

```powershell
# 全フェーズ実行（Phase 1: Java/MyBatis → Phase 2: JSP → Phase 3: JS）
uv run python ast-analyzer/main.py --config ast-analyzer/config.yaml

# Neo4j に書き込まずに解析結果を確認
uv run python ast-analyzer/main.py --config ast-analyzer/config.yaml --dry-run

# 特定フェーズのみ実行
uv run python ast-analyzer/main.py --config ast-analyzer/config.yaml --phase 2

# グラフをリセットして再構築
uv run python ast-analyzer/main.py --config ast-analyzer/config.yaml --reset

# Cypher クエリを実行
uv run python ast-analyzer/run_queries.py
```

### graph-explorer

```powershell
# Streamlit UI を起動（localhost:8501）
uv run streamlit run graph-explorer/app.py
```

### mattermost-gate（手動テスト）

```powershell
# stdin に PermissionRequest JSON を渡してフックをテスト
'{"tool_name":"Bash","tool_input":{"command":"ls","description":"List files"},"cwd":"C:\\claude","session_id":"abc123"}' | uv run python mattermost-gate/permissionrequest.py
```

> **注意（PowerShell BOM 問題）**: PowerShell のパイプ経由で JSON を渡すと UTF-16 BOM が付加され、JSON パースに失敗する場合がある。その場合は Python スクリプト側でテスト用に直接 stdin を読み込む方式に切り替えること。

## Architecture

### ast-analyzer — 3フェーズ解析パイプライン

`main.py` が3フェーズを順番に実行する。各フェーズは独立して `--phase N` で単独実行可能。

```
Phase 1: Java/MyBatis 解析
  parsers/ → ControllerInfo / ServiceInfo / DaoInfo / SqlStatement
  → Neo4j: ControllerMethod, ServiceMethod, DaoMethod, SqlStatement, Table ノード＋エッジ

Phase 2: JSP 解析
  parsers/jsp_parser.py → ScreenInfo（ボタン・リダイレクト情報を含む）
  linker/url_linker.py → ボタンの form action を Controller にリンク
  linker/view_linker.py → Controller の return 値を JSP ファイルにリンク
  → Neo4j: Screen, Button ノード＋エッジ

Phase 3: JavaScript 解析
  parsers/js_parser.py → JsFunction, AjaxCall（regex ベース）
  linker/js_linker.py → ボタン→JS関数・AJAX→Controller をリンク
  → Neo4j: JsFunction, AjaxCall ノード＋エッジ
```

**中間表現（IR）**: `model/ir.py` のデータクラス（`ScreenInfo`, `ButtonInfo`, `ControllerInfo` 等）がパーサーとグラフ層の橋渡しをする。パーサーは IR を返し、グラフ層（`graph/neo4j_client.py`）が Neo4j に書き込む。

**テスト用サンプルアプリ**: `ast-analyzer/sample-app/` に Spring MVC + MyBatis の完全なアプリ（3コントローラ・6サービス・3DAO・8JSP・3JSファイル）がある。

### mattermost-gate — フック設計

| フックイベント | スクリプト | 役割 |
|---|---|---|
| `PermissionRequest` | `permissionrequest.py` | Mattermost に承認リクエストを投稿し、絵文字リアクションで allow/deny を判定 |
| `PostToolUse` | `posttooluse.py` | ツール実行完了後、承認済み投稿に `terminal_emoji` を付与 |
| `Stop` | `stop.py` | セッション終了時、未処理の残存投稿に `terminal_emoji` を付与 |
| `PermissionDenied` | `stop.py` | 権限拒否時も同上 |

**非自明な設計判断:**

**`registry.py`（`mattermost-gate/tmp/` 以下のファイルキャッシュ）**
- `PermissionRequest` と `PostToolUse` は**別プロセス**で起動される
- `permissionrequest.py` は承認後に `tmp/{session_id}/{uuid}.json` へ `(tool_name, post_id)` を書き込む
- `posttooluse.py` はこのファイルを参照して対応投稿を特定し、絵文字を付与してから削除する

**deny 時の否決理由取得**
- ❌ リアクション後、`deny_reply_timeout_seconds`（デフォルト 60s）の間スレッド返信を待つ
- 返信があればその内容を Claude Code の deny メッセージとして返す

**LLM プレチェック（`lib/precheck.py`）**
- `policy.md` が存在する場合、Claude Haiku でツール内容を事前審査する
- 結果（`safe` / `risky` / `dangerous`）を Mattermost 投稿に絵文字で添付する

**`terminal_emoji`（デフォルト `computer`）**
- 承認済み投稿が「実行完了」したことをオペレーターに視覚的に伝えるためのマーク

**`audit.py`（`mattermost-gate/log/audit.jsonl`）**
- 全リクエストと決定を JSONL 形式で記録
- `analyze_audit.py` でログを分析できる

### graph-explorer — Streamlit UI

- Neo4j の接続情報は `ast-analyzer/config.yaml` を共有して読み込む（専用設定ファイルなし）
- `@st.cache_resource` で Neo4j クライアントをキャッシュする
- `graph_builder.py` の `build_pyvis_graph()` が pyvis の `Network` を構築し、HTML として Streamlit に埋め込む
