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

function Update-Phase {
    param(
        [string]$Name,
        [string]$Detail = ""
    )
    $result.phase = $Name
    $result.phase_detail = $Detail
    $result.heartbeat_at = (Get-Date).ToString("o")
    Write-JsonFile -Path $outJson -Data $result
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
$expectedWindowTitleFragment = "PB_studio"

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
    app_exit_code = $null
    app_window_title = $null
    app_processes = @()
    app_stdout = $null
    app_stderr = $null
    app_failure_screenshot = $null
    app_direct_process_alive = $false
    phase = "init"
    phase_detail = ""
    heartbeat_at = (Get-Date).ToString("o")
    installer_elapsed_s = $null
    app_launch_elapsed_s = $null
    root_loader_files = @{}
    blockers = @()
    ended_at = $null
}

try {
    Update-Phase -Name "init" -Detail "probe started"
    $osInfo = Get-CimInstance Win32_OperatingSystem
    $result.os = [ordered]@{
        caption = $osInfo.Caption
        version = $osInfo.Version
        build = $osInfo.BuildNumber
    }

    if (-not $result.installer_exists) { $result.blockers += "installer-missing" }
    if (-not $result.payload_exists) { $result.blockers += "payload-missing" }
    if ($result.blockers.Count -eq 0) {
        $result.root_loader_files = [ordered]@{}
        foreach ($loaderFile in @("python310.dll", "python3.dll", "zlib.dll", "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")) {
            $loaderPath = Join-Path (Join-Path $RepoRoot "dist\pb_studio\_internal") $loaderFile
            $result.root_loader_files[$loaderFile] = Test-Path -LiteralPath $loaderPath -PathType Leaf
        }
        Update-Phase -Name "install-start" -Detail "starting silent installer"
        $proc = Start-Process -FilePath $installer -ArgumentList "/S" -PassThru
        $installStarted = Get-Date
        $installDeadline = $installStarted.AddMinutes(30)
        while ((Get-Date) -lt $installDeadline) {
            $proc.Refresh()
            $result.installer_elapsed_s = [int]((Get-Date) - $installStarted).TotalSeconds
            Update-Phase -Name "install-wait" -Detail "silent installer running"
            if ($proc.HasExited) {
                $result.installer_exit_code = $proc.ExitCode
                break
            }
            Start-Sleep -Seconds 10
        }
        $proc.Refresh()
        if (-not $proc.HasExited) {
            $result.installer_timed_out = $true
            $result.installer_elapsed_s = [int]((Get-Date) - $installStarted).TotalSeconds
            Update-Phase -Name "install-timeout" -Detail "silent installer timed out"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        } elseif ($null -eq $result.installer_exit_code) {
            $result.installer_exit_code = $proc.ExitCode
        }
        Update-Phase -Name "install-ended" -Detail "silent installer process ended or was stopped"

        $deadline = (Get-Date).AddMinutes(5)
        Update-Phase -Name "install-artifact-wait" -Detail "waiting for installed exe and registry"
        while ((Get-Date) -lt $deadline) {
            if ((Test-Path -LiteralPath $installExe -PathType Leaf) -and (Test-Path -LiteralPath $regPath)) {
                break
            }
            Update-Phase -Name "install-artifact-wait" -Detail "installed exe or registry missing"
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
        Update-Phase -Name "install-artifact-check" -Detail "checked installed exe, uninstaller, registry"

        if ($result.installed_exe_exists) {
            Update-Phase -Name "app-start" -Detail "starting installed app"
            $app = Start-Process `
                -FilePath $installExe `
                -WorkingDirectory (Split-Path -Parent $installExe) `
                -PassThru

            $deadline = (Get-Date).AddSeconds(120)
            $appStarted = Get-Date
            while ((Get-Date) -lt $deadline) {
                $app.Refresh()
                $result.app_launch_elapsed_s = [int]((Get-Date) - $appStarted).TotalSeconds
                $direct = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
                $allPbStudio = @(Get-Process -Name "pb_studio" -ErrorAction SilentlyContinue)
                $windowed = @($allPbStudio | Where-Object { $_.MainWindowTitle -like "*$expectedWindowTitleFragment*" })
                $result.app_processes = @($allPbStudio | ForEach-Object {
                    [ordered]@{
                        id = $_.Id
                        main_window_title = $_.MainWindowTitle
                        start_time = try { $_.StartTime.ToString("o") } catch { $null }
                    }
                })
                Update-Phase -Name "app-wait" -Detail "waiting for PB_studio main window"
                if ($windowed.Count -gt 0) {
                    $selected = $windowed[0]
                    $result.app_started = $true
                    $result.app_pid = $selected.Id
                    $result.app_window_title = $selected.MainWindowTitle
                    break
                }
                if ($app.HasExited) {
                    $result.app_exit_code = $app.ExitCode
                    break
                }
                Start-Sleep -Seconds 2
            }

            $app.Refresh()
            if ($null -eq $result.app_exit_code -and $app.HasExited) {
                $result.app_exit_code = $app.ExitCode
            }
            $directAfterLaunch = Get-Process -Id $app.Id -ErrorAction SilentlyContinue
            $result.app_direct_process_alive = $null -ne $directAfterLaunch
            $result.app_processes = @(Get-Process -Name "pb_studio" -ErrorAction SilentlyContinue | ForEach-Object {
                [ordered]@{
                    id = $_.Id
                    main_window_title = $_.MainWindowTitle
                    start_time = try { $_.StartTime.ToString("o") } catch { $null }
                }
            })
            if (-not $result.app_started) {
                try {
                    Add-Type -AssemblyName System.Windows.Forms
                    Add-Type -AssemblyName System.Drawing
                    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
                    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
                    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
                    $screenshot = Join-Path $qaDir "clean_vm_app_failure.png"
                    $bitmap.Save($screenshot, [System.Drawing.Imaging.ImageFormat]::Png)
                    $graphics.Dispose()
                    $bitmap.Dispose()
                    $result.app_failure_screenshot = $screenshot
                } catch {
                    $result.app_failure_screenshot = "screenshot-failed: " + $_.Exception.Message
                }
            }
            if ($result.app_started -and $result.app_pid) {
                Stop-Process -Id $result.app_pid -Force -ErrorAction SilentlyContinue
            }
            Update-Phase -Name "app-ended" -Detail "installed app launch check finished"
        }
    }

    if (-not $result.installed_exe_exists) { $result.blockers += "installed-exe-missing" }
    if (-not $result.uninstall_exe_exists) { $result.blockers += "uninstall-exe-missing" }
    if (-not $result.registry_entry_exists) { $result.blockers += "registry-entry-missing" }
    if (-not $result.app_started) { $result.blockers += "installed-app-start-failed" }

    if ($result.blockers.Count -eq 0) {
        $result.status = "pass"
    }
    Update-Phase -Name "result" -Detail $result.status
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
release_gate_proof: true
proof_type: clean-vm-install
status: pass
evidence_level: live
---

# Clean VM Install Proof - Windows Sandbox - 2026-07-02

## Evidence

- Environment: Windows Sandbox / clean ephemeral Windows user $proofUser on $proofComputer.
- OS: $($proofOs["caption"]) $($proofOs["version"]) build $($proofOs["build"]).
- Installer: $installer
- Payload: $payload
- Installed EXE: $installExe
- Registry key: $regPath
- App launch: process started successfully in sandbox.
- JSON proof: $outJson

## Limit

This proof covers a clean Windows Sandbox install and launch. It does not prove public publisher trust; the installer uses the self-signed certificate approved for the free app path.
"@
    $md | Set-Content -LiteralPath $outMd -Encoding UTF8
}

exit $(if ($result.status -eq "pass") { 0 } else { 1 })
