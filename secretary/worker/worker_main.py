"""Worker エントリポイント: worker-config.yaml を読んで Claude Code を単発実行する。

コンテナ内契約:
  /config/worker-config.yaml (:ro)  … ClaudeAgentOptions とジョブ指示
  /config/system_prompt.md   (:ro)  … システムプロンプト
  /snapshot                  (:ro)  … Orchestrator が生成した入力
  /shared                    (rw)   … 成果物の出力先（唯一の書き込み先）
  env JOB_ID                        … ジョブ ID（/shared/{JOB_ID}/ に出力）
  env ANTHROPIC_API_KEY             … 支出上限つき専用キー

stdout の最終行に実行統計 JSON を1行出力する（Orchestrator が監査ログに記録する）。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import yaml
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

CONFIG_PATH = Path("/config/worker-config.yaml")


async def run() -> int:
    job_id = os.environ["JOB_ID"]
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    out_dir = Path("/shared") / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    options = ClaudeAgentOptions(
        system_prompt=Path(cfg["system_prompt_file"]).read_text(encoding="utf-8"),
        allowed_tools=cfg["allowed_tools"],
        permission_mode=cfg["permission_mode"],
        max_turns=cfg["max_turns"],
        cwd=cfg["cwd"],
    )
    if cfg.get("model"):
        options.model = cfg["model"]
    if cfg.get("mcp_servers"):
        options.mcp_servers = cfg["mcp_servers"]

    prompt = cfg["job_prompt"].replace("{job_id}", job_id)

    stats: dict = {"job_id": job_id, "is_error": True}
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            stats = {
                "job_id": job_id,
                "is_error": message.is_error,
                "num_turns": message.num_turns,
                "duration_ms": message.duration_ms,
                "total_cost_usd": message.total_cost_usd,
                "usage": getattr(message, "usage", None),
            }

    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        # Worker が summary を書かずに終わった場合も回収可能にする
        summary_path.write_text(
            json.dumps({"action": "none", "reason": "worker が summary.json を出力しなかった"},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        stats["missing_summary"] = True

    print(json.dumps(stats, ensure_ascii=False))
    return 1 if stats.get("is_error") else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
