"""Key Detection Service — Musikalische Tonerkennung (Krumhansl-Kessler + Camelot Wheel).

Erkennt die Tonart eines Audio-Tracks und gibt Key + Camelot-Code zurueck.
Nutzt librosa.feature.chroma fuer die Chroma-Analyse und Krumhansl-Kessler
Profil-Korrelation fuer die Tonerkennung.
"""

import logging
from dataclasses import dataclass

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


@dataclass
class KeyResult:
    """Ergebnis der Key-Erkennung."""
    key: str                # z.B. "Am", "C#m", "F"
    camelot: str            # z.B. "8A", "3B"
    confidence: float       # 0.0-1.0
    is_minor: bool


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation between two arrays (returns 0 on degenerate input)."""
    if x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


class KeyDetectionService:
    """Erkennt die musikalische Tonart eines Audio-Tracks."""

    def detect_key(self, file_path: str) -> KeyResult:
        """Erkennt die Tonart aus einer Audio-Datei.

        Args:
            file_path: Pfad zur Audio-Datei (WAV, MP3, FLAC)

        Returns:
            KeyResult mit Key, Camelot-Code und Confidence
        """
        fallback = KeyResult(key="Am", camelot="8A", confidence=0.0, is_minor=True)

        if not _HAS_LIBROSA:
            log.warning("librosa nicht installiert — Key Detection nicht verfuegbar")
            return fallback

        try:
            # ------------------------------------------------------------------
            # 1. Audio laden (sr=22050, mono, max 120s fuer Performance)
            # ------------------------------------------------------------------
            from services.audio_constants import DEFAULT_SR, MAX_DURATION_KEY, CHROMA_HOP_LENGTH, CONFIDENCE_EPSILON
            y, sr = librosa.load(file_path, sr=DEFAULT_SR, mono=True, duration=MAX_DURATION_KEY)
            if y is None or len(y) == 0:
                log.warning("Audio-Datei leer oder nicht lesbar: %s", file_path)
                return fallback

            # ------------------------------------------------------------------
            # 2. Chroma-CQT Features extrahieren
            # ------------------------------------------------------------------
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=CHROMA_HOP_LENGTH)
            # chroma shape: (12, n_frames)

            # ------------------------------------------------------------------
            # 3. Durchschnittliches Chroma-Profil (12-dim Vektor)
            # ------------------------------------------------------------------
            chroma_avg = np.mean(chroma, axis=1)  # shape (12,)

            # ------------------------------------------------------------------
            # 4+5+6. Korrelation mit Krumhansl-Kessler Profilen fuer alle
            #         12 Rotationen (Pitch-Classes C..B), Major + Minor
            # ------------------------------------------------------------------
            correlations = []  # (correlation, key_index, is_minor)

            for shift in range(12):
                # G-01: Rotation direction: np.roll(_KK_MAJOR, -shift) rotiert das
                # Referenzprofil nach LINKS um `shift` Positionen. Das bedeutet:
                # Bei shift=0 (C) bleibt das Profil unveraendert.
                # Bei shift=1 (C#) wird das Profil so rotiert, dass Index 0
                # dem Profil-Eintrag fuer C# als Tonika entspricht.
                # Die NEGATIVE Richtung ist korrekt, weil wir das Referenzprofil
                # an die feste chroma_avg-Reihenfolge (C, C#, D, ...) anpassen,
                # NICHT umgekehrt. Equivalent zu: chroma_avg um +shift rotieren.
                rotated_major = np.roll(_KK_MAJOR, -shift)
                rotated_minor = np.roll(_KK_MINOR, -shift)

                corr_major = _pearson(chroma_avg, rotated_major)
                corr_minor = _pearson(chroma_avg, rotated_minor)

                correlations.append((corr_major, shift, False))
                correlations.append((corr_minor, shift, True))

            # ------------------------------------------------------------------
            # 7. Hoechste Korrelation = erkannter Key
            # ------------------------------------------------------------------
            correlations.sort(key=lambda x: x[0], reverse=True)
            best_corr, best_idx, best_minor = correlations[0]

            key_name = KEY_NAMES[best_idx]
            if best_minor:
                key_name += "m"

            camelot = CAMELOT_WHEEL.get(key_name, "??")

            # ------------------------------------------------------------------
            # 8. Confidence = (max_corr - mean_corr) / (max_corr - min_corr)
            # ------------------------------------------------------------------
            all_corrs = np.array([c[0] for c in correlations])
            max_c = all_corrs.max()
            min_c = all_corrs.min()
            mean_c = all_corrs.mean()

            if (max_c - min_c) > CONFIDENCE_EPSILON:
                confidence = float((max_c - mean_c) / (max_c - min_c))
            else:
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))

            log.info(
                "Key detected: %s (Camelot %s), confidence=%.2f, corr=%.4f",
                key_name, camelot, confidence, best_corr,
            )
            return KeyResult(
                key=key_name,
                camelot=camelot,
                confidence=round(confidence, 3),
                is_minor=best_minor,
            )

        except Exception as e:
            log.exception("Fehler bei der Key-Erkennung fuer: %s", file_path)
            log.warning("detect_key(): fallback result returned due to: %s", e)
            return fallback

    def get_compatible_keys(self, key: str) -> list[str]:
        """Gibt kompatible Keys zurück (Camelot-Wheel Nachbarn).

        Nützlich für DJ-Mix Übergangserkennung.
        """
        camelot = CAMELOT_WHEEL.get(key)
        if not camelot:
            return []
        num = int(camelot[:-1])
        letter = camelot[-1]
        neighbors = []
        # Gleiche Nummer, andere Tonalität (Major↔Minor)
        neighbors.append(f"{num}{'A' if letter == 'B' else 'B'}")
        # +1 und -1 auf dem Wheel
        neighbors.append(f"{(num % 12) + 1}{letter}")
        neighbors.append(f"{((num - 2) % 12) + 1}{letter}")
        return neighbors
