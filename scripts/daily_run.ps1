# Runs the daily job discovery pipeline: ingest new listings, then match
# against your active resume. Designed to be triggered by Windows Task
# Scheduler, not run manually — see README.md for setup steps.
#
# Logs to logs/ with a timestamped filename so you can verify a run
# actually happened and check what it found, without needing to watch it
# live every day.

$ErrorActionPreference = "Continue"  # don't kill the whole run on one bad step

$ProjectDir = "C:\Job Hunter\job-hunter-mvp"
$LogDir = Join-Path $ProjectDir "logs"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$LogFile = Join-Path $LogDir "run_$Timestamp.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Set-Location $ProjectDir
& "$ProjectDir\.venv\Scripts\Activate.ps1"

"=== Daily run started: $(Get-Date) ===" | Tee-Object -FilePath $LogFile -Append

python -m app.ingest 2>&1 | Tee-Object -FilePath $LogFile -Append
python -m app.match 2>&1 | Tee-Object -FilePath $LogFile -Append

"=== Daily run finished: $(Get-Date) ===" | Tee-Object -FilePath $LogFile -Append

# Keep only the last 14 days of logs so this folder doesn't grow forever
Get-ChildItem $LogDir -Filter "run_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force