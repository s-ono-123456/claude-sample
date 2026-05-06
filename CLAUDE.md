# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working Rules

ファイルを修正する前に、必ず以下の手順を踏むこと：

1. **Plan モードで実行計画を立てる** — `EnterPlanMode` を使い、変更内容・対象ファイル・手順を明示する
   - 計画にはテスト方法（実行コマンド・確認ポイント）を必ず含めること
2. **ユーザの承認を得る** — 計画をユーザに提示し、「進めてよいか」確認してから実装に移る
3. **実装後にテストを実施する** — 計画で定めたテスト方法に従い、実際に動作確認を行うこと

## Project Overview

**mattermost-gate** は Claude Code のフックとして動作し、ツール操作を Mattermost 経由でオペレーターが監視・制御できるようにするゲートウェイ。詳細は README.md を参照。

| フックイベント | スクリプト | 役割 |
|---|---|---|
| `PermissionRequest` | `permissionrequest.py` | Mattermost に承認リクエストを投稿し、絵文字リアクションで allow/deny を判定 |
| `PostToolUse` | `posttooluse.py` | ツール実行完了後、承認済み投稿に `terminal_emoji` を付与 |
| `Stop` | `stop.py` | セッション終了時、未処理の残存投稿に `terminal_emoji` を付与 |
| `PermissionDenied` | `stop.py` | 権限拒否時も同上 |

## Setup

```powershell
uv sync
Copy-Item mattermost-gate\config.json.sample mattermost-gate\config.json
# config.json を編集して mattermost_url / token / channel_id を設定
```

詳細なセットアップ手順・設定リファレンスは README.md を参照。

## Running the Hook Manually

```powershell
# stdin に PermissionRequest JSON を渡してテスト
'{"tool_name":"Bash","tool_input":{"command":"ls","description":"List files"},"cwd":"C:\\claude","session_id":"abc123"}' | .venv\Scripts\python.exe mattermost-gate\permissionrequest.py
```

## Architecture

### 非自明な設計判断

**`registry.py`（`mattermost-gate/tmp/` 以下のファイルキャッシュ）**
- `PermissionRequest` と `PostToolUse` は別プロセスで起動される
- `permissionrequest.py` は承認後に `tmp/{session_id}/{uuid}.json` へ `(tool_name, post_id)` を書き込む
- `posttooluse.py` はこのファイルを参照して対応投稿を特定し、削除する

**deny 時の否決理由取得**
- ❌ リアクション後、`deny_reply_timeout_seconds`（デフォルト 60s）の間スレッド返信を待つ
- 返信があればその内容を Claude Code の deny メッセージとして返す

**`terminal_emoji`（デフォルト `computer`）**
- 承認済み投稿が「実行完了」したことをオペレーターに視覚的に伝えるためのマーク
- `PostToolUse` または `Stop`/`PermissionDenied` 時に付与される

**`audit.py`（`mattermost-gate/log/audit.jsonl`）**
- 全リクエストと決定を JSONL 形式で記録
- `analyze_audit.py` でログを分析できる
