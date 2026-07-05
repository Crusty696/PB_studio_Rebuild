param(
    [Parameter(Mandatory = $true)]
    [string]$OutputLog,

    [Parameter(Mandatory = $true)]
    [string]$StopFile,

    [string]$AppLog = "",
    [int]$IntervalSec = 2,
    [int]$ProcessSnapshotEverySec = 10
)

$ErrorActionPreference = "Stop"

if (-not $AppLog) {
    $AppLog = Join-Path $env:LOCALAPPDATA "PB Studio\_internal\logs\pb_studio.log"
}

$outDir = Split-Path -Parent $OutputLog
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

function Add-ManualLog {
    param([string]$Text)
    Add-Content -LiteralPath $OutputLog -Value $Text -Encoding UTF8
}

function Read-NewText {
    param(
        [string]$Path,
        [ref]$Position
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }

    $fs = $null
    $reader = $null
    try {
        $fs = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        if ($Position.Value -gt $fs.Length) {
            $Position.Value = 0
        }
        [void]$fs.Seek([int64]$Position.Value, [System.IO.SeekOrigin]::Begin)
        $reader = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8, $true)
        $text = $reader.ReadToEnd()
        $Position.Value = $fs.Position
        return $text
    } finally {
        if ($reader) {
            $reader.Dispose()
        } elseif ($fs) {
            $fs.Dispose()
        }
    }
}

function Format-ProcessSnapshot {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $proc = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -eq "pb_studio" } |
        Select-Object -First 1

    if (-not $proc) {
        return "[$now] PROCESS pb_studio not running"
    }

    $privateGb = [math]::Round($proc.PrivateMemorySize64 / 1GB, 3)
    $workingGb = [math]::Round($proc.WorkingSet64 / 1GB, 3)
    $cpu = [math]::Round($proc.CPU, 2)
    return "[$now] PROCESS pid=$($proc.Id) responding=$($proc.Responding) cpu_s=$cpu private_gb=$privateGb working_gb=$workingGb title='$($proc.MainWindowTitle)'"
}

$started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-ManualLog "# PB Studio Manual Test Log"
Add-ManualLog ""
Add-ManualLog "started: $started"
Add-ManualLog "app_log: $AppLog"
Add-ManualLog "stop_file: $StopFile"
Add-ManualLog ""
Add-ManualLog "## Initial Process"
Add-ManualLog (Format-ProcessSnapshot)
Add-ManualLog ""
Add-ManualLog "## App Log Tail At Start"
if (Test-Path -LiteralPath $AppLog) {
    Get-Content -LiteralPath $AppLog -Tail 80 | ForEach-Object {
        Add-ManualLog $_
    }
    $position = (Get-Item -LiteralPath $AppLog).Length
} else {
    Add-ManualLog "APP_LOG_MISSING"
    $position = 0
}
Add-ManualLog ""
Add-ManualLog "## Live Events"

$posRef = [ref]$position
$nextSnapshot = Get-Date

while (-not (Test-Path -LiteralPath $StopFile)) {
    $text = Read-NewText -Path $AppLog -Position $posRef
    if ($text) {
        $trimmed = $text.TrimEnd()
        if ($trimmed) {
            Add-ManualLog $trimmed
        }
    }

    if ((Get-Date) -ge $nextSnapshot) {
        Add-ManualLog (Format-ProcessSnapshot)
        $nextSnapshot = (Get-Date).AddSeconds($ProcessSnapshotEverySec)
    }

    Start-Sleep -Seconds $IntervalSec
}

$stopped = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-ManualLog ""
Add-ManualLog "stopped: $stopped"
