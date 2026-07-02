param(
    [string]$RepoRoot = "C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease",
    [string]$PythonExe = "C:\Users\WDAGUtilityAccount\Desktop\PBStudioPython\python.exe"
)

$ErrorActionPreference = "Stop"

function Write-JsonFile {
    param(
        [string]$Path,
        [object]$Data
    )
    $Data | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Run-Step {
    param(
        [string]$Name,
        [string]$Script
    )
    $stdout = Join-Path $qaDir "$Name.stdout.txt"
    $stderr = Join-Path $qaDir "$Name.stderr.txt"
    $started = Get-Date
    Push-Location $RepoRoot
    try {
        $oldErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $PythonExe $Script 1> $stdout 2> $stderr
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
        Pop-Location
    }
    return [ordered]@{
        name = $Name
        script = $Script
        exit_code = $exitCode
        timed_out = $false
        elapsed_s = [int]((Get-Date) - $started).TotalSeconds
        stdout = $stdout
        stderr = $stderr
    }
}

$qaDir = Join-Path $RepoRoot "tests\qa_artifacts"
$synthDir = Join-Path $RepoRoot "docs\superpowers\synthesis"
New-Item -ItemType Directory -Force -Path $qaDir, $synthDir | Out-Null

$outJson = Join-Path $qaDir "otk021_vm_portability_probe.json"
$outMd = Join-Path $synthDir "otk021-vm-portability-live-2026-07-02.md"
$bundleJson = Join-Path $qaDir "otk021_project_bundle_roundtrip_result.json"
$backupJson = Join-Path $qaDir "otk021_backup_restore_portable_result.json"
$sandboxWorkRoot = Join-Path $env:TEMP "PBStudioOtk021VmWork"
New-Item -ItemType Directory -Force -Path $sandboxWorkRoot | Out-Null

$result = [ordered]@{
    status = "fail"
    proof_type = "otk021-vm-portability"
    evidence_level = "live"
    started_at = (Get-Date).ToString("o")
    repo_root = $RepoRoot
    python_exe = $PythonExe
    sandbox_work_root = $sandboxWorkRoot
    computer = $env:COMPUTERNAME
    user = $env:USERNAME
    os = $null
    python_exists = Test-Path -LiteralPath $PythonExe -PathType Leaf
    steps = @()
    project_bundle_ok = $false
    backup_restore_ok = $false
    project_bundle_json = $bundleJson
    backup_restore_json = $backupJson
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

    if (-not $result.python_exists) {
        $result.blockers += "python-exe-missing"
    } else {
        Remove-Item -LiteralPath $bundleJson -Force -ErrorAction SilentlyContinue
        $env:PB_OTK021_WORK_ROOT = $sandboxWorkRoot
        $projectStep = Run-Step `
            -Name "otk021_project_bundle_vm" `
            -Script (Join-Path $RepoRoot "scripts\diag\verify_otk021_project_bundle_roundtrip.py")
        $result.steps += $projectStep

        Remove-Item -LiteralPath $backupJson -Force -ErrorAction SilentlyContinue
        $env:PB_OTK021_WORK_ROOT = $sandboxWorkRoot
        $backupStep = Run-Step `
            -Name "otk021_backup_restore_vm" `
            -Script (Join-Path $RepoRoot "scripts\diag\verify_otk021_backup_restore_portable.py")
        $result.steps += $backupStep

        if (Test-Path -LiteralPath $bundleJson -PathType Leaf) {
            $bundle = Get-Content -LiteralPath $bundleJson -Raw | ConvertFrom-Json
            $result.project_bundle_ok = [bool]$bundle.ok
        }
        if (Test-Path -LiteralPath $backupJson -PathType Leaf) {
            $backup = Get-Content -LiteralPath $backupJson -Raw | ConvertFrom-Json
            $result.backup_restore_ok = [bool]$backup.ok
        }
        if ($projectStep.exit_code -ne 0) { $result.blockers += "project-bundle-vm-exit-not-zero" }
        if ($backupStep.exit_code -ne 0) { $result.blockers += "backup-restore-vm-exit-not-zero" }
        if (-not $result.project_bundle_ok) { $result.blockers += "project-bundle-vm-failed" }
        if (-not $result.backup_restore_ok) { $result.blockers += "backup-restore-vm-failed" }
    }

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
    $proofUser = $result["user"]
    $proofComputer = $result["computer"]
    $proofOs = $result["os"]
    $md = @"
---
release_gate_proof: false
proof_type: otk021-vm-portability
status: pass
evidence_level: live
date: 2026-07-02
---

# OTK-021 VM Portability Live Proof - 2026-07-02

## Scope

OTK-021 90 Live-Verify steps 6 and 7:

- Project-Export + Import on another VM.
- Backup + Restore on VM.

## Evidence

- Environment: Windows Sandbox / ephemeral Windows user $proofUser on $proofComputer.
- OS: $($proofOs["caption"]) $($proofOs["version"]) build $($proofOs["build"]).
- Project bundle verifier: pass.
- Backup/restore verifier: pass.
- JSON proof: $outJson
- Project bundle JSON: $bundleJson
- Backup/restore JSON: $backupJson

## Honest Limit

This proof runs the real PB Studio Python services inside Windows Sandbox using
the mapped PB Studio Python environment as runtime. It proves VM execution of
the service roundtrips, not manual GUI clicks inside the installed app and not
public distribution upload.
"@
    $md | Set-Content -LiteralPath $outMd -Encoding UTF8
}

exit $(if ($result.status -eq "pass") { 0 } else { 1 })
