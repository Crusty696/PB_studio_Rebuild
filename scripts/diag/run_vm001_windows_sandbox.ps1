param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"

$sandboxExe = Join-Path $env:WINDIR "System32\WindowsSandbox.exe"
if (-not (Test-Path -LiteralPath $sandboxExe -PathType Leaf)) {
    throw "WindowsSandbox.exe not found. Reboot after enabling Windows Sandbox may be required."
}

$repo = (Resolve-Path $RepoRoot).Path
$wsb = Join-Path $repo "tests\qa_artifacts\vm001_pb_studio_clean_install.wsb"
$escapedRepo = [System.Security.SecurityElement]::Escape($repo)

$content = @"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$escapedRepo</HostFolder>
      <SandboxFolder>C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -ExecutionPolicy Bypass -File C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\scripts\diag\vm001_sandbox_probe.ps1 -RepoRoot C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease</Command>
  </LogonCommand>
</Configuration>
"@

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $wsb) | Out-Null
$content | Set-Content -LiteralPath $wsb -Encoding UTF8
Start-Process -FilePath $sandboxExe -ArgumentList $wsb

[pscustomobject]@{
    status = "started"
    sandbox_config = $wsb
    expected_json = Join-Path $repo "tests\qa_artifacts\clean_vm_sandbox_probe.json"
    expected_proof = Join-Path $repo "docs\superpowers\synthesis\clean-vm-sandbox-install-proof-2026-07-02.md"
} | ConvertTo-Json -Depth 3
