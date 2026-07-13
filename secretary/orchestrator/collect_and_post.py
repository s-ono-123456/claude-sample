"""Worker の成果物を回収し、成果があった場合のみ Mattermost に投稿する。

- summary.json の action が "none" → 無音（audit のみ）
- action が "report" → 秘書チャンネルへ成果サマリ + ファイルパスを投稿
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from audit import log_event

SECRETARY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SECRETARY_DIR.parent / "mattermost-gate"))
from lib.mattermost import MattermostClient  # noqa: E402


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(job_id: str, config: dict) -> None:
    shared_dir = Path(config["worker"]["shared_dir"])
    summary_path = shared_dir / job_id / "summary.json"

    if not summary_path.exists():
        log_event("collect_missing_summary", job_id=job_id)
        print(f"[secretary] summary.json がありません: {summary_path}", file=sys.stderr)
        return

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    action = summary.get("action", "none")

    if action != "report":
        log_event("collect_no_action", job_id=job_id, reason=summary.get("reason", ""))
        return

    mm_conf = config["mattermost"]
    gate = json.loads(Path(mm_conf["gate_config"]).read_text(encoding="utf-8"))
    client = MattermostClient({
        "mattermost_url": gate["mattermost_url"],
        "token": gate["token"],
        "channel_id": mm_conf["channel_id"],
    })

    files = summary.get("files", [])
    file_lines = "\n".join(f"- `{shared_dir / job_id / f}`" for f in files)
    message = (
        f"#### :bulb: {summary.get('title', '秘書からの提案')}\n"
        f"{summary.get('reason', '')}\n\n"
        f"**成果物:**\n{file_lines}\n\n"
        f"`job: {job_id}`"
    )
    post_id = client.post_message(message)
    log_event("posted", job_id=job_id, post_id=post_id, title=summary.get("title", ""))
    print(f"[secretary] posted: {post_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--config", default=str(SECRETARY_DIR / "config.yaml"))
    args = parser.parse_args()
    run(args.job_id, load_yaml(Path(args.config)))


if __name__ == "__main__":
    main()
