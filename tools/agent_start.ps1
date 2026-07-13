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

Write-Section "FFmpeg Identity"
$pythonCandidates = @(
    (Join-Path $env:USERPROFILE "miniconda3\envs\pb-studio\python.exe"),
    (Join-Path $env:USERPROFILE "anaconda3\envs\pb-studio\python.exe"),
    (Join-Path $repoRoot ".venv310\Scripts\python.exe"),
    (Join-Path $repoRoot ".venv\Scripts\python.exe")
)
$verifyPython = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $verifyPython) {
    Write-Host "BLOCKED: canonical PB Studio Python runtime not found for FFmpeg verification"
    exit 5
}
& $verifyPython "tools\verify_ffmpeg_identity.py"
$ffmpegVerifyExit = $LASTEXITCODE
if ($ffmpegVerifyExit -ne 0) {
    Write-Host "BLOCKED: canonical FFmpeg identity verification failed"
    exit 6
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
