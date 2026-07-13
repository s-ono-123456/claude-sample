# secretary 30-min pipeline (invoked by Task Scheduler)
#   1. build snapshot -> 2. run worker -> 3. collect results & post to Mattermost
# NOTE: keep this file ASCII-only (PowerShell 5.1 misreads UTF-8 without BOM)
$ErrorActionPreference = "Stop"
Set-Location "C:\claude"

# 1. snapshot_builder (last stdout line = snapshot path)
$snapshotDir = (uv run python secretary\orchestrator\snapshot_builder.py --config secretary\config.yaml | Select-Object -Last 1)
if (-not $snapshotDir) { throw "snapshot_builder failed" }
$jobId = Split-Path $snapshotDir -Leaf
Write-Host "[pipeline] snapshot: $snapshotDir"

# 2. run worker (attempt collection even if it fails)
uv run python secretary\orchestrator\run_worker.py $snapshotDir --config secretary\config.yaml
if ($LASTEXITCODE -ne 0) { Write-Warning "[pipeline] worker exited with $LASTEXITCODE" }

# 3. collect results and post (silent when action:none)
uv run python secretary\orchestrator\collect_and_post.py $jobId --config secretary\config.yaml

Write-Host "[pipeline] done: $jobId"
