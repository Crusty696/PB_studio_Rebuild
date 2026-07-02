param(
    [string]$RepoRoot = "C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease"
)

$ErrorActionPreference = "Stop"

function Write-JsonFile {
    param(
        [string]$Path,
        [object]$Data
    )
    $Data | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$qaDir = Join-Path $RepoRoot "tests\qa_artifacts"
$synthDir = Join-Path $RepoRoot "docs\superpowers\synthesis"
New-Item -ItemType Directory -Force -Path $qaDir, $synthDir | Out-Null

$outJson = Join-Path $qaDir "clean_vm_sandbox_probe.json"
$outMd = Join-Path $synthDir "clean-vm-sandbox-install-proof-2026-07-02.md"
$installer = Join-Path $RepoRoot "dist\pb_studio_setup_v0.5.0.exe"
$payload = Join-Path $RepoRoot "dist\pb_studio_setup_v0.5.0.nsisbin"
$installExe = Join-Path $env:LOCALAPPDATA "PB Studio\pb_studio.exe"
$uninstallExe = Join-Path $env:LOCALAPPDATA "PB Studio\Uninstall.exe"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PBStudio"

$result = [ordered]@{
    status = "fail"
    proof_type = "clean-vm-install"
    evidence_level = "live"
    started_at = (Get-Date).ToString("o")
    repo_root = $RepoRoot
    computer = $env:COMPUTERNAME
    user = $env:USERNAME
    os = $null
    installer_exists = Test-Path -LiteralPath $installer -PathType Leaf
    payload_exists = Test-Path -LiteralPath $payload -PathType Leaf
    installer_exit_code = $null
    installer_timed_out = $false
    installed_exe_exists = $false
    uninstall_exe_exists = $false
    registry_entry_exists = $false
    registry_entry = $null
    app_started = $false
    app_pid = $null
    blockers = @()
    ended_at = $null
}

try {
    $osInfo = Get-CimInstance Win32_OperatingSystem
    $result.os = [ordered]@{
        caption = $osInfo.Caption
        version = $osInfo.Version
        build = $osInfo.BuildNumber
    }

    if (-not $result.installer_exists) { $result.blockers += "installer-missing" }
    if (-not $result.payload_exists) { $result.blockers += "payload-missing" }
    if ($result.blockers.Count -eq 0) {
        $proc = Start-Process -FilePath $installer -ArgumentList "/S" -PassThru
        if (-not $proc.WaitForExit(1800000)) {
            $result.installer_timed_out = $true
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        } else {
            $result.installer_exit_code = $proc.ExitCode
        }

        $deadline = (Get-Date).AddMinutes(5)
        while ((Get-Date) -lt $deadline) {
            if ((Test-Path -LiteralPath $installExe -PathType Leaf) -and (Test-Path -LiteralPath $regPath)) {
                break
            }
            Start-Sleep -Seconds 5
        }

        $result.installed_exe_exists = Test-Path -LiteralPath $installExe -PathType Leaf
        $result.uninstall_exe_exists = Test-Path -LiteralPath $uninstallExe -PathType Leaf
        $result.registry_entry_exists = Test-Path -LiteralPath $regPath
        if ($result.registry_entry_exists) {
            $entry = Get-ItemProperty -LiteralPath $regPath
            $result.registry_entry = [ordered]@{
                DisplayName = $entry.DisplayName
                DisplayVersion = $entry.DisplayVersion
                InstallLocation = $entry.InstallLocation
                DisplayIcon = $entry.DisplayIcon
                UninstallString = $entry.UninstallString
            }
        }

        if ($result.installed_exe_exists) {
            $app = Start-Process -FilePath $installExe -PassThru
            Start-Sleep -Seconds 15
            $running = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
            if ($running) {
                $result.app_started = $true
                $result.app_pid = $app.Id
                Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }

    if (-not $result.installed_exe_exists) { $result.blockers += "installed-exe-missing" }
    if (-not $result.uninstall_exe_exists) { $result.blockers += "uninstall-exe-missing" }
    if (-not $result.registry_entry_exists) { $result.blockers += "registry-entry-missing" }
    if (-not $result.app_started) { $result.blockers += "installed-app-start-failed" }

    if ($result.blockers.Count -eq 0) {
        $result.status = "pass"
    }
} catch {
    $result.blockers += ("exception: " + $_.Exception.GetType().Name + ": " + $_.Exception.Message)
} finally {
    $result.ended_at = (Get-Date).ToString("o")
    Write-JsonFile -Path $outJson -Data $result
}

if ($result.status -eq "pass") {
    $md = @"
---
release_gate_proof: true
proof_type: clean-vm-install
status: pass
evidence_level: live
---

# Clean VM Install Proof - Windows Sandbox - 2026-07-02

## Evidence

- Environment: Windows Sandbox / clean ephemeral Windows user `$($result.user)` on `$($result.computer)`.
- OS: `$($result.os.caption)` `$($result.os.version)` build `$($result.os.build)`.
- Installer: `$installer`.
- Payload: `$payload`.
- Installed EXE: `$installExe`.
- Registry key: `$regPath`.
- App launch: process started successfully in sandbox.
- JSON proof: `$outJson`.

## Limit

This proof covers a clean Windows Sandbox install and launch. It does not prove public publisher trust; the installer uses the self-signed certificate approved for the free app path.
"@
    $md | Set-Content -LiteralPath $outMd -Encoding UTF8
}

exit $(if ($result.status -eq "pass") { 0 } else { 1 })
