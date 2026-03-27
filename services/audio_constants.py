"""Gemeinsame Audio-Konstanten fuer alle Analyse-Services.

Zentralisiert Sample-Raten, Dauer-Limits und Analyse-Parameter
damit sie an einer Stelle konfiguriert werden koennen.
"""

# -- Audio Loading -----------------------------------------------------
DEFAULT_SR: int = 22050

# Max. Dauer in Sekunden die geladen wird (schuetzt RAM bei langen Dateien)
MAX_DURATION_KEY: float = 120.0      # Key Detection: 2 Min reichen
MAX_DURATION_CLASSIFY: float = 180.0  # Classification: 3 Min fuer Feature-Extraktion
MAX_DURATION_SPECTRAL: float = 300.0  # Spektral: 5 Min fuer Band-Analyse
MAX_DURATION_STRUCTURE: float = 600.0  # Struktur: 10 Min fuer Segment-Erkennung

# -- STFT Parameters ---------------------------------------------------
N_FFT: int = 2048
HOP_LENGTH: int = 512
CHROMA_HOP_LENGTH: int = 2048  # Groesser fuer stabilere Chroma-Features

# -- Key Detection -----------------------------------------------------
CONFIDENCE_EPSILON: float = 1e-9

# -- LUFS --------------------------------------------------------------
FFMPEG_TIMEOUT_SEC: int = 120
MIN_LUFS_DB: float = -70.0   # Clamp fuer -inf
MAX_LUFS_DB: float = 0.0     # Clamp fuer +inf
ST_MAX_HEADROOM_DB: float = 3.0  # Short-term max darf TP + 3dB nicht uebersteigen

# -- Classification Thresholds -----------------------------------------
HIGH_CENTROID_HZ: float = 3500.0
MID_CENTROID_HZ: float = 3000.0
LOW_CENTROID_HZ: float = 2000.0
VERY_LOW_CENTROID_HZ: float = 2500.0
HIGH_RMS: float = 0.08
MID_RMS: float = 0.05
LOW_RMS: float = 0.03
VERY_HIGH_RMS: float = 0.1

# -- DJ-Mix Detection --------------------------------------------------
MIN_MIX_DURATION_SEC: float = 600.0    # < 10 Min = kein Mix
LIKELY_MIX_DURATION_SEC: float = 1800.0  # > 30 Min = sicher Mix
BPM_VARIANCE_THRESHOLD: float = 2.0    # BPM Peak-to-Peak ueber Segmente

# -- Spectral Event Detection -----------------------------------------
DROP_ENERGY_RATIO: float = 2.0     # Energie-Verhaeltnis fuer Drop-Erkennung
BUILDUP_MIN_WINDOWS: int = 8       # Min. Fenster fuer Buildup
BUILDUP_MIN_RISE: float = 0.5      # Min. Gesamt-Energieanstieg
BUILDUP_MAX_START_ENERGY: float = 0.6  # Buildup startet nur unter diesem Level
BUILDUP_JITTER_TOLERANCE: float = 0.95  # Erlaubter Rueckgang in Buildup-Phase
BREAKDOWN_MIN_PREV_ENERGY: float = 0.4  # Min. Energie vor Breakdown
BREAKDOWN_DROP_RATIO: float = 0.5  # Min. Energieabfall fuer Breakdown

# -- Structure Detection -----------------------------------------------
STRUCTURE_SMOOTH_WINDOW: int = 16   # Moving Average Fenster (Beats)
INTRO_OUTRO_FRACTION: float = 0.05  # Erste/Letzte 5% des Tracks
INTRO_OUTRO_MAX_EXPANSION: float = 0.25  # Max. Expansion bis 25%
LOW_ENERGY_THRESHOLD: float = 0.3  # Unter diesem Wert = Intro/Outro
BUILDUP_GRADIENT_THRESHOLD: float = 0.015
BUILDUP_MIN_TOTAL_RISE: float = 0.15
DROP_ENERGY_THRESHOLD: float = 0.7
DROP_LOOKBACK_BEATS: int = 8
BREAKDOWN_HIGH_THRESHOLD: float = 0.6
BREAKDOWN_LOW_THRESHOLD: float = 0.35
BREAKDOWN_EXTEND_THRESHOLD: float = 0.45
VERSE_CHORUS_SPLIT: float = 0.5
MIN_SEGMENT_BEATS: int = 8
