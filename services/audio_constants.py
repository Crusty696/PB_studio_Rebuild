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

# -- Key Modulation Tracking -------------------------------------------
MAX_DURATION_MODULATION: float = 600.0   # 10 Min fuer Modulation-Tracking
MODULATION_WINDOW_SEC: float = 30.0      # Sliding-Window Breite
MODULATION_HOP_SEC: float = 15.0         # Sliding-Window Schritt
MIN_DURATION_MODULATION: float = 90.0    # Min. Tracklaenge fuer Modulation-Tracking
TENSION_RESOLUTION_SEC: float = 2.0      # Tension-Curve Aufloesung (Sek/Wert)

# -- LUFS --------------------------------------------------------------
FFMPEG_TIMEOUT_SEC: int = 120
MIN_LUFS_DB: float = -70.0   # Clamp fuer -inf
MAX_LUFS_DB: float = 0.0     # Clamp fuer +inf
ST_MAX_HEADROOM_DB: float = 3.0  # Short-term max darf TP + 3dB nicht uebersteigen

# -- Classification Thresholds -----------------------------------------
HIGH_CENTROID_HZ: float = 3500.0
MID_CENTROID_HZ: float = 3000.0
LOW_CENTROID_HZ: float = 2000.0
VERY_LOW_CENTROID_HZ: float = 1500.0
HIGH_RMS: float = 0.08
MID_RMS: float = 0.05
LOW_RMS: float = 0.03
VERY_HIGH_RMS: float = 0.1

# -- Sub-Genre Classification ------------------------------------------
MIN_SUB_GENRE_SCORE: float = 0.45   # Min. Gesamt-Score fuer Sub-Genre-Zuweisung

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

# -- WARMUP Detection (F-005) ------------------------------------------
WARMUP_ENERGY_MIN: float = 0.3        # Min. Energie fuer WARMUP
WARMUP_ENERGY_MAX: float = 0.55       # Max. Energie fuer WARMUP
WARMUP_MIN_BEATS: int = 8             # Min. Laenge eines WARMUP
WARMUP_MAX_POSITION: float = 0.4      # WARMUP nur in ersten 40% des Tracks
WARMUP_GRADIENT_MIN: float = 0.005    # Min. positive Gradient (sanfter Anstieg)
WARMUP_CENTROID_RISING: float = 0.4   # Min. Spectral Centroid fuer WARMUP

# -- Multi-Feature Section Detection -----------------------------------
BASS_FREQ_MAX_HZ: float = 250.0          # Bass band cutoff (Hz)
SPECTRAL_CENTROID_HIGH: float = 0.65     # Normalized centroid → high-energy section
SPECTRAL_CENTROID_LOW: float = 0.35      # Normalized centroid → calm section
BEAT_REGULARITY_THRESHOLD: float = 0.12  # IBI std-dev threshold (regular = EDM drop)
MULTI_FEATURE_BASS_DROP_THRESHOLD: float = 0.6   # Bass energy threshold for DROP label

# -- Input Validation Ranges -------------------------------------------
BPM_MIN: float = 40.0       # Untergrenze: langsamstes sinnvolles BPM (Downtempo)
BPM_MAX: float = 300.0      # Obergrenze: schnellstes sinnvolles BPM (Hardcore/Speedcore)
CONFIDENCE_MIN: float = 0.0  # Konfidenz-Werte immer im Bereich [0, 1]
CONFIDENCE_MAX: float = 1.0
ENERGY_MIN: float = 0.0      # Normalisierte Energie immer im Bereich [0, 1]
ENERGY_MAX: float = 1.0


def clamp_bpm(value: float | None) -> float | None:
    """Clamp BPM to the valid DJ/music range [40, 300].

    Returns None if value is None; raises ValueError for NaN/inf.
    """
    # L-7 Fix: Type annotation now matches actual behavior (can return None)
    if value is None:
        return None
    import math
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"Ungültiger BPM-Wert: {value}")
    return max(BPM_MIN, min(BPM_MAX, float(value)))


def clamp_confidence(value: float) -> float:
    """Clamp confidence score to [0.0, 1.0].

    Returns None if value is None.
    """
    if value is None:
        return None
    return max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, float(value)))


def clamp_energy(value: float) -> float:
    """Clamp a single normalized energy value to [0.0, 1.0].

    Returns None if value is None.
    """
    if value is None:
        return None
    return max(ENERGY_MIN, min(ENERGY_MAX, float(value)))


# -- Genre Detection (BPM-based) ---------------------------------------
GENRE_PSYTRANCE_BPM_MIN: float = 138.0
GENRE_PSYTRANCE_BPM_MAX: float = 150.0
GENRE_TECHNO_BPM_MIN: float = 125.0
GENRE_TECHNO_BPM_MAX: float = 145.0
GENRE_HOUSE_BPM_MIN: float = 118.0
GENRE_HOUSE_BPM_MAX: float = 132.0

# -- DJ-Mix Transition Detection ---------------------------------------
DJ_MIX_ENERGY_DIP_THRESHOLD: float = 0.25   # Normalized energy dip depth
DJ_MIX_TRANSITION_MIN_GAP_SEC: float = 60.0  # Min seconds between transitions
DJ_MIX_MIN_TRANSITIONS: int = 2              # Min transitions to classify as DJ mix

# -- Mastering / EBU R128 Compliance -----------------------------------
EBU_R128_BROADCAST_TARGET: float = -23.0   # LUFS, EBU R128 Broadcast-Standard
EBU_R128_BROADCAST_TOLERANCE: float = 1.0  # ±1 LU (akzeptiert: -24 bis -22 LUFS)
EBU_R128_STREAMING_MIN: float = -16.0      # Streaming untere Grenze (LUFS)
EBU_R128_STREAMING_MAX: float = -9.0       # Streaming obere Grenze (LUFS)
EBU_TRUE_PEAK_MAX: float = -1.0            # Maximaler True Peak (dBTP)
CREST_FACTOR_COMPRESSED_DB: float = 8.0   # Darunter = stark komprimiert
CREST_FACTOR_WIDE_DB: float = 15.0         # Darueber = weite Dynamik

# -- Stem-Namen (Audio-V2 Pipeline, OTK-018 Bucket-B) ------------------
# Reihenfolge entspricht Demucs-4-Stem-Output. Genutzt von
# services/stem_router.py (SERVICE_ROUTING / Stem-Auswahl pro Service).
STEM_NAMES: tuple[str, ...] = ("vocals", "drums", "bass", "other")
