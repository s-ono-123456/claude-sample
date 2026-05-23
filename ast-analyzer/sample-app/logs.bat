@echo off
wsl -d Ubuntu-24.04 -e bash -c "docker compose -f /mnt/c/claude/ast-analyzer/sample-app/docker-compose.yml logs -f"
