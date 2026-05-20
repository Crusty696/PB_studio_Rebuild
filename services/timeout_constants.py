"""Zentrale Timeout-Konstanten fuer alle Services.

Ersetzt Magic Numbers in subprocess.run(timeout=...), urlopen(timeout=...),
SQLAlchemy pool_timeout, PRAGMA busy_timeout usw.

Kategorien:
  - FFMPEG_*  : FFmpeg/ffprobe Subprozesse
  - HTTP_*    : HTTP-Anfragen (Ollama, Update-Check)
  - MODEL_*   : ML-Modell Download / Verifikation
  - DB_*      : Datenbank-Verbindung und Locking
  - STARTUP_* : Einmalige Startup-Checks (parallel)
  - THREAD_*  : Thread.join() / Future.result()
  - ML_*      : ML-Inference / Demucs-Subprozesse
  - AGENT_*   : Local-Agent Future-Timeouts
"""

# ---------------------------------------------------------------------------
# FFmpeg / ffprobe
# ---------------------------------------------------------------------------

# Schnelle Abfragen: -version, -encoders, -hwaccels, ffprobe-Metadaten
FFMPEG_PROBE_TIMEOUT_SEC: int = 10

# Thumbnail / Frame-Extraktion (ein einziges Frame, sollte schnell sein)
FFMPEG_THUMBNAIL_TIMEOUT_SEC: int = 10

# Standard-Render (Audio-Mix, Video-Render bis ~60 Min)
FFMPEG_RENDER_TIMEOUT_SEC: int = 300

# Langer Export / Konvertierung (kompletter DJ-Set, 2-3 h)
FFMPEG_EXPORT_TIMEOUT_SEC: int = 600

# LUFS-Messung (loudnorm-Filter, kann bei langen Dateien dauern)
FFMPEG_LUFS_MEASURE_TIMEOUT_SEC: int = 300

# LUFS-Normalisierung (zweiter Pass)
FFMPEG_LUFS_NORMALIZE_TIMEOUT_SEC: int = 600

# LUFS per audio_constants — synchronisiert mit FFMPEG_LUFS_MEASURE_TIMEOUT_SEC
# audio_constants.FFMPEG_TIMEOUT_SEC bleibt fuer Rueckwaerts-Kompatibilitaet erhalten.

# ---------------------------------------------------------------------------
# HTTP / API
# ---------------------------------------------------------------------------

# Schnelle Health-Checks (Ollama /api/version, lokale Dienste)
HTTP_HEALTH_CHECK_TIMEOUT_SEC: int = 2

# Normale API-Aufrufe (Ollama /api/tags, /api/generate mit kleinen Prompts)
HTTP_API_TIMEOUT_SEC: int = 5

# Video-Pipeline Caption darf UI-nahe Workflows nicht minutenlang blockieren.
HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC: int = 30

# Model-Info Abfrage (Ollama /api/show — Cold-Start kann 10-15s brauchen)
HTTP_MODEL_INFO_TIMEOUT_SEC: int = 15

# Update-Check (externe URL, muss nicht sofort antworten)
HTTP_VERSION_CHECK_TIMEOUT_SEC: int = 10

# ---------------------------------------------------------------------------
# Modell-Download / -Verifikation
# ---------------------------------------------------------------------------

# Vollstaendiger Modell-Download (Demucs, SigLIP, Moondream2 — 1-10 GB)
MODEL_DOWNLOAD_TIMEOUT_SEC: int = 3600

# Modell-Integritaetspruefung nach Download
MODEL_VERIFY_TIMEOUT_SEC: int = 30

# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------

# SQLAlchemy connection pool timeout
DB_POOL_TIMEOUT_SEC: int = 60

# PRAGMA busy_timeout (Millisekunden) — kurze Queries / Timeline-Locking
DB_BUSY_TIMEOUT_MS: int = 30_000  # 30 s

# PRAGMA busy_timeout (Millisekunden) — lange Analysen mit Write-Lock
DB_BUSY_TIMEOUT_ANALYSIS_MS: int = 120_000  # 120 s

# sqlite3.connect(timeout=...) in Sekunden
DB_SQLITE_CONNECT_TIMEOUT_SEC: int = 30

# ---------------------------------------------------------------------------
# Startup-Checks (parallel, kurze Windows)
# ---------------------------------------------------------------------------

STARTUP_FFMPEG_CHECK_TIMEOUT_SEC: int = 8
STARTUP_GPU_CHECK_TIMEOUT_SEC: int = 3
STARTUP_DISK_CHECK_TIMEOUT_SEC: int = 4
STARTUP_OLLAMA_CHECK_TIMEOUT_SEC: int = 10  # FIX H-1: aligned with _check_ollama() internal timeout
STARTUP_MODEL_CHECK_TIMEOUT_SEC: int = 3

# ---------------------------------------------------------------------------
# Thread / Future
# ---------------------------------------------------------------------------

# stderr-Reader Thread nach Prozessende joinen
THREAD_JOIN_TIMEOUT_SEC: int = 10

# ---------------------------------------------------------------------------
# ML-Inference
# ---------------------------------------------------------------------------

# Demucs Stem-Separation als Subprozess (kompletter Track)
ML_DEMUCS_TIMEOUT_SEC: int = 300

# ---------------------------------------------------------------------------
# Local-Agent Futures
# ---------------------------------------------------------------------------

# Normales Agent-Task Future (kurze Analyse)
AGENT_TASK_TIMEOUT_SEC: int = 60

# Langes Agent-Task Future (komplexe Multi-Step-Analyse)
AGENT_TASK_LONG_TIMEOUT_SEC: int = 120
