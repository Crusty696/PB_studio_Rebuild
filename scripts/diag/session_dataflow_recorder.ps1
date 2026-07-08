# Dataflow-Recorder fuer PB Studio
#
# Laeuft OHNE Claude Code: wird von start_pb_studio_clicklog.bat parallel zur
# App gestartet (wie session_log_monitor.ps1). Zeichnet alle ~30 s auf,
# WOHIN Daten fliessen und was in der DB landet, mit Zeitstempel + Delta:
#     logs\dataflow_<SessionTag>.md
#
# Erfasst je Snapshot:
#   - aktive Projekt-DB (neueste pb_studio.db): Tabellen-Counts, Audio-Track-
#     Felder (mood/genre/sub_genre/is_dj_mix/duration), analysis_status,
#     timeline_entries pro Spur
#   - Datei-Artefakte im Projektordner: storage\stems, storage\keyframes,
#     data\vector, exports (Anzahl + MB)
#   - Delta seit letztem Snapshot = der Datenfluss ueber die Zeit
#
# Beendet sich selbst ~15 s nachdem kein "python ... main.py" mehr laeuft.
param(
    [string]$SessionTag = (Get-Date -Format "yyyy-MM-dd_HHmmss"),
    [string]$PbPython = ""
)

$ErrorActionPreference = "SilentlyContinue"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$snapPy = Join-Path $PSScriptRoot "_dataflow_snapshot.py"
$outFile = Join-Path $repo ("logs\dataflow_{0}.md" -f $SessionTag)

# Python aufloesen (gleiche Logik wie start_pb_studio.bat)
if (-not $PbPython -or -not (Test-Path $PbPython)) {
    $cand = @(
        (Join-Path $env:USERPROFILE "miniconda3\envs\pb-studio\python.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\envs\pb-studio\python.exe"),
        (Join-Path $repo ".venv310\Scripts\python.exe"),
        (Join-Path $repo ".venv\Scripts\python.exe")
    )
    $PbPython = $cand | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Find-ActiveDb {
    $cands = @(
        (Join-Path $repo "pb_studio.db"),
        (Join-Path $repo "storage\pb_studio.db")
    )
    foreach ($g in @("outputs\*\pb_studio.db", "storage\projects\*\pb_studio.db", "projects\*\pb_studio.db")) {
        $cands += (Get-ChildItem -Path (Join-Path $repo $g) -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    $cands | Where-Object { $_ -and (Test-Path $_) } |
        Where-Object { $_ -notmatch "\\backups\\|\\.worktrees\\|\\dist\\" } |
        Get-Item -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

function Dir-Stat($base, $rel) {
    $p = Join-Path $base $rel
    if (-not (Test-Path $p)) { return @{ n = 0; mb = 0.0 } }
    $files = Get-ChildItem -Path $p -Recurse -File -ErrorAction SilentlyContinue
    $mb = if ($files) { [math]::Round((($files | Measure-Object Length -Sum).Sum / 1MB), 1) } else { 0.0 }
    return @{ n = ($files | Measure-Object).Count; mb = $mb }
}

"# PB Studio — Dataflow-Aufzeichnung (Tag=$SessionTag)" | Out-File -FilePath $outFile -Encoding utf8
"Start: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  |  Python: $PbPython" | Out-File -FilePath $outFile -Append -Encoding utf8
"Snapshot alle ~30s: DB-Zustand + Datei-Artefakte + Delta. Selbst-Stopp bei App-Ende." | Out-File -FilePath $outFile -Append -Encoding utf8

$prev = @{}
$appGoneSince = $null

while ($true) {
    $ts = Get-Date -Format 'HH:mm:ss'
    $db = Find-ActiveDb
    $block = @("", "## $ts")

    if ($db) {
        $block += "DB: $($db.FullName)"
        $json = & $PbPython $snapPy $db.FullName 2>$null
        $snap = $null
        try { $snap = $json | ConvertFrom-Json } catch {}
        if ($snap) {
            $tb = $snap.tables
            $block += ("Tabellen: audio_tracks={0} beatgrids={1} waveform={2} video_clips={3} scenes={4} timeline={5} analysis_status={6}" -f `
                $tb.audio_tracks, $tb.beatgrids, $tb.waveform_data, $tb.video_clips, $tb.scenes, $tb.timeline_entries, $tb.analysis_status)
            foreach ($a in $snap.audio) {
                $block += ("  Audio[{0}]: mood={1} genre={2} sub={3} is_dj_mix={4} dur={5}s" -f $a.id, $a.mood, $a.genre, $a.sub_genre, $a.is_dj_mix, $a.dur)
            }
            if ($snap.counts) {
                $cs = ($snap.counts.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join " "
                if ($cs) { $block += "  Counts: $cs" }
            }
            # Delta DB
            $curTl = [int]$tb.timeline_entries; $curBg = [int]$tb.beatgrids; $curWf = [int]$tb.waveform_data; $curSc = [int]$tb.scenes
            $dTl = $curTl - [int]$prev["tl"]; $dBg = $curBg - [int]$prev["bg"]; $dWf = $curWf - [int]$prev["wf"]; $dSc = $curSc - [int]$prev["sc"]
            if ($dTl -or $dBg -or $dWf -or $dSc) {
                $block += ("  Δ DB: timeline_entries {0:+0;-0;0}, beatgrids {1:+0;-0;0}, waveform {2:+0;-0;0}, scenes {3:+0;-0;0}" -f $dTl, $dBg, $dWf, $dSc)
            }
            $prev["tl"] = $curTl; $prev["bg"] = $curBg; $prev["wf"] = $curWf; $prev["sc"] = $curSc
        } else {
            $block += "  (DB gerade gelockt/leer - naechster Snapshot)"
        }

        # Datei-Artefakte im Projektordner
        $proj = Split-Path -Parent $db.FullName
        $stems = Dir-Stat $proj "storage\stems"
        $kf = Dir-Stat $proj "storage\keyframes"
        $vec = Dir-Stat $proj "data\vector"
        $exp = Dir-Stat $proj "exports"
        $block += ("Artefakte: stems={0}D/{1}MB keyframes={2}D/{3}MB vector={4}D/{5}MB exports={6}D/{7}MB" -f `
            $stems.n, $stems.mb, $kf.n, $kf.mb, $vec.n, $vec.mb, $exp.n, $exp.mb)
        $dStems = $stems.n - [int]$prev["stems"]; $dKf = $kf.n - [int]$prev["kf"]; $dVec = $vec.n - [int]$prev["vec"]; $dExp = $exp.n - [int]$prev["exp"]
        if ($dStems -or $dKf -or $dVec -or $dExp) {
            $block += ("  Δ Dateien: stems {0:+0;-0;0}, keyframes {1:+0;-0;0}, vector {2:+0;-0;0}, exports {3:+0;-0;0}" -f $dStems, $dKf, $dVec, $dExp)
        }
        $prev["stems"] = $stems.n; $prev["kf"] = $kf.n; $prev["vec"] = $vec.n; $prev["exp"] = $exp.n
    } else {
        $block += "(noch keine Projekt-DB gefunden)"
    }

    $block -join "`n" | Out-File -FilePath $outFile -Append -Encoding utf8

    # Selbst-Beendigung: App weg -> 15 s Nachlauf, dann Exit
    $app = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'main\.py' }
    if (-not $app) {
        if ($null -eq $appGoneSince) { $appGoneSince = Get-Date }
        elseif (((Get-Date) - $appGoneSince).TotalSeconds -gt 15) {
            "", "## $(Get-Date -Format 'HH:mm:ss') — App beendet, Recorder stoppt." |
                Out-File -FilePath $outFile -Append -Encoding utf8
            break
        }
    } else {
        $appGoneSince = $null
    }

    Start-Sleep -Seconds 30
}
