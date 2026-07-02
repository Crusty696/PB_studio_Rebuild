param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$PythonEnvRoot = "C:\Users\David_Lochmann\miniconda3\envs\pb-studio"
)

$ErrorActionPreference = "Stop"

$sandboxExe = Join-Path $env:WINDIR "System32\WindowsSandbox.exe"
if (-not (Test-Path -LiteralPath $sandboxExe -PathType Leaf)) {
    throw "WindowsSandbox.exe not found. Reboot after enabling Windows Sandbox may be required."
}

$repo = (Resolve-Path $RepoRoot).Path
$pythonEnv = (Resolve-Path $PythonEnvRoot).Path
$hostPython = Join-Path $pythonEnv "python.exe"
if (-not (Test-Path -LiteralPath $hostPython -PathType Leaf)) {
    throw "Python env python.exe not found: $hostPython"
}

$wsb = Join-Path $repo "tests\qa_artifacts\otk021_vm_portability.wsb"
$escapedRepo = [System.Security.SecurityElement]::Escape($repo)
$escapedPythonEnv = [System.Security.SecurityElement]::Escape($pythonEnv)

$content = @"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$escapedRepo</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>$escapedPythonEnv</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\PBStudioPython</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -ExecutionPolicy Bypass -File C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\scripts\diag\otk021_sandbox_probe.ps1 -RepoRoot C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease -PythonExe C:\Users\WDAGUtilityAccount\Desktop\PBStudioPython\python.exe</Command>
  </LogonCommand>
</Configuration>
"@

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $wsb) | Out-Null
$content | Set-Content -LiteralPath $wsb -Encoding UTF8
Start-Process -FilePath $sandboxExe -ArgumentList $wsb

[pscustomobject]@{
    status = "started"
    sandbox_config = $wsb
    expected_json = Join-Path $repo "tests\qa_artifacts\otk021_vm_portability_probe.json"
    expected_proof = Join-Path $repo "docs\superpowers\synthesis\otk021-vm-portability-live-2026-07-02.md"
    python_env = $pythonEnv
} | ConvertTo-Json -Depth 3
