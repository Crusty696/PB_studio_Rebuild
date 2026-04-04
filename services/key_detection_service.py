"""Key Detection Service — ML-basierte Tonerkennung (Ensemble).

Erkennt die Tonart eines Audio-Tracks mit:
- Ensemble-Methode: Krumhansl-Kessler + Temperley-Kostka-Payne Profile (gewichtet)
- Chroma CENS (rauschrobust) + Chroma CQT (klangtreu) Feature-Ensemble
- Key-Modulation-Tracking fuer DJ-Mixes (Sliding-Window, 30s/15s)
- Harmonic Tension Curve (Dissonanz-Verlauf relativ zum erkannten Key)
- Camelot-Wheel-Kompatibilitaet und harmonischer Distanz-Berechnung
"""

import logging
from dataclasses import dataclass, field

import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    _HAS_LIBROSA = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pitch class names (chromatic, starting from C)
# ---------------------------------------------------------------------------
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# ---------------------------------------------------------------------------
# Krumhansl-Kessler tonal profiles (starting from C)
# ---------------------------------------------------------------------------
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# ---------------------------------------------------------------------------
# Temperley-Kostka-Payne tonal profiles (starting from C)
# Quelle: Temperley 2001 "The Cognition of Basic Musical Structures"
# Robuster fuer modale und elektronische Musik
# ---------------------------------------------------------------------------
_TKP_MAJOR = np.array([0.748, 0.060, 0.488, 0.082, 0.670, 0.460, 0.096, 0.715, 0.104, 0.366, 0.057, 0.400])
_TKP_MINOR = np.array([0.712, 0.084, 0.474, 0.618, 0.049, 0.460, 0.105, 0.747, 0.404, 0.067, 0.133, 0.330])

# Ensemble weights: KK und TKP (summe = 1.0)
_WEIGHT_KK: float = 0.6
_WEIGHT_TKP: float = 0.4

# ---------------------------------------------------------------------------
# Camelot Wheel Mapping: Key -> Camelot Code (sharp + flat aliases)
# ---------------------------------------------------------------------------
CAMELOT_WHEEL = {
    # Sharp notation
    "C": "8B",   "Cm": "5A",   "C#": "3B",  "C#m": "12A",
    "D": "10B",  "Dm": "7A",   "D#": "5B",  "D#m": "2A",
    "E": "12B",  "Em": "9A",   "F": "7B",   "Fm": "4A",
    "F#": "2B",  "F#m": "11A", "G": "9B",   "Gm": "6A",
    "G#": "4B",  "G#m": "1A",  "A": "11B",  "Am": "8A",
    "A#": "6B",  "A#m": "3A",  "B": "1B",   "Bm": "10A",
    # Flat aliases
    "Db": "3B",  "Dbm": "12A",
    "Eb": "5B",  "Ebm": "2A",
    "Gb": "2B",  "Gbm": "11A",
    "Ab": "4B",  "Abm": "1A",
    "Bb": "6B",  "Bbm": "3A",
}

# Reverse mapping: Camelot Code -> canonical Key name
_CAMELOT_TO_KEY = {v: k for k, v in CAMELOT_WHEEL.items() if len(k) <= 3}


@dataclass
class KeyResult:
    """Ergebnis der ML-basierten Key-Erkennung."""
    key: str                         # z.B. "Am", "C#m", "F"
    camelot: str                     # z.B. "8A", "3B"
    confidence: float                # 0.0-1.0
    is_minor: bool
    method: str = "ensemble"         # "ensemble" | "kk_only"
    modulation_segments: list = field(default_factory=list)
    # [{time: float, key: str, camelot: str, confidence: float}, ...]
    harmonic_tension_curve: list = field(default_factory=list)
    # [float, ...] — Dissonanz-Werte [0.0-1.0] pro TENSION_RESOLUTION_SEC


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation between two arrays (returns 0 on degenerate input)."""
    if x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _ensemble_correlations(chroma_avg: np.ndarray) -> list[tuple[float, int, bool]]:
    """Berechnet Ensemble-Korrelationen fuer alle 24 Keys (Major + Minor).

    Kombiniert KK und TKP Profile gewichtet und gibt eine sortierte Liste
    (correlation, key_index, is_minor) zurueck.
    """
    correlations = []
    for shift in range(12):
        # Rotation: neg. shift passt Referenz an feste chroma-Reihenfolge (C..B) an
        kk_maj = np.roll(_KK_MAJOR, -shift)
        kk_min = np.roll(_KK_MINOR, -shift)
        tkp_maj = np.roll(_TKP_MAJOR, -shift)
        tkp_min = np.roll(_TKP_MINOR, -shift)

        corr_major = _WEIGHT_KK * _pearson(chroma_avg, kk_maj) + _WEIGHT_TKP * _pearson(chroma_avg, tkp_maj)
        corr_minor = _WEIGHT_KK * _pearson(chroma_avg, kk_min) + _WEIGHT_TKP * _pearson(chroma_avg, tkp_min)

        correlations.append((corr_major, shift, False))
        correlations.append((corr_minor, shift, True))

    correlations.sort(key=lambda x: x[0], reverse=True)
    return correlations


def _confidence_from_correlations(correlations: list[tuple]) -> float:
    """Berechnet Confidence aus der Korrelationsverteilung."""
    from services.audio_constants import CONFIDENCE_EPSILON
    all_corrs = np.array([c[0] for c in correlations])
    max_c = all_corrs.max()
    min_c = all_corrs.min()
    mean_c = all_corrs.mean()
    if (max_c - min_c) > CONFIDENCE_EPSILON:
        conf = float((max_c - mean_c) / (max_c - min_c))
    else:
        conf = 0.0
    return max(0.0, min(1.0, conf))


def _detect_key_from_chroma(chroma_avg: np.ndarray) -> tuple[str, str, float, bool]:
    """Kernlogik: Erkennt Key + Camelot + Confidence aus einem Chroma-Vektor.

    Returns:
        (key_name, camelot, confidence, is_minor)
    """
    correlations = _ensemble_correlations(chroma_avg)
    best_corr, best_idx, best_minor = correlations[0]

    key_name = KEY_NAMES[best_idx]
    if best_minor:
        key_name += "m"

    camelot = CAMELOT_WHEEL.get(key_name, "??")
    confidence = round(_confidence_from_correlations(correlations), 3)
    return key_name, camelot, confidence, best_minor


def harmonic_distance(camelot1: str, camelot2: str) -> int:
    """Berechnet den harmonischen Abstand zweier Camelot-Codes.

    0 = identisch
    1 = adjacent (ein Schritt auf dem Wheel, oder gleiche Zahl, andere Tonalitaet)
    2 = zwei Schritte ...
    13 = unbekannt / nicht berechenbar

    Args:
        camelot1: z.B. "8B"
        camelot2: z.B. "5A"

    Returns:
        Harmonischer Abstand als Integer
    """
    if not camelot1 or not camelot2 or "?" in camelot1 or "?" in camelot2:
        return 13
    if camelot1 == camelot2:
        return 0
    try:
        n1, m1 = int(camelot1[:-1]), camelot1[-1]
        n2, m2 = int(camelot2[:-1]), camelot2[-1]
    except (ValueError, IndexError):
        return 13

    mode_cost = 0 if m1 == m2 else 1
    wheel_dist = min(abs(n1 - n2), 12 - abs(n1 - n2))
    return wheel_dist + mode_cost


class KeyDetectionService:
    """Erkennt die musikalische Tonart eines Audio-Tracks (ML-Ensemble)."""

    def detect_key(self, file_path: str) -> KeyResult:
        """Erkennt die Tonart aus einer Audio-Datei.

        Laeuft vollstaendige Analyse:
        - Ensemble Key Detection (KK + TKP, CENS + CQT)
        - Modulation Tracking (bei Tracks >= MIN_DURATION_MODULATION)
        - Harmonic Tension Curve

        Args:
            file_path: Pfad zur Audio-Datei (WAV, MP3, FLAC)

        Returns:
            KeyResult mit Key, Camelot, Confidence, Modulation und Tension
        """
        fallback = KeyResult(key="Am", camelot="8A", confidence=0.0, is_minor=True, method="fallback")

        if not _HAS_LIBROSA:
            log.warning("librosa nicht installiert — Key Detection nicht verfuegbar")
            return fallback

        try:
            from services.audio_constants import (
                DEFAULT_SR, MAX_DURATION_MODULATION, CHROMA_HOP_LENGTH,
                MIN_DURATION_MODULATION, MODULATION_WINDOW_SEC, MODULATION_HOP_SEC,
                TENSION_RESOLUTION_SEC,
            )

            # ------------------------------------------------------------------
            # 1. Audio laden — bis zu MAX_DURATION_MODULATION fuer volle Analyse
            # ------------------------------------------------------------------
            y, sr = librosa.load(file_path, sr=DEFAULT_SR, mono=True, duration=MAX_DURATION_MODULATION)
            if y is None or len(y) == 0:
                log.warning("Audio-Datei leer oder nicht lesbar: %s", file_path)
                return fallback

            duration_sec = len(y) / sr

            # ------------------------------------------------------------------
            # 2. Feature Ensemble: Chroma CQT + Chroma CENS (rauschrobust)
            #    Benutze ersten 120s fuer den globalen Key (schnell + stabil)
            # ------------------------------------------------------------------
            max_key_samples = int(120.0 * sr)
            y_key = y[:max_key_samples]

            chroma_cqt = librosa.feature.chroma_cqt(y=y_key, sr=sr, hop_length=CHROMA_HOP_LENGTH)
            chroma_cens = librosa.feature.chroma_cens(y=y_key, sr=sr, hop_length=CHROMA_HOP_LENGTH)

            # Gewichtetes Feature-Ensemble: CQT (klangtreu) + CENS (rauschrobust)
            chroma_avg = 0.5 * np.mean(chroma_cqt, axis=1) + 0.5 * np.mean(chroma_cens, axis=1)

            # ------------------------------------------------------------------
            # 3. Ensemble Key Detection (KK + TKP Profile)
            # ------------------------------------------------------------------
            key_name, camelot, confidence, is_minor = _detect_key_from_chroma(chroma_avg)
            best_shift = KEY_NAMES.index(key_name.replace("m", ""))

            log.info(
                "Key detected (ensemble): %s (Camelot %s), confidence=%.2f",
                key_name, camelot, confidence,
            )

            # ------------------------------------------------------------------
            # 4. Harmonic Tension Curve
            #    Dissonanz jedes Frames relativ zum erkannten Key
            # ------------------------------------------------------------------
            tension_curve = self._compute_tension_curve(
                y_key, sr, best_shift, is_minor,
                CHROMA_HOP_LENGTH, TENSION_RESOLUTION_SEC,
            )

            # ------------------------------------------------------------------
            # 5. Key Modulation Tracking (nur bei langen Tracks)
            # ------------------------------------------------------------------
            modulation_segments: list[dict] = []
            if duration_sec >= MIN_DURATION_MODULATION:
                modulation_segments = self._detect_modulation_segments(
                    y, sr, CHROMA_HOP_LENGTH,
                    MODULATION_WINDOW_SEC, MODULATION_HOP_SEC,
                )
                log.info(
                    "Modulation tracking: %d Segmente erkannt (Dauer=%.0fs)",
                    len(modulation_segments), duration_sec,
                )

            return KeyResult(
                key=key_name,
                camelot=camelot,
                confidence=confidence,
                is_minor=is_minor,
                method="ensemble",
                modulation_segments=modulation_segments,
                harmonic_tension_curve=tension_curve,
            )

        except (OSError, IOError, ValueError, RuntimeError) as e:
            log.exception("Fehler bei der Key-Erkennung fuer: %s", file_path)
            log.warning("detect_key(): fallback result returned due to: %s", e)
            return fallback

    def _compute_tension_curve(
        self,
        y: np.ndarray,
        sr: int,
        key_shift: int,
        is_minor: bool,
        hop_length: int,
        resolution_sec: float,
    ) -> list[float]:
        """Berechnet die Harmonic Tension Curve relativ zum erkannten Key.

        Tension = 1 - normierte Korrelation zwischen Frame-Chroma und Key-Profil.
        Hohe Tension = hohe Dissonanz (Modulation, fremde Akkorde).
        Niedrige Tension = harmonisches Zentrum (Key-Bestaetigung).

        Returns:
            Liste von Tension-Werten [0.0-1.0], je TENSION_RESOLUTION_SEC
        """
        try:
            chroma = librosa.feature.chroma_cens(y=y, sr=sr, hop_length=hop_length)
            profile = np.roll(_KK_MINOR if is_minor else _KK_MAJOR, -key_shift)
            # Normalisieren fuer stabilen Pearson-Vergleich
            profile_std = profile.std()
            if profile_std < 1e-9:
                return []

            frames_per_resolution = max(1, int(resolution_sec * sr / hop_length))
            n_frames = chroma.shape[1]
            tension_values = []

            for i in range(0, n_frames, frames_per_resolution):
                block = chroma[:, i:i + frames_per_resolution]
                frame_avg = np.mean(block, axis=1)
                corr = _pearson(frame_avg, profile)
                # corr ∈ [-1, 1] → tension ∈ [0, 1]: hohe Korrelation = niedrige Tension
                tension = max(0.0, min(1.0, (1.0 - corr) / 2.0))
                tension_values.append(round(float(tension), 3))

            return tension_values
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as e:
            log.warning("Tension Curve Berechnung fehlgeschlagen: %s", e)
            return []

    def _detect_modulation_segments(
        self,
        y: np.ndarray,
        sr: int,
        hop_length: int,
        window_sec: float,
        hop_sec: float,
    ) -> list[dict]:
        """Sliding-Window Key Detection fuer Modulation-Tracking.

        Analysiert den Track in ueberlappenden Fenstern und gibt erkannte
        Key-Segmente zurueck. Aufeinanderfolgende identische Keys werden
        zusammengefasst.

        Returns:
            Liste von Dicts: [{time: float, key: str, camelot: str, confidence: float}, ...]
        """
        try:
            window_samples = int(window_sec * sr)
            hop_samples = int(hop_sec * sr)
            total_samples = len(y)

            raw_segments = []
            pos = 0
            while pos + window_samples <= total_samples:
                window = y[pos:pos + window_samples]
                chroma = librosa.feature.chroma_cens(y=window, sr=sr, hop_length=hop_length)
                chroma_avg = np.mean(chroma, axis=1)
                key_name, camelot, confidence, _ = _detect_key_from_chroma(chroma_avg)
                time_sec = round(pos / sr, 1)
                raw_segments.append({
                    "time": time_sec,
                    "key": key_name,
                    "camelot": camelot,
                    "confidence": confidence,
                })
                pos += hop_samples

            # Zusammenfassen: aufeinanderfolgende gleiche Keys mergen
            return _merge_modulation_segments(raw_segments)

        except (ValueError, RuntimeError, OSError) as e:
            log.warning("Modulation Tracking fehlgeschlagen: %s", e)
            return []

    def get_compatible_keys(self, key: str) -> list[str]:
        """Gibt kompatible Keys zurueck (Camelot-Wheel Nachbarn).

        Nuetzlich fuer DJ-Mix Uebergangserkennung.
        """
        camelot = CAMELOT_WHEEL.get(key)
        if not camelot:
            return []
        num = int(camelot[:-1])
        letter = camelot[-1]
        neighbors = []
        # Gleiche Nummer, andere Tonalitaet (Major<->Minor)
        neighbors.append(f"{num}{'A' if letter == 'B' else 'B'}")
        # +1 und -1 auf dem Wheel
        neighbors.append(f"{(num % 12) + 1}{letter}")
        neighbors.append(f"{((num - 2) % 12) + 1}{letter}")
        return neighbors

    def get_camelot_neighbors(self, camelot: str) -> list[str]:
        """Gibt alle harmonisch kompatiblen Camelot-Codes zurueck (1A-12B).

        Erweiterte Version von get_compatible_keys() — gibt direkt Camelot-Codes.
        """
        if not camelot or "?" in camelot:
            return []
        try:
            num = int(camelot[:-1])
            letter = camelot[-1]
        except (ValueError, IndexError):
            return []
        return [
            camelot,                                     # selbst
            f"{num}{'A' if letter == 'B' else 'B'}",   # gleiche Zahl, andere Tonalitaet
            f"{(num % 12) + 1}{letter}",                # +1
            f"{((num - 2) % 12) + 1}{letter}",          # -1
        ]


def _merge_modulation_segments(raw: list[dict]) -> list[dict]:
    """Fasst aufeinanderfolgende Segmente mit gleichem Key zusammen.

    Behaelt den ersten Zeitstempel und mittelt die Confidence.
    """
    if not raw:
        return []
    merged = []
    current = dict(raw[0])
    conf_sum = current["confidence"]
    count = 1

    for seg in raw[1:]:
        if seg["key"] == current["key"]:
            conf_sum += seg["confidence"]
            count += 1
        else:
            current["confidence"] = round(conf_sum / count, 3)
            merged.append(current)
            current = dict(seg)
            conf_sum = seg["confidence"]
            count = 1

    current["confidence"] = round(conf_sum / count, 3)
    merged.append(current)
    return merged
