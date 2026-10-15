param(
    [Parameter(Mandatory = $false)]
    [ValidatePattern("^\d{2}:\d{2}$")]
    [string]$Time = "09:00",

    [Parameter(Mandatory = $false)]
    [string]$TaskName = "CrawlerSysDaily",

    [Parameter(Mandatory = $false)]
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "run_main.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Cannot find launcher script: $scriptPath"
}

$runAt = [datetime]::ParseExact($Time, "HH:mm", $null)
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At $runAt
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

$description = "Run crawler_sys daily via uv run main.py"

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $description `
    -Force | Out-Null

Write-Host "Task '$TaskName' registered to run daily at $Time."
Write-Host "Launcher: $scriptPath"
Write-Host "WakeToRun: enabled"

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Task '$TaskName' started."
}
