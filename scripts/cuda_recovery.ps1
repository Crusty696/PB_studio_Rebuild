# CUDA-Recovery — repariert einen "CUDA unknown error" Stuck-State der NVIDIA-GPU
# ohne Computer-Neustart. Muss als Admin ausgefuehrt werden.
#
# Was es tut:
#   1. Killt ALLE Python-Prozesse (inkl. die im Kernel-Call verstuckten)
#   2. Disabled + Enabled die NVIDIA-GPU via PnPUtil
#   3. Verifiziert dass torch.cuda.is_available() wieder True liefert
#
# Aufruf (User-Perspektive):
#   Aus erhoehter PowerShell, oder:
#   powershell -ExecutionPolicy Bypass -File scripts\cuda_recovery.ps1
#   (falls als Nicht-Admin gestartet: Skript versucht Self-Elevation)

param(
    [string]$VenvPython = "",
    [string]$GpuInstanceId = "PCI\VEN_10DE&DEV_1C20&SUBSYS_00241414&REV_A1\4&3B87FCA8&0&00E4"
)

function Write-Step($msg) {
    Write-Host "[CUDA-Recovery] $msg" -ForegroundColor Cyan
}

# Self-elevate via UAC wenn nicht bereits Admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Step "Fordere Admin-Rechte an (UAC-Prompt folgt)..."
    $args = "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($VenvPython) { $args += " -VenvPython `"$VenvPython`"" }
    Start-Process powershell -Verb RunAs -ArgumentList $args
    exit
}

Write-Step "Als Administrator laufend. Starte Recovery..."

# 1. Python-Prozesse hart beenden (auch die im Kernel-Call verstuckten)
Write-Step "Schritt 1: Python-Prozesse beenden"
$pythons = Get-Process python -ErrorAction SilentlyContinue
if ($pythons) {
    foreach ($p in $pythons) {
        Write-Host "   Kill PID $($p.Id) (Mem $([math]::Round($p.WorkingSet/1MB,0)) MB)"
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
        } catch {
            Write-Host "   Konnte $($p.Id) nicht beenden: $_" -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host "   Keine Python-Prozesse aktiv."
}

# 2. NVIDIA GPU disable + enable
Write-Step "Schritt 2: NVIDIA-GPU Reset"
Write-Host "   InstanceId: $GpuInstanceId"
try {
    Disable-PnpDevice -InstanceId $GpuInstanceId -Confirm:$false -ErrorAction Stop
    Write-Host "   GPU disabled" -ForegroundColor Yellow
    Start-Sleep -Seconds 3
    Enable-PnpDevice -InstanceId $GpuInstanceId -Confirm:$false -ErrorAction Stop
    Write-Host "   GPU enabled" -ForegroundColor Green
    Start-Sleep -Seconds 3
} catch {
    Write-Host "   FEHLER beim GPU-Reset: $_" -ForegroundColor Red
    Write-Host "   Fallback: Computer-Neustart bleibt die Option."
    Read-Host "Enter zum Beenden"
    exit 1
}

# 3. CUDA-Verifikation im frischen Python-Prozess
Write-Step "Schritt 3: CUDA-Verifikation"
$projectDir = Split-Path -Parent $PSCommandPath | Split-Path -Parent
if (-not $VenvPython) {
    $VenvPython = Join-Path $projectDir ".venv310\Scripts\python.exe"
}
if (Test-Path $VenvPython) {
    $output = & $VenvPython -c "import torch; print('TORCH', torch.__version__); print('CUDA_AVAIL', torch.cuda.is_available()); print('DEVICE', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'n/a')" 2>&1
    Write-Host ($output -join "`n")
    if ($output -match "CUDA_AVAIL True") {
        Write-Step "CUDA ist wieder aktiv! App kann normal gestartet werden." -ForegroundColor Green
    } else {
        Write-Host "[WARNUNG] CUDA weiterhin nicht aktiv. Computer-Neustart erforderlich." -ForegroundColor Red
    }
} else {
    Write-Host "   venv-Python nicht gefunden: $VenvPython" -ForegroundColor Yellow
    Write-Host "   Manuelle Verifikation: python -c `"import torch; print(torch.cuda.is_available())`""
}

Write-Host "`nFertig. Fenster schliesst in 10s..." -ForegroundColor Cyan
Start-Sleep -Seconds 10
