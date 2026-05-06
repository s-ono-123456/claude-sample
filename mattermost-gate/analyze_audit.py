#!/usr/bin/env python3
"""
analyze_audit.py - audit.jsonl を分析して allowedTools 候補を Markdown で出力する

使い方:
  .venv\\Scripts\\python.exe mattermost-gate\\analyze_audit.py
  .venv\\Scripts\\python.exe mattermost-gate\\analyze_audit.py --output mattermost-gate/log/report.md
  .venv\\Scripts\\python.exe mattermost-gate\\analyze_audit.py --since 7 --min-allow 2
  .venv\\Scripts\\python.exe mattermost-gate\\analyze_audit.py --include-internal
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

# ---- ツール分類 ----

READONLY_TOOLS = {"Read", "Glob", "Grep"}

INTERNAL_TOOLS = {
    "EnterPlanMode", "ExitPlanMode", "Skill",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    "TaskOutput", "TaskStop", "TaskDelete",
    "AskUserQuestion", "RemoteTrigger", "ScheduleWakeup",
    "CronCreate", "CronDelete", "CronList", "Monitor", "ToolSearch",
    "ShareOnboardingGuide", "PushNotification",
}

DECISION_TYPES = ("allow", "deny", "timeout", "cancelled")

# これより長いコマンドは allowedTools 候補に含めない（手動確認推奨）
CMD_CANDIDATE_MAX = 100

CAT_LABEL = {
    "A": "A: 読み取り専用",
    "B": "B: 実行・変更",
    "C": "C: 内部ツール",
}


def get_category(tool: str) -> str:
    if tool in READONLY_TOOLS:
        return "A"
    if tool in INTERNAL_TOOLS:
        return "C"
    return "B"


def get_group_key(tool: str, tool_input: dict) -> str:
    """ツール入力からグループキー文字列を返す"""
    if tool in ("Bash", "PowerShell"):
        cmd = tool_input.get("command", "")
        return cmd[:120] + ("…" if len(cmd) > 120 else "")

    if tool in ("Edit", "Write"):
        return tool_input.get("file_path", "(unknown)")

    if tool == "NotebookEdit":
        return tool_input.get("notebook_path", "(unknown)")

    if tool == "Read":
        return tool_input.get("file_path", "(unknown)")

    if tool == "Glob":
        return tool_input.get("pattern", "(unknown)")

    if tool == "Grep":
        pat = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return f"{pat}" + (f" in {path}" if path else "")

    if tool == "WebFetch":
        url = tool_input.get("url", "")
        try:
            p = urlparse(url)
            return f"{p.netloc}{p.path[:50]}"
        except Exception:
            return url[:60]

    if tool == "WebSearch":
        return tool_input.get("query", "")[:60]

    if tool == "Agent":
        subtype = tool_input.get("subagent_type", "")
        desc = tool_input.get("description", "")[:50]
        return f"{subtype}: {desc}" if subtype else desc

    if tool == "ExitPlanMode":
        plan = tool_input.get("plan", "")
        first = plan.strip().split("\n")[0].lstrip("# ") if plan else ""
        return first[:60] if first else "(プランなし)"

    if tool == "EnterPlanMode":
        return "(引数なし)"

    if tool == "Skill":
        return tool_input.get("skill", "(unknown)")

    if tool in INTERNAL_TOOLS or tool.startswith("Task"):
        return f"({tool})"

    raw = json.dumps(tool_input, ensure_ascii=False)
    return raw[:80] + ("…" if len(raw) > 80 else "")


# ---- データ読み込み ----

def load_paired_records(log_path: Path, since_days: int | None) -> list[dict]:
    """JSONL を読み込み request/decision をペアリングして返す"""
    since_dt = None
    if since_days is not None:
        since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)

    reqs: dict[str, dict] = {}
    decs: dict[str, dict] = {}

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            if since_dt:
                try:
                    ts = datetime.fromisoformat(rec.get("ts", ""))
                    if ts < since_dt:
                        continue
                except ValueError:
                    pass

            pid = rec.get("post_id", "")
            event = rec.get("event", "")
            if event == "request":
                reqs[pid] = rec
            elif event == "decision":
                decs[pid] = rec

    paired = []
    for pid, req in reqs.items():
        dec = decs.get(pid)
        decision = dec.get("decision", "cancelled") if dec else "cancelled"
        if decision not in DECISION_TYPES:
            decision = "cancelled"
        paired.append({
            "ts": req.get("ts", ""),
            "tool_name": req.get("tool_name", ""),
            "tool_input": req.get("tool_input", {}),
            "post_id": pid,
            "decision": decision,
        })

    paired.sort(key=lambda r: r["ts"])
    return paired


# ---- 集計 ----

def build_summary(records: list[dict]) -> dict:
    """{ tool_name: { group_key: { decision: count } } }"""
    s: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for rec in records:
        tool = rec["tool_name"]
        key = get_group_key(tool, rec["tool_input"])
        s[tool][key][rec["decision"]] += 1
    return s


def collect_candidates(summary: dict, min_allow: int, include_internal: bool) -> dict:
    """{ "A": [...], "B": [...], "C": [...] } 形式で候補エントリを返す"""
    result: dict[str, list[str]] = {"A": [], "B": [], "C": []}

    for tool in sorted(summary.keys()):
        cat = get_category(tool)
        if cat == "C" and not include_internal:
            continue

        groups = summary[tool]

        if tool in ("Bash", "PowerShell"):
            # コマンド単位で候補を選出
            for key, counts in groups.items():
                a = counts.get("allow", 0)
                d = counts.get("deny", 0)
                t = counts.get("timeout", 0)
                if a >= min_allow and d == 0 and t == 0:
                    raw_cmd = key.rstrip("…")
                    if len(raw_cmd) <= CMD_CANDIDATE_MAX:
                        entry = f"{tool}({raw_cmd})"
                        if entry not in result[cat]:
                            result[cat].append(entry)
        else:
            # ツール単位：すべての呼び出しで deny/timeout がなければ候補
            total_allow = sum(g.get("allow", 0) for g in groups.values())
            total_deny = sum(g.get("deny", 0) for g in groups.values())
            total_timeout = sum(g.get("timeout", 0) for g in groups.values())
            if total_allow >= min_allow and total_deny == 0 and total_timeout == 0:
                if tool not in result[cat]:
                    result[cat].append(tool)

    return result


# ---- Markdown 生成 ----

def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def md_summary_section(summary: dict) -> list[str]:
    lines = ["## ツール別 詳細サマリー", ""]

    for tool in sorted(summary.keys(), key=lambda t: (get_category(t), t)):
        cat = get_category(tool)
        lines.append(f"### [{CAT_LABEL[cat]}] {tool}")
        lines.append("")
        lines.append("| 詳細 | allow | deny | timeout | cancelled |")
        lines.append("|---|---:|---:|---:|---:|")

        groups = summary[tool]
        for key in sorted(
            groups,
            key=lambda k: (-groups[k].get("allow", 0), -groups[k].get("cancelled", 0)),
        ):
            c = groups[key]
            a = c.get("allow", 0)
            d = c.get("deny", 0)
            t = c.get("timeout", 0)
            ca = c.get("cancelled", 0)
            lines.append(f"| `{_md_cell(key)}` | {a} | {d} | {t} | {ca} |")
        lines.append("")

    return lines


def md_allow_history(records: list[dict]) -> list[str]:
    jst = timezone(timedelta(hours=9))
    lines = ["## allow された履歴", ""]
    lines.append("| 日時(JST) | ツール | 内容 |")
    lines.append("|---|---|---|")

    found = False
    for rec in records:
        if rec["decision"] != "allow":
            continue
        tool = rec["tool_name"]
        try:
            ts = datetime.fromisoformat(rec["ts"]).astimezone(jst).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            ts = rec["ts"]
        key = get_group_key(tool, rec["tool_input"])
        lines.append(f"| {ts} | {tool} | `{_md_cell(key)}` |")
        found = True

    if not found:
        lines.append("| — | — | （該当なし） |")
    lines.append("")
    return lines


def md_candidates_section(candidates: dict, min_allow: int) -> list[str]:
    lines = ["## allowedTools 追記候補", ""]
    lines.append(f"> 選出条件：allow &ge; {min_allow}、かつ deny = 0、かつ timeout = 0")
    lines.append("")

    a_list = candidates.get("A", [])
    b_list = candidates.get("B", [])
    c_list = candidates.get("C", [])

    if a_list:
        lines.append("### A: 読み取り専用 — まとめて追加を推奨")
        lines.append("")
        lines.append("> 副作用がないため、ファイルパスを問わず一括許可が安全です。")
        lines.append("")
        for e in a_list:
            lines.append(f"- `{e}`")
        lines.append("")

    if b_list:
        lines.append("### B: 実行・変更系 — 内容を確認してから追加")
        lines.append("")
        lines.append(
            "> `Bash(cmd)` の形式は指定した文字列で**前方一致**します。"
            " 例: `Bash(ls)` は `ls -la` なども許可されます。"
        )
        lines.append("")
        for e in b_list:
            lines.append(f"- `{e}`")
        lines.append("")

    if c_list:
        lines.append("### C: 内部ツール")
        lines.append("")
        for e in c_list:
            lines.append(f"- `{e}`")
        lines.append("")

    all_entries = a_list + b_list + c_list
    lines.append("### settings.json に追記する JSON")
    lines.append("")
    if all_entries:
        lines.append("```json")
        lines.append(json.dumps(all_entries, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("```json")
        lines.append("[]")
        lines.append("```")
        lines.append("")
        lines.append("_候補なし。条件を満たすコマンドがありません。_")

    lines.append("")
    return lines


def build_report(
    records: list[dict],
    summary: dict,
    candidates: dict,
    min_allow: int,
    since_days: int | None,
) -> str:
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y-%m-%d")
    title = f"# Audit Report — {today}"
    if since_days:
        title += f"（直近 {since_days} 日）"

    lines = [title, ""]
    lines += md_summary_section(summary)
    lines += md_allow_history(records)
    lines += md_candidates_section(candidates, min_allow)
    return "\n".join(lines)


# ---- エントリポイント ----

def main() -> None:
    parser = argparse.ArgumentParser(
        description="audit.jsonl を分析して allowedTools 候補を Markdown で出力する"
    )
    parser.add_argument(
        "--log",
        default="mattermost-gate/log/audit.jsonl",
        metavar="PATH",
        help="監査ログのパス（デフォルト: mattermost-gate/log/audit.jsonl）",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="出力先 .md ファイル（省略時は stdout）",
    )
    parser.add_argument(
        "--since",
        type=int,
        metavar="DAYS",
        help="過去 N 日分のみ対象（デフォルト: 全期間）",
    )
    parser.add_argument(
        "--min-allow",
        type=int,
        default=1,
        dest="min_allow",
        metavar="N",
        help="候補の最小 allow 回数（デフォルト: 1）",
    )
    parser.add_argument(
        "--include-internal",
        action="store_true",
        help="内部ツール（カテゴリC）も allowedTools 候補に含める",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Error: ログファイルが見つかりません: {log_path}", file=sys.stderr)
        sys.exit(1)

    records = load_paired_records(log_path, args.since)
    if not records:
        print("対象レコードがありません。", file=sys.stderr)
        sys.exit(0)

    summary = build_summary(records)
    candidates = collect_candidates(summary, args.min_allow, args.include_internal)
    report = build_report(records, summary, candidates, args.min_allow, args.since)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"レポートを保存しました: {out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
