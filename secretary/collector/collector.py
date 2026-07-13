"""アクティブウィンドウを定期サンプリングしてイベント JSONL に追記する常駐 Collector。

許可リスト（config.yaml collector.allowlist）にマッチしたウィンドウだけを記録する。
連続する同一ウィンドウのサンプルは1レコードに集約し、滞在時間（dwell_seconds）を持たせる。
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import win32gui
import win32process
import yaml

SECRETARY_DIR = Path(__file__).resolve().parent.parent
EVENTS_DIR = SECRETARY_DIR / "data" / "events"


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_foreground_window() -> tuple[str, str] | None:
    """(プロセス名小文字, ウィンドウタイトル) を返す。取得失敗時は None。"""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid).name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    return process, title


def match_allowlist(process: str, title: str, allowlist: list[dict]) -> bool:
    for rule in allowlist:
        if process != rule["process"].lower():
            continue
        pattern = rule.get("title_pattern")
        if pattern is None or re.search(pattern, title):
            return True
    return False


def append_event(record: dict) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EVENTS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(config: dict) -> None:
    interval = config["collector"].get("poll_interval_seconds", 10)
    # 同一ウィンドウが続く場合もこの秒数ごとにレコードを区切る（プロセス強制終了時の取りこぼし防止）
    flush_max = config["collector"].get("flush_max_seconds", 300)
    allowlist = config["collector"]["allowlist"]

    current: dict | None = None  # 集約中のウィンドウ {process, title, start, samples}

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        append_event({
            "ts": current["start"],
            "process": current["process"],
            "title": current["title"],
            "dwell_seconds": current["samples"] * interval,
        })
        current = None

    print(f"[collector] started (interval={interval}s). Ctrl+C to stop.", file=sys.stderr)
    try:
        while True:
            info = get_foreground_window()
            if info is not None:
                process, title = info
                if match_allowlist(process, title, allowlist):
                    if current and current["process"] == process and current["title"] == title:
                        current["samples"] += 1
                        if current["samples"] * interval >= flush_max:
                            flush()
                    else:
                        flush()
                        current = {
                            "process": process,
                            "title": title,
                            "start": datetime.now(timezone.utc).isoformat(),
                            "samples": 1,
                        }
                else:
                    flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        flush()
        print("[collector] stopped.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(SECRETARY_DIR / "config.yaml"))
    args = parser.parse_args()
    run(load_config(Path(args.config)))


if __name__ == "__main__":
    main()
