param(
    [Parameter(Mandatory = $true)]
    [string]$OutputLog,

    [Parameter(Mandatory = $true)]
    [string]$StopFile,

    [string]$AppLog = "",
    [int]$IntervalSec = 2,
    [int]$ProcessSnapshotEverySec = 5,
    [int]$GpuSnapshotEverySec = 5,
    [int]$RelevantProcessEverySec = 10,
    [int]$LogGapWarnSec = 30
)

$ErrorActionPreference = "Stop"

if (-not $AppLog) {
    $AppLog = Join-Path $env:LOCALAPPDATA "PB Studio\_internal\logs\pb_studio.log"
}

$outDir = Split-Path -Parent $OutputLog
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

function Add-MonitorLog {
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

function Get-PbProcess {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -eq "pb_studio" } |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
}

function Get-SystemMemoryLine {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $totalGb = [math]::Round(($os.TotalVisibleMemorySize * 1KB) / 1GB, 3)
        $freeGb = [math]::Round(($os.FreePhysicalMemory * 1KB) / 1GB, 3)
        $usedGb = [math]::Round($totalGb - $freeGb, 3)
        return "[$now] SYS_MEM used_gb=$usedGb free_gb=$freeGb total_gb=$totalGb"
    } catch {
        return "[$now] SYS_MEM error=$($_.Exception.Message)"
    }
}

function Get-PbProcessLine {
    param(
        [object]$Previous,
        [datetime]$PreviousAt
    )

    $nowDt = Get-Date
    $now = $nowDt.ToString("yyyy-MM-dd HH:mm:ss")
    $proc = Get-PbProcess
    if (-not $proc) {
        return [pscustomobject]@{
            Line = "[$now] PB_PROCESS not_running"
            Proc = $null
            CpuPercent = $null
        }
    }

    $cpuPercent = $null
    if ($Previous -and $PreviousAt) {
        $elapsed = ($nowDt - $PreviousAt).TotalSeconds
        if ($elapsed -gt 0) {
            $cpuDelta = [double]$proc.CPU - [double]$Previous.CPU
            $cpuPercent = [math]::Round(($cpuDelta / $elapsed / [Environment]::ProcessorCount) * 100, 1)
        }
    }

    $privateGb = [math]::Round($proc.PrivateMemorySize64 / 1GB, 3)
    $workingGb = [math]::Round($proc.WorkingSet64 / 1GB, 3)
    $cpuTotal = [math]::Round($proc.CPU, 2)
    $cpuText = if ($null -eq $cpuPercent) { "n/a" } else { "$cpuPercent" }
    $line = "[$now] PB_PROCESS pid=$($proc.Id) responding=$($proc.Responding) cpu_pct=$cpuText cpu_s=$cpuTotal private_gb=$privateGb working_gb=$workingGb handles=$($proc.HandleCount) threads=$($proc.Threads.Count) title='$($proc.MainWindowTitle)'"

    if (-not $proc.Responding) {
        $line += " FREEZE_SUSPECT responding_false"
    }
    if ($privateGb -ge 5.0) {
        $line += " MEM_WARN private_gb_ge_5"
    }
    if ($null -ne $cpuPercent -and $cpuPercent -ge 80) {
        $line += " CPU_WARN pct_ge_80"
    }

    return [pscustomobject]@{
        Line = $line
        Proc = $proc
        CpuPercent = $cpuPercent
    }
}

function Get-GpuLines {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $smi = (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)
    if (-not $smi) {
        return @("[$now] GPU nvidia-smi_missing")
    }

    $lines = @()
    try {
        $query = & $smi.Source --query-gpu=name,driver_version,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>$null
        foreach ($row in @($query)) {
            if (-not $row) { continue }
            $parts = $row -split ",\s*"
            if ($parts.Count -ge 8) {
                $lines += "[$now] GPU name='$($parts[0])' driver=$($parts[1]) gpu_pct=$($parts[2]) mem_pct=$($parts[3]) vram_used_mb=$($parts[4]) vram_total_mb=$($parts[5]) temp_c=$($parts[6]) power_w=$($parts[7])"
            } else {
                $lines += "[$now] GPU raw='$row'"
            }
        }
    } catch {
        $lines += "[$now] GPU error=$($_.Exception.Message)"
    }

    try {
        $apps = & $smi.Source --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>$null
        foreach ($row in @($apps)) {
            if ($row) {
                $lines += "[$now] GPU_APP $row"
            }
        }
    } catch {
        $lines += "[$now] GPU_APP error=$($_.Exception.Message)"
    }

    return $lines
}

function Get-RelevantProcessLines {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $names = @("pb_studio", "ffmpeg", "ffprobe", "ollama", "ollama app", "python", "pythonw")
    $procs = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $names -contains $_.ProcessName } |
        Sort-Object ProcessName, Id

    if (-not $procs) {
        return @("[$now] RELEVANT_PROCS none")
    }

    $lines = @()
    foreach ($p in $procs) {
        $privateGb = [math]::Round($p.PrivateMemorySize64 / 1GB, 3)
        $workingGb = [math]::Round($p.WorkingSet64 / 1GB, 3)
        $cpu = if ($null -eq $p.CPU) { "n/a" } else { [math]::Round($p.CPU, 2) }
        $lines += "[$now] RELEVANT_PROC name='$($p.ProcessName)' pid=$($p.Id) cpu_s=$cpu private_gb=$privateGb working_gb=$workingGb responding=$($p.Responding) path='$($p.Path)'"
    }
    return $lines
}

function Convert-AppLogLine {
    param([string]$Line)

    if (-not $Line.Trim()) {
        return $null
    }

    $tag = "APPLOG"
    if ($Line -match "SLOW EVENT|PerfWatchdog") {
        $tag = "APPLOG_PERF"
    } elseif ($Line -match "Analysis started|Analysis completed|\\[PIPELINE\\]|Audio|Demucs|SigLIP|RAFT|Motion|scene_db_storage|vector_db_storage|metadata_extract|keyframe|Timeline|AutoEdit|B-598") {
        $tag = "APPLOG_PIPELINE"
    } elseif ($Line -match "ERROR|CRITICAL|Traceback|Exception|failed|fehlgeschlagen|timed out|timeout") {
        $tag = "APPLOG_ERROR"
    } elseif ($Line -match "WARNING|WARN") {
        $tag = "APPLOG_WARN"
    }
    return "$tag $Line"
}

$started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-MonitorLog ""
Add-MonitorLog "## Enhanced Freeze/Pipeline/Resource Monitor"
Add-MonitorLog "started: $started"
Add-MonitorLog "app_log: $AppLog"
Add-MonitorLog "stop_file: $StopFile"
Add-MonitorLog "interval_sec: $IntervalSec"
Add-MonitorLog ""
Add-MonitorLog (Get-SystemMemoryLine)
foreach ($line in Get-GpuLines) { Add-MonitorLog $line }
foreach ($line in Get-RelevantProcessLines) { Add-MonitorLog $line }

if (Test-Path -LiteralPath $AppLog) {
    $position = (Get-Item -LiteralPath $AppLog).Length
} else {
    $position = 0
    Add-MonitorLog "APP_LOG_MISSING $AppLog"
}

$posRef = [ref]$position
$previousProc = $null
$previousProcAt = Get-Date
$nextProcess = Get-Date
$nextGpu = Get-Date
$nextRelevant = Get-Date
$nextSysMem = Get-Date
$lastAppLogAt = Get-Date

while (-not (Test-Path -LiteralPath $StopFile)) {
    $now = Get-Date
    $text = Read-NewText -Path $AppLog -Position $posRef
    if ($text) {
        $lastAppLogAt = Get-Date
        foreach ($line in ($text -split "`r?`n")) {
            $converted = Convert-AppLogLine -Line $line
            if ($converted) {
                Add-MonitorLog $converted
            }
        }
    }

    if ($now -ge $nextProcess) {
        $snap = Get-PbProcessLine -Previous $previousProc -PreviousAt $previousProcAt
        Add-MonitorLog $snap.Line
        $previousProc = $snap.Proc
        $previousProcAt = Get-Date
        $nextProcess = (Get-Date).AddSeconds($ProcessSnapshotEverySec)
    }

    if ($now -ge $nextSysMem) {
        Add-MonitorLog (Get-SystemMemoryLine)
        $nextSysMem = (Get-Date).AddSeconds($ProcessSnapshotEverySec)
    }

    if ($now -ge $nextGpu) {
        foreach ($line in Get-GpuLines) { Add-MonitorLog $line }
        $nextGpu = (Get-Date).AddSeconds($GpuSnapshotEverySec)
    }

    if ($now -ge $nextRelevant) {
        foreach ($line in Get-RelevantProcessLines) { Add-MonitorLog $line }
        $nextRelevant = (Get-Date).AddSeconds($RelevantProcessEverySec)
    }

    $gapSec = ((Get-Date) - $lastAppLogAt).TotalSeconds
    if ($gapSec -ge $LogGapWarnSec) {
        $gapRounded = [math]::Round($gapSec, 1)
        Add-MonitorLog "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] LOG_GAP_WARN no_new_app_log_for_sec=$gapRounded"
        $lastAppLogAt = Get-Date
    }

    Start-Sleep -Seconds $IntervalSec
}

$stopped = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-MonitorLog "stopped: $stopped"
