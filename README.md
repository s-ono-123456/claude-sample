# mattermost-gate

Claude Code の `PermissionRequest` フックとして動作し、全ツール使用の承認を Mattermost 経由にルーティングするゲートウェイです。
Claude Code がツールの実行許可を求めるたびに Mattermost チャンネルへ通知を投稿し、オペレーターが ✅ / ❌ の絵文字リアクションで承認・拒否します。

## 主な機能

- **Mattermost 承認フロー** — ツール実行前に Mattermost へ通知。絵文字リアクションで許否を判断
- **ツール別整形表示** — `Edit`/`Write` は unified diff、`Bash`/`PowerShell` はパイプライン・セミコロン単位で分割表示
- **AI 事前審査** — `policy.md` に基づき Claude Haiku が `safe` / `risky` / `dangerous` を判定してメッセージに付記
- **タイムアウト自動 deny** — 設定時間内に反応がなければ自動的に拒否

## 前提条件

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)（パッケージ管理）
- Mattermost サーバーと Bot トークン（または Personal Access Token）
- Claude Code CLI（AI 事前審査機能を使う場合）

## セットアップ

### 1. 依存関係のインストール

```powershell
uv sync
```

### 2. 設定ファイルの作成

```powershell
Copy-Item mattermost-gate\config.json.sample mattermost-gate\config.json
```

`mattermost-gate\config.json` を開き、以下の値を設定してください。

```json
{
  "mattermost_url": "https://your-mm.example.com",
  "token": "your-bot-or-personal-access-token",
  "channel_id": "your-channel-id"
}
```

### 3. Claude Code へのフック登録確認

`.claude/settings.json` に以下の設定が含まれていることを確認します（初回セットアップ時のみ）。

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\claude\\.venv\\Scripts\\python.exe C:\\claude\\mattermost-gate\\permissionrequest.py",
            "shell": "powershell",
            "statusMessage": "Waiting for Mattermost approval..."
          }
        ]
      }
    ]
  }
}
```

### 4.（任意）AI 事前審査ポリシーのカスタマイズ

`mattermost-gate\policy.md` を編集して、`safe` / `risky` / `dangerous` の判定基準を調整できます。
ファイルが存在しない場合、AI 事前審査はスキップされます。

## 設定リファレンス

`mattermost-gate/config.json` で指定できるフィールド一覧です。

| フィールド | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `mattermost_url` | ✅ | — | Mattermost サーバーの URL |
| `token` | ✅ | — | Bot または Personal Access Token |
| `channel_id` | ✅ | — | 通知先チャンネル ID |
| `timeout_seconds` | | `300` | 承認待ちタイムアウト（秒）。超過すると自動 deny |
| `poll_interval_seconds` | | `2` | リアクション確認のポーリング間隔（秒） |
| `approve_emoji` | | `white_check_mark` | 承認を示す絵文字名 |
| `deny_emoji` | | `x` | 拒否を示す絵文字名 |
| `deny_reply_timeout_seconds` | | `60` | deny 後にスレッド返信（否決理由）を待つ時間（秒） |
| `terminal_emoji` | | `computer` | ツール実行完了を示す絵文字名（PostToolUse フックで付与） |

`config.json` は `.gitignore` で除外されています。機密情報をコミットしないよう注意してください。

## 動作フロー

### PermissionRequest（ツール実行の承認）

```
Claude Code
    │  PermissionRequest イベント
    ▼
permissionrequest.py  ─── policy.md が存在する場合 ──→  llm_precheck()
    │                                        （Claude Haiku による事前審査）
    │  審査結果を付記してメッセージ投稿 / registry に post_id を記録
    ▼
Mattermost チャンネル
    │  ✅ または ❌ のリアクションを待機
    ▼
poll_for_decision()  ─── タイムアウト ──→  deny（自動拒否）
    │ deny の場合: スレッド返信（否決理由）を最大 deny_reply_timeout_seconds 待機
    ▼
stdout に決定 JSON を出力
    │
    ▼
Claude Code（allow / deny を受け取る）
```

### PostToolUse（ツール実行完了の通知）

```
Claude Code
    │  PostToolUse イベント（ツール実行完了後）
    ▼
posttooluse.py
    │  registry から該当ツールの post_id を取得
    ▼
Mattermost 投稿に 💻 (terminal_emoji) を付与
    └  registry エントリを削除
```

### Stop / PermissionDenied（セッション終了・権限拒否）

```
Claude Code
    │  Stop または PermissionDenied イベント
    ▼
stop.py
    │  registry から未処理の全 post_id を取得
    ▼
各投稿に 💻 (terminal_emoji) を付与して終了を通知
    └  registry エントリを削除
```

## ディレクトリ構成

```
mattermost-gate/
├── permissionrequest.py  # PermissionRequest フック（承認待ちのメインループ）
├── posttooluse.py        # PostToolUse フック（承認済み投稿を完了状態に更新）
├── stop.py               # Stop / PermissionDenied フック（未処理投稿を終了状態に更新）
├── analyze_audit.py      # 監査ログ分析スクリプト
├── config.json.sample    # 設定ファイルのテンプレート
├── config.json           # 実際の設定（.gitignore 済み）
├── policy.md             # AI 事前審査ポリシー（任意）
└── lib/
    ├── mattermost.py     # Mattermost REST API クライアント
    ├── precheck.py       # Claude Haiku による LLM 事前審査
    ├── registry.py       # PermissionRequest→PostToolUse 間の揮発性キャッシュ（tmp/ 以下）
    └── audit.py          # log/audit.jsonl への JSONL 監査ログ
```

## 手動テスト

フックを直接実行して動作確認できます。

```powershell
# Bash ツールの承認リクエストを送信する例
'{"tool_name":"Bash","tool_input":{"command":"ls -la","description":"List files"},"cwd":"C:\\claude","session_id":"abc123"}' |
    .venv\Scripts\python.exe mattermost-gate\permissionrequest.py
```

Mattermost チャンネルに通知が届いたら、✅ または ❌ でリアクションしてください。
stdout に以下の形式でレスポンスが返ります。

```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
```

## AI 事前審査について

`mattermost-gate/policy.md` が存在する場合、各リクエストを Claude Haiku で事前審査し、結果を Mattermost メッセージに付記します。

| 判定 | 表示 | 意味 |
|---|---|---|
| `safe` | ✅ | 問題なし |
| `risky` | ⚠️ | 注意が必要 |
| `dangerous` | 🚨 | 危険な操作の可能性あり |

事前審査はあくまで参考情報です。最終的な承認・拒否はオペレーターが絵文字リアクションで行います。
