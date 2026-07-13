# Register Task Scheduler entries (run manually, once)
#   - secretary-pipeline : run pipeline.ps1 every 30 minutes
#   - secretary-collector: start the collector at logon
# Remove: schtasks /delete /tn secretary-pipeline /f; schtasks /delete /tn secretary-collector /f
# NOTE: keep this file ASCII-only (PowerShell 5.1 misreads UTF-8 without BOM)

$pipeline = "powershell -NoProfile -ExecutionPolicy Bypass -File C:\claude\secretary\orchestrator\pipeline.ps1"
schtasks /create /f /tn "secretary-pipeline" /sc minute /mo 30 /tr $pipeline

$collector = "C:\claude\.venv\Scripts\pythonw.exe C:\claude\secretary\collector\collector.py"
schtasks /create /f /tn "secretary-collector" /sc onlogon /tr $collector

Write-Host "Registered. Verify with: schtasks /query /tn secretary-pipeline"
