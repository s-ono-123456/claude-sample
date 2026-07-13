# secretary Worker: 使い捨てコンテナで Claude Code (Agent SDK) を単発実行する
FROM python:3.12-slim

# Claude Code CLI は Node.js ランタイムを必要とする
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force

RUN pip install --no-cache-dir claude-agent-sdk pyyaml

# 設定(:ro)・入力(:ro)・出力(rw) は実行時にマウントされる
#   /config /snapshot /shared
COPY worker_main.py /app/worker_main.py

WORKDIR /app
ENTRYPOINT ["python", "/app/worker_main.py"]
