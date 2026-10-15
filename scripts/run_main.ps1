$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs\scheduler"
$uvCacheDir = Join-Path $repoRoot ".uv-cache"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "crawler_task_$timestamp.log"
$crawlerProfile = Join-Path $repoRoot "web"

function Stop-CrawlerChromeProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfilePath,

        [Parameter(Mandatory = $true)]
        [string]$LogPath,

        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    $escapedProfile = [Regex]::Escape($ProfilePath)
    $processes = Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "--user-data-dir=`"?$escapedProfile" }

    foreach ($proc in $processes) {
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Stopping crawler Chrome process $($proc.ProcessId) ($Reason)." |
            Out-File -FilePath $LogPath -Encoding utf8 -Append
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $uvCacheDir | Out-Null
Set-Location $repoRoot

$uvCommand = Get-Command uv -ErrorAction Stop
$env:UV_CACHE_DIR = $uvCacheDir
$env:PYTHONIOENCODING = "utf-8"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting scheduled crawler run." | Out-File -FilePath $logPath -Encoding utf8 -Append
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Working directory: $repoRoot" | Out-File -FilePath $logPath -Encoding utf8 -Append
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Using uv: $($uvCommand.Source)" | Out-File -FilePath $logPath -Encoding utf8 -Append
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Using UV cache: $uvCacheDir" | Out-File -FilePath $logPath -Encoding utf8 -Append
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Using crawler Chrome profile: $crawlerProfile" | Out-File -FilePath $logPath -Encoding utf8 -Append

Stop-CrawlerChromeProcesses -ProfilePath $crawlerProfile -LogPath $logPath -Reason "before run cleanup"

try {
    $stdoutPath = Join-Path $logDir "uv_stdout_$timestamp.log"
    $stderrPath = Join-Path $logDir "uv_stderr_$timestamp.log"
    $process = Start-Process `
        -FilePath $uvCommand.Source `
        -ArgumentList @("run", "main.py") `
        -WorkingDirectory $repoRoot `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath

    if (Test-Path $stdoutPath) {
        Get-Content $stdoutPath | Out-File -FilePath $logPath -Encoding utf8 -Append
    }
    if (Test-Path $stderrPath) {
        Get-Content $stderrPath | Out-File -FilePath $logPath -Encoding utf8 -Append
    }

    $exitCode = $process.ExitCode
}
catch {
    $_ | Out-File -FilePath $logPath -Encoding utf8 -Append
    throw
}
finally {
    Stop-CrawlerChromeProcesses -ProfilePath $crawlerProfile -LogPath $logPath -Reason "after run cleanup"

    if ($null -eq $exitCode) {
        $exitCode = 1
    }
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Finished scheduled crawler run with exit code $exitCode." | Out-File -FilePath $logPath -Encoding utf8 -Append
}

exit $exitCode
