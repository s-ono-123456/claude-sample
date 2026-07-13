"""Worker に渡すスナップショットを生成する（決定的処理・LLM なし）。

allow リスト方式: ここで明示的に詰めたものだけがスナップショットに入る。
出力: secretary/data/snapshots/<job_id>/
  ├── diff-summary.md   … 前回実行以降の変化の機械的サマリ（Worker の早期終了判断用）
  └── context/
      ├── window-activity.md
      ├── sessions.md
      └── git.md
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

SECRETARY_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SECRETARY_DIR / "data"
STATE_PATH = DATA_DIR / "state.json"

MAX_SESSION_FILES = 5
MAX_MESSAGES_PER_SESSION = 20
MAX_MESSAGE_CHARS = 500
MAX_LOG_LINES = 30


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"last_run": None}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------
# ウィンドウイベント
# ---------------------------------------------------------------

def collect_window_activity(since: datetime | None, top_n: int) -> list[dict]:
    """(process, title) ごとに滞在時間を集約し、上位 top_n を返す。"""
    events_dir = DATA_DIR / "events"
    if not events_dir.exists():
        return []
    totals: dict[tuple[str, str], float] = {}
    for path in sorted(events_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = datetime.fromisoformat(ev["ts"])
            if since and ts < since:
                continue
            key = (ev["process"], ev["title"])
            totals[key] = totals.get(key, 0) + ev.get("dwell_seconds", 0)
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [
        {"process": p, "title": t, "dwell_seconds": int(s)}
        for (p, t), s in ranked
    ]


# ---------------------------------------------------------------
# Claude Code セッションログ
# ---------------------------------------------------------------

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def collect_sessions(since: datetime | None, projects_dir: Path) -> list[dict]:
    """前回実行以降に更新されたセッションログからユーザー発言と要約を機械抽出する。"""
    if not projects_dir.exists():
        return []
    since_ts = since.timestamp() if since else 0
    files = [
        p for p in projects_dir.glob("*/*.jsonl")
        if p.stat().st_mtime >= since_ts
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    sessions = []
    for path in files[:MAX_SESSION_FILES]:
        user_messages: list[str] = []
        summaries: list[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") == "summary" and rec.get("summary"):
                summaries.append(rec["summary"])
            elif rec.get("type") == "user" and isinstance(rec.get("message"), dict):
                text = _extract_text(rec["message"].get("content")).strip()
                # ツール結果や割り込み等のシステム的レコードは除外
                if text and not text.startswith("<") and not text.startswith("["):
                    user_messages.append(text[:MAX_MESSAGE_CHARS])
        sessions.append({
            "project": path.parent.name,
            "file": path.name,
            "summaries": summaries[-3:],
            "user_messages": user_messages[-MAX_MESSAGES_PER_SESSION:],
        })
    return sessions


# ---------------------------------------------------------------
# git アクティビティ
# ---------------------------------------------------------------

def _git(repo: str, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        return out.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def collect_git(repos: list[str], since: datetime | None) -> list[dict]:
    results = []
    for repo in repos:
        if not Path(repo).exists():
            continue
        branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        log_args = ["log", "--oneline", f"--max-count={MAX_LOG_LINES}"]
        if since:
            log_args.append(f"--since={since.isoformat()}")
        new_commits = _git(repo, *log_args)
        status = "\n".join(_git(repo, "status", "--short").splitlines()[:MAX_LOG_LINES])
        results.append({
            "repo": repo,
            "branch": branch,
            "new_commits": new_commits,
            "status": status,
        })
    return results


# ---------------------------------------------------------------
# スナップショット出力
# ---------------------------------------------------------------

def write_snapshot(job_id: str, since: datetime | None,
                   windows: list[dict], sessions: list[dict], git_info: list[dict]) -> Path:
    snap_dir = DATA_DIR / "snapshots" / job_id
    ctx_dir = snap_dir / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)

    commit_count = sum(len(g["new_commits"].splitlines()) for g in git_info if g["new_commits"])
    since_str = since.isoformat() if since else "（初回実行）"

    diff = [
        f"# 差分サマリ（前回実行: {since_str}）",
        "",
        "このファイルだけを読んで、調査を続行する価値があるか判断すること。",
        "",
        f"- ウィンドウ活動: {len(windows)} 件（詳細: context/window-activity.md）",
        f"- 更新された Claude Code セッション: {len(sessions)} 件（詳細: context/sessions.md）",
        f"- 新規コミット: {commit_count} 件（詳細: context/git.md）",
    ]
    if not windows and not sessions and commit_count == 0:
        diff.append("")
        diff.append("**前回実行から観測可能な変化はない。**")
    (snap_dir / "diff-summary.md").write_text("\n".join(diff) + "\n", encoding="utf-8")

    lines = ["# ウィンドウ活動（滞在時間順）", ""]
    for w in windows:
        lines.append(f"- [{w['dwell_seconds']}秒] {w['process']}: {w['title']}")
    (ctx_dir / "window-activity.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = ["# Claude Code セッション（新しい順）", ""]
    for s in sessions:
        lines.append(f"## {s['project']} / {s['file']}")
        for smr in s["summaries"]:
            lines.append(f"- 要約: {smr}")
        for msg in s["user_messages"]:
            lines.append(f"- ユーザー発言: {msg}")
        lines.append("")
    (ctx_dir / "sessions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = ["# git アクティビティ", ""]
    for g in git_info:
        lines.append(f"## {g['repo']}（ブランチ: {g['branch']}）")
        lines.append("### 新規コミット")
        lines.append(g["new_commits"] or "（なし）")
        lines.append("### 未コミットの変更")
        lines.append(g["status"] or "（なし）")
        lines.append("")
    (ctx_dir / "git.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return snap_dir


def build(config: dict) -> Path:
    state = load_state()
    since = datetime.fromisoformat(state["last_run"]) if state.get("last_run") else None
    now = datetime.now(timezone.utc)
    job_id = now.astimezone().strftime("%Y-%m-%d_%H%M")

    src = config["sources"]
    projects_dir = Path(src["claude_projects_dir"] or Path.home() / ".claude" / "projects")

    windows = collect_window_activity(since, src.get("window_top_n", 15))
    sessions = collect_sessions(since, projects_dir)
    git_info = collect_git(src.get("git_repos", []), since)

    snap_dir = write_snapshot(job_id, since, windows, sessions, git_info)
    save_state({"last_run": now.isoformat()})
    return snap_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(SECRETARY_DIR / "config.yaml"))
    args = parser.parse_args()
    snap_dir = build(load_config(Path(args.config)))
    # pipeline がこのパスを次工程（run_worker）へ渡す
    print(snap_dir)


if __name__ == "__main__":
    main()
