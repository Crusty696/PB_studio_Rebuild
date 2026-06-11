# PB Studio — Wrapper fuer tests/gui_db_inspector.py (pb-gui-tester).
# Portabel: Pfade relativ zum Script, Python via $env:PB_PYTHON oder conda-env
# "pb-studio" unter %USERPROFILE% (miniconda3/anaconda3). Aufruf-Args durchgereicht.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args2
)

$root = Split-Path -Parent $PSScriptRoot   # tests/ -> Repo-Root
$DB = Join-Path $PSScriptRoot 'gui_db_inspector.py'

if (-not $env:PB_PYTHON) {
    $cand = Join-Path $env:USERPROFILE 'miniconda3\envs\pb-studio\python.exe'
    if (-not (Test-Path $cand)) {
        $cand = Join-Path $env:USERPROFILE 'anaconda3\envs\pb-studio\python.exe'
    }
    $env:PB_PYTHON = $cand
}
$PY = $env:PB_PYTHON

if (-not (Test-Path $PY)) {
    Write-Error "Python nicht gefunden: $PY  (setze `$env:PB_PYTHON oder lege conda-env 'pb-studio' an)"
    exit 1
}

Set-Location $root
& $PY $DB @Args2
exit $LASTEXITCODE
