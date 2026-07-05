param(
    [switch]$Wait,
    [string[]]$AppArgs = @()
)

$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:LOCALAPPDATA "PB Studio"
$exe = Join-Path $installDir "pb_studio.exe"

if (-not (Test-Path -LiteralPath $exe)) {
    throw "PB Studio not installed at: $exe"
}

$startArgs = @{
    FilePath = $exe
    WorkingDirectory = $installDir
    PassThru = $true
}

if ($AppArgs.Count -gt 0) {
    $startArgs.ArgumentList = $AppArgs
}

$process = Start-Process @startArgs
Write-Host "PB Studio started. PID=$($process.Id)"

if ($Wait) {
    $process.WaitForExit()
    exit $process.ExitCode
}
