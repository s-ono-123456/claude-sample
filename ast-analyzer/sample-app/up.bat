@echo off
wsl -d Ubuntu-24.04 -e bash -c "DOCKER_BUILDKIT=0 docker compose -f /mnt/c/claude/ast-analyzer/sample-app/docker-compose.yml up --build -d"
