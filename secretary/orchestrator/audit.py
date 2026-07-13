"""監査ログ（secretary/log/audit.jsonl）。mattermost-gate の audit.py パターンを踏襲。"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "log"
_LOG_PATH = _LOG_DIR / "audit.jsonl"


def log_event(event: str, **fields) -> None:
    record = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields}
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[secretary] audit write error: {e}", file=sys.stderr)
