# Secretary Phase 1 実装ドキュメント

Phase 1 のスコープ: セッションログ + git + アクティブウィンドウを収集し、30分サイクルで Worker（隔離コンテナの Claude Code）が1周回り、成果が Mattermost に届く。

関連: [requirements.md](requirements.md) / [architecture.md](architecture.md)

---

## 1. ファイル構成

```
secretary/
  config.yaml(.example)      # Orchestrator/Collector の設定（config.yaml は gitignore）
  collector/collector.py     # 常駐: アクティブウィンドウ10秒ポーリング → data/events/*.jsonl
  orchestrator/
    pipeline.ps1             # Task Scheduler エントリ（30分ごと）
    snapshot_builder.py      # 収集 → data/snapshots/<job_id>/（diff-summary.md + context/）
    run_worker.py            # wsl docker run（キー注入・マウント・timeout 監視）
    collect_and_post.py      # summary.json 回収 → 成果があれば Mattermost 投稿
    audit.py                 # log/audit.jsonl への JSONL 追記
    register_task.ps1        # Task Scheduler 登録（手動実行）
  worker/
    Dockerfile               # python:3.12-slim + Node.js + claude-code CLI + claude-agent-sdk
    worker_main.py           # ClaudeAgentOptions を組んで query() 単発実行
    worker-config.yaml       # ★ Worker 設定のファイル管理（再ビルド不要）
    system_prompt.md         # ★ 秘書ペルソナ・早期終了規約・セキュリティ規約
  docker/
    docker-compose.yml       # egress-proxy 常駐 + secretary_internal ネットワーク
    tinyproxy.conf
    egress-allowlist.txt     # ★ 許可ドメインのファイル管理
  data/ log/                 # 実行時生成（gitignore）
secretary-workspace/         # Worker が rw マウントできる唯一のホスト領域（gitignore）
```

★ = ファイル編集だけで挙動を変更できる管理ポイント（イメージ再ビルド不要）

## 2. 初期セットアップ

```powershell
# 1. 設定ファイル作成（許可リスト・監視リポジトリ・channel_id を記入）
Copy-Item secretary\config.yaml.example secretary\config.yaml

# 2. 支出上限つき Anthropic API キーを Credential Manager に登録
uv run python -c "import keyring; keyring.set_password('secretary-anthropic', 'api-key', '<APIキー>')"

# 3. Worker イメージのビルド + egress-proxy 起動（WSL2）
wsl -d Ubuntu-24.04 -- bash -c "docker build -t secretary-worker:latest /mnt/c/claude/secretary/worker"
wsl -d Ubuntu-24.04 -- bash -c "cd /mnt/c/claude/secretary/docker && docker compose up -d --build"

# 4. Collector を手動起動（動作確認後は register_task.ps1 でログオン時常駐化）
uv run python secretary\collector\collector.py

# 5. パイプラインを手動で1周実行して確認
powershell -File secretary\orchestrator\pipeline.ps1

# 6. 問題なければ Task Scheduler に登録（30分ごと + ログオン時 Collector）
powershell -File secretary\orchestrator\register_task.ps1
```

## 3. コンテナ内契約（Worker）

| パス / env | 内容 |
|---|---|
| `/config` (:ro) | `worker-config.yaml`（ClaudeAgentOptions・ジョブ指示）+ `system_prompt.md` |
| `/snapshot` (:ro) | snapshot_builder が生成した入力（diff-summary.md + context/） |
| `/shared` (rw) | `secretary-workspace`。成果物の唯一の出力先 |
| `JOB_ID` | ジョブ ID（= スナップショットのディレクトリ名） |
| `ANTHROPIC_API_KEY` | keyring → `WSLENV` 経由で注入（コマンドラインに露出しない） |
| `HTTPS_PROXY` | `http://secretary-egress-proxy:8888`（外部到達は許可リスト先のみ） |

**summary.json 契約**（Worker は最後に必ず書く。書かない場合 worker_main が `action:none` で補完）:

```json
{"action": "report" | "none", "title": "...", "reason": "...", "files": ["report.md"]}
```

`action:none` の回は Mattermost に何も投稿されない（audit のみ）。

## 4. egress 制限の変更方法

`secretary/docker/egress-allowlist.txt` に ERE 正規表現を1行追記（アンカー必須。例: `^api\.example\.com$`）し、

```powershell
wsl -d Ubuntu-24.04 -- bash -c "cd /mnt/c/claude/secretary/docker && docker compose restart egress-proxy"
```

## 5. 実装上の注意

- **`.ps1` ファイルは ASCII のみで書く。** Windows PowerShell 5.1 は BOM なし UTF-8 を ANSI として読むため、日本語コメントが文字化けしてパース自体が壊れる（pipeline.ps1 で実際に発生し、ASCII 化で解消）
- Git Bash から WSL2 Docker を叩くときはパス変換対策として `wsl -d Ubuntu-24.04 -- bash -c "..."` 形式を使う（CLAUDE.md の慣例どおり）

## 6. 監査ログ

`secretary/log/audit.jsonl` に全イベントを JSONL で記録:
`worker_start` / `worker_end`（コスト・ターン数含む）/ `worker_timeout` / `collect_no_action` / `collect_missing_summary` / `posted`

スナップショット自体も `data/snapshots/<job_id>/` に保全され、「Worker に何を渡したか」を後から確認できる。

## 7. テスト実施状況（2026-07-11）

| テスト | 結果 |
|---|---|
| Collector（許可リスト・JSONL 記録） | ✅ 確認済み |
| snapshot_builder（diff-summary + context 生成） | ✅ 確認済み |
| Worker イメージビルド | ✅ 成功 |
| egress 制限（api.anthropic.com のみ許可・直接続不可） | ✅ 確認済み（401/403 Filtered/gaierror） |
| collect_and_post（action:none の無音パス + audit） | ✅ 確認済み |
| run_worker（キー未登録時の明示エラー） | ✅ 確認済み |
| **Worker 実機実行・早期終了・コスト取得** | ⏳ API キー登録待ち |
| **Mattermost 投稿（report パス）** | ⏳ 秘書チャンネル channel_id 記入待ち |
| **E2E（pipeline.ps1 1周）** | ⏳ 上記2点の準備後に実施 |
