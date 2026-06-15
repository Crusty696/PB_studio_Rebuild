param(
    [string]$VideoRoot = "C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur",
    [string]$AudioPath = "C:\Users\David Lochmann\Music\Audio\Psy-Set\Podcast-04.m4a",
    [string]$OutputRoot = "test-report\dg001-h1-4h-20260615",
    [int]$TargetSeconds = 14400,
    [switch]$WritePlan,
    [switch]$BuildInput
)

$ErrorActionPreference = "Stop"

function Invoke-JsonFfprobe {
    param([string]$Path)
    $json = & ffprobe -v error -show_entries format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,duration,channels,sample_rate -of json -- $Path
    if ($LASTEXITCODE -ne 0) {
        throw "ffprobe failed: $Path"
    }
    return ($json | ConvertFrom-Json)
}

function Get-VideoDuration {
    param($Probe)
    if ($Probe.format -and $Probe.format.duration) {
        return [double]::Parse([string]$Probe.format.duration, [Globalization.CultureInfo]::InvariantCulture)
    }
    $video = @($Probe.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1)
    if ($video -and $video.duration) {
        return [double]::Parse([string]$video.duration, [Globalization.CultureInfo]::InvariantCulture)
    }
    return 0.0
}

function Write-Utf8NoBom {
    param([string]$Path, [string[]]$Lines)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines((Resolve-Path -LiteralPath (Split-Path -Parent $Path)).Path + "\" + (Split-Path -Leaf $Path), $Lines, $encoding)
}

function Format-InvariantNumber {
    param([double]$Value)
    return $Value.ToString("0.###", [Globalization.CultureInfo]::InvariantCulture)
}

$repoRoot = (Resolve-Path -LiteralPath ".").Path
$resolvedOutputRoot = Join-Path $repoRoot $OutputRoot

Write-Host "DG-001 H1.3 prepare only"
Write-Host "VideoRoot: $VideoRoot"
Write-Host "AudioPath: $AudioPath"
Write-Host "OutputRoot: $resolvedOutputRoot"
Write-Host "TargetSeconds: $TargetSeconds"

if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw "ffprobe not found in PATH"
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg not found in PATH"
}
if (-not (Test-Path -LiteralPath $VideoRoot)) {
    throw "VideoRoot missing: $VideoRoot"
}
if (-not (Test-Path -LiteralPath $AudioPath)) {
    throw "AudioPath missing: $AudioPath"
}

$videoFiles = Get-ChildItem -LiteralPath $VideoRoot -File -Recurse |
    Where-Object { $_.Extension -match '^(?i)\.(mp4|mov|mkv|avi|m4v|webm)$' } |
    Sort-Object Length -Descending

if (-not $videoFiles -or $videoFiles.Count -eq 0) {
    throw "No video files found under: $VideoRoot"
}

$candidates = New-Object System.Collections.Generic.List[object]
foreach ($file in $videoFiles) {
    try {
        $probe = Invoke-JsonFfprobe -Path $file.FullName
        $videoStream = @($probe.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1)
        if (-not $videoStream) {
            continue
        }
        $duration = Get-VideoDuration -Probe $probe
        if ($duration -le 0) {
            continue
        }
        $audioStream = @($probe.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1)
        $candidates.Add([pscustomobject]@{
            path = $file.FullName
            duration_seconds = [math]::Round($duration, 3)
            size_bytes = $file.Length
            video_codec = $videoStream.codec_name
            width = $videoStream.width
            height = $videoStream.height
            frame_rate = $videoStream.r_frame_rate
            has_audio = [bool]$audioStream
        })
    }
    catch {
        Write-Warning "Skip unreadable video: $($file.FullName) :: $($_.Exception.Message)"
    }
}

if ($candidates.Count -eq 0) {
    throw "No probe-readable video candidates under: $VideoRoot"
}

$audioProbe = Invoke-JsonFfprobe -Path $AudioPath
$audioStream0 = @($audioProbe.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1)
if (-not $audioStream0) {
    throw "Audio file has no audio stream: $AudioPath"
}
$audioDuration = [double]::Parse([string]$audioProbe.format.duration, [Globalization.CultureInfo]::InvariantCulture)

$totalUniqueSeconds = ($candidates | Measure-Object -Property duration_seconds -Sum).Sum
$loopsNeeded = [math]::Ceiling($TargetSeconds / [math]::Max($totalUniqueSeconds, 1.0))

Write-Host ("Video candidates: {0}" -f $candidates.Count)
Write-Host ("Unique video seconds: {0}" -f (Format-InvariantNumber $totalUniqueSeconds))
Write-Host ("Audio seconds: {0}" -f (Format-InvariantNumber $audioDuration))
Write-Host ("Full candidate-set loops needed: {0}" -f $loopsNeeded)

if ($WritePlan -or $BuildInput) {
    New-Item -ItemType Directory -Path $resolvedOutputRoot -Force | Out-Null

    $candidateJson = Join-Path $resolvedOutputRoot "source_candidates.json"
    $candidates | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $candidateJson -Encoding UTF8

    $ffconcatPath = Join-Path $resolvedOutputRoot "video_loop.ffconcat"
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("ffconcat version 1.0")
    $seconds = 0.0
    while ($seconds -lt $TargetSeconds) {
        foreach ($candidate in $candidates) {
            if ($seconds -ge $TargetSeconds) {
                break
            }
            $escaped = $candidate.path.Replace("'", "'\''")
            $lines.Add("file '$escaped'")
            $seconds += [double]$candidate.duration_seconds
        }
    }
    Write-Utf8NoBom -Path $ffconcatPath -Lines $lines

    $commandsPath = Join-Path $resolvedOutputRoot "commands.ps1"
    $inputMp4 = Join-Path $resolvedOutputRoot "input_4h_real_video_real_audio.mp4"
    $commands = @(
        '$ErrorActionPreference = "Stop"',
        '$here = Split-Path -Parent $MyInvocation.MyCommand.Path',
        '$concat = Join-Path $here "video_loop.ffconcat"',
        '$out = Join-Path $here "input_4h_real_video_real_audio.mp4"',
        ('ffmpeg -hide_banner -y -stream_loop -1 -i "{0}" -f concat -safe 0 -i "$concat" -t {1} -map 1:v:0 -map 0:a:0 -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p" -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "$out"' -f $AudioPath, $TargetSeconds),
        'ffprobe -v error -show_entries format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,duration,channels,sample_rate -of json "$out" | Set-Content -LiteralPath (Join-Path $here "input_4h_probe.json") -Encoding UTF8'
    )
    Write-Utf8NoBom -Path $commandsPath -Lines $commands

    $readmePath = Join-Path $resolvedOutputRoot "README.md"
    $readme = @(
        "# DG-001 H1.3 Prepared Inputs",
        "",
        "Status: prepared only. No 4h input built unless -BuildInput or commands.ps1 is run.",
        "",
        "Video source root: $VideoRoot",
        "Audio source: $AudioPath",
        "Target seconds: $TargetSeconds",
        "Video candidates: $($candidates.Count)",
        ("Unique video seconds: {0}" -f (Format-InvariantNumber $totalUniqueSeconds)),
        ("Audio seconds: {0}" -f (Format-InvariantNumber $audioDuration)),
        "Full candidate-set loops needed: $loopsNeeded",
        "",
        "Files:",
        "- source_candidates.json",
        "- video_loop.ffconcat",
        "- commands.ps1",
        "- future output: input_4h_real_video_real_audio.mp4",
        "",
        "Build only when intentionally scheduled:",
        "",
        "powershell command:",
        "powershell -ExecutionPolicy Bypass -File tools\prepare_dg001_h1_4h.ps1 -BuildInput",
        ""
    )
    Write-Utf8NoBom -Path $readmePath -Lines $readme

    Write-Host "Wrote: $candidateJson"
    Write-Host "Wrote: $ffconcatPath"
    Write-Host "Wrote: $commandsPath"
    Write-Host "Wrote: $readmePath"
}

if ($BuildInput) {
    $commandsPath = Join-Path $resolvedOutputRoot "commands.ps1"
    Write-Host "Building 4h input via: $commandsPath"
    powershell -ExecutionPolicy Bypass -File $commandsPath
    if ($LASTEXITCODE -ne 0) {
        throw "4h input build failed"
    }
}
else {
    Write-Host "No 4h encoding started. No pipeline started."
}
