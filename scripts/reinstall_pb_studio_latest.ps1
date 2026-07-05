param(
    [switch]$SkipLaunch,
    [int]$OllamaTimeoutSec = 60,
    [int]$InstallTimeoutSec = 300
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[PB-Reinstall] $Message"
}

function Wait-Ollama {
    param([int]$TimeoutSec)

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3
            $count = @($response.models).Count
            Write-Step "Ollama bereit. Modelle=$count"
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    return $false
}

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$installer = Join-Path $repoRoot "dist\pb_studio_setup_v0.5.0.exe"
$payload = Join-Path $repoRoot "dist\pb_studio_setup_v0.5.0.nsisbin"
$distExe = Join-Path $repoRoot "dist\pb_studio\pb_studio.exe"
$installDir = Join-Path $env:LOCALAPPDATA "PB Studio"
$installedExe = Join-Path $installDir "pb_studio.exe"
$ffmpeg = Join-Path $installDir "_internal\bin\ffmpeg.exe"
$ffprobe = Join-Path $installDir "_internal\bin\ffprobe.exe"
$ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"

Write-Step "Repo: $repoRoot"

$runningPb = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -eq "pb_studio" }
if ($runningPb) {
    $ids = ($runningPb | Select-Object -ExpandProperty Id) -join ", "
    throw "PB Studio laeuft noch (PID $ids). Bitte App schliessen und Skript erneut starten."
}

foreach ($required in @($installer, $payload, $distExe)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Fehlt: $required"
    }
}

if (-not (Wait-Ollama -TimeoutSec 3)) {
    if (Test-Path -LiteralPath $ollamaApp) {
        Write-Step "Starte Ollama App: $ollamaApp"
        Start-Process -FilePath $ollamaApp -WindowStyle Hidden | Out-Null
    } else {
        Write-Step "Ollama App nicht gefunden: $ollamaApp"
    }

    if (-not (Wait-Ollama -TimeoutSec $OllamaTimeoutSec)) {
        throw "Ollama nicht erreichbar auf http://127.0.0.1:11434 nach ${OllamaTimeoutSec}s."
    }
}

Write-Step "Installiere PB Studio silent: $installer"
$process = Start-Process -FilePath $installer -ArgumentList "/S" -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit($InstallTimeoutSec * 1000)) {
    throw "Installer laeuft nach ${InstallTimeoutSec}s noch. Installation nicht als erfolgreich gewertet."
}
Write-Step "Installer ExitCode=$($process.ExitCode)"

if ($process.ExitCode -ne 0) {
    throw "Installer fehlgeschlagen. ExitCode=$($process.ExitCode)"
}

if (-not (Test-Path -LiteralPath $installedExe)) {
    throw "Installierte EXE fehlt: $installedExe"
}

$distHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $distExe).Hash
$installedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installedExe).Hash
Write-Step "dist hash=$distHash"
Write-Step "installed hash=$installedHash"
if ($distHash -ne $installedHash) {
    throw "Installierte EXE entspricht nicht dist-Build."
}

foreach ($tool in @($ffmpeg, $ffprobe)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Tool fehlt: $tool"
    }
    $p = Start-Process -FilePath $tool -ArgumentList "-version" -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$env:TEMP\pb_tool_out.txt" -RedirectStandardError "$env:TEMP\pb_tool_err.txt"
    if ($p.ExitCode -ne 0) {
        throw "$tool -version ExitCode=$($p.ExitCode)"
    }
    Write-Step "$(Split-Path $tool -Leaf) OK"
}

if (-not $SkipLaunch) {
    Write-Step "Starte PB Studio: $installedExe"
    $app = Start-Process -FilePath $installedExe -WorkingDirectory $installDir -PassThru
    Start-Sleep -Seconds 5
    $live = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
    if (-not $live) {
        throw "PB Studio Prozess nach Start nicht gefunden."
    }
    Write-Step "PB Studio gestartet. PID=$($live.Id) Responding=$($live.Responding)"
}

Write-Step "Fertig."
