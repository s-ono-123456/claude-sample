# log-explorer

Claude Code のセッションログ（`~/.claude/projects/`以下）を調査する Python CLI ツール。メインエージェントの会話・ツール呼び出し・thinking ブロック、サブエージェントの処理内容、トークン使用量を対話的に確認できる。

## 前提条件

```powershell
uv sync    # rich>=13.0 が追加されていること
```

## 基本的な使い方

```powershell
uv run python log-explorer/main.py [session-id] [subcommand] [options]
```

`session-id` には以下を指定できる：

| 形式 | 例 | 説明 |
|------|-----|------|
| 完全 UUID | `0c6a9ea5-afd5-4db7-9c02-ce57b4bd0e12` | 完全一致 |
| UUID プレフィックス | `0c6a9ea5` | 先頭一致（1件に絞れればOK） |
| `latest` | `latest` | 最新のセッション |

## ログ一覧

```powershell
# 最新20件を表示
uv run python log-explorer/main.py --list

# 最新50件を表示
uv run python log-explorer/main.py --list -n 50
```

出力例：

```
  Session ID                             更新日時       サイズ   サブエージェント
 ─────────────────────────────────────────────────────────────────────────────
  0c6a9ea5-afd5-4db7-9c02-ce57b4bd0e12   2026-06-06     338 KB   4
  593ee3cd-bd76-4ef3-9340-a318089b9a8d   2026-06-06     26 KB    -
```

## サブコマンド

### `summary`（デフォルト）

セッション全体の概要を表示する。

```powershell
uv run python log-explorer/main.py 0c6a9ea5
# または
uv run python log-explorer/main.py 0c6a9ea5 summary
```

表示内容：
- 開始・終了時刻、モード
- ユーザー/アシスタントターン数、ツール呼び出し数、thinking ブロック数
- サブエージェント一覧と各エージェントのトークン数
- 総トークン数（メイン＋全サブエージェント合算）

---

### `timeline`

会話の時系列を表示する。メインエージェントの発言・ツール呼び出しと、サブエージェントの内部処理をインデントで展開する。

```powershell
uv run python log-explorer/main.py 0c6a9ea5 timeline

# thinking ブロックも表示する
uv run python log-explorer/main.py 0c6a9ea5 timeline --thinking

# 表示を先頭30件に制限
uv run python log-explorer/main.py 0c6a9ea5 timeline --limit 30
```

---

### `tools`

ツール呼び出しの一覧を表示する。メイン・全サブエージェントのツールを時系列で並べる。

```powershell
uv run python log-explorer/main.py 0c6a9ea5 tools
```

表示内容：時刻・エージェント名・ツール名・入力・結果（先頭80文字）

---

### `agents`

サブエージェントの概要を一覧表示する。インデックス番号付き。

```powershell
uv run python log-explorer/main.py 0c6a9ea5 agents
```

表示内容：agentType・説明・Agent ID・Tool Use ID・実行時間・ツール呼び出し数・トークン数

---

### `tokens`

エージェント別のトークン使用量を集計する。

```powershell
uv run python log-explorer/main.py 0c6a9ea5 tokens
```

表示内容：エージェントごとに Input / Output / Cache Write / Cache Read / Total I/O

## `--agent` オプション（サブエージェント絞り込み）

特定のサブエージェントに絞って詳細を確認する。`timeline` / `tools` / `agents` / `tokens` の各サブコマンドで使用できる。

### 指定方法

| 形式 | 例 | 説明 |
|------|-----|------|
| インデックス番号 | `--agent 0` | `agents` 一覧の表示順（[0], [1], ...） |
| agent_id プレフィックス | `--agent a9c6c0c` | Agent ID の先頭一致 |
| agent_type 名 | `--agent claude-code-guide` | 大文字小文字問わず |

> **注意**: 同じ型のエージェントが複数いる場合（例: `Explore` が3件）は型名指定がエラーになるため、インデックスで指定すること。

### 使用例

```powershell
# まずインデックスを確認
uv run python log-explorer/main.py 0c6a9ea5 agents

# agents: 概要テーブル + 会話タイムラインをまとめて表示
uv run python log-explorer/main.py 0c6a9ea5 agents --agent 3
uv run python log-explorer/main.py 0c6a9ea5 agents --agent claude-code-guide
uv run python log-explorer/main.py 0c6a9ea5 agents --agent a9c6c0c

# timeline: そのエージェントの会話のみを表示
uv run python log-explorer/main.py 0c6a9ea5 timeline --agent 0

# tools: そのエージェントのツール呼び出しのみ
uv run python log-explorer/main.py 0c6a9ea5 tools --agent 3

# tokens: そのエージェントのメッセージ単位のトークン内訳
uv run python log-explorer/main.py 0c6a9ea5 tokens --agent 3
```

## オプション一覧

| オプション | 説明 |
|-----------|------|
| `--list` | セッション一覧を表示 |
| `-n N` | `--list` の表示件数（デフォルト: 20） |
| `--agent QUERY` | サブエージェントを絞り込む（インデックス / ID プレフィックス / 型名） |
| `--thinking` | thinking ブロックを表示（`timeline` のみ有効） |
| `--limit N` | 表示行数の上限（`timeline` で有効） |
| `--json` | JSON 形式で出力（パイプ加工用） |
| `--no-color` | カラー出力を無効化 |
| `--log-dir PATH` | ログディレクトリを指定（デフォルト: `~/.claude/projects/C--claude`） |

## ログディレクトリのデフォルト値

`DEFAULT_LOG_DIR = Path.home() / ".claude" / "projects" / "C--claude"` に設定されている（`log-explorer/main.py` の先頭）。別プロジェクトのログを見る場合は `--log-dir` で上書きできる。

```powershell
uv run python log-explorer/main.py --list --log-dir "$env:USERPROFILE\.claude\projects\MyOtherProject"
```
