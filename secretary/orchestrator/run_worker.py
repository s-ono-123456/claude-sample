"""Worker コンテナを1ジョブ実行する。

- ANTHROPIC_API_KEY は Windows Credential Manager（keyring）から取得して env 注入
- スナップショット :ro / worker 設定 :ro / 共有ディレクトリ rw をマウント
- secretary_internal ネットワーク + egress-proxy 経由で外部到達先を制限
- worker-config.yaml の timeout_minutes を超えたら docker kill
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import keyring
import yaml

from audit import log_event

SECRETARY_DIR = Path(__file__).resolve().parent.parent
WORKER_DIR = SECRETARY_DIR / "worker"


def to_wsl_path(win_path: Path) -> str:
    p = win_path.resolve()
    drive = p.drive.rstrip(":").lower()
    rest = str(p)[len(p.drive):].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(snapshot_dir: Path, config: dict) -> dict:
    job_id = snapshot_dir.name
    wcfg = load_yaml(WORKER_DIR / "worker-config.yaml")
    worker = config["worker"]

    api_key = keyring.get_password(worker["anthropic_key_service"], worker["anthropic_key_username"])
    if not api_key:
        raise SystemExit(
            f"ANTHROPIC_API_KEY が Credential Manager にありません。次で登録してください:\n"
            f'  uv run python -c "import keyring; keyring.set_password('
            f"'{worker['anthropic_key_service']}', '{worker['anthropic_key_username']}', '<APIキー>')\""
        )

    shared_dir = Path(worker["shared_dir"])
    shared_dir.mkdir(parents=True, exist_ok=True)

    container = f"secretary-worker-{job_id}"
    proxy = worker["egress_proxy"]
    docker_cmd = [
        "docker", "run", "--rm", "--name", container,
        "--network", worker["docker_network"],
        "-v", f"{to_wsl_path(snapshot_dir)}:/snapshot:ro",
        "-v", f"{to_wsl_path(WORKER_DIR)}:/config:ro",
        "-v", f"{to_wsl_path(shared_dir)}:/shared",
        "-e", f"JOB_ID={job_id}",
        "-e", "ANTHROPIC_API_KEY",  # 値はコマンドラインに出さず env 経由で渡す
        "-e", f"HTTPS_PROXY={proxy}",
        "-e", f"HTTP_PROXY={proxy}",
        "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
        worker["image"],
    ]
    # wsl.exe に環境変数を持ち込むため WSLENV を利用する
    cmd = ["wsl", "-d", worker["wsl_distro"], "--", *docker_cmd]
    env = {
        **os.environ,
        "ANTHROPIC_API_KEY": api_key,
        "WSLENV": "ANTHROPIC_API_KEY",
    }

    timeout_sec = wcfg.get("timeout_minutes", 15) * 60
    log_event("worker_start", job_id=job_id, snapshot=str(snapshot_dir), image=worker["image"])
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["wsl", "-d", worker["wsl_distro"], "--", "docker", "kill", container],
            capture_output=True, timeout=60,
        )
        log_event("worker_timeout", job_id=job_id, timeout_minutes=wcfg.get("timeout_minutes", 15))
        return {"job_id": job_id, "is_error": True, "error": "timeout"}

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")

    stats: dict = {"job_id": job_id, "is_error": proc.returncode != 0}
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                stats = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    if proc.returncode != 0:
        stats.setdefault("error", stderr[-2000:])
    log_event("worker_end", **stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir")
    parser.add_argument("--config", default=str(SECRETARY_DIR / "config.yaml"))
    args = parser.parse_args()
    stats = run(Path(args.snapshot_dir), load_yaml(Path(args.config)))
    print(json.dumps(stats, ensure_ascii=False))
    sys.exit(1 if stats.get("is_error") else 0)


if __name__ == "__main__":
    main()
