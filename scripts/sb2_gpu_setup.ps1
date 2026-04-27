# Surface-Book-2 GPU-Setup -- VORBEUGENDE Settings, kein reaktiver BSOD-Pfad.
#
# Setzt System-Settings, die laut Web-Recherche die Code-47-Haeufigkeit
# auf SB2 reduzieren. KEINE Disable/Enable-Aktion auf der GPU -- das
# Risiko ist in D-022 + B-098 dokumentiert (Word-Dokument-Verlust durch
# Auto-Reboot). Reine Konfigurations-Aenderungen, jederzeit zurueckdrehbar.
#
# Was es tut:
#   1. Diagnose: aktueller GPU-State, Treiber-Version, Power-Plan
#   2. PCIe Link State Power Management auf OFF (verhindert dGPU D3-Cold)
#   3. NVIDIA-Optimus Settings auslesen + Empfehlung anzeigen
#      (das Setzen muss der User im NVIDIA Control Panel machen -- keine
#      sichere CLI-API dafuer)
#   4. Reset-Anleitung: was tun bei Code-47 (Reboot ODER Tablet-Detach)
#
# Aufruf:
#   powershell -ExecutionPolicy Bypass -File scripts\sb2_gpu_setup.ps1
#   (braucht Admin-Rechte fuer Power-Plan-Aenderung; Self-Elevation via UAC)

param(
    [switch]$DryRun = $false,
    [switch]$NoElevate = $false
)

function Write-Hdr {
    param([string]$msg)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host $msg -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
}

function Write-OK {
    param([string]$label, [string]$value)
    Write-Host "[OK]  $($label): $value" -ForegroundColor Green
}

function Write-Warn2 {
    param([string]$label, [string]$value)
    Write-Host "[!!]  $($label): $value" -ForegroundColor Yellow
}

function Write-Info {
    param([string]$label, [string]$value)
    Write-Host "      $($label): $value"
}

# Self-elevate via UAC wenn noetig
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ((-not $isAdmin) -and (-not $NoElevate)) {
    Write-Host "Fordere Admin-Rechte an (UAC-Prompt folgt)..." -ForegroundColor Yellow
    $argList = "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($DryRun) { $argList += " -DryRun" }
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit 0
}

# === 1. Diagnose ==========================================================
Write-Hdr "1. GPU-Diagnose"

$nvidia = Get-PnpDevice -Class Display -PresentOnly | Where-Object { $_.FriendlyName -like '*NVIDIA*' }
if (-not $nvidia) {
    Write-Warn2 "NVIDIA-GPU" "nicht gefunden"
    Write-Host "Dieses Skript ist fuer Surface Book 2 mit NVIDIA dGPU gedacht." -ForegroundColor Yellow
    Write-Host "Wenn du auf einem anderen System bist: nichts zu tun, schliesse das Fenster." -ForegroundColor Yellow
    exit 0
}

if ($nvidia.Status -eq "OK") {
    $msg = "$($nvidia.FriendlyName) -- OK ($($nvidia.Problem))"
    Write-OK "GPU-Status" $msg
} else {
    $msg = "$($nvidia.FriendlyName) -- $($nvidia.Status) ($($nvidia.Problem))"
    Write-Warn2 "GPU-Status" $msg
    if ($nvidia.Problem -eq 'CM_PROB_HELD_FOR_EJECT') {
        Write-Host ""
        Write-Host "  >> Code 47 erkannt. Vorbeugende Settings koennen das nicht reparieren --" -ForegroundColor Yellow
        Write-Host "     dafuer brauchst du Reboot oder Tablet-Detach+Reattach." -ForegroundColor Yellow
        Write-Host "     Das Skript laeuft trotzdem weiter und konfiguriert die Settings," -ForegroundColor Yellow
        Write-Host "     damit der naechste Vorfall hoffentlich seltener wird." -ForegroundColor Yellow
    }
}

$nvWmi = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like '*NVIDIA*' } | Select-Object -First 1
if ($nvWmi) {
    Write-Info "Treiber-Version" $nvWmi.DriverVersion
    Write-Info "Treiber-Datum" $nvWmi.DriverDate
}

$schemeRaw = (powercfg /getactivescheme)
Write-Info "Energiesparplan" $schemeRaw

# === 2. PCIe Link State Power Management ==================================
Write-Hdr "2. PCIe Link State Power Management"

# GUID: ee12f906-d277-404b-b6da-e5fa1a576df5  -> "PCI Express"
# Sub:  501a4d13-42af-4429-9fd1-a8218c268e20  -> "Verbindungszustand-Energieverwaltung"
# 0 = Aus, 1 = Moderate, 2 = Maximum

$pcieGuid = 'ee12f906-d277-404b-b6da-e5fa1a576df5'
$linkStateGuid = '501a4d13-42af-4429-9fd1-a8218c268e20'

if ($DryRun) {
    Write-Host "[DryRun] Wuerde setzen: PCIe LinkState = OFF (AC + DC)" -ForegroundColor Yellow
} else {
    Write-Host "Setze PCIe Link State Power Management auf 'Aus' (AC + DC)..." -ForegroundColor Cyan
    powercfg /setacvalueindex SCHEME_CURRENT $pcieGuid $linkStateGuid 0 | Out-Null
    powercfg /setdcvalueindex SCHEME_CURRENT $pcieGuid $linkStateGuid 0 | Out-Null
    powercfg /S SCHEME_CURRENT | Out-Null
    Write-OK "PCIe LinkState" "OFF (AC + DC) -- verhindert dGPU-D3-Cold im Idle"
    Write-Info "Effekt" "marginal hoehere Idle-Leistung, dafuer keine Code-47-Trigger durch PCIe-Sleep"
    $rollback = "powercfg /setacvalueindex SCHEME_CURRENT $pcieGuid $linkStateGuid 2"
    Write-Info "Rueckgaengig" $rollback
}

# === 3. NVIDIA Optimus Settings -- Diagnose only ==========================
Write-Hdr "3. NVIDIA Optimus Bevorzugter Prozessor"

# Die Optimus-Settings sind im Registry-Key des NVIDIA-Treibers, aber das
# Setzen von "Bevorzugter Grafikprozessor" auf "High Performance NVIDIA" ist
# ueber das NVIDIA Control Panel sicher -- Skript-Aenderung kann den Treiber
# inkonsistent lassen. Daher nur Diagnose + Anweisung.

$nvBaseKey = 'HKLM:\SOFTWARE\NVIDIA Corporation\Global\NVTweak'
if (Test-Path $nvBaseKey) {
    Write-OK "NVIDIA-Treiber-Registry" "vorhanden"
} else {
    Write-Warn2 "NVIDIA-Treiber-Registry" "nicht gefunden -- NVIDIA Control Panel evtl. nicht installiert"
}

Write-Host ""
Write-Host "Empfohlen (manuell im NVIDIA Control Panel):" -ForegroundColor Cyan
Write-Host "   1. Rechtsklick auf Desktop -- 'NVIDIA Systemsteuerung'" -ForegroundColor White
Write-Host "   2. '3D-Einstellungen verwalten' -- Tab 'Globale Einstellungen'" -ForegroundColor White
Write-Host "   3. 'Bevorzugter Grafikprozessor' -- 'Hochleistungs-NVIDIA-Prozessor'" -ForegroundColor White
Write-Host "   4. 'Anwenden' klicken" -ForegroundColor White
Write-Host ""
Write-Host "Effekt: dGPU bleibt aktiv statt automatisch auszuschalten." -ForegroundColor Cyan
Write-Host "        Reduziert Code-47-Haeufigkeit deutlich. Stromverbrauch leicht hoeher." -ForegroundColor Cyan

# === 4. Recovery-Anleitung ================================================
Write-Hdr "4. Was tun bei Code-47-Vorfall"

Write-Host "Wenn die GPU trotz dieser Settings in Code-47 faellt, zwei sichere Wege:" -ForegroundColor White
Write-Host ""
Write-Host "  A: Computer neu starten -- zuverlaessig, dauert etwa 30s." -ForegroundColor Green
Write-Host "     Speichere ALLE offenen Programme zuerst (Word, Browser etc.)." -ForegroundColor Gray
Write-Host ""
Write-Host "  B: Tablet vom Keyboard abnehmen, wieder ansetzen, Geraete-Manager F5." -ForegroundColor Green
Write-Host "     Surface Book 2 spezifisch, oft erfolgreich, kein Reboot." -ForegroundColor Gray
Write-Host ""
Write-Host "  C: Risiko-Pfad NUR im Notfall: scripts\cuda_recovery.ps1" -ForegroundColor Yellow
Write-Host "     Disable+Enable der NVIDIA-GPU. Hat in B-098 zu Word-Dokument-" -ForegroundColor Gray
Write-Host "     Verlust gefuehrt durch Auto-Reboot. Nur bewusst und gespeichert nutzen." -ForegroundColor Gray

Write-Hdr "Setup abgeschlossen"
Write-Host "Naechste Schritte fuer dich:" -ForegroundColor Cyan
Write-Host "  1. NVIDIA Control Panel -- 'Hochleistungs-NVIDIA-Prozessor' setzen (siehe oben)" -ForegroundColor White
Write-Host "  2. Wenn GPU gerade in Code-47: Reboot oder Tablet-Detach+Reattach" -ForegroundColor White
Write-Host "  3. App neu starten" -ForegroundColor White
Write-Host ""
if (-not $NoElevate) {
    Write-Host "Druecke eine Taste um zu schliessen..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
