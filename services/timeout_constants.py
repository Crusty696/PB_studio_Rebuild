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


def ffmpeg_timeout_for(duration_sec, min_sec: float = 600.0,
                       factor: float = 3.0) -> float:
    """B-506: Dauer-basierter FFmpeg-Timeout statt statischem Per-File-Kill.

    Der statische ``FFMPEG_EXPORT_TIMEOUT_SEC`` (600 s) killte lange
    Quellen (3h-DJ-Set) nach 10 Minuten mitten im Encode. Vorbild:
    dauerbasierter Timeout in ``export_service`` (Concat/Filtergraph).

    Args:
        duration_sec: Quell-Dauer in Sekunden. ``None``/``<= 0``/nicht
            numerisch → Dauer unbekannt → konservativ ``min_sec``
            (bisheriger Default).
        min_sec: Untergrenze (Default 600 s = alter statischer Wert).
        factor: Sicherheitsfaktor auf die Quell-Dauer (Default 3.0 —
            auch ein langsamer CPU-Encode unter Last bleibt unter 3×
            Realtime fuer die hiesigen Presets).

    Returns:
        ``max(min_sec, duration_sec * factor)`` als float.
    """
    try:
        d = float(duration_sec) if duration_sec is not None else 0.0
    except (TypeError, ValueError):
        d = 0.0
    if d <= 0.0:
        return float(min_sec)
    return max(float(min_sec), d * float(factor))

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

# Video-Pipeline Caption: Vision-LLMs der 4B-Klasse (gemma4:e4b, MoE mit
# Teil-CPU-Offload auf GTX 1060) brauchen warm 30-90 s pro Bild, kalt mehr.
# Fixplan 2026-07-07: 30 s riss den Caption-Batch nach 3 Szenen (Circuit-
# Breaker) — Captions laufen als Hintergrund-Pipeline-Step, nicht UI-nah.
HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC: int = 240

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
