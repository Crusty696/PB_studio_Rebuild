# Session-Log-Monitor fuer PB Studio (Fixplan 2026-07-07)
#
# Laeuft OHNE Claude Code: wird von start_pb_studio_clicklog.bat parallel
# zur App gestartet. Filtert logs\pb_studio.log live auf die relevanten
# Marker (Fehler, Auto-Edit-Ergebnis, Pacing-Qualitaet, Timeline-Budget,
# Captioning, Render) und schreibt sie kompakt nach:
#     logs\monitor_<SessionTag>.log
# Ein Agent muss danach nur diese Datei lesen statt des vollen Logs.
#
# Beendet sich selbst ~15 s nachdem kein "python ... main.py"-Prozess
# mehr laeuft (App geschlossen).
param(
    [string]$SessionTag = (Get-Date -Format "yyyy-MM-dd_HHmmss")
)

$ErrorActionPreference = "SilentlyContinue"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logFile = Join-Path $repo "logs\pb_studio.log"
$outFile = Join-Path $repo ("logs\monitor_{0}.log" -f $SessionTag)

$pattern = @(
    "ERROR", "CRITICAL", "Traceback", "UNHANDLED",
    "Phase 3 Auto-Edit", "Phase 3: \d+ Segmente",
    "finalize_cut_beats", "Mindestdauer:",
    "Caption-Mood-Anreicherung", "Schritt-3-Diversitaet",
    "Sektionen aus Struktur-Analyse", "Erkannte Sektionen",
    "apply_auto_edit_segments", "Timeline-Integritaet repariert",
    "plan_video_timeline_add", "Nicht hinzugefuegt", "nicht uebergeben",
    "Starte Vision-Captioning", "Vision-Captioning abgeschlossen",
    "\[CLICK\] PRESS.*QPushButton", "\[KEY\] PRESS",
    "Click/Key-Logger aktiv", "Logging initialisiert",
    "GpuSerializer holder='render'", "Export", "output\.mp4"
) -join "|"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Session-Monitor gestartet (Tag=$SessionTag)" |
    Out-File -FilePath $outFile -Encoding utf8

# Warten bis pb_studio.log existiert (frische Installation)
$tries = 0
while (-not (Test-Path $logFile) -and $tries -lt 60) { Start-Sleep 1; $tries++ }
if (-not (Test-Path $logFile)) {
    "[$(Get-Date -Format 'HH:mm:ss')] pb_studio.log nicht gefunden - Monitor beendet." |
        Out-File -FilePath $outFile -Append -Encoding utf8
    exit 1
}

# Poll-Schleife: neue Zeilen ab Dateiende lesen, filtern, anhaengen.
$pos = (Get-Item $logFile).Length
$appGoneSince = $null
while ($true) {
    Start-Sleep -Seconds 2

    $len = (Get-Item $logFile).Length
    if ($len -lt $pos) { $pos = 0 }  # Log-Rotation
    if ($len -gt $pos) {
        $fs = [System.IO.File]::Open($logFile, 'Open', 'Read', 'ReadWrite')
        try {
            $fs.Seek($pos, 'Begin') | Out-Null
            $sr = New-Object System.IO.StreamReader($fs, [Text.Encoding]::UTF8)
            $chunk = $sr.ReadToEnd()
            $pos = $fs.Position
        } finally { $fs.Close() }
        $hits = $chunk -split "`n" | Where-Object { $_ -match $pattern }
        if ($hits) { $hits | Out-File -FilePath $outFile -Append -Encoding utf8 }
    }

    # Selbst-Beendigung: App weg -> 15 s Nachlauf, dann Exit
    $app = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'main\.py' }
    if (-not $app) {
        if ($null -eq $appGoneSince) { $appGoneSince = Get-Date }
        elseif (((Get-Date) - $appGoneSince).TotalSeconds -gt 15) {
            "[$(Get-Date -Format 'HH:mm:ss')] App beendet - Monitor stoppt. Auswertung: docs\SESSION_MONITORING_UND_ANALYSE.md" |
                Out-File -FilePath $outFile -Append -Encoding utf8
            break
        }
    } else {
        $appGoneSince = $null
    }
}
