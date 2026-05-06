#!/usr/bin/env python3
import atexit
import difflib
import json
import os
import sys

from lib.mattermost import MattermostClient
from lib.precheck import llm_precheck, _VERDICT_EMOJI
from lib import audit, registry

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.md")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


_MAX_BLOCK_CHARS = 3000


def _truncate(text: str, max_chars: int = _MAX_BLOCK_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n… _(以降 {len(text) - max_chars} 文字省略)_"


def _split_command(cmd: str) -> list[str]:
    """Split a shell/PowerShell command at top-level '; ' and ' | ' separators.

    Respects single/double quotes, parentheses, and braces so that separators
    inside strings or scriptblocks are not treated as split points.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_sq = False
    in_dq = False
    i = 0
    n = len(cmd)
    while i < n:
        c = cmd[i]
        if in_sq:
            buf.append(c)
            if c == "'":
                in_sq = False
            i += 1
        elif in_dq:
            if c == '`' and i + 1 < n:
                buf.append(c)
                buf.append(cmd[i + 1])
                i += 2
            else:
                buf.append(c)
                if c == '"':
                    in_dq = False
                i += 1
        elif c == "'":
            in_sq = True
            buf.append(c)
            i += 1
        elif c == '"':
            in_dq = True
            buf.append(c)
            i += 1
        elif c in '({':
            depth += 1
            buf.append(c)
            i += 1
        elif c in ')}':
            depth -= 1
            buf.append(c)
            i += 1
        elif depth == 0 and c == ';' and i + 1 < n and cmd[i + 1] == ' ':
            s = ''.join(buf).strip()
            if s:
                parts.append(s)
            buf = []
            i += 2
        elif depth == 0 and c == ' ' and i + 2 < n and cmd[i + 1] == '|' and cmd[i + 2] == ' ':
            s = ''.join(buf).strip()
            if s:
                parts.append(s)
            buf = ['| ']
            i += 3
        else:
            buf.append(c)
            i += 1
    remaining = ''.join(buf).strip()
    if remaining:
        parts.append(remaining)
    return parts


def _format_command(cmd: str) -> str:
    """Return cmd with newlines added at statement/pipeline boundaries."""
    if '\n' in cmd:
        return cmd
    parts = _split_command(cmd)
    if len(parts) <= 1:
        return cmd
    lines = []
    for part in parts:
        lines.append('    ' + part if part.startswith('| ') else part)
    return '\n'.join(lines)


def format_tool_input(tool_name: str, tool_input: dict) -> str:
    if tool_name in ("Bash", "PowerShell"):
        cmd = _format_command(tool_input.get("command", ""))
        desc = tool_input.get("description", "")
        lines = [f"```\n{cmd}\n```"]
        if desc:
            lines.append(f"_{desc}_")
        return "\n".join(lines)

    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        replace_all = tool_input.get("replace_all", False)
        diff_lines = list(difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        ))
        diff_text = "\n".join(line.rstrip("\n") for line in diff_lines)
        extra = " _(replace_all)_" if replace_all else ""
        header = f"`{path}`{extra}\n"
        if diff_text:
            return header + f"```diff\n{_truncate(diff_text)}\n```"
        return header + "_(変更なし)_"

    if tool_name == "Write":
        path = tool_input.get("file_path", tool_input.get("path", ""))
        content = tool_input.get("content", "")
        header = f"`{path}`\n"
        try:
            with open(path, encoding="utf-8") as f:
                old_content = f.read()
            diff_lines = list(difflib.unified_diff(
                old_content.splitlines(),
                content.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            ))
            diff_text = "\n".join(line.rstrip("\n") for line in diff_lines)
            if diff_text:
                return header + f"```diff\n{_truncate(diff_text)}\n```"
            return header + "_(変更なし)_"
        except FileNotFoundError:
            diff_lines = list(difflib.unified_diff(
                [],
                content.splitlines(),
                fromfile="/dev/null",
                tofile=f"b/{path}",
            ))
            diff_text = "\n".join(line.rstrip("\n") for line in diff_lines)
            return header + "_(新規ファイル)_\n" + f"```diff\n{_truncate(diff_text)}\n```"
        except Exception:
            return header + f"```\n{_truncate(content)}\n```"

    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        offset = tool_input.get("offset")
        limit = tool_input.get("limit")
        detail = f"`{path}`"
        if offset or limit:
            detail += f"  _(offset={offset}, limit={limit})_"
        return detail

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        result = f"パターン: `{pattern}`"
        if path:
            result += f"\nディレクトリ: `{path}`"
        return result

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", ".")
        glob = tool_input.get("glob", "")
        result = f"パターン: `{pattern}`\nパス: `{path}`"
        if glob:
            result += f"\nファイル絞込: `{glob}`"
        return result

    if tool_name == "WebFetch":
        url = tool_input.get("url", "")
        prompt = tool_input.get("prompt", "")
        result = f"URL: {url}"
        if prompt:
            result += f"\n_{_truncate(prompt, 300)}_"
        return result

    if tool_name == "WebSearch":
        return f"検索クエリ: `{tool_input.get('query', '')}`"

    if tool_name == "Agent":
        subagent_type = tool_input.get("subagent_type", "")
        model = tool_input.get("model", "")
        description = tool_input.get("description", "")
        prompt = tool_input.get("prompt", "")
        meta = []
        if subagent_type:
            meta.append(f"タイプ: `{subagent_type}`")
        if model:
            meta.append(f"モデル: `{model}`")
        if description:
            meta.append(f"説明: {description}")
        header = "  ".join(meta) + "\n" if meta else ""
        return header + f"**プロンプト:**\n```\n{_truncate(prompt)}\n```"

    if tool_name == "ExitPlanMode":
        plan = tool_input.get("plan", "")
        plan_file = tool_input.get("planFilePath", "")
        lines = []
        if plan_file:
            lines.append(f"**プランファイル:** `{plan_file}`")
        if plan:
            lines.append("")
            lines.append(_truncate(plan))
        return "\n".join(lines)

    if tool_name == "NotebookEdit":
        path = tool_input.get("notebook_path", "")
        edit_mode = tool_input.get("edit_mode", "replace")
        cell_type = tool_input.get("cell_type", "")
        cell_id = tool_input.get("cell_id", "")
        new_source = tool_input.get("new_source", "")
        meta = f"`{path}`  mode: `{edit_mode}`"
        if cell_id:
            meta += f"  cell: `{cell_id}`"
        if cell_type:
            meta += f"  type: `{cell_type}`"
        if edit_mode == "delete":
            return meta
        lang = "python" if cell_type in ("code", "") else cell_type
        if edit_mode == "replace" and cell_id:
            try:
                with open(path, encoding="utf-8") as f:
                    nb = json.load(f)
                old_source = ""
                for cell in nb.get("cells", []):
                    if cell.get("id") == cell_id:
                        src = cell.get("source", [])
                        old_source = "".join(src) if isinstance(src, list) else src
                        break
                diff_lines = list(difflib.unified_diff(
                    old_source.splitlines(),
                    new_source.splitlines(),
                    fromfile=f"a/{path}#{cell_id}",
                    tofile=f"b/{path}#{cell_id}",
                ))
                diff_text = "\n".join(line.rstrip("\n") for line in diff_lines)
                if diff_text:
                    return meta + f"\n```diff\n{_truncate(diff_text)}\n```"
                return meta + "\n_(変更なし)_"
            except Exception:
                pass
        return meta + f"\n```{lang}\n{_truncate(new_source)}\n```"

    # Generic fallback: show key=value pairs
    pairs = [f"`{k}`: {json.dumps(v, ensure_ascii=False)}" for k, v in tool_input.items()]
    return "\n".join(pairs) if pairs else "(no input)"


def build_message(hook_input: dict, precheck_result: dict | None = None) -> str:
    tool_name = hook_input.get("tool_name", "Unknown")
    tool_input = hook_input.get("tool_input", {})
    cwd = hook_input.get("cwd", "")
    session_id = hook_input.get("session_id", "")

    detail = format_tool_input(tool_name, tool_input)

    lines = [
        "### :bell: Claude Code 承認リクエスト",
        "",
        f"**ツール:** `{tool_name}`",
        f"**作業ディレクトリ:** `{cwd}`",
        f"**セッションID:** `{session_id[:8]}...`" if session_id else None,
        "",
        "**内容:**",
        detail,
    ]

    if precheck_result:
        verdict = precheck_result.get("verdict", "unknown")
        reason = precheck_result.get("reason", "")
        emoji = _VERDICT_EMOJI.get(verdict, "❓")
        lines += [
            "",
            "### 🤖 AI事前審査",
            "",
            "| verdict | reason |",
            "|---|---|",
            f"| {emoji} {verdict} | {reason} |",
        ]

    lines += [
        "",
        "---",
        "✅ で承認、❌ で拒否してください",
    ]
    return "\n".join(line for line in lines if line is not None)


def output_decision(decision: str, reason: str = "") -> None:
    result = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": decision,
            },
        }
    }
    if decision == "deny" and reason:
        result["hookSpecificOutput"]["decision"]["message"] = reason
    print(json.dumps(result, ensure_ascii=False))


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"[mattermost-gate] failed to parse stdin: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        config = load_config()
    except Exception as e:
        print(f"[mattermost-gate] failed to load config: {e}", file=sys.stderr)
        sys.exit(2)

    policy = None
    if os.path.exists(POLICY_PATH):
        try:
            with open(POLICY_PATH, encoding="utf-8") as f:
                policy = f.read()
        except Exception as e:
            print(f"[mattermost-gate] failed to load policy: {e}", file=sys.stderr)

    precheck_result = None
    if policy:
        precheck_result = llm_precheck(hook_input, policy)

    try:
        client = MattermostClient(config)
        bot_user_id = client.get_bot_user_id()
    except Exception as e:
        print(f"[mattermost-gate] failed to initialize Mattermost client: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        message = build_message(hook_input, precheck_result)
        post_id = client.post_message(message)
    except Exception as e:
        print(f"[mattermost-gate] failed to send message: {e}", file=sys.stderr)
        sys.exit(2)

    session_id = hook_input.get("session_id", "")
    tool_name = hook_input.get("tool_name", "")
    terminal_emoji = config.get("terminal_emoji", "computer")
    registry_key = registry.create_entry(session_id, tool_name, post_id)
    atexit.register(registry.delete_entry, session_id, registry_key)
    audit.log_request(session_id, tool_name, hook_input.get("tool_input", {}), post_id)

    approve_emoji = config.get("approve_emoji", "white_check_mark")
    deny_emoji = config.get("deny_emoji", "x")
    for emoji in (approve_emoji, deny_emoji):
        try:
            client.add_reaction(bot_user_id, post_id, emoji)
        except Exception as e:
            print(f"[mattermost-gate] failed to add reaction {emoji}: {e}", file=sys.stderr)

    decision = client.poll_for_decision(post_id, bot_user_id, terminal_emoji)

    if decision == "cancelled":
        audit.log_decision(session_id, tool_name, post_id, "cancelled")
        sys.exit(0)
    elif decision == "allow":
        audit.log_decision(session_id, tool_name, post_id, "allow")
        output_decision("allow")
    elif decision == "deny":
        reply_timeout = config.get("deny_reply_timeout_seconds", 60)
        reply = client.poll_for_thread_reply(post_id, bot_user_id, reply_timeout)
        deny_message = reply if reply else "Mattermost で拒否されました"
        audit.log_decision(session_id, tool_name, post_id, "deny", deny_message)
        output_decision("deny", deny_message)
    else:  # timeout
        audit.log_decision(session_id, tool_name, post_id, "timeout")
        try:
            client.post_reply(post_id, ":alarm_clock: タイムアウトしました。ターミナルで承認/拒否してください。")
        except Exception as e:
            print(f"[mattermost-gate] failed to post timeout reply: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
