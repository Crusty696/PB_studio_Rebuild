# CUDA TDR-Config — erhoeht den Windows Timeout Detection & Recovery (TDR) Timeout
# von 2s Standard auf 60s. Das reduziert sporadisches "CUDA unknown error"-
# Verhalten auf Surface Book 2 (GTX 1060 Mobile, Treiber 461.40 eingefroren)
# bei kalten CUDA-Initialisierungen und laenger-laufenden Kerneln.
#
# Hintergrund (siehe user_gpu_setup.md in Memory):
#   - Microsoft hat Surface-Book-2-GPU-Treiber im Januar 2021 bei 461.40
#     eingefroren. NVIDIA-Force-Installs brechen Surface-Integrationen.
#   - Bei kalten Starts eines Python-Prozesses blockiert der NVIDIA-Kernel-
#     Driver manchmal > 2s beim ersten CUDA-Kontext-Init. Windows interpretiert
#     das als GPU-Hang (TDR = Timeout Detection & Recovery) und resettet die
#     GPU → torch.cuda.is_available() liefert dauerhaft False mit
#     "CUDA initialization: CUDA unknown error".
#   - TdrDelay=60 gibt dem Treiber 60s Zeit statt 2s, bevor TDR greift.
#
# Was das Skript macht:
#   1. Prueft ob bereits gesetzt (dann nur Ausgabe).
#   2. Setzt HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\TdrDelay = 60
#      (DWORD).
#   3. Fordert zum Neustart auf (Registry-Key wirkt erst nach Reboot).
#
# Reversibilitaet: Das Skript akzeptiert -Restore um TdrDelay wieder zu loeschen
# (Windows-Default = 2s).
#
# Aufruf:
#   powershell -ExecutionPolicy Bypass -File scripts\cuda_tdr_config.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\cuda_tdr_config.ps1 -Restore

param(
    [switch]$Restore,
    [int]$Seconds = 60
)

$ErrorActionPreference = "Stop"
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"

function Write-Step($msg) {
    Write-Host "[TDR-Config] $msg" -ForegroundColor Cyan
}

# Admin-Rechte pruefen + Self-Elevation
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Step "Fordere Admin-Rechte an (UAC-Prompt folgt)..."
    $invokeArgs = "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($Restore) { $invokeArgs += " -Restore" }
    if ($Seconds -ne 60) { $invokeArgs += " -Seconds $Seconds" }
    Start-Process powershell -Verb RunAs -ArgumentList $invokeArgs
    exit
}

# Aktuellen Stand anzeigen
$current = (Get-ItemProperty -Path $regPath -Name TdrDelay -ErrorAction SilentlyContinue).TdrDelay
if ($null -eq $current) {
    Write-Step "Aktueller TdrDelay: nicht gesetzt (Windows-Default = 2s)"
} else {
    Write-Step "Aktueller TdrDelay: $current s"
}

if ($Restore) {
    if ($null -eq $current) {
        Write-Step "Bereits auf Windows-Default (nichts zu tun)."
    } else {
        Remove-ItemProperty -Path $regPath -Name TdrDelay
        Write-Step "TdrDelay geloescht. Windows-Default (2s) greift nach Neustart." -ForegroundColor Yellow
    }
    exit
}

if ($current -eq $Seconds) {
    Write-Step "TdrDelay bereits auf $Seconds s. Kein Aenderung noetig."
    exit
}

Set-ItemProperty -Path $regPath -Name TdrDelay -Value $Seconds -Type DWord
Write-Step "TdrDelay auf $Seconds s gesetzt." -ForegroundColor Green
Write-Step "Neustart erforderlich damit die Aenderung greift." -ForegroundColor Yellow
Write-Host "`nFertig. Fenster schliesst in 10s..."
Start-Sleep -Seconds 10
