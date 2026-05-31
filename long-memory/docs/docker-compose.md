# Long-Memory Docker Compose 設計（WSL2 Ubuntu-24.04）

## ファイル配置

```
long-memory/
  docker/
    docker-compose.yml
    neo4j/
      conf/
        neo4j.conf       # ベクトル検索プラグイン有効化設定
```

---

## docker-compose.yml

```yaml
version: "3.8"

services:
  neo4j:
    image: neo4j:5.20-community
    # ベクトル検索は Community Edition でも利用可能（5.11 以降）
    container_name: long-memory-neo4j
    environment:
      NEO4J_AUTH: neo4j/longmemory  # 本番環境では変更すること
      NEO4J_server_memory_heap_initial__size: 512m
      NEO4J_server_memory_heap_max__size: 2G
    ports:
      - "7474:7474"   # Neo4j Browser
      - "7687:7687"   # Bolt プロトコル（Python ドライバー接続先）
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - ./neo4j/conf:/conf
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
```

> **注意**: WSL2 上で実行するため、Windows 側の Python スクリプトからは  
> `bolt://localhost:7687` で接続可能（WSL2 はホスト側の localhost にポートフォワードされる）。

---

## 起動手順

```bash
# WSL2 Ubuntu-24.04 上で実行
wsl -d Ubuntu-24.04 -- bash -c "cd /mnt/c/claude/long-memory/docker && docker compose up -d"

# 初回: ベクトルインデックスの作成
wsl -d Ubuntu-24.04 -- bash -c "docker exec long-memory-neo4j cypher-shell -u neo4j -p longmemory < /mnt/c/claude/long-memory/scripts/init_schema.cypher"
```
