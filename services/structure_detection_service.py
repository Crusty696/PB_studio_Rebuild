"""Structure Detection Service — Song-Struktur Erkennung.

Erkennt Sektionen eines Audio-Tracks: INTRO, BUILDUP, DROP, BREAKDOWN, OUTRO.
Nutzt Energie-Verlauf, Spektral-Analyse und Beat-Grid für die Segmentierung.
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


@dataclass
class StructureSegmentResult:
    """Ein erkanntes Struktur-Segment."""
    start_time: float       # Sekunden
    end_time: float         # Sekunden
    label: str              # SEGMENT_LABELS
    energy: float           # Durchschnittliche Energie 0.0-1.0
    confidence: float       # 0.0-1.0


@dataclass
class StructureResult:
    """Ergebnis der Struktur-Erkennung."""
    segments: list[StructureSegmentResult] = field(default_factory=list)
    is_dj_mix: bool = False
    transition_count: int = 0


class StructureDetectionService:
    """Erkennt die Makro-Struktur eines Audio-Tracks."""

    def detect(self, file_path: str, bpm: float | None = None,
               beat_positions: list[float] | None = None,
               energy_per_beat: list[float] | None = None) -> StructureResult:
        """Erkennt die Song-Struktur.

        Args:
            file_path: Pfad zur Audio-Datei
            bpm: Bereits erkannter BPM-Wert (optional)
            beat_positions: Bereits erkannte Beat-Positionen in Sekunden (optional)
            energy_per_beat: Bereits berechnete Energie pro Beat (optional, 0.0-1.0)

        Returns:
            StructureResult mit erkannten Segmenten
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
            # ── 1. Energie-Kurve beschaffen ─────────────────────────────
            if energy_per_beat is not None and len(energy_per_beat) > 0:
                energy = np.array(energy_per_beat, dtype=np.float64)
                # Beat-Positionen ableiten falls nicht gegeben
                if beat_positions is not None and len(beat_positions) == len(energy_per_beat):
                    beats = np.array(beat_positions, dtype=np.float64)
                elif bpm and bpm > 0:
                    beat_dur = 60.0 / bpm
                    beats = np.arange(len(energy)) * beat_dur
                else:
                    # Schaetze ~120 BPM als Fallback
                    beats = np.arange(len(energy)) * 0.5
                log.info("Struktur-Erkennung: %d Beats aus energy_per_beat", len(energy))
            else:
                # Audio selbst laden und Energie berechnen
                energy, beats, bpm = self._compute_energy_from_audio(
                    file_path, bpm, beat_positions
                )
                if energy is None or len(energy) == 0:
                    log.warning("Konnte keine Energie aus Audio berechnen: %s", file_path)
                    return StructureResult(segments=[], is_dj_mix=False, transition_count=0)

            n_beats = len(energy)

            # Edge case: Sehr kurzer Track
            if n_beats < 8:
                duration = float(beats[-1]) if len(beats) > 0 else 0.0
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

            # ── 2. Glaetten (Moving Average, window=16 Beats) ──────────
            smooth_window = min(STRUCTURE_SMOOTH_WINDOW, n_beats // 2)
            if smooth_window < 2:
                smooth_window = 2
            kernel = np.ones(smooth_window) / smooth_window
            energy_smooth = np.convolve(energy, kernel, mode='same')

            # ── 3. Normalisieren auf 0.0-1.0 ───────────────────────────
            e_max = np.max(energy_smooth)
            e_min = np.min(energy_smooth)
            if e_max - e_min > 1e-9:
                energy_norm = (energy_smooth - e_min) / (e_max - e_min)
            else:
                # Stiller Track oder konstante Energie
                energy_norm = np.zeros_like(energy_smooth)

            # ── 4. Gradient (erste Ableitung) ───────────────────────────
            gradient = np.gradient(energy_norm)

            # ── 5. Segmentierung ────────────────────────────────────────
            labels = [""] * n_beats  # Label pro Beat

            self._label_intro_outro(labels, energy_norm, n_beats)
            self._label_buildups(labels, gradient, energy_norm, n_beats)
            self._label_drops(labels, energy_norm, n_beats)
            self._label_breakdowns(labels, energy_norm, n_beats)

            # Verbleibende unlabeled Beats: VERSE oder CHORUS
            for i in range(n_beats):
                if not labels[i]:
                    labels[i] = "VERSE" if energy_norm[i] < VERSE_CHORUS_SPLIT else "CHORUS"

            # ── 6. Post-Processing ──────────────────────────────────────
            segments = self._form_segments(labels, beats, energy_norm, n_beats)
            segments = self._remove_short_segments(segments, min_beats=MIN_SEGMENT_BEATS, bpm=bpm)
            segments = self._merge_consecutive(segments)

            log.info(
                "Struktur-Erkennung abgeschlossen: %d Segmente fuer %s",
                len(segments), file_path,
            )

            return StructureResult(
                segments=segments,
                is_dj_mix=False,
                transition_count=0,
            )

        except Exception:
            log.exception("Fehler bei Struktur-Erkennung von %s", file_path)
            return StructureResult(segments=[], is_dj_mix=False, transition_count=0)

    # ── Labeling-Hilfsmethoden (mutieren labels in-place) ──────────────

    def _label_intro_outro(self, labels: list[str], energy_norm, n_beats: int) -> None:
        """Labelt INTRO- und OUTRO-Bereiche basierend auf niedriger Energie."""
        from services.audio_constants import (
            INTRO_OUTRO_FRACTION, LOW_ENERGY_THRESHOLD, INTRO_OUTRO_MAX_EXPANSION,
        )

        intro_end = int(n_beats * INTRO_OUTRO_FRACTION)
        outro_start = int(n_beats * (1.0 - INTRO_OUTRO_FRACTION))

        # INTRO: Erste 5% des Tracks, wenn Energie < LOW_ENERGY_THRESHOLD
        if intro_end > 0:
            intro_avg = float(np.mean(energy_norm[:intro_end]))
            if intro_avg < LOW_ENERGY_THRESHOLD:
                for i in range(intro_end):
                    labels[i] = "INTRO"
                # Erweitere INTRO solange Energie niedrig bleibt
                for i in range(intro_end, min(n_beats, int(n_beats * INTRO_OUTRO_MAX_EXPANSION))):
                    if energy_norm[i] < LOW_ENERGY_THRESHOLD:
                        labels[i] = "INTRO"
                    else:
                        break

        # OUTRO: Letzte 5% des Tracks, wenn Energie < LOW_ENERGY_THRESHOLD
        if outro_start < n_beats:
            outro_avg = float(np.mean(energy_norm[outro_start:]))
            if outro_avg < LOW_ENERGY_THRESHOLD:
                for i in range(outro_start, n_beats):
                    labels[i] = "OUTRO"
                # Erweitere OUTRO rueckwaerts solange Energie niedrig bleibt
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
            if labels[i]:  # Bereits gelabelt (INTRO/OUTRO)
                i += 1
                continue

            # Suche sustained positive gradient
            run_length = 0
            for j in range(i, n_beats):
                if gradient[j] > BUILDUP_GRADIENT_THRESHOLD:
                    run_length += 1
                elif gradient[j] > 0.0 and run_length > 0:
                    # Erlaube kleinen Jitter
                    run_length += 1
                else:
                    break

            if run_length >= min_buildup_beats:
                # Verifiziere dass die Gesamtenergie signifikant steigt
                end_idx = i + run_length
                total_rise = energy_norm[min(end_idx, n_beats - 1)] - energy_norm[i]
                if total_rise > BUILDUP_MIN_TOTAL_RISE:
                    for k in range(i, min(end_idx, n_beats)):
                        if not labels[k]:
                            labels[k] = "BUILDUP"
                    i = end_idx
                    continue
            i += 1

    def _label_drops(self, labels: list[str], energy_norm, n_beats: int) -> None:
        """Labelt DROP-Bereiche: hohe Energie direkt nach BUILDUP."""
        from services.audio_constants import (
            DROP_ENERGY_THRESHOLD, DROP_LOOKBACK_BEATS, BREAKDOWN_HIGH_THRESHOLD,
        )

        for i in range(n_beats):
            if labels[i]:
                continue
            if energy_norm[i] > DROP_ENERGY_THRESHOLD:
                # Pruefe ob davor ein BUILDUP war (innerhalb von DROP_LOOKBACK_BEATS Beats)
                has_buildup_before = False
                for back in range(1, min(DROP_LOOKBACK_BEATS + 1, i + 1)):
                    if i - back >= 0 and labels[i - back] == "BUILDUP":
                        has_buildup_before = True
                        break

                if has_buildup_before:
                    labels[i] = "DROP"
                    # Markiere auch folgende High-Energy-Beats als DROP
                    for j in range(i + 1, n_beats):
                        if labels[j]:
                            break
                        if energy_norm[j] > BREAKDOWN_HIGH_THRESHOLD:
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
            if i > 0 and energy_norm[i - 1] > BREAKDOWN_HIGH_THRESHOLD and energy_norm[i] < BREAKDOWN_LOW_THRESHOLD:
                labels[i] = "BREAKDOWN"
                # Erweitere Breakdown solange Energie niedrig bleibt
                for j in range(i + 1, n_beats):
                    if labels[j]:
                        break
                    if energy_norm[j] < BREAKDOWN_EXTEND_THRESHOLD:
                        labels[j] = "BREAKDOWN"
                    else:
                        break

    def _form_segments(self, labels: list[str], beats, energy_norm, n_beats: int) -> list[StructureSegmentResult]:
        """Formt zusammenhaengende Labels zu StructureSegmentResult-Liste."""
        segments: list[StructureSegmentResult] = []
        seg_start_idx = 0
        current_label = labels[0]

        for i in range(1, n_beats):
            if labels[i] != current_label:
                seg_start_time = float(beats[seg_start_idx]) if seg_start_idx < len(beats) else 0.0
                seg_end_time = float(beats[i]) if i < len(beats) else float(beats[-1])
                avg_energy = float(np.mean(energy_norm[seg_start_idx:i]))
                segments.append(StructureSegmentResult(
                    start_time=round(seg_start_time, 3),
                    end_time=round(seg_end_time, 3),
                    label=current_label,
                    energy=round(avg_energy, 4),
                    confidence=self._label_confidence(current_label, avg_energy, i - seg_start_idx),
                ))
                seg_start_idx = i
                current_label = labels[i]

        # Letztes Segment — end_time = letzter Beat (nicht track-Ende, da
        # wir nur beat-basierte Segmente liefern)
        seg_start_time = float(beats[seg_start_idx]) if seg_start_idx < len(beats) else 0.0
        seg_end_time = float(beats[-1]) if len(beats) > 0 else seg_start_time
        remaining = max(1, n_beats - seg_start_idx)  # Guard gegen 0 bei letztem Beat
        avg_energy = float(np.mean(energy_norm[seg_start_idx:]))
        segments.append(StructureSegmentResult(
            start_time=round(seg_start_time, 3),
            end_time=round(seg_end_time, 3),
            label=current_label,
            energy=round(avg_energy, 4),
            confidence=self._label_confidence(current_label, avg_energy, remaining),
        ))

        return segments

    # ── Weitere Hilfsmethoden ────────────────────────────────────────────

    def _compute_energy_from_audio(
        self,
        file_path: str,
        bpm: float | None,
        beat_positions: list[float] | None,
    ):
        """Laedt Audio und berechnet Energie pro Beat.

        Returns:
            Tuple (energy_array, beat_array, bpm) oder (None, None, None) bei Fehler
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            log.error("librosa/numpy nicht verfuegbar fuer Audio-basierte Struktur-Erkennung")
            return None, None, None

        try:
            from services.audio_constants import DEFAULT_SR, HOP_LENGTH, MAX_DURATION_STRUCTURE
            sr = DEFAULT_SR
            hop_length = HOP_LENGTH

            log.info("Lade Audio fuer Struktur-Erkennung: %s", file_path)
            y, sr = librosa.load(file_path, sr=sr, mono=True, duration=MAX_DURATION_STRUCTURE)

            if len(y) == 0:
                return None, None, None

            duration_sec = len(y) / sr

            # Track < 30s: Vereinfachte Behandlung
            if duration_sec < 30:
                log.info("Kurzer Track (%.1fs) — vereinfachte Segmentierung", duration_sec)

            # RMS-Energie berechnen
            rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

            if beat_positions is not None and len(beat_positions) > 1:
                beats = np.array(beat_positions, dtype=np.float64)
            else:
                # Beat-Tracking falls keine Beats gegeben
                if bpm and bpm > 0:
                    # Erzeuge gleichmaessiges Beat-Grid
                    beat_dur = 60.0 / bpm
                    beats = np.arange(0, duration_sec, beat_dur)
                else:
                    # Librosa Beat-Tracking
                    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
                    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
                    if hasattr(tempo, '__len__'):
                        bpm = float(tempo[0]) if len(tempo) > 0 else 120.0
                    else:
                        bpm = float(tempo) if tempo > 0 else 120.0

                if len(beats) < 2:
                    # Fallback: 0.5s Fenster
                    beats = np.arange(0, duration_sec, 0.5)

            # RMS an Beat-Positionen samplen
            rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
            energy_per_beat = np.zeros(len(beats), dtype=np.float64)

            for i, bt in enumerate(beats):
                # Finde naechsten RMS-Frame
                idx = np.searchsorted(rms_times, bt)
                idx = min(idx, len(rms) - 1)
                # Mittelwert ueber kleines Fenster um den Beat
                window_start = max(0, idx - 2)
                window_end = min(len(rms), idx + 3)
                energy_per_beat[i] = float(np.mean(rms[window_start:window_end]))

            return energy_per_beat, beats, bpm

        except Exception:
            log.exception("Fehler beim Laden/Verarbeiten von %s", file_path)
            return None, None, None

    @staticmethod
    def _label_confidence(label: str, avg_energy: float, n_beats: int) -> float:
        """Berechnet Confidence fuer ein Segment basierend auf Label und Energie."""
        conf = 0.5  # Basis

        # Laengere Segmente → hoehere Confidence
        if n_beats >= 32:
            conf += 0.2
        elif n_beats >= 16:
            conf += 0.1

        # Energie passt zum Label
        if label == "DROP" and avg_energy > 0.7:
            conf += 0.2
        elif label == "BREAKDOWN" and avg_energy < 0.4:
            conf += 0.15
        elif label in ("INTRO", "OUTRO") and avg_energy < 0.3:
            conf += 0.2
        elif label == "BUILDUP" and 0.3 < avg_energy < 0.7:
            conf += 0.15
        elif label == "VERSE" and avg_energy < 0.5:
            conf += 0.1
        elif label == "CHORUS" and avg_energy >= 0.5:
            conf += 0.1

        return round(min(1.0, conf), 3)

    @staticmethod
    def _remove_short_segments(
        segments: list[StructureSegmentResult],
        min_beats: int = 8,
        bpm: float | None = None,
    ) -> list[StructureSegmentResult]:
        """Entfernt Segmente die kuerzer als min_beats sind und verschmilzt sie mit dem Nachbarn."""
        if len(segments) <= 1:
            return segments

        # Berechne Mindestdauer in Sekunden
        if bpm and bpm > 0:
            min_duration = (60.0 / bpm) * min_beats
        else:
            min_duration = min_beats * 0.5  # Fallback: 0.5s pro Beat

        changed = True
        while changed:
            changed = False
            new_segments: list[StructureSegmentResult] = []
            i = 0
            while i < len(segments):
                seg = segments[i]
                seg_duration = seg.end_time - seg.start_time

                if seg_duration < min_duration and len(segments) > 1:
                    # Verschmelze mit Nachbar (bevorzugt vorheriger)
                    if new_segments:
                        prev = new_segments[-1]
                        # Erweitere den vorherigen Segment
                        merged_energy = (prev.energy + seg.energy) / 2.0
                        new_segments[-1] = StructureSegmentResult(
                            start_time=prev.start_time,
                            end_time=seg.end_time,
                            label=prev.label,
                            energy=round(merged_energy, 4),
                            confidence=round(min(prev.confidence, seg.confidence), 3),
                        )
                        changed = True
                    elif i + 1 < len(segments):
                        # Verschmelze mit naechstem
                        nxt = segments[i + 1]
                        merged_energy = (seg.energy + nxt.energy) / 2.0
                        new_segments.append(StructureSegmentResult(
                            start_time=seg.start_time,
                            end_time=nxt.end_time,
                            label=nxt.label,
                            energy=round(merged_energy, 4),
                            confidence=round(min(seg.confidence, nxt.confidence), 3),
                        ))
                        i += 2  # Ueberspringe naechstes Segment
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
                # Zusammenfassen
                total_dur = (prev.end_time - prev.start_time) + (seg.end_time - seg.start_time)
                prev_weight = (prev.end_time - prev.start_time) / total_dur if total_dur > 0 else 0.5
                seg_weight = 1.0 - prev_weight
                avg_energy = prev.energy * prev_weight + seg.energy * seg_weight
                avg_conf = prev.confidence * prev_weight + seg.confidence * seg_weight

                merged[-1] = StructureSegmentResult(
                    start_time=prev.start_time,
                    end_time=seg.end_time,
                    label=prev.label,
                    energy=round(avg_energy, 4),
                    confidence=round(avg_conf, 3),
                )
            else:
                merged.append(seg)

        return merged

    def save_to_db(self, audio_track_id: int, result: StructureResult):
        """Speichert erkannte Segmente in die DB.

        Args:
            audio_track_id: ID des AudioTrack
            result: Erkannte Struktur
        """
        from database import engine, StructureSegment
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            try:
                # Alte Segmente löschen + Neue einfügen in einer Transaktion
                session.query(StructureSegment).filter_by(audio_track_id=audio_track_id).delete()
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
                log.info("Struktur gespeichert: %d Segmente für AudioTrack %d", len(result.segments), audio_track_id)
            except Exception:
                session.rollback()
                log.exception("Fehler beim Speichern der Struktur für AudioTrack %d", audio_track_id)
                raise
