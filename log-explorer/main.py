"""Claude Code セッションログ調査 CLI ツール"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from rich.panel import Panel
    from rich.text import Text
    RICH = True
except ImportError:
    RICH = False

DEFAULT_LOG_DIR = Path.home() / ".claude" / "projects" / "C--claude"
TOOL_TRUNCATE = 300
TEXT_TRUNCATE = 500


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    type: str
    uuid: str = ""
    parent_uuid: str | None = None
    timestamp: datetime | None = None
    message: dict | None = None
    is_sidechain: bool = False
    agent_id: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class SubagentInfo:
    agent_id: str
    agent_type: str
    description: str
    tool_use_id: str
    entries: list[Entry] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    entries: list[Entry] = field(default_factory=list)
    subagents: list[SubagentInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_entry(raw: dict) -> Entry:
    return Entry(
        type=raw.get("type", ""),
        uuid=raw.get("uuid", ""),
        parent_uuid=raw.get("parentUuid"),
        timestamp=_parse_ts(raw.get("timestamp")),
        message=raw.get("message"),
        is_sidechain=raw.get("isSidechain", False),
        agent_id=raw.get("agentId"),
        raw=raw,
    )


def _load_jsonl(path: Path) -> list[Entry]:
    entries = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_parse_entry(json.loads(line)))
            except json.JSONDecodeError:
                continue
    return entries


def _load_subagents(session_dir: Path) -> list[SubagentInfo]:
    sub_dir = session_dir / "subagents"
    if not sub_dir.exists():
        return []
    subagents = []
    for meta_path in sub_dir.glob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        agent_id = meta_path.stem.replace(".meta", "").replace("agent-", "")
        jsonl_path = sub_dir / f"agent-{agent_id}.jsonl"
        entries = _load_jsonl(jsonl_path) if jsonl_path.exists() else []
        subagents.append(SubagentInfo(
            agent_id=agent_id,
            agent_type=meta.get("agentType", "unknown"),
            description=meta.get("description", ""),
            tool_use_id=meta.get("toolUseId", ""),
            entries=entries,
        ))
    return subagents


def resolve_session_id(prefix: str, log_dir: Path) -> str:
    if prefix == "latest":
        candidates = sorted(log_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise SystemExit("セッションログが見つかりません")
        return candidates[0].stem
    # exact match
    if (log_dir / f"{prefix}.jsonl").exists():
        return prefix
    # prefix match
    matches = [p.stem for p in log_dir.glob(f"{prefix}*.jsonl")]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(f"セッション ID が曖昧です（{len(matches)} 件マッチ）: {matches[:5]}")
    raise SystemExit(f"セッション '{prefix}' が見つかりません")


def load_session(session_id: str, log_dir: Path) -> Session:
    jsonl_path = log_dir / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        raise SystemExit(f"ログファイルが見つかりません: {jsonl_path}")
    entries = _load_jsonl(jsonl_path)
    session_dir = log_dir / session_id
    subagents = _load_subagents(session_dir)
    return Session(session_id=session_id, entries=entries, subagents=subagents)


# ---------------------------------------------------------------------------
# Content extraction helpers
# ---------------------------------------------------------------------------

def _content_blocks(entry: Entry) -> list[dict]:
    if not entry.message:
        return []
    content = entry.message.get("content", [])
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [{len(text) - limit} chars more]"


def _usage(entry: Entry) -> dict:
    if not entry.message:
        return {}
    return entry.message.get("usage") or {}


def _all_tool_calls(session: Session, include_subagents: bool = True) -> list[dict]:
    """(entry, block, agent_label) のリストを時系列で返す"""
    results = []
    for e in session.entries:
        if e.type != "assistant":
            continue
        for b in _content_blocks(e):
            if b.get("type") == "tool_use":
                results.append({"entry": e, "block": b, "label": "main"})
    if include_subagents:
        for sa in session.subagents:
            for e in sa.entries:
                if e.type != "assistant":
                    continue
                for b in _content_blocks(e):
                    if b.get("type") == "tool_use":
                        results.append({"entry": e, "block": b, "label": sa.agent_type})
    results.sort(key=lambda x: x["entry"].timestamp or datetime.min.replace(tzinfo=timezone.utc))
    return results


def _tool_result_map(entries: list[Entry]) -> dict[str, str]:
    """tool_use_id -> result text"""
    mapping = {}
    for e in entries:
        for b in _content_blocks(e):
            if b.get("type") == "tool_result":
                tid = b.get("tool_use_id", "")
                content = b.get("content", "")
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            parts.append(item.get("text", ""))
                        else:
                            parts.append(str(item))
                    content = "\n".join(parts)
                mapping[tid] = str(content)
    return mapping


def _sum_usage(entries: list[Entry]) -> dict:
    total = {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0}
    for e in entries:
        u = _usage(e)
        total["input"] += u.get("input_tokens", 0)
        total["output"] += u.get("output_tokens", 0)
        total["cache_create"] += u.get("cache_creation_input_tokens", 0)
        total["cache_read"] += u.get("cache_read_input_tokens", 0)
    return total


def _resolve_agent(query: str, subagents: list[SubagentInfo]) -> SubagentInfo:
    if not subagents:
        raise SystemExit("このセッションにサブエージェントはありません")
    if query.isdigit():
        idx = int(query)
        if idx >= len(subagents):
            raise SystemExit(f"インデックス {idx} は範囲外（0〜{len(subagents) - 1}）")
        return subagents[idx]
    by_id = [sa for sa in subagents if sa.agent_id.startswith(query)]
    if len(by_id) == 1:
        return by_id[0]
    if len(by_id) > 1:
        raise SystemExit(f"agent_id プレフィックス '{query}' が複数マッチしました")
    by_type = [sa for sa in subagents if sa.agent_type.lower() == query.lower()]
    if len(by_type) == 1:
        return by_type[0]
    if len(by_type) > 1:
        raise SystemExit(
            f"'{query}' が {len(by_type)} 件マッチしました。"
            f"インデックス (0〜{len(subagents) - 1}) で指定してください"
        )
    raise SystemExit(f"サブエージェント '{query}' が見つかりません")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _make_console(no_color: bool) -> "Console | None":
    if not RICH:
        return None
    return Console(highlight=False, no_color=no_color)


def _fmt_ts(ts: datetime | None, short: bool = False) -> str:
    if ts is None:
        return "-"
    local = ts.astimezone()
    if short:
        return local.strftime("%H:%M:%S")
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _print(console, text: str = "", style: str = ""):
    if console:
        console.print(text, style=style)
    else:
        print(text)


def _print_header(console, title: str):
    if console:
        console.rule(f"[bold cyan]{title}[/]")
    else:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(log_dir: Path, n: int, console):
    files = sorted(log_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    if not files:
        _print(console, "セッションログが見つかりません", style="red")
        return

    if console:
        table = Table(title=f"最近のセッション（最大{n}件）", box=box.SIMPLE_HEAD)
        table.add_column("Session ID", style="cyan", no_wrap=True)
        table.add_column("更新日時", style="green")
        table.add_column("サイズ")
        table.add_column("サブエージェント")
        for f in files:
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size = f"{stat.st_size // 1024} KB"
            sub_dir = log_dir / f.stem / "subagents"
            sub_count = len(list(sub_dir.glob("*.meta.json"))) if sub_dir.exists() else 0
            sub_str = str(sub_count) if sub_count else "-"
            table.add_row(f.stem, mtime, size, sub_str)
        console.print(table)
    else:
        print(f"{'Session ID':<40} {'更新日時':<20} {'サイズ':>8} {'Sub':>4}")
        print("-" * 80)
        for f in files:
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size = f"{stat.st_size // 1024} KB"
            sub_dir = log_dir / f.stem / "subagents"
            sub_count = len(list(sub_dir.glob("*.meta.json"))) if sub_dir.exists() else 0
            print(f"{f.stem:<40} {mtime:<20} {size:>8} {sub_count:>4}")


def cmd_summary(session: Session, console):
    entries = session.entries
    user_entries = [e for e in entries if e.type == "user"]
    asst_entries = [e for e in entries if e.type == "assistant"]

    timestamps = [e.timestamp for e in entries if e.timestamp]
    start_ts = min(timestamps) if timestamps else None
    end_ts = max(timestamps) if timestamps else None

    mode = next((e.raw.get("mode") for e in entries if e.type == "mode"), "-")
    perm_mode = next((e.raw.get("permissionMode") for e in entries if e.type == "permission-mode"), "-")

    tool_uses = sum(
        1 for e in asst_entries
        for b in _content_blocks(e) if b.get("type") == "tool_use"
    )
    thinking_blocks = sum(
        1 for e in asst_entries
        for b in _content_blocks(e) if b.get("type") == "thinking"
    )
    usage = _sum_usage(asst_entries)

    sub_usages = []
    for sa in session.subagents:
        su = _sum_usage([e for e in sa.entries if e.type == "assistant"])
        sub_usages.append((sa.agent_type, su))

    total_input = usage["input"] + sum(u["input"] for _, u in sub_usages)
    total_output = usage["output"] + sum(u["output"] for _, u in sub_usages)

    _print_header(console, f"Session Summary: {session.session_id}")

    if console:
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("開始時刻", _fmt_ts(start_ts))
        table.add_row("終了時刻", _fmt_ts(end_ts))
        table.add_row("モード", f"{mode} / {perm_mode}")
        table.add_row("ユーザーターン", str(len(user_entries)))
        table.add_row("アシスタントターン", str(len(asst_entries)))
        table.add_row("ツール呼び出し", str(tool_uses))
        table.add_row("Thinking ブロック", str(thinking_blocks))
        table.add_row("サブエージェント", str(len(session.subagents)))
        for agent_type, su in sub_usages:
            table.add_row(f"  └ {agent_type}", f"in={su['input']:,} out={su['output']:,}")
        table.add_row("総入力トークン", f"{total_input:,}")
        table.add_row("総出力トークン", f"{total_output:,}")
        console.print(table)
    else:
        print(f"  開始時刻         : {_fmt_ts(start_ts)}")
        print(f"  終了時刻         : {_fmt_ts(end_ts)}")
        print(f"  モード           : {mode} / {perm_mode}")
        print(f"  ユーザーターン   : {len(user_entries)}")
        print(f"  アシスタントターン: {len(asst_entries)}")
        print(f"  ツール呼び出し   : {tool_uses}")
        print(f"  Thinking ブロック: {thinking_blocks}")
        print(f"  サブエージェント : {len(session.subagents)}")
        for agent_type, su in sub_usages:
            print(f"    └ {agent_type}: in={su['input']:,} out={su['output']:,}")
        print(f"  総入力トークン   : {total_input:,}")
        print(f"  総出力トークン   : {total_output:,}")

    if session.subagents:
        _print(console)
        _print_header(console, "Subagents")
        for sa in session.subagents:
            _print(console, f"  [{sa.agent_type}] {sa.description}", style="dim")


def cmd_timeline(session: Session, console, show_thinking: bool = False, limit: int | None = None,
                 agent: SubagentInfo | None = None):
    if agent:
        _print_header(console, f"Timeline [{agent.agent_type}]: {agent.description[:50]}")
        entries = agent.entries
        result_map = _tool_result_map(agent.entries)
        sa_by_tool_use_id: dict = {}
    else:
        _print_header(console, f"Timeline: {session.session_id[:8]}...")
        entries = session.entries
        sa_by_tool_use_id = {sa.tool_use_id: sa for sa in session.subagents}
        result_map = _tool_result_map(session.entries)

    count = 0
    for e in entries:
        if e.type not in ("user", "assistant"):
            continue
        if limit and count >= limit:
            _print(console, f"  ... (--limit {limit} に達しました)", style="dim")
            break

        ts = _fmt_ts(e.timestamp, short=True)

        if e.type == "user":
            for b in _content_blocks(e):
                if b.get("type") == "tool_result":
                    continue  # タイムライン上では省略（toolsコマンドで確認）
                if b.get("type") == "text":
                    text = _truncate(b.get("text", ""), TEXT_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [bold green]USER[/] {text}")
                    else:
                        print(f"[{ts}] USER  {text}")
                    count += 1

        elif e.type == "assistant":
            for b in _content_blocks(e):
                btype = b.get("type")
                if btype == "text":
                    text = _truncate(b.get("text", ""), TEXT_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [bold blue]ASST[/] {text}")
                    else:
                        print(f"[{ts}] ASST  {text}")
                    count += 1
                elif btype == "thinking" and show_thinking:
                    text = _truncate(b.get("thinking", ""), TEXT_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [dim italic]THINK {text}[/]")
                    else:
                        print(f"[{ts}] THINK {text}")
                    count += 1
                elif btype == "tool_use":
                    tool_name = b.get("name", "?")
                    tool_id = b.get("id", "")
                    inp = json.dumps(b.get("input", {}), ensure_ascii=False)
                    inp_str = _truncate(inp, TOOL_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [bold yellow]TOOL[/] [yellow]{tool_name}[/] {inp_str}")
                    else:
                        print(f"[{ts}] TOOL  {tool_name}  {inp_str}")
                    count += 1

                    # サブエージェントが紐付いている場合はインデント展開
                    sa = sa_by_tool_use_id.get(tool_id)
                    if sa:
                        _print_subagent_inline(sa, console, ts, show_thinking, result_map)

                    # ツール結果を表示
                    result = result_map.get(tool_id, "")
                    if result and not result.startswith("<persisted-output>"):
                        result_str = _truncate(result, TOOL_TRUNCATE)
                        if console:
                            console.print(f"[{ts}]   [dim]→ {result_str}[/]")
                        else:
                            print(f"[{ts}]   -> {result_str}")
                        count += 1


def _print_subagent_inline(sa: SubagentInfo, console, parent_ts: str, show_thinking: bool, _ignored):
    indent = "    "
    sa_result_map = _tool_result_map(sa.entries)
    if console:
        console.print(f"{indent}[bold magenta]↳ AGENT[/] [{sa.agent_type}] {sa.description[:60]}")
    else:
        print(f"{indent}↳ AGENT [{sa.agent_type}] {sa.description[:60]}")

    for e in sa.entries:
        if e.type != "assistant":
            continue
        ts = _fmt_ts(e.timestamp, short=True)
        for b in _content_blocks(e):
            btype = b.get("type")
            if btype == "text":
                text = _truncate(b.get("text", ""), 200)
                if console:
                    console.print(f"{indent}  [{ts}] [blue]{text}[/]")
                else:
                    print(f"{indent}  [{ts}] {text}")
            elif btype == "thinking" and show_thinking:
                text = _truncate(b.get("thinking", ""), 200)
                if console:
                    console.print(f"{indent}  [{ts}] [dim italic]THINK {text}[/]")
                else:
                    print(f"{indent}  [{ts}] THINK {text}")
            elif btype == "tool_use":
                tool_name = b.get("name", "?")
                tool_id = b.get("id", "")
                inp = json.dumps(b.get("input", {}), ensure_ascii=False)
                inp_str = _truncate(inp, 200)
                if console:
                    console.print(f"{indent}  [{ts}] [yellow]{tool_name}[/] {inp_str}")
                else:
                    print(f"{indent}  [{ts}] {tool_name}  {inp_str}")
                result = sa_result_map.get(tool_id, "")
                if result and not result.startswith("<persisted-output>"):
                    result_str = _truncate(result, 200)
                    if console:
                        console.print(f"{indent}       [dim]→ {result_str}[/]")
                    else:
                        print(f"{indent}       -> {result_str}")


def cmd_tools(session: Session, console, agent: SubagentInfo | None = None):
    if agent:
        _print_header(console, f"Tool Calls [{agent.agent_type}]: {agent.description[:40]}")
        calls = [
            {"entry": e, "block": b, "label": agent.agent_type}
            for e in agent.entries if e.type == "assistant"
            for b in _content_blocks(e) if b.get("type") == "tool_use"
        ]
        calls.sort(key=lambda x: x["entry"].timestamp or datetime.min.replace(tzinfo=timezone.utc))
        result_maps = {agent.agent_type: _tool_result_map(agent.entries)}
    else:
        _print_header(console, f"Tool Calls: {session.session_id[:8]}...")
        calls = _all_tool_calls(session, include_subagents=True)
        result_map_main = _tool_result_map(session.entries)
        result_maps = {"main": result_map_main}
        for sa in session.subagents:
            result_maps[sa.agent_type] = _tool_result_map(sa.entries)

    if console:
        table = Table(box=box.SIMPLE_HEAD)
        table.add_column("時刻", style="green", no_wrap=True)
        table.add_column("Agent", style="magenta")
        table.add_column("Tool", style="yellow")
        table.add_column("Input")
        table.add_column("Result")
        for item in calls:
            e, b, label = item["entry"], item["block"], item["label"]
            ts = _fmt_ts(e.timestamp, short=True)
            tool_name = b.get("name", "?")
            tool_id = b.get("id", "")
            inp = json.dumps(b.get("input", {}), ensure_ascii=False)
            inp_str = _truncate(inp, 80)
            result = result_maps.get(label, {}).get(tool_id, "")
            if result.startswith("<persisted-output>"):
                result_str = "[persisted]"
            else:
                result_str = _truncate(result, 80)
            table.add_row(ts, label, tool_name, inp_str, result_str)
        console.print(table)
    else:
        print(f"{'時刻':<10} {'Agent':<20} {'Tool':<15} {'Input':<50}")
        print("-" * 100)
        for item in calls:
            e, b, label = item["entry"], item["block"], item["label"]
            ts = _fmt_ts(e.timestamp, short=True)
            tool_name = b.get("name", "?")
            inp = json.dumps(b.get("input", {}), ensure_ascii=False)
            print(f"{ts:<10} {label:<20} {tool_name:<15} {_truncate(inp, 50)}")


def _render_agent_summary(sa: SubagentInfo, idx: int | None, console):
    asst_entries = [e for e in sa.entries if e.type == "assistant"]
    tool_calls = sum(1 for e in asst_entries for b in _content_blocks(e) if b.get("type") == "tool_use")
    usage = _sum_usage(asst_entries)

    timestamps = [e.timestamp for e in sa.entries if e.timestamp]
    start_ts = min(timestamps) if timestamps else None
    end_ts = max(timestamps) if timestamps else None
    duration = ""
    if start_ts and end_ts:
        secs = int((end_ts - start_ts).total_seconds())
        duration = f"{secs}s"

    tool_names = list(dict.fromkeys(
        b.get("name", "?")
        for e in asst_entries
        for b in _content_blocks(e)
        if b.get("type") == "tool_use"
    ))

    idx_label = f"[{idx}] " if idx is not None else ""
    if console:
        console.rule(f"[magenta]{idx_label}{sa.agent_type}[/]")
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("Description", sa.description)
        table.add_row("Agent ID", sa.agent_id)
        table.add_row("Tool Use ID (main)", sa.tool_use_id)
        table.add_row("開始〜終了", f"{_fmt_ts(start_ts, True)} ~ {_fmt_ts(end_ts, True)} ({duration})")
        table.add_row("ツール呼び出し", f"{tool_calls} 回 ({', '.join(tool_names)})")
        table.add_row("入力トークン", f"{usage['input']:,}")
        table.add_row("出力トークン", f"{usage['output']:,}")
        table.add_row("キャッシュ作成", f"{usage['cache_create']:,}")
        table.add_row("キャッシュ読取", f"{usage['cache_read']:,}")
        console.print(table)
    else:
        print(f"\n{idx_label}[{sa.agent_type}] {sa.description}")
        print(f"  開始〜終了      : {_fmt_ts(start_ts)} ~ {_fmt_ts(end_ts)} ({duration})")
        print(f"  ツール呼び出し  : {tool_calls} 回 ({', '.join(tool_names)})")
        print(f"  入力トークン    : {usage['input']:,}")
        print(f"  出力トークン    : {usage['output']:,}")


def _render_agent_timeline(sa: SubagentInfo, console, show_thinking: bool = False):
    """サブエージェントの会話を完全表示（インデントなし）"""
    result_map = _tool_result_map(sa.entries)
    for e in sa.entries:
        if e.type not in ("user", "assistant"):
            continue
        ts = _fmt_ts(e.timestamp, short=True)
        if e.type == "user":
            for b in _content_blocks(e):
                if b.get("type") == "text":
                    text = _truncate(b.get("text", ""), TEXT_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [bold green]USER[/] {text}")
                    else:
                        print(f"[{ts}] USER  {text}")
        elif e.type == "assistant":
            for b in _content_blocks(e):
                btype = b.get("type")
                if btype == "text":
                    text = _truncate(b.get("text", ""), TEXT_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [bold blue]ASST[/] {text}")
                    else:
                        print(f"[{ts}] ASST  {text}")
                elif btype == "thinking" and show_thinking:
                    text = _truncate(b.get("thinking", ""), TEXT_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [dim italic]THINK {text}[/]")
                    else:
                        print(f"[{ts}] THINK {text}")
                elif btype == "tool_use":
                    tool_name = b.get("name", "?")
                    tool_id = b.get("id", "")
                    inp = json.dumps(b.get("input", {}), ensure_ascii=False)
                    inp_str = _truncate(inp, TOOL_TRUNCATE)
                    if console:
                        console.print(f"[{ts}] [bold yellow]TOOL[/] [yellow]{tool_name}[/] {inp_str}")
                    else:
                        print(f"[{ts}] TOOL  {tool_name}  {inp_str}")
                    result = result_map.get(tool_id, "")
                    if result and not result.startswith("<persisted-output>"):
                        result_str = _truncate(result, TOOL_TRUNCATE)
                        if console:
                            console.print(f"[{ts}]   [dim]→ {result_str}[/]")
                        else:
                            print(f"[{ts}]   -> {result_str}")


def cmd_agents(session: Session, console, agent: SubagentInfo | None = None):
    if agent:
        _print_header(console, f"Agent Detail: {agent.agent_type} [{agent.agent_id[:8]}]")
        _render_agent_summary(agent, idx=None, console=console)
        _print_header(console, "Timeline")
        _render_agent_timeline(agent, console)
        return

    _print_header(console, f"Subagents: {session.session_id[:8]}...")

    if not session.subagents:
        _print(console, "サブエージェントなし", style="dim")
        return

    for idx, sa in enumerate(session.subagents):
        _render_agent_summary(sa, idx=idx, console=console)


def cmd_tokens(session: Session, console, agent: SubagentInfo | None = None):
    if agent:
        _print_header(console, f"Token Usage [{agent.agent_type}]: {agent.description[:40]}")
        asst_entries = [e for e in agent.entries if e.type == "assistant"]
        if console:
            table = Table(box=box.SIMPLE_HEAD)
            table.add_column("時刻", style="green", no_wrap=True)
            table.add_column("Input", justify="right")
            table.add_column("Output", justify="right")
            table.add_column("Cache Write", justify="right")
            table.add_column("Cache Read", justify="right")
            for e in asst_entries:
                u = _usage(e)
                table.add_row(
                    _fmt_ts(e.timestamp, short=True),
                    f"{u.get('input_tokens', 0):,}",
                    f"{u.get('output_tokens', 0):,}",
                    f"{u.get('cache_creation_input_tokens', 0):,}",
                    f"{u.get('cache_read_input_tokens', 0):,}",
                )
            table.add_section()
            totals = _sum_usage(asst_entries)
            table.add_row(
                "[bold]TOTAL[/]",
                f"[bold]{totals['input']:,}[/]",
                f"[bold]{totals['output']:,}[/]",
                f"[bold]{totals['cache_create']:,}[/]",
                f"[bold]{totals['cache_read']:,}[/]",
            )
            console.print(table)
        else:
            print(f"{'時刻':<10} {'Input':>10} {'Output':>10} {'CacheW':>10} {'CacheR':>10}")
            print("-" * 55)
            for e in asst_entries:
                u = _usage(e)
                print(
                    f"{_fmt_ts(e.timestamp, short=True):<10}"
                    f" {u.get('input_tokens', 0):>10,}"
                    f" {u.get('output_tokens', 0):>10,}"
                    f" {u.get('cache_creation_input_tokens', 0):>10,}"
                    f" {u.get('cache_read_input_tokens', 0):>10,}"
                )
            totals = _sum_usage(asst_entries)
            print("-" * 55)
            print(f"{'TOTAL':<10} {totals['input']:>10,} {totals['output']:>10,} {totals['cache_create']:>10,} {totals['cache_read']:>10,}")
        return

    _print_header(console, f"Token Usage: {session.session_id[:8]}...")

    rows = []
    main_u = _sum_usage([e for e in session.entries if e.type == "assistant"])
    rows.append(("main", main_u))
    for sa in session.subagents:
        su = _sum_usage([e for e in sa.entries if e.type == "assistant"])
        rows.append((sa.agent_type, su))

    totals = {k: sum(r[k] for _, r in rows) for k in ("input", "output", "cache_create", "cache_read")}

    if console:
        table = Table(box=box.SIMPLE_HEAD)
        table.add_column("Agent", style="cyan")
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
        table.add_column("Cache Write", justify="right")
        table.add_column("Cache Read", justify="right")
        table.add_column("Total I/O", justify="right")
        for label, u in rows:
            table.add_row(
                label,
                f"{u['input']:,}",
                f"{u['output']:,}",
                f"{u['cache_create']:,}",
                f"{u['cache_read']:,}",
                f"{u['input'] + u['output']:,}",
            )
        table.add_section()
        table.add_row(
            "[bold]TOTAL[/]",
            f"[bold]{totals['input']:,}[/]",
            f"[bold]{totals['output']:,}[/]",
            f"[bold]{totals['cache_create']:,}[/]",
            f"[bold]{totals['cache_read']:,}[/]",
            f"[bold]{totals['input'] + totals['output']:,}[/]",
        )
        console.print(table)
    else:
        print(f"{'Agent':<25} {'Input':>10} {'Output':>10} {'CacheW':>10} {'CacheR':>10}")
        print("-" * 70)
        for label, u in rows:
            print(f"{label:<25} {u['input']:>10,} {u['output']:>10,} {u['cache_create']:>10,} {u['cache_read']:>10,}")
        print("-" * 70)
        print(f"{'TOTAL':<25} {totals['input']:>10,} {totals['output']:>10,} {totals['cache_create']:>10,} {totals['cache_read']:>10,}")


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _to_json(session: Session) -> dict:
    def _entry_dict(e: Entry) -> dict:
        return {
            "type": e.type,
            "uuid": e.uuid,
            "parent_uuid": e.parent_uuid,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "agent_id": e.agent_id,
            "message_content": _content_blocks(e),
            "usage": _usage(e),
        }
    return {
        "session_id": session.session_id,
        "entries": [_entry_dict(e) for e in session.entries],
        "subagents": [
            {
                "agent_id": sa.agent_id,
                "agent_type": sa.agent_type,
                "description": sa.description,
                "tool_use_id": sa.tool_use_id,
                "entries": [_entry_dict(e) for e in sa.entries],
            }
            for sa in session.subagents
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code セッションログ調査 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  uv run python log-explorer/main.py --list
  uv run python log-explorer/main.py latest
  uv run python log-explorer/main.py 0c6a9ea5 timeline
  uv run python log-explorer/main.py 0c6a9ea5 tools
  uv run python log-explorer/main.py 0c6a9ea5 agents
  uv run python log-explorer/main.py 0c6a9ea5 tokens
  uv run python log-explorer/main.py 0c6a9ea5 timeline --thinking
        """,
    )
    parser.add_argument("session_id", nargs="?", help="セッション ID (UUID またはプレフィックス、'latest' 可)")
    parser.add_argument("subcommand", nargs="?", default="summary",
                        choices=["summary", "timeline", "tools", "agents", "tokens"],
                        help="サブコマンド (default: summary)")
    parser.add_argument("--list", action="store_true", help="セッション一覧を表示")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR,
                        help=f"ログディレクトリ (default: {DEFAULT_LOG_DIR})")
    parser.add_argument("--json", action="store_true", help="JSON 出力")
    parser.add_argument("--no-color", action="store_true", help="カラー出力を無効化")
    parser.add_argument("--thinking", action="store_true", help="thinking ブロックを表示 (timeline のみ)")
    parser.add_argument("--limit", type=int, default=None, help="表示行数の上限")
    parser.add_argument("-n", type=int, default=20, help="--list の表示件数 (default: 20)")
    parser.add_argument(
        "--agent", default=None,
        help="サブエージェントを指定 (インデックス番号 / agent_id プレフィックス / agent_type名)",
    )

    args = parser.parse_args()

    console = _make_console(args.no_color or args.json) if not args.json else None

    if args.list:
        cmd_list(args.log_dir, args.n, console)
        return

    if not args.session_id:
        parser.print_help()
        sys.exit(1)

    session_id = resolve_session_id(args.session_id, args.log_dir)
    session = load_session(session_id, args.log_dir)

    if args.json:
        print(json.dumps(_to_json(session), ensure_ascii=False, indent=2))
        return

    agent = _resolve_agent(args.agent, session.subagents) if args.agent else None

    cmd = args.subcommand
    if cmd == "summary":
        cmd_summary(session, console)
    elif cmd == "timeline":
        cmd_timeline(session, console, show_thinking=args.thinking, limit=args.limit, agent=agent)
    elif cmd == "tools":
        cmd_tools(session, console, agent=agent)
    elif cmd == "agents":
        cmd_agents(session, console, agent=agent)
    elif cmd == "tokens":
        cmd_tokens(session, console, agent=agent)


if __name__ == "__main__":
    main()
