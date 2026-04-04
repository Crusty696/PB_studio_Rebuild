"""Structure Detection Service — Song-Struktur Erkennung.

Erkennt Sektionen eines Audio-Tracks: INTRO, BUILDUP, DROP, BREAKDOWN, OUTRO.
Nutzt Multi-Feature-Analyse (RMS + Spectral Centroid + Beat Regularity + Bass Energy)
fuer genre-spezifische Segmentierung (Psytrance, Techno, House).
Erkennt DJ-Mix-Uebergaenge und berechnet Confidence-Scores.
"""

import logging
from dataclasses import dataclass, field

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

# Gültige Segment-Labels
SEGMENT_LABELS = ["INTRO", "BUILDUP", "DROP", "BREAKDOWN", "OUTRO", "VERSE", "CHORUS", "BRIDGE"]

# Bekannte Genres
KNOWN_GENRES = ["psytrance", "techno", "house", ""]


@dataclass
class StructureSegmentResult:
    """Ein erkanntes Struktur-Segment mit Multi-Feature-Daten."""
    start_time: float       # Sekunden
    end_time: float         # Sekunden
    label: str              # SEGMENT_LABELS
    energy: float           # Durchschnittliche RMS-Energie 0.0-1.0
    confidence: float       # 0.0-1.0
    spectral_centroid: float = 0.0   # Normalisierter Spectral Centroid 0.0-1.0
    bass_energy: float = 0.0         # Normalisierte Bass-Energie 0.0-1.0
    beat_regularity: float = 1.0     # 1.0 = sehr regelmaessig, 0.0 = unregelmaessig


@dataclass
class StructureResult:
    """Ergebnis der Struktur-Erkennung."""
    segments: list[StructureSegmentResult] = field(default_factory=list)
    is_dj_mix: bool = False
    transition_count: int = 0
    detected_genre: str = ""         # "psytrance", "techno", "house" oder ""
    genre_confidence: float = 0.0    # 0.0-1.0
    dj_transitions: list[float] = field(default_factory=list)  # Uebergangszeiten in Sekunden


class StructureDetectionService:
    """Erkennt die Makro-Struktur eines Audio-Tracks.

    Verwendet Multi-Feature-Analyse:
    - RMS Energie (Lautheit)
    - Spectral Centroid (Klangfarbe/Helligkeit)
    - Bass-Energie (Tiefton-Anteil)
    - Beat-Regularitaet (IBI-Varianz)

    Genre-spezifische Templates fuer Psytrance, Techno und House
    verfeinern die Segmentierung. DJ-Mix-Erkennung basiert auf
    Energie-Einbruechen und Track-Uebergangs-Signaturen.
    """

    def detect(self, file_path: str, bpm: float | None = None,
               beat_positions: list[float] | None = None,
               energy_per_beat: list[float] | None = None) -> StructureResult:
        """Erkennt die Song-Struktur mit Multi-Feature-Analyse.

        Args:
            file_path: Pfad zur Audio-Datei
            bpm: Bereits erkannter BPM-Wert (optional)
            beat_positions: Bereits erkannte Beat-Positionen in Sekunden (optional)
            energy_per_beat: Bereits berechnete Energie pro Beat (optional, 0.0-1.0)

        Returns:
            StructureResult mit erkannten Segmenten, Genre und DJ-Mix-Info
        """
        if not _HAS_NUMPY:
            log.error(
                "numpy nicht verfuegbar — Struktur-Erkennung uebersprungen. "
                "Installiere mit: pip install numpy"
            )
            return StructureResult(segments=[], is_dj_mix=False, transition_count=0)

        try:
            from services.audio_constants import (
                STRUCTURE_SMOOTH_WINDOW, VERSE_CHORUS_SPLIT, MIN_SEGMENT_BEATS,
            )

            # ── 1. Multi-Feature-Kurven beschaffen ──────────────────────
            centroid_per_beat = None
            bass_per_beat = None
            regularity_per_beat = None

            if energy_per_beat is not None and len(energy_per_beat) > 0:
                energy = np.array(energy_per_beat, dtype=np.float64)
                if beat_positions is not None and len(beat_positions) == len(energy_per_beat):
                    beats = np.array(beat_positions, dtype=np.float64)
                elif bpm and bpm > 0:
                    beat_dur = 60.0 / bpm
                    beats = np.arange(len(energy)) * beat_dur
                else:
                    beats = np.arange(len(energy)) * 0.5
                log.info("Struktur-Erkennung: %d Beats aus energy_per_beat", len(energy))
                # Versuche zusaetzliche Features aus der Audio-Datei zu laden
                if _HAS_LIBROSA:
                    extra = self._compute_extra_features(file_path, beats, bpm)
                    if extra is not None:
                        centroid_per_beat, bass_per_beat = extra
            else:
                result = self._compute_multi_features_from_audio(file_path, bpm, beat_positions)
                if result is None:
                    log.warning("Konnte keine Features aus Audio berechnen: %s", file_path)
                    return StructureResult(segments=[], is_dj_mix=False, transition_count=0)
                energy, beats, bpm, centroid_per_beat, bass_per_beat = result

            n_beats = len(energy)

            if n_beats == 0 or len(beats) == 0:
                return StructureResult(segments=[], is_dj_mix=False, transition_count=0)

            if n_beats < 8:
                duration = float(beats[-1])
                avg_e = float(np.mean(energy))
                return StructureResult(
                    segments=[StructureSegmentResult(
                        start_time=0.0,
                        end_time=duration,
                        label="VERSE",
                        energy=round(avg_e, 4),
                        confidence=0.3,
                    )],
                    is_dj_mix=False,
                    transition_count=0,
                )

            # ── 2. Beat-Regularitaet berechnen ──────────────────────────
            regularity_per_beat = self._compute_beat_regularity(beats, n_beats)

            # ── 3. Features normalisieren ────────────────────────────────
            energy_norm = self._normalize(energy)
            centroid_norm = self._normalize(centroid_per_beat) if centroid_per_beat is not None \
                else np.full(n_beats, 0.5)
            bass_norm = self._normalize(bass_per_beat) if bass_per_beat is not None \
                else energy_norm.copy()

            # ── 4. Glaetten ──────────────────────────────────────────────
            smooth_window = min(STRUCTURE_SMOOTH_WINDOW, n_beats // 2)
            smooth_window = max(smooth_window, 2)
            kernel = np.ones(smooth_window) / smooth_window
            energy_smooth = np.convolve(energy_norm, kernel, mode='same')
            centroid_smooth = np.convolve(centroid_norm, kernel, mode='same')
            bass_smooth = np.convolve(bass_norm, kernel, mode='same')

            # Re-normalisieren nach Glaettung
            energy_smooth = self._normalize(energy_smooth)
            centroid_smooth = self._normalize(centroid_smooth)
            bass_smooth = self._normalize(bass_smooth)

            # ── 5. Genre erkennen ────────────────────────────────────────
            detected_genre, genre_confidence = self._detect_genre(
                bpm, energy_smooth, centroid_smooth, bass_smooth, beats
            )
            log.info("Genre erkannt: %s (conf=%.2f)", detected_genre or "unbekannt", genre_confidence)

            # ── 6. Gradient fuer Buildup-Erkennung ──────────────────────
            gradient = np.gradient(energy_smooth)

            # ── 7. Segmentierung ─────────────────────────────────────────
            labels = [""] * n_beats

            self._label_intro_outro(labels, energy_smooth, n_beats)
            self._label_buildups(labels, gradient, energy_smooth, n_beats)
            self._label_drops_multi(labels, energy_smooth, bass_smooth, centroid_smooth,
                                    regularity_per_beat, n_beats)
            self._label_breakdowns(labels, energy_smooth, n_beats)

            # Verbleibende unlabeled Beats: VERSE oder CHORUS
            for i in range(n_beats):
                if not labels[i]:
                    labels[i] = "VERSE" if energy_smooth[i] < VERSE_CHORUS_SPLIT else "CHORUS"

            # ── 8. Genre-Template anwenden ───────────────────────────────
            if detected_genre:
                labels = self._apply_genre_template(labels, energy_smooth, detected_genre, n_beats)

            # ── 9. Post-Processing ───────────────────────────────────────
            segments = self._form_segments_multi(
                labels, beats, energy_smooth, centroid_smooth, bass_smooth,
                regularity_per_beat, n_beats
            )
            segments = self._remove_short_segments(segments, min_beats=MIN_SEGMENT_BEATS, bpm=bpm)
            segments = self._merge_consecutive(segments)

            # ── 10. DJ-Mix-Erkennung ─────────────────────────────────────
            track_duration = float(beats[-1]) if len(beats) > 0 else 0.0
            dj_transitions = self._detect_dj_transitions(energy_smooth, beats, bpm)
            is_dj_mix = self._classify_dj_mix(track_duration, dj_transitions, bpm)

            log.info(
                "Struktur-Erkennung abgeschlossen: %d Segmente, genre=%s, dj_mix=%s fuer %s",
                len(segments), detected_genre or "?", is_dj_mix, file_path,
            )

            return StructureResult(
                segments=segments,
                is_dj_mix=is_dj_mix,
                transition_count=len(dj_transitions),
                detected_genre=detected_genre,
                genre_confidence=round(genre_confidence, 3),
                dj_transitions=[round(t, 3) for t in dj_transitions],
            )

        except Exception as e:
            log.exception("Fehler bei Struktur-Erkennung von %s", file_path)
            log.warning("detect(): fallback result returned due to: %s", e)
            return StructureResult(segments=[], is_dj_mix=False, transition_count=0)

    # ── Feature-Extraktion ───────────────────────────────────────────────

    def _compute_multi_features_from_audio(
        self,
        file_path: str,
        bpm: float | None,
        beat_positions: list[float] | None,
    ):
        """Laedt Audio und berechnet RMS, Spectral Centroid und Bass-Energie pro Beat.

        Returns:
            Tuple (energy, beats, bpm, centroid_per_beat, bass_per_beat)
            oder None bei Fehler
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            log.error("librosa/numpy nicht verfuegbar fuer Multi-Feature-Extraktion")
            return None

        try:
            from services.audio_constants import (
                DEFAULT_SR, HOP_LENGTH, MAX_DURATION_STRUCTURE, BASS_FREQ_MAX_HZ,
            )
            sr = DEFAULT_SR
            hop_length = HOP_LENGTH

            log.info("Lade Audio fuer Multi-Feature-Extraktion: %s", file_path)
            y, sr = librosa.load(file_path, sr=sr, mono=True, duration=MAX_DURATION_STRUCTURE)

            if len(y) == 0:
                return None

            duration_sec = len(y) / sr

            # Beat-Grid bestimmen
            if beat_positions is not None and len(beat_positions) > 1:
                beats = np.array(beat_positions, dtype=np.float64)
            elif bpm and bpm > 0:
                beat_dur = 60.0 / bpm
                beats = np.arange(0, duration_sec, beat_dur)
            else:
                tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
                beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
                if hasattr(tempo, '__len__'):
                    bpm = float(tempo[0]) if len(tempo) > 0 else 120.0
                else:
                    bpm = float(tempo) if tempo > 0 else 120.0

            if len(beats) < 2:
                beats = np.arange(0, duration_sec, 0.5)

            frame_times = librosa.frames_to_time(
                np.arange(int(len(y) / hop_length) + 1), sr=sr, hop_length=hop_length
            )

            # RMS
            rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

            # Spectral Centroid
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]

            # Bass-Energie: Bandpass-Filterung (< BASS_FREQ_MAX_HZ)
            # Nutze STFT und summiere Bins unterhalb der Cutoff-Frequenz
            stft = np.abs(librosa.stft(y, hop_length=hop_length))
            freqs = librosa.fft_frequencies(sr=sr)
            bass_mask = freqs <= BASS_FREQ_MAX_HZ
            bass_energy = np.mean(stft[bass_mask, :], axis=0) if bass_mask.any() else rms.copy()

            # Passen Sie Laengen an (STFT kann +1 Frame haben)
            min_frames = min(len(rms), len(centroid), len(bass_energy), len(frame_times))
            rms = rms[:min_frames]
            centroid = centroid[:min_frames]
            bass_energy = bass_energy[:min_frames]
            frame_times = frame_times[:min_frames]

            # Features an Beat-Positionen samplen
            energy_per_beat = self._sample_feature_at_beats(rms, frame_times, beats)
            centroid_per_beat = self._sample_feature_at_beats(centroid, frame_times, beats)
            bass_per_beat = self._sample_feature_at_beats(bass_energy, frame_times, beats)

            return energy_per_beat, beats, bpm, centroid_per_beat, bass_per_beat

        except Exception:
            log.exception("Fehler beim Multi-Feature-Laden von %s", file_path)
            return None

    def _compute_extra_features(
        self,
        file_path: str,
        beats,
        bpm: float | None,
    ):
        """Berechnet Spectral Centroid und Bass-Energie fuer bereits vorhandene Beat-Positionen."""
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            return None
        try:
            from services.audio_constants import (
                DEFAULT_SR, HOP_LENGTH, MAX_DURATION_STRUCTURE, BASS_FREQ_MAX_HZ,
            )
            y, sr = librosa.load(file_path, sr=DEFAULT_SR, mono=True,
                                 duration=MAX_DURATION_STRUCTURE)
            if len(y) == 0:
                return None

            hop_length = HOP_LENGTH
            frame_times = librosa.frames_to_time(
                np.arange(int(len(y) / hop_length) + 1), sr=sr, hop_length=hop_length
            )
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
            stft = np.abs(librosa.stft(y, hop_length=hop_length))
            freqs = librosa.fft_frequencies(sr=sr)
            bass_mask = freqs <= BASS_FREQ_MAX_HZ
            bass_energy = np.mean(stft[bass_mask, :], axis=0) if bass_mask.any() else None

            min_f = min(len(centroid), len(frame_times))
            centroid = centroid[:min_f]
            frame_times = frame_times[:min_f]

            centroid_per_beat = self._sample_feature_at_beats(centroid, frame_times, beats)
            bass_per_beat = None
            if bass_energy is not None:
                bass_energy = bass_energy[:min_f]
                bass_per_beat = self._sample_feature_at_beats(bass_energy, frame_times, beats)

            return centroid_per_beat, bass_per_beat

        except Exception:
            log.debug("Extra-Feature-Berechnung fehlgeschlagen fuer %s", file_path)
            return None

    @staticmethod
    def _sample_feature_at_beats(feature_frames, frame_times, beats, window: int = 2):
        """Sampelt ein Frame-basiertes Feature an Beat-Positionen (Mittelwert ueber Fenster)."""
        result = np.zeros(len(beats), dtype=np.float64)
        for i, bt in enumerate(beats):
            idx = int(np.searchsorted(frame_times, bt))
            idx = min(idx, len(feature_frames) - 1)
            w_start = max(0, idx - window)
            w_end = min(len(feature_frames), idx + window + 1)
            result[i] = float(np.mean(feature_frames[w_start:w_end]))
        return result

    @staticmethod
    def _compute_beat_regularity(beats, n_beats: int):
        """Berechnet Beat-Regularitaet (IBI-Varianz) pro Beat-Fenster.

        Returns:
            Array der Laenge n_beats mit Regularitaets-Werten (1.0=regelmaessig, 0.0=unregelmaessig)
        """
        regularity = np.ones(n_beats, dtype=np.float64)
        if n_beats < 4:
            return regularity

        ibis = np.diff(beats)  # Inter-Beat-Intervalle
        if len(ibis) == 0:
            return regularity

        window = 8
        for i in range(n_beats):
            start = max(0, i - window // 2)
            end = min(len(ibis), start + window)
            local_ibis = ibis[start:end]
            if len(local_ibis) >= 2:
                mean_ibi = np.mean(local_ibis)
                if mean_ibi > 1e-9:
                    cv = float(np.std(local_ibis) / mean_ibi)  # Variationskoeffizient
                    # cv=0 → perfekt regelmaessig, cv>0.12 → unregelmaessig
                    regularity[i] = max(0.0, 1.0 - cv / 0.3)

        return regularity

    @staticmethod
    def _normalize(arr):
        """Normalisiert ein Array auf 0.0-1.0."""
        if arr is None:
            return None
        a = np.asarray(arr, dtype=np.float64)
        a_min, a_max = np.min(a), np.max(a)
        if a_max - a_min > 1e-9:
            return (a - a_min) / (a_max - a_min)
        return np.zeros_like(a)

    # ── Genre-Erkennung ───────────────────────────────────────────────────

    @staticmethod
    def _detect_genre(bpm, energy_norm, centroid_norm, bass_norm, beats):
        """Erkennt Genre basierend auf BPM-Range und spektralen Merkmalen.

        Returns:
            Tuple (genre_name: str, confidence: float)
        """
        from services.audio_constants import (
            GENRE_PSYTRANCE_BPM_MIN, GENRE_PSYTRANCE_BPM_MAX,
            GENRE_TECHNO_BPM_MIN, GENRE_TECHNO_BPM_MAX,
            GENRE_HOUSE_BPM_MIN, GENRE_HOUSE_BPM_MAX,
        )

        if bpm is None or bpm <= 0:
            return "", 0.0

        candidates: list[tuple[str, float]] = []

        avg_centroid = float(np.mean(centroid_norm))
        avg_bass = float(np.mean(bass_norm))
        avg_energy = float(np.mean(energy_norm))

        # Psytrance: 138-150 BPM, hohe Bass-Energie, starke Drops
        if GENRE_PSYTRANCE_BPM_MIN <= bpm <= GENRE_PSYTRANCE_BPM_MAX:
            score = 0.5
            if avg_bass > 0.5:
                score += 0.2
            if avg_energy > 0.45:
                score += 0.15
            if avg_centroid > 0.45:
                score += 0.15
            candidates.append(("psytrance", score))

        # Techno: 125-145 BPM (ueberlappend mit Psytrance), minimaler Centroid
        if GENRE_TECHNO_BPM_MIN <= bpm <= GENRE_TECHNO_BPM_MAX:
            score = 0.4
            if avg_centroid < 0.5:
                score += 0.2  # Techno ist dunkler/metallischer
            if avg_bass > 0.4:
                score += 0.2
            if avg_energy > 0.4:
                score += 0.2
            candidates.append(("techno", score))

        # House: 118-132 BPM, mittlere Energie, ausgeglichener Centroid
        if GENRE_HOUSE_BPM_MIN <= bpm <= GENRE_HOUSE_BPM_MAX:
            score = 0.45
            if 0.3 < avg_centroid < 0.7:
                score += 0.2
            if 0.3 < avg_energy < 0.7:
                score += 0.2
            if avg_bass > 0.35:
                score += 0.15
            candidates.append(("house", score))

        if not candidates:
            return "", 0.0

        best_genre, best_score = max(candidates, key=lambda x: x[1])

        # Mindest-Score fuer Zuweisung
        if best_score < 0.5:
            return "", round(best_score, 3)

        return best_genre, round(min(best_score, 1.0), 3)

    # ── DJ-Mix-Erkennung ──────────────────────────────────────────────────

    @staticmethod
    def _detect_dj_transitions(energy_norm, beats, bpm: float | None) -> list[float]:
        """Erkennt DJ-Mix-Uebergaenge als tiefe Energie-Einbrueche zwischen Tracks.

        Typisch fuer DJ-Mixes: Kurze Energie-Minima (~30-120s Abstand) gefolgt
        von einem Energie-Anstieg (neuer Track beginnt).

        Returns:
            Liste von Uebergangszeiten in Sekunden
        """
        from services.audio_constants import (
            DJ_MIX_ENERGY_DIP_THRESHOLD, DJ_MIX_TRANSITION_MIN_GAP_SEC,
        )

        if len(energy_norm) < 32 or len(beats) < 32:
            return []

        transitions: list[float] = []
        n = len(energy_norm)
        min_gap_beats = 32  # Mind. 32 Beats zwischen Uebergaengen

        i = 16  # Starte nach dem Intro
        last_transition_beat = 0

        while i < n - 16:
            # Erkenne: vorher hohe Energie, jetzt niedriger Einbruch, dann wieder hoch
            before_energy = float(np.mean(energy_norm[max(0, i - 8):i]))
            current_energy = float(energy_norm[i])
            after_energy = float(np.mean(energy_norm[i + 1:min(n, i + 9)]))

            is_dip = (
                current_energy < DJ_MIX_ENERGY_DIP_THRESHOLD
                and before_energy > current_energy + 0.15
                and after_energy > current_energy + 0.10
                and (i - last_transition_beat) >= min_gap_beats
            )

            if is_dip:
                transition_time = float(beats[i]) if i < len(beats) else 0.0
                # Verifiziere Mindestabstand in Sekunden
                if not transitions or (transition_time - transitions[-1]) >= DJ_MIX_TRANSITION_MIN_GAP_SEC:
                    transitions.append(transition_time)
                    last_transition_beat = i
                    i += min_gap_beats
                    continue

            i += 1

        return transitions

    @staticmethod
    def _classify_dj_mix(track_duration: float, transitions: list[float], bpm: float | None) -> bool:
        """Klassifiziert ob ein Track ein DJ-Mix ist.

        Kriterien:
        - Track > 10 Minuten
        - Mindestens 2 erkannte Uebergaenge
        """
        from services.audio_constants import (
            MIN_MIX_DURATION_SEC, DJ_MIX_MIN_TRANSITIONS,
        )

        if track_duration < MIN_MIX_DURATION_SEC:
            return False

        if len(transitions) >= DJ_MIX_MIN_TRANSITIONS:
            return True

        # Sehr lange Tracks (>30min) sind wahrscheinlich DJ-Mixes auch ohne klare Uebergaenge
        if track_duration >= 1800.0:
            return True

        return False

    # ── Labeling-Hilfsmethoden ────────────────────────────────────────────

    def _label_intro_outro(self, labels: list[str], energy_norm, n_beats: int) -> None:
        """Labelt INTRO- und OUTRO-Bereiche basierend auf niedriger Energie."""
        from services.audio_constants import (
            INTRO_OUTRO_FRACTION, LOW_ENERGY_THRESHOLD, INTRO_OUTRO_MAX_EXPANSION,
        )

        intro_end = int(n_beats * INTRO_OUTRO_FRACTION)
        outro_start = int(n_beats * (1.0 - INTRO_OUTRO_FRACTION))

        if intro_end > 0:
            intro_avg = float(np.mean(energy_norm[:intro_end]))
            if intro_avg < LOW_ENERGY_THRESHOLD:
                for i in range(intro_end):
                    labels[i] = "INTRO"
                for i in range(intro_end, min(n_beats, int(n_beats * INTRO_OUTRO_MAX_EXPANSION))):
                    if energy_norm[i] < LOW_ENERGY_THRESHOLD:
                        labels[i] = "INTRO"
                    else:
                        break

        if outro_start < n_beats:
            outro_avg = float(np.mean(energy_norm[outro_start:]))
            if outro_avg < LOW_ENERGY_THRESHOLD:
                for i in range(outro_start, n_beats):
                    labels[i] = "OUTRO"
                for i in range(outro_start - 1, max(0, int(n_beats * (1.0 - INTRO_OUTRO_MAX_EXPANSION))), -1):
                    if energy_norm[i] < LOW_ENERGY_THRESHOLD:
                        labels[i] = "OUTRO"
                    else:
                        break

    def _label_buildups(self, labels: list[str], gradient, energy_norm, n_beats: int) -> None:
        """Labelt BUILDUP-Bereiche: sustained positive gradient."""
        from services.audio_constants import (
            STRUCTURE_SMOOTH_WINDOW, BUILDUP_GRADIENT_THRESHOLD, BUILDUP_MIN_TOTAL_RISE,
        )

        min_buildup_beats = min(STRUCTURE_SMOOTH_WINDOW, n_beats // 4)
        if min_buildup_beats < 4:
            min_buildup_beats = 4
        i = 0
        while i < n_beats - min_buildup_beats:
            if labels[i]:
                i += 1
                continue

            run_length = 0
            for j in range(i, n_beats):
                if gradient[j] > BUILDUP_GRADIENT_THRESHOLD:
                    run_length += 1
                elif gradient[j] > 0.0 and run_length > 0:
                    run_length += 1
                else:
                    break

            if run_length >= min_buildup_beats:
                end_idx = i + run_length
                total_rise = energy_norm[min(end_idx, n_beats - 1)] - energy_norm[i]
                if total_rise > BUILDUP_MIN_TOTAL_RISE:
                    for k in range(i, min(end_idx, n_beats)):
                        if not labels[k]:
                            labels[k] = "BUILDUP"
                    i = end_idx
                    continue
            i += 1

    def _label_drops_multi(
        self,
        labels: list[str],
        energy_norm,
        bass_norm,
        centroid_norm,
        regularity,
        n_beats: int,
    ) -> None:
        """Labelt DROP-Bereiche mit Multi-Feature-Bestaetigung.

        Ein DROP wird erkannt wenn:
        - Hohe RMS-Energie (> DROP_ENERGY_THRESHOLD)
        - ODER hohe Bass-Energie (> MULTI_FEATURE_BASS_DROP_THRESHOLD) + mittlere RMS
        - UND hoher Spectral Centroid (Hochfrequenzanteil steigt)
        - ODER Beat-Regularitaet hoch (Maschinen-Beat im Drop)
        - Vorher ein BUILDUP
        """
        from services.audio_constants import (
            DROP_ENERGY_THRESHOLD, DROP_LOOKBACK_BEATS, BREAKDOWN_HIGH_THRESHOLD,
            MULTI_FEATURE_BASS_DROP_THRESHOLD, SPECTRAL_CENTROID_HIGH,
            BEAT_REGULARITY_THRESHOLD,
        )

        for i in range(n_beats):
            if labels[i]:
                continue

            rms_high = energy_norm[i] > DROP_ENERGY_THRESHOLD
            bass_high = bass_norm[i] > MULTI_FEATURE_BASS_DROP_THRESHOLD
            centroid_high = centroid_norm[i] > SPECTRAL_CENTROID_HIGH
            beat_regular = regularity[i] > (1.0 - BEAT_REGULARITY_THRESHOLD)

            # Multi-Feature DROP-Kriterium
            is_drop_candidate = (
                rms_high
                or (bass_high and energy_norm[i] > DROP_ENERGY_THRESHOLD * 0.8)
                or (centroid_high and rms_high)
                or (beat_regular and rms_high)
            )

            if not is_drop_candidate:
                continue

            # Pruefe vorherigen BUILDUP
            has_buildup_before = any(
                labels[i - back] == "BUILDUP"
                for back in range(1, min(DROP_LOOKBACK_BEATS + 1, i + 1))
                if i - back >= 0
            )

            if has_buildup_before:
                labels[i] = "DROP"
                for j in range(i + 1, n_beats):
                    if labels[j]:
                        break
                    still_drop = (
                        energy_norm[j] > BREAKDOWN_HIGH_THRESHOLD
                        or bass_norm[j] > MULTI_FEATURE_BASS_DROP_THRESHOLD * 0.85
                    )
                    if still_drop:
                        labels[j] = "DROP"
                    else:
                        break

    def _label_breakdowns(self, labels: list[str], energy_norm, n_beats: int) -> None:
        """Labelt BREAKDOWN-Bereiche: Energie faellt von hoch auf niedrig."""
        from services.audio_constants import (
            BREAKDOWN_HIGH_THRESHOLD, BREAKDOWN_LOW_THRESHOLD, BREAKDOWN_EXTEND_THRESHOLD,
        )

        for i in range(1, n_beats):
            if labels[i]:
                continue
            if (energy_norm[i - 1] > BREAKDOWN_HIGH_THRESHOLD
                    and energy_norm[i] < BREAKDOWN_LOW_THRESHOLD):
                labels[i] = "BREAKDOWN"
                for j in range(i + 1, n_beats):
                    if labels[j]:
                        break
                    if energy_norm[j] < BREAKDOWN_EXTEND_THRESHOLD:
                        labels[j] = "BREAKDOWN"
                    else:
                        break

    # ── Genre-Templates ───────────────────────────────────────────────────

    def _apply_genre_template(
        self,
        labels: list[str],
        energy_norm,
        genre: str,
        n_beats: int,
    ) -> list[str]:
        """Verfeinert Labels anhand genre-spezifischer Struktur-Templates.

        Psytrance: Lange BREAKDOWNs vor BUILDUPs → DROPs sind kurz und intensiv
        Techno:    Wenig VERSE/CHORUS, hauptsaechlich DROP mit langen Phasen
        House:     VERSE/CHORUS-Wechsel betonen, BUILDUP ist kurz
        """
        labels = labels[:]  # Kopie

        if genre == "psytrance":
            labels = self._template_psytrance(labels, energy_norm, n_beats)
        elif genre == "techno":
            labels = self._template_techno(labels, energy_norm, n_beats)
        elif genre == "house":
            labels = self._template_house(labels, energy_norm, n_beats)

        return labels

    @staticmethod
    def _template_psytrance(labels: list[str], energy_norm, n_beats: int) -> list[str]:
        """Psytrance: CHORUS → DROP umwandeln bei hoher Energie (> 0.65)."""
        for i in range(n_beats):
            if labels[i] == "CHORUS" and energy_norm[i] > 0.65:
                labels[i] = "DROP"
        return labels

    @staticmethod
    def _template_techno(labels: list[str], energy_norm, n_beats: int) -> list[str]:
        """Techno: VERSE/CHORUS → DROP bei mittlerer bis hoher Energie (> 0.45).

        Techno hat selten echte Verses — wenn Energie > 0.45, ist es eher ein Drop-Phase.
        """
        for i in range(n_beats):
            if labels[i] in ("VERSE", "CHORUS") and energy_norm[i] > 0.45:
                labels[i] = "DROP"
        return labels

    @staticmethod
    def _template_house(labels: list[str], energy_norm, n_beats: int) -> list[str]:
        """House: DROP → CHORUS wenn Energie nicht extrem hoch (< 0.85).

        House hat weniger aggressive Drops — sehr hohe Energie-Sektionen sind CHORUS.
        """
        for i in range(n_beats):
            if labels[i] == "DROP" and energy_norm[i] < 0.85:
                labels[i] = "CHORUS"
        return labels

    # ── Segment-Bildung ───────────────────────────────────────────────────

    def _form_segments_multi(
        self,
        labels: list[str],
        beats,
        energy_norm,
        centroid_norm,
        bass_norm,
        regularity,
        n_beats: int,
    ) -> list[StructureSegmentResult]:
        """Formt zusammenhaengende Labels zu StructureSegmentResult-Liste (mit Multi-Features)."""
        segments: list[StructureSegmentResult] = []
        seg_start_idx = 0
        current_label = labels[0]

        def make_segment(start_idx: int, end_idx: int, label: str) -> StructureSegmentResult:
            start_t = float(beats[start_idx]) if start_idx < len(beats) else 0.0
            end_t = float(beats[end_idx]) if end_idx < len(beats) else float(beats[-1])
            sl = slice(start_idx, end_idx)
            avg_e = float(np.mean(energy_norm[sl]))
            avg_c = float(np.mean(centroid_norm[sl]))
            avg_b = float(np.mean(bass_norm[sl]))
            avg_r = float(np.mean(regularity[sl]))
            n_seg = end_idx - start_idx
            conf = _label_confidence_multi(label, avg_e, avg_c, avg_b, avg_r, n_seg)
            return StructureSegmentResult(
                start_time=round(start_t, 3),
                end_time=round(end_t, 3),
                label=label,
                energy=round(avg_e, 4),
                confidence=conf,
                spectral_centroid=round(avg_c, 4),
                bass_energy=round(avg_b, 4),
                beat_regularity=round(avg_r, 4),
            )

        for i in range(1, n_beats):
            if labels[i] != current_label:
                segments.append(make_segment(seg_start_idx, i, current_label))
                seg_start_idx = i
                current_label = labels[i]

        # Letztes Segment
        segments.append(make_segment(seg_start_idx, n_beats - 1, current_label))

        return segments

    # ── Legacy-Methoden (Rueckwaerts-Kompatibilitaet) ─────────────────────

    def _form_segments(self, labels: list[str], beats, energy_norm, n_beats: int) -> list[StructureSegmentResult]:
        """Formt zusammenhaengende Labels zu StructureSegmentResult-Liste (Legacy)."""
        dummy = np.full(n_beats, 0.5)
        return self._form_segments_multi(
            labels, beats, energy_norm, dummy, dummy, np.ones(n_beats), n_beats
        )

    # ── Weitere Hilfsmethoden ─────────────────────────────────────────────

    def _compute_energy_from_audio(
        self,
        file_path: str,
        bpm: float | None,
        beat_positions: list[float] | None,
    ):
        """Laedt Audio und berechnet Energie pro Beat (Legacy — verwendet Multi-Feature intern).

        Returns:
            Tuple (energy_array, beat_array, bpm) oder (None, None, None) bei Fehler
        """
        result = self._compute_multi_features_from_audio(file_path, bpm, beat_positions)
        if result is None:
            return None, None, None
        energy, beats, bpm, _, _ = result
        return energy, beats, bpm

    @staticmethod
    def _remove_short_segments(
        segments: list[StructureSegmentResult],
        min_beats: int = 8,
        bpm: float | None = None,
    ) -> list[StructureSegmentResult]:
        """Entfernt Segmente die kuerzer als min_beats sind und verschmilzt sie mit dem Nachbarn."""
        if len(segments) <= 1:
            return segments

        if bpm and bpm > 0:
            min_duration = (60.0 / bpm) * min_beats
        else:
            min_duration = min_beats * 0.5

        changed = True
        while changed:
            changed = False
            new_segments: list[StructureSegmentResult] = []
            i = 0
            while i < len(segments):
                seg = segments[i]
                seg_duration = seg.end_time - seg.start_time

                if seg_duration < min_duration and len(segments) > 1:
                    if new_segments:
                        prev = new_segments[-1]
                        total_dur = (prev.end_time - prev.start_time) + seg_duration
                        w_p = (prev.end_time - prev.start_time) / total_dur if total_dur > 0 else 0.5
                        w_s = 1.0 - w_p
                        new_segments[-1] = StructureSegmentResult(
                            start_time=prev.start_time,
                            end_time=seg.end_time,
                            label=prev.label,
                            energy=round(prev.energy * w_p + seg.energy * w_s, 4),
                            confidence=round(min(prev.confidence, seg.confidence), 3),
                            spectral_centroid=round(prev.spectral_centroid * w_p + seg.spectral_centroid * w_s, 4),
                            bass_energy=round(prev.bass_energy * w_p + seg.bass_energy * w_s, 4),
                            beat_regularity=round(prev.beat_regularity * w_p + seg.beat_regularity * w_s, 4),
                        )
                        changed = True
                    elif i + 1 < len(segments):
                        nxt = segments[i + 1]
                        total_dur = seg_duration + (nxt.end_time - nxt.start_time)
                        w_s = seg_duration / total_dur if total_dur > 0 else 0.5
                        w_n = 1.0 - w_s
                        new_segments.append(StructureSegmentResult(
                            start_time=seg.start_time,
                            end_time=nxt.end_time,
                            label=nxt.label,
                            energy=round(seg.energy * w_s + nxt.energy * w_n, 4),
                            confidence=round(min(seg.confidence, nxt.confidence), 3),
                            spectral_centroid=round(seg.spectral_centroid * w_s + nxt.spectral_centroid * w_n, 4),
                            bass_energy=round(seg.bass_energy * w_s + nxt.bass_energy * w_n, 4),
                            beat_regularity=round(seg.beat_regularity * w_s + nxt.beat_regularity * w_n, 4),
                        ))
                        i += 2
                        changed = True
                        continue
                    else:
                        new_segments.append(seg)
                else:
                    new_segments.append(seg)
                i += 1
            segments = new_segments

        return segments

    @staticmethod
    def _merge_consecutive(segments: list[StructureSegmentResult]) -> list[StructureSegmentResult]:
        """Verschmilzt aufeinanderfolgende Segmente mit gleichem Label."""
        if len(segments) <= 1:
            return segments

        merged: list[StructureSegmentResult] = [segments[0]]

        for seg in segments[1:]:
            prev = merged[-1]
            if seg.label == prev.label:
                total_dur = (prev.end_time - prev.start_time) + (seg.end_time - seg.start_time)
                w_p = (prev.end_time - prev.start_time) / total_dur if total_dur > 0 else 0.5
                w_s = 1.0 - w_p
                merged[-1] = StructureSegmentResult(
                    start_time=prev.start_time,
                    end_time=seg.end_time,
                    label=prev.label,
                    energy=round(prev.energy * w_p + seg.energy * w_s, 4),
                    confidence=round(prev.confidence * w_p + seg.confidence * w_s, 3),
                    spectral_centroid=round(prev.spectral_centroid * w_p + seg.spectral_centroid * w_s, 4),
                    bass_energy=round(prev.bass_energy * w_p + seg.bass_energy * w_s, 4),
                    beat_regularity=round(prev.beat_regularity * w_p + seg.beat_regularity * w_s, 4),
                )
            else:
                merged.append(seg)

        return merged

    def save_to_db(self, audio_track_id: int, result: StructureResult,
                   max_retries: int = 5):
        """Speichert erkannte Segmente in die DB mit Retry bei DB-Lock."""
        import time as _time
        from database import engine, StructureSegment, nullpool_session
        from sqlalchemy.exc import OperationalError

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    engine.dispose()
                    _time.sleep(1)

                with nullpool_session() as session:
                    session.query(StructureSegment).filter_by(
                        audio_track_id=audio_track_id
                    ).delete()
                    for seg in result.segments:
                        session.add(StructureSegment(
                            audio_track_id=audio_track_id,
                            start_time=seg.start_time,
                            end_time=seg.end_time,
                            label=seg.label,
                            energy=seg.energy,
                            confidence=seg.confidence,
                        ))
                    session.commit()
                    log.info("Struktur gespeichert: %d Segmente fuer AudioTrack %d",
                             len(result.segments), audio_track_id)
                    return

            except OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    log.warning("DB locked bei Struktur-Save, Retry %d/%d (warte %ds)...",
                                attempt + 1, max_retries, wait)
                    _time.sleep(wait)
                else:
                    log.exception("Fehler beim Speichern der Struktur fuer AudioTrack %d",
                                  audio_track_id)
                    raise


# ── Modul-Hilfsfunktionen ─────────────────────────────────────────────────────

def _label_confidence_multi(
    label: str,
    avg_energy: float,
    avg_centroid: float,
    avg_bass: float,
    avg_regularity: float,
    n_beats: int,
) -> float:
    """Berechnet Confidence fuer ein Segment basierend auf Multi-Feature-Uebereinstimmung.

    Hoehere Confidence wenn mehrere Features das Label gleichzeitig unterstuetzen.
    """
    conf = 0.35  # Niedrigere Basis — Multi-Feature muss bestaetigen

    # Laengere Segmente → mehr Sicherheit
    if n_beats >= 32:
        conf += 0.15
    elif n_beats >= 16:
        conf += 0.08
    elif n_beats >= 8:
        conf += 0.04

    # Label-spezifische Multi-Feature-Pruefung
    if label == "DROP":
        if avg_energy > 0.7:
            conf += 0.15
        if avg_bass > 0.6:
            conf += 0.15
        if avg_centroid > 0.6:
            conf += 0.10
        if avg_regularity > 0.8:
            conf += 0.10

    elif label == "BUILDUP":
        if 0.3 < avg_energy < 0.8:
            conf += 0.12
        if avg_centroid > 0.5:
            conf += 0.08
        if avg_regularity > 0.7:
            conf += 0.10

    elif label == "BREAKDOWN":
        if avg_energy < 0.4:
            conf += 0.15
        if avg_bass < 0.35:
            conf += 0.10
        if avg_centroid < 0.45:
            conf += 0.10

    elif label in ("INTRO", "OUTRO"):
        if avg_energy < 0.3:
            conf += 0.20
        if avg_bass < 0.3:
            conf += 0.10

    elif label == "CHORUS":
        if avg_energy >= 0.5:
            conf += 0.10
        if avg_centroid > 0.5:
            conf += 0.10

    elif label == "VERSE":
        if avg_energy < 0.5:
            conf += 0.10
        if avg_centroid < 0.55:
            conf += 0.05

    return round(min(1.0, conf), 3)
