import json
import os
import sys
from datetime import datetime, timezone

_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "log")
_LOG_PATH = os.path.join(_LOG_DIR, "audit.jsonl")


def _append(record: dict) -> None:
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[mattermost-gate] audit write error: {e}", file=sys.stderr)


def log_request(session_id: str, tool_name: str, tool_input: dict, post_id: str) -> None:
    _append({
        "event": "request",
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "post_id": post_id,
    })


def log_decision(session_id: str, tool_name: str, post_id: str, decision: str, message: str = "") -> None:
    record: dict = {
        "event": "decision",
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "tool_name": tool_name,
        "post_id": post_id,
        "decision": decision,
    }
    if message:
        record["message"] = message
    _append(record)
