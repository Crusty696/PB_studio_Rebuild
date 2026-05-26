param(
    [switch]$Pull
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

Write-Section "Agent Start"
Write-Host "Repo: $repoRoot"

$status = (& git status --short --branch)
$status | ForEach-Object { Write-Host $_ }

$dirty = (& git status --porcelain)
if ($dirty) {
    Write-Section "BLOCKED"
    Write-Host "Dirty worktree found before agent start."
    Write-Host "Resolve first: commit, named stash, or user-approved dirty handoff."
    Write-Host ""
    $dirty | ForEach-Object { Write-Host $_ }
    exit 3
}

if ($Pull) {
    Write-Section "Remote Sync"
    & git fetch --prune
    $branch = (& git branch --show-current).Trim()
    $upstream = (& git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $upstream) {
        & git pull --ff-only
    } else {
        Write-Host "No upstream configured for $branch; fetch done, pull skipped."
    }
}

Write-Section "Recent Commits"
& git log --oneline -n 5

Write-Section "Active Plan"
if (Test-Path "docs/superpowers/ACTIVE_PLAN.md") {
    Get-Content "docs/superpowers/ACTIVE_PLAN.md" | Select-Object -First 80
} else {
    Write-Host "BLOCKED: docs/superpowers/ACTIVE_PLAN.md missing"
    exit 4
}

Write-Section "Handoff"
if (Test-Path "docs/superpowers/AGENT_HANDOFF.md") {
    Get-Content "docs/superpowers/AGENT_HANDOFF.md" | Select-Object -First 120
} else {
    Write-Host "WARN: docs/superpowers/AGENT_HANDOFF.md missing"
}

Write-Section "Result"
Write-Host "OK: clean start state. Continue with AGENTS.md plan checks."
