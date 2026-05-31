"""Audio Classification Service — Mood/Genre Erkennung.

Klassifiziert einen Audio-Track nach Stimmung (Mood) und Genre.
Nutzt Audio-Features (Spektral, Rhythmik, Harmonie) für die Klassifikation.
"""

import logging
from dataclasses import dataclass

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    librosa = None  # type: ignore[assignment]
    _HAS_LIBROSA = False

log = logging.getLogger(__name__)


@dataclass
class ClassifyResult:
    """Ergebnis der Audio-Klassifikation."""
    mood: str               # "energetic", "melancholic", "dark", "euphoric", "chill"
    genre: str              # "Psytrance", "Techno", "House", "DnB", "Ambient"
    energy_level: str       # "low", "medium", "high"
    is_dj_mix: bool         # DJ-Mix erkannt (Übergänge, BPM-Wechsel)
    confidence: float       # 0.0-1.0
    description: str        # Menschenlesbarer Text
    sub_genre: str = ""     # Sub-Genre z.B. "Dark Psytrance", "Deep House", "Neurofunk"


# Feature-basierte Heuristiken für Genre-Erkennung
GENRE_BPM_RANGES = {
    "Ambient": (60, 100),
    "Hip-Hop": (80, 115),
    "House": (118, 132),
    "Techno": (125, 150),
    "Trance": (130, 150),
    "Psytrance": (140, 155),
    "Drum & Bass": (160, 180),
    "Dubstep": (135, 145),
}


# Sub-Genre Fingerprints: {parent_genre: {sub_genre: {feature: (min, max)}}}
# Features: bpm, centroid (Hz), rms, zcr (zero-crossing rate)
SUB_GENRE_FINGERPRINTS: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
    "Psytrance": {
        "Full-On Psytrance": {
            "bpm": (143.0, 150.0),
            "centroid": (2800.0, 4500.0),
            "rms": (0.07, 0.15),
            "zcr": (0.05, 0.15),
        },
        "Progressive Psytrance": {
            "bpm": (138.0, 145.0),
            "centroid": (2000.0, 3500.0),
            "rms": (0.05, 0.10),
            "zcr": (0.03, 0.10),
        },
        "Dark Psytrance": {
            "bpm": (148.0, 158.0),
            "centroid": (1200.0, 2500.0),
            "rms": (0.08, 0.18),
            "zcr": (0.06, 0.18),
        },
        "Goa Trance": {
            "bpm": (140.0, 148.0),
            "centroid": (3000.0, 5000.0),
            "rms": (0.06, 0.12),
            "zcr": (0.04, 0.12),
        },
    },
    "Techno": {
        "Industrial Techno": {
            "bpm": (140.0, 155.0),
            "centroid": (2500.0, 5000.0),
            "rms": (0.08, 0.20),
            "zcr": (0.08, 0.25),
        },
        "Minimal Techno": {
            "bpm": (128.0, 136.0),
            "centroid": (1500.0, 3000.0),
            "rms": (0.04, 0.08),
            "zcr": (0.02, 0.08),
        },
        "Acid Techno": {
            "bpm": (133.0, 145.0),
            "centroid": (2000.0, 4000.0),
            "rms": (0.06, 0.12),
            "zcr": (0.04, 0.12),
        },
        "Detroit Techno": {
            "bpm": (128.0, 138.0),
            "centroid": (2000.0, 3500.0),
            "rms": (0.05, 0.10),
            "zcr": (0.03, 0.10),
        },
        "Hard Techno": {
            "bpm": (145.0, 162.0),
            "centroid": (2800.0, 5500.0),
            "rms": (0.09, 0.22),
            "zcr": (0.07, 0.22),
        },
    },
    "House": {
        "Deep House": {
            "bpm": (118.0, 125.0),
            "centroid": (1200.0, 2500.0),
            "rms": (0.04, 0.08),
            "zcr": (0.02, 0.07),
        },
        "Tech House": {
            "bpm": (122.0, 130.0),
            "centroid": (2000.0, 3500.0),
            "rms": (0.06, 0.12),
            "zcr": (0.04, 0.11),
        },
        "Melodic House": {
            "bpm": (120.0, 127.0),
            "centroid": (2500.0, 4500.0),
            "rms": (0.05, 0.10),
            "zcr": (0.03, 0.10),
        },
        "Progressive House": {
            "bpm": (124.0, 132.0),
            "centroid": (2200.0, 4000.0),
            "rms": (0.06, 0.12),
            "zcr": (0.03, 0.11),
        },
        "Afro House": {
            "bpm": (118.0, 126.0),
            "centroid": (1800.0, 3500.0),
            "rms": (0.05, 0.10),
            "zcr": (0.04, 0.12),
        },
    },
    "Drum & Bass": {
        "Liquid DnB": {
            "bpm": (168.0, 180.0),
            "centroid": (2200.0, 4000.0),
            "rms": (0.05, 0.11),
            "zcr": (0.04, 0.12),
        },
        "Neurofunk": {
            "bpm": (172.0, 180.0),
            "centroid": (1500.0, 3000.0),
            "rms": (0.07, 0.15),
            "zcr": (0.05, 0.18),
        },
        "Jump Up": {
            "bpm": (172.0, 182.0),
            "centroid": (2500.0, 5000.0),
            "rms": (0.08, 0.18),
            "zcr": (0.06, 0.20),
        },
        "Jungle": {
            "bpm": (158.0, 172.0),
            "centroid": (2000.0, 4000.0),
            "rms": (0.06, 0.14),
            "zcr": (0.05, 0.15),
        },
        "Drumstep": {
            "bpm": (140.0, 160.0),
            "centroid": (2000.0, 4000.0),
            "rms": (0.06, 0.14),
            "zcr": (0.04, 0.15),
        },
    },
}


def _fallback_result(reason: str = "librosa nicht verfuegbar") -> ClassifyResult:
    """Return a sensible default when analysis cannot run."""
    return ClassifyResult(
        mood="unknown",
        genre="Unknown",
        energy_level="medium",
        is_dj_mix=False,
        confidence=0.0,
        description=f"Klassifikation nicht moeglich: {reason}",
    )


class AudioClassifyService:
    """Klassifiziert Audio-Tracks nach Mood und Genre."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, file_path: str, bpm: float | None = None) -> ClassifyResult:
        """Klassifiziert einen Audio-Track.

        Args:
            file_path: Pfad zur Audio-Datei
            bpm: Bereits erkannter BPM-Wert (optional, spart Neuberechnung)

        Returns:
            ClassifyResult mit Mood, Genre, Energy
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            log.warning("classify(): librosa/numpy nicht installiert — Fallback")
            return _fallback_result("librosa/numpy nicht installiert")

        try:
            # ----------------------------------------------------------
            # 1. Audio laden
            # ----------------------------------------------------------
            from services.audio_constants import DEFAULT_SR, MAX_DURATION_CLASSIFY
            y, sr = librosa.load(file_path, sr=DEFAULT_SR, mono=True, duration=MAX_DURATION_CLASSIFY)
            # L-8 Fix: librosa.load() never returns None (raises exception instead)
            if len(y) == 0:
                log.warning("classify(): Leere Audio-Daten fuer %s", file_path)
                return _fallback_result("Leere Audio-Daten")

            # ----------------------------------------------------------
            # 2. Feature-Extraktion
            # ----------------------------------------------------------
            spectral_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
            spectral_rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
            rms_energy = float(np.mean(librosa.feature.rms(y=y)))
            zero_crossing = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))

            # BPM — re-use caller value or detect
            if bpm is not None and bpm > 0:
                tempo = float(bpm)
            else:
                _tempo_arr, _ = librosa.beat.beat_track(y=y, sr=sr)
                # librosa >= 0.10 returns an array; older versions a scalar
                tempo = float(np.atleast_1d(_tempo_arr)[0])

            log.debug(
                "Features — centroid=%.0f rolloff=%.0f rms=%.4f zcr=%.4f bpm=%.1f",
                spectral_centroid, spectral_rolloff, rms_energy, zero_crossing, tempo,
            )

            # ----------------------------------------------------------
            # 3. Genre-Klassifikation (BPM + Spectral)
            # ----------------------------------------------------------
            genre, confidence = self._classify_genre(
                tempo, spectral_centroid, rms_energy,
            )

            # ----------------------------------------------------------
            # 3b. Sub-Genre-Klassifikation (spektral + rhythmisch)
            # ----------------------------------------------------------
            sub_genre, sub_confidence = self._classify_sub_genre(
                genre, tempo, spectral_centroid, rms_energy, zero_crossing,
            )
            # Wenn Sub-Genre erkannt → hebe Confidence an
            if sub_genre != genre:
                confidence = max(confidence, sub_confidence)

            # ----------------------------------------------------------
            # 4. Mood-Klassifikation
            # ----------------------------------------------------------
            mood = self._classify_mood(spectral_centroid, rms_energy)

            # ----------------------------------------------------------
            # 5. Energy Level
            # ----------------------------------------------------------
            energy_level = self._classify_energy(rms_energy)

            # ----------------------------------------------------------
            # 6. DJ-Mix Erkennung (schnell, wiederverwendet geladenes y)
            # ----------------------------------------------------------
            duration_sec = float(len(y)) / sr
            is_dj_mix = self._quick_dj_mix_check(y, sr, duration_sec, tempo)

            # ----------------------------------------------------------
            # 7. Beschreibung generieren
            # ----------------------------------------------------------
            display_genre = sub_genre if sub_genre != genre else genre
            description = (
                f"{display_genre}-Track, {mood} Stimmung, "
                f"Energie {energy_level} "
                f"(BPM {tempo:.0f}, Centroid {spectral_centroid:.0f} Hz)"
            )
            if is_dj_mix:
                description += " — vermutlich ein DJ-Mix"

            return ClassifyResult(
                mood=mood,
                genre=genre,
                energy_level=energy_level,
                is_dj_mix=is_dj_mix,
                confidence=confidence,
                description=description,
                sub_genre=sub_genre if sub_genre != genre else "",
            )

        except (OSError, IOError, ValueError, RuntimeError):
            # M-16 Fix: Remove redundant warning (exception already logs stack trace + message)
            log.exception("classify() fehlgeschlagen fuer %s", file_path)
            return _fallback_result("Analyse-Fehler")

    def detect_dj_mix(self, file_path: str) -> bool:
        """Erkennt ob eine Audio-Datei ein DJ-Mix ist.

        Heuristik:
        - Dateilaenge > 10 Min (Pflicht)
        - BPM-Varianz ueber drei Segmente (Anfang / Mitte / Ende)
        - Dateilaenge > 30 Min = sehr wahrscheinlich Mix
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            log.warning("detect_dj_mix(): librosa/numpy nicht installiert — False")
            return False

        try:
            # ----------------------------------------------------------
            # 1. Gesamtdauer pruefen
            # ----------------------------------------------------------
            from services.audio_constants import (
                DEFAULT_SR, MIN_MIX_DURATION_SEC, LIKELY_MIX_DURATION_SEC,
                BPM_VARIANCE_THRESHOLD,
            )
            duration = librosa.get_duration(path=file_path)
            if duration < MIN_MIX_DURATION_SEC:
                log.debug("detect_dj_mix(): Datei zu kurz (%.0fs < 600s)", duration)
                return False

            # Sehr lange Dateien sind fast immer Mixes
            if duration > LIKELY_MIX_DURATION_SEC:  # > 30 min
                log.info("detect_dj_mix(): Datei > 30 Min (%.0fs) — DJ-Mix angenommen", duration)
                return True

            # ----------------------------------------------------------
            # 2. Drei Segmente laden (je 60s)
            # ----------------------------------------------------------
            sr = DEFAULT_SR
            seg_dur = 60.0
            mid_offset = max(0.0, (duration / 2.0) - 30.0)
            end_offset = max(0.0, duration - 60.0)

            offsets = [0.0, mid_offset, end_offset]
            tempos: list[float] = []

            for off in offsets:
                y_seg, _ = librosa.load(
                    file_path, sr=sr, mono=True,
                    offset=off, duration=seg_dur,
                )
                if y_seg is None or len(y_seg) == 0:
                    continue
                _t, _ = librosa.beat.beat_track(y=y_seg, sr=sr)
                tempos.append(float(np.atleast_1d(_t)[0]))

            if len(tempos) < 2:
                log.debug("detect_dj_mix(): Nicht genug Segmente analysiert")
                return False

            # ----------------------------------------------------------
            # 3. BPM-Varianz pruefen
            # ----------------------------------------------------------
            tempo_arr = np.array(tempos)
            tempo_var = float(np.ptp(tempo_arr))  # max - min
            log.debug(
                "detect_dj_mix(): Segment-BPMs=%s  Varianz=%.2f",
                tempos, tempo_var,
            )

            if tempo_var > BPM_VARIANCE_THRESHOLD:
                log.info(
                    "detect_dj_mix(): BPM-Varianz %.2f > 2.0 — DJ-Mix erkannt", tempo_var,
                )
                return True

            return False

        except (OSError, IOError, ValueError, RuntimeError):
            log.exception("detect_dj_mix() fehlgeschlagen fuer %s", file_path)
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_genre(
        tempo: float,
        spectral_centroid: float,
        rms_energy: float,
    ) -> tuple[str, float]:
        """BPM-basierte Genre-Erkennung mit spektraler Disambiguierung.

        Returns:
            (genre_name, confidence)
        """
        from services.audio_constants import MID_CENTROID_HZ, LOW_CENTROID_HZ, HIGH_RMS, MID_RMS

        # Sammle alle BPM-passenden Genres
        candidates: list[str] = []
        for genre, (lo, hi) in GENRE_BPM_RANGES.items():
            if lo <= tempo <= hi:
                candidates.append(genre)

        if not candidates:
            # Kein BPM-Match — bestes Raten anhand Spektral-Merkmale
            if spectral_centroid > MID_CENTROID_HZ and rms_energy > HIGH_RMS:
                return ("Techno", 0.4)
            if spectral_centroid < LOW_CENTROID_HZ:
                return ("Ambient", 0.4)
            return ("Unknown", 0.3)

        if len(candidates) == 1:
            return (candidates[0], 0.7)

        # Mehrere Kandidaten — disambiguiere ueber Spektral-Merkmale
        if spectral_centroid > MID_CENTROID_HZ and rms_energy > HIGH_RMS:
            # Bevorzuge energetische Genres
            for pref in ("Psytrance", "Drum & Bass", "Techno", "Trance"):
                if pref in candidates:
                    return (pref, 0.7)

        if spectral_centroid < LOW_CENTROID_HZ and rms_energy < MID_RMS:
            # Bevorzuge ruhige Genres
            for pref in ("Ambient", "Hip-Hop"):
                if pref in candidates:
                    return (pref, 0.7)

        # Medium-Bereich — bevorzuge House/Techno
        for pref in ("House", "Techno", "Trance", "Dubstep"):
            if pref in candidates:
                return (pref, 0.7)

        return (candidates[0], 0.7)

    @staticmethod
    def _classify_mood(spectral_centroid: float, rms_energy: float) -> str:
        """Mood-Bestimmung aus Spectral Centroid + RMS Energy."""
        from services.audio_constants import (
            HIGH_CENTROID_HZ, MID_CENTROID_HZ, LOW_CENTROID_HZ, VERY_LOW_CENTROID_HZ,
            VERY_HIGH_RMS, MID_RMS, LOW_RMS,
        )
        if spectral_centroid > HIGH_CENTROID_HZ and rms_energy > VERY_HIGH_RMS:
            return "energetic"
        if spectral_centroid > MID_CENTROID_HZ and rms_energy > MID_RMS:
            return "euphoric"
        if spectral_centroid < VERY_LOW_CENTROID_HZ and rms_energy < LOW_RMS:
            return "chill"
        if spectral_centroid < LOW_CENTROID_HZ and rms_energy < MID_RMS:
            return "melancholic"
        return "dark"

    @staticmethod
    def _classify_energy(rms_energy: float) -> str:
        """Energy-Level aus RMS-Wert."""
        from services.audio_constants import HIGH_RMS, LOW_RMS
        if rms_energy > HIGH_RMS:
            return "high"
        if rms_energy > LOW_RMS:
            return "medium"
        return "low"

    @staticmethod
    def _quick_dj_mix_check(
        y, sr: int, duration_sec: float, overall_tempo: float,
    ) -> bool:
        """Schnelle Mix-Pruefung auf bereits geladenen Audio-Daten.

        Wird innerhalb von classify() aufgerufen, um einen zusaetzlichen
        detect_dj_mix()-Call zu vermeiden.  Prueft nur Dauer + lokale
        BPM-Abweichung der ersten / letzten 30 Sekunden.
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            return False

        from services.audio_constants import MIN_MIX_DURATION_SEC, LIKELY_MIX_DURATION_SEC, BPM_VARIANCE_THRESHOLD

        if duration_sec < MIN_MIX_DURATION_SEC:
            return False

        if duration_sec > LIKELY_MIX_DURATION_SEC:
            return True

        try:
            seg_samples = int(30 * sr)
            if len(y) < seg_samples * 2:
                return False

            y_start = y[:seg_samples]
            y_end = y[-seg_samples:]

            t_start, _ = librosa.beat.beat_track(y=y_start, sr=sr)
            t_end, _ = librosa.beat.beat_track(y=y_end, sr=sr)

            t_start = float(np.atleast_1d(t_start)[0])
            t_end = float(np.atleast_1d(t_end)[0])

            variance = abs(t_start - t_end)
            if variance > BPM_VARIANCE_THRESHOLD:
                log.debug(
                    "_quick_dj_mix_check: BPM-Diff %.1f zwischen Start/Ende", variance,
                )
                return True
        except (OSError, IOError, ValueError, RuntimeError):
            log.debug("_quick_dj_mix_check: Fehler bei Segment-Analyse", exc_info=True)

        return False

    @staticmethod
    def _score_sub_genre(
        fingerprint: dict[str, tuple[float, float]],
        bpm: float,
        centroid: float,
        rms: float,
        zcr: float,
    ) -> float:
        """Bewertet wie gut ein Sub-Genre-Fingerprint zu den Features passt.

        Fuer jedes Feature wird der normalisierte Abstand vom Mittelpunkt des
        Zielbereichs berechnet.  Score 1.0 = exakt im Zentrum, 0.5 = am Rand,
        faellt linear ab ausserhalb des Bereichs.

        Returns:
            Mittlerer Score aller Features (0.0 – 1.0).
        """
        feature_values: dict[str, float] = {
            "bpm": bpm,
            "centroid": centroid,
            "rms": rms,
            "zcr": zcr,
        }
        scores: list[float] = []
        for feat, (lo, hi) in fingerprint.items():
            val = feature_values.get(feat, 0.0)
            mid = (lo + hi) / 2.0
            half_range = (hi - lo) / 2.0 if (hi - lo) > 0.0 else 1.0
            dist = abs(val - mid) / half_range  # 0 = Zentrum, 1 = Rand, >1 = aussen
            scores.append(max(0.0, 1.0 - 0.5 * dist))
        return sum(scores) / len(scores) if scores else 0.0

    def _classify_sub_genre(
        self,
        genre: str,
        bpm: float,
        centroid: float,
        rms: float,
        zcr: float,
    ) -> tuple[str, float]:
        """Praezise Sub-Genre-Erkennung auf Basis spektraler + rhythmischer Fingerprints.

        Vergleicht die extrahierten Features gegen alle Sub-Genre-Fingerprints
        des uebergeordneten Genres und waehlt das beste Match.

        Args:
            genre: Bereits erkanntes Haupt-Genre (muss in SUB_GENRE_FINGERPRINTS sein)
            bpm: Erkanntes Tempo
            centroid: Spektraler Schwerpunkt (Hz)
            rms: Effektivwert-Energie
            zcr: Zero-Crossing-Rate

        Returns:
            (sub_genre_name, score) – faellt auf parent genre zurueck wenn kein
            Sub-Genre die MIN_SUB_GENRE_SCORE-Schwelle ueberschreitet.
        """
        from services.audio_constants import MIN_SUB_GENRE_SCORE

        sub_genres = SUB_GENRE_FINGERPRINTS.get(genre)
        if not sub_genres:
            log.debug("_classify_sub_genre: kein Fingerprint fuer Genre '%s'", genre)
            return (genre, 0.5)

        best_name = genre
        best_score = 0.0
        for name, fingerprint in sub_genres.items():
            score = self._score_sub_genre(fingerprint, bpm, centroid, rms, zcr)
            log.debug("_classify_sub_genre: %s → score=%.3f", name, score)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score < MIN_SUB_GENRE_SCORE:
            log.debug(
                "_classify_sub_genre: bester Score %.3f < %.2f — kein Sub-Genre",
                best_score, MIN_SUB_GENRE_SCORE,
            )
            return (genre, best_score)

        log.debug("_classify_sub_genre: %s (score=%.3f)", best_name, best_score)
        return (best_name, best_score)
