param(
    [switch]$CheckPush,
    [switch]$ReleaseGate
)

$ErrorActionPreference = "Stop"

function Write-Section($Title) {
    Write-Host ""
    Write-Host "== $Title =="
}

$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
    Write-Host "BLOCKED: not inside Git repository"
    exit 2
}

Set-Location $repoRoot

Write-Section "Agent Handoff"
Write-Host "Repo: $repoRoot"

$status = (& git status --short --branch)
$status | ForEach-Object { Write-Host $_ }

$dirty = (& git status --porcelain)
if ($dirty) {
    Write-Section "BLOCKED"
    Write-Host "Dirty worktree cannot be handed off."
    Write-Host "Resolve first: commit, named stash, or explicit user-approved dirty state documented in Vault and chat."
    Write-Host ""
    $dirty | ForEach-Object { Write-Host $_ }
    exit 3
}

if ($CheckPush) {
    Write-Section "Push Check"
    $branch = (& git branch --show-current).Trim()
    $upstream = (& git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $upstream) {
        $counts = (& git rev-list --left-right --count "$upstream...HEAD").Trim()
        Write-Host "$upstream...HEAD $counts"
        $parts = $counts -split "\s+"
        if ($parts.Count -eq 2 -and [int]$parts[1] -gt 0) {
            Write-Host "WARN: local commits not pushed."
        }
    } else {
        Write-Host "WARN: no upstream configured for $branch."
    }
}

Write-Section "Recent Commits"
& git log --oneline -n 5

Write-Section "Active Plan"
if (Test-Path "docs/superpowers/ACTIVE_PLAN.md") {
    Get-Content "docs/superpowers/ACTIVE_PLAN.md" | Select-Object -First 80
} else {
    Write-Host "WARN: docs/superpowers/ACTIVE_PLAN.md missing"
}

Write-Section "Release Gate"
$py = Join-Path $env:USERPROFILE "miniconda3\envs\pb-studio\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py "tools/release_gate.py"
$gateExit = $LASTEXITCODE
if ($gateExit -notin @(0, 2)) {
    Write-Section "BLOCKED"
    Write-Host "Release gate execution failed (exit $gateExit)."
    exit 5
}
if ($gateExit -eq 2) {
    if ($ReleaseGate) {
        Write-Section "BLOCKED"
        Write-Host "Release/fixed claim refused: open release blockers (see above)."
        exit 4
    } else {
        Write-Host "WARN: open release blockers - no 'release/fixed' claim allowed until cleared."
    }
}

Write-Section "Result"
Write-Host "OK: clean handoff state."
