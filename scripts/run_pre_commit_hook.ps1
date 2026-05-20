param(
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

$hook = Join-Path $RepoRoot ".git\hooks\pre-commit"
if (-not (Test-Path -LiteralPath $hook)) {
    Write-Error "pre-commit hook not found: $hook"
}

$bashCandidates = @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files\Git\usr\bin\bash.exe"
)

$bash = $bashCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $bash) {
    $cmd = Get-Command bash -ErrorAction SilentlyContinue
    if ($cmd) {
        $bash = $cmd.Source
    }
}

if (-not $bash) {
    Write-Error "Git Bash not found. Install Git for Windows or add bash.exe to PATH."
}

Push-Location $RepoRoot
try {
    & $bash ".git/hooks/pre-commit"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
