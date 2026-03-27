"""Spectral Analysis Service — 8-Band Frequenz-Analyse.

Zerlegt ein Audio-Signal in 8 Frequenzbänder und berechnet die Energie
pro Band. Erkennt spektrale Events wie Drops, Buildups und Breakdowns.
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

# Standard 8-Band Aufteilung (Hz)
FREQUENCY_BANDS = [
    ("Sub Bass", 20, 60),
    ("Bass", 60, 250),
    ("Low Mid", 250, 500),
    ("Mid", 500, 2000),
    ("Upper Mid", 2000, 4000),
    ("Presence", 4000, 6000),
    ("Brilliance", 6000, 12000),
    ("Air", 12000, 20000),
]


@dataclass
class SpectralBand:
    """Energie eines einzelnen Frequenzbands."""
    name: str
    freq_low: int
    freq_high: int
    energy: float           # 0.0-1.0 normalisiert


@dataclass
class SpectralEvent:
    """Spektrales Event (Drop, Buildup, Breakdown)."""
    time: float             # Sekunden
    event_type: str         # "drop", "buildup", "breakdown", "transition"
    energy_delta: float     # Energieänderung (-1.0 bis 1.0)
    confidence: float       # 0.0-1.0


@dataclass
class SpectralResult:
    """Ergebnis der Spektral-Analyse."""
    bands: list[SpectralBand] = field(default_factory=list)
    events: list[SpectralEvent] = field(default_factory=list)
    dominant_band: str = ""
    spectral_centroid_mean: float = 0.0


class SpectralAnalysisService:
    """8-Band Frequenz-Analyse für Audio-Tracks."""

    def analyze(self, file_path: str, bpm: float | None = None) -> SpectralResult:
        """Analysiert die Frequenzverteilung einer Audio-Datei.

        Args:
            file_path: Pfad zur Audio-Datei
            bpm: Bekannter BPM-Wert (optional, fuer Beat-basierte Fensterung)

        Returns:
            SpectralResult mit 8 Frequenzbändern und erkannten Events
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            log.error(
                "librosa/numpy nicht verfuegbar — Spektral-Analyse uebersprungen. "
                "Installiere mit: pip install librosa numpy"
            )
            return SpectralResult(
                bands=[SpectralBand(name=n, freq_low=lo, freq_high=hi, energy=0.0)
                       for n, lo, hi in FREQUENCY_BANDS],
                events=[],
                dominant_band="",
                spectral_centroid_mean=0.0,
            )

        try:
            from services.audio_constants import DEFAULT_SR, N_FFT, HOP_LENGTH, MAX_DURATION_SPECTRAL
            sr = DEFAULT_SR
            n_fft = N_FFT
            hop_length = HOP_LENGTH

            # ── 1. Audio laden ──────────────────────────────────────────
            log.info("Lade Audio fuer Spektral-Analyse: %s", file_path)
            y, sr = librosa.load(file_path, sr=sr, mono=True, duration=MAX_DURATION_SPECTRAL)

            if len(y) == 0:
                log.warning("Audio-Datei ist leer: %s", file_path)
                return SpectralResult(
                    bands=[SpectralBand(name=n, freq_low=lo, freq_high=hi, energy=0.0)
                           for n, lo, hi in FREQUENCY_BANDS],
                    events=[],
                    dominant_band="",
                    spectral_centroid_mean=0.0,
                )

            duration_sec = len(y) / sr

            # ── 2. STFT berechnen ───────────────────────────────────────
            stft_matrix = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)

            # ── 3. Power Spectrogram: S = |STFT|^2 ─────────────────────
            power_spec = np.abs(stft_matrix) ** 2

            # ── 4. Energie pro Frequenzband ─────────────────────────────
            band_energies_raw: list[float] = []
            bands: list[SpectralBand] = []

            nyquist = sr / 2.0
            for name, freq_low, freq_high in FREQUENCY_BANDS:
                # Clamp frequencies to Nyquist limit (sr/2)
                freq_low = min(freq_low, nyquist)
                freq_high = min(freq_high, nyquist)
                if freq_high <= freq_low:
                    bands.append(SpectralBand(name=name, freq_low=freq_low, freq_high=freq_high, energy=0.0))
                    band_energies_raw.append(0.0)
                    continue
                bin_low = int(freq_low * n_fft / sr)
                bin_high = int(freq_high * n_fft / sr)

                # Clamp to valid range
                bin_low = max(0, min(bin_low, power_spec.shape[0] - 1))
                bin_high = max(bin_low + 1, min(bin_high, power_spec.shape[0]))

                # Sum power across the band's bins, average across time
                band_power = power_spec[bin_low:bin_high, :]
                energy_raw = float(np.mean(band_power))
                band_energies_raw.append(energy_raw)
                bands.append(SpectralBand(
                    name=name, freq_low=freq_low, freq_high=freq_high,
                    energy=energy_raw,  # wird unten normalisiert
                ))

            # ── 5. Normalisieren auf 0.0-1.0 ───────────────────────────
            max_energy = max(band_energies_raw) if band_energies_raw else 1.0
            if max_energy > 0:
                for i, band in enumerate(bands):
                    band.energy = round(band_energies_raw[i] / max_energy, 4)
            else:
                for band in bands:
                    band.energy = 0.0

            # ── 6. Dominant Band ────────────────────────────────────────
            dominant_idx = int(np.argmax(band_energies_raw)) if band_energies_raw else 0
            dominant_band = bands[dominant_idx].name if bands else ""

            # ── 7. Spectral Centroid ────────────────────────────────────
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length)
            spectral_centroid_mean = float(np.mean(centroid))

            # ── 8. Event-Erkennung ──────────────────────────────────────
            events = self._detect_events(power_spec, sr, hop_length, n_fft, bpm, duration_sec)

            log.info(
                "Spektral-Analyse abgeschlossen: dominant=%s, centroid=%.1f Hz, %d events",
                dominant_band, spectral_centroid_mean, len(events),
            )

            return SpectralResult(
                bands=bands,
                events=events,
                dominant_band=dominant_band,
                spectral_centroid_mean=round(spectral_centroid_mean, 2),
            )

        except Exception:
            log.exception("Fehler bei Spektral-Analyse von %s", file_path)
            return SpectralResult(
                bands=[SpectralBand(name=n, freq_low=lo, freq_high=hi, energy=0.0)
                       for n, lo, hi in FREQUENCY_BANDS],
                events=[],
                dominant_band="",
                spectral_centroid_mean=0.0,
            )

    def _detect_events(
        self,
        power_spec,
        sr: int,
        hop_length: int,
        n_fft: int,
        bpm: float | None,
        duration_sec: float,
    ) -> list[SpectralEvent]:
        """Erkennt spektrale Events (Drop, Buildup, Breakdown) aus dem Power-Spektrogramm.

        Berechnet Gesamt-Energie in Zeitfenstern und sucht nach markanten
        Energieaenderungen.
        """
        if not _HAS_NUMPY:
            return []

        # Berechne Fenstergroesse: 4 Beats (wenn BPM bekannt) oder 2 Sekunden
        if bpm and bpm > 0:
            beat_duration_sec = 60.0 / bpm
            window_duration_sec = beat_duration_sec * 4  # 4 Beats
        else:
            window_duration_sec = 2.0

        # Frames pro Fenster
        frames_per_window = max(1, int(window_duration_sec * sr / hop_length))
        n_frames = power_spec.shape[1]

        if n_frames < 2 * frames_per_window:
            return []  # Track zu kurz fuer Event-Erkennung

        # Gesamt-Energie pro Fenster berechnen
        n_windows = n_frames // frames_per_window
        window_energies: list[float] = []

        for w in range(n_windows):
            start_frame = w * frames_per_window
            end_frame = min(start_frame + frames_per_window, n_frames)
            window_power = power_spec[:, start_frame:end_frame]
            window_energies.append(float(np.mean(window_power)))

        if len(window_energies) < 3:
            return []

        # In numpy fuer einfachere Verarbeitung
        energies = np.array(window_energies, dtype=np.float64)

        # Normalisieren fuer Vergleiche
        max_e = np.max(energies)
        if max_e > 0:
            energies_norm = energies / max_e
        else:
            return []

        events: list[SpectralEvent] = []
        events.extend(self._detect_drops(energies_norm, window_duration_sec))
        events.extend(self._detect_buildups(energies_norm, window_duration_sec))
        events.extend(self._detect_breakdowns(energies_norm, window_duration_sec))

        events.sort(key=lambda e: e.time)
        events = self._deduplicate_events(events, window_duration_sec * 0.8)

        return events

    def _detect_drops(self, energies_norm, window_duration: float) -> list[SpectralEvent]:
        """Erkennt Drop-Events: Energie-Verhaeltnis > DROP_ENERGY_RATIO zum Vorgaenger."""
        from services.audio_constants import DROP_ENERGY_RATIO

        events: list[SpectralEvent] = []
        for t in range(1, len(energies_norm)):
            prev_e = energies_norm[t - 1]
            curr_e = energies_norm[t]

            if prev_e > 0.01 and curr_e / prev_e > DROP_ENERGY_RATIO:
                time_sec = t * window_duration
                delta = float(curr_e - prev_e)
                confidence = min(1.0, (curr_e / prev_e - 1.0) / 3.0)  # 3x = 0.67 conf, 4x = 1.0
                events.append(SpectralEvent(
                    time=round(time_sec, 2),
                    event_type="drop",
                    energy_delta=round(delta, 4),
                    confidence=round(confidence, 3),
                ))
        return events

    def _detect_buildups(self, energies_norm, window_duration: float) -> list[SpectralEvent]:
        """Erkennt Buildup-Events: Energie steigt sustained ueber mehrere Fenster."""
        from services.audio_constants import (
            BUILDUP_MIN_WINDOWS, BUILDUP_MAX_START_ENERGY,
            BUILDUP_JITTER_TOLERANCE, BUILDUP_MIN_RISE,
        )

        events: list[SpectralEvent] = []
        min_buildup_windows = BUILDUP_MIN_WINDOWS
        if len(energies_norm) >= min_buildup_windows:
            i = 0
            while i < len(energies_norm) - min_buildup_windows:
                # Starte nur wenn Energie relativ niedrig ist
                if energies_norm[i] > BUILDUP_MAX_START_ENERGY:
                    i += 1
                    continue

                # Suche wie lang die Energie kontinuierlich steigt
                rise_length = 0
                for j in range(i + 1, len(energies_norm)):
                    if energies_norm[j] >= energies_norm[j - 1] * BUILDUP_JITTER_TOLERANCE:  # erlaube leichten Jitter
                        rise_length += 1
                    else:
                        break

                if rise_length >= min_buildup_windows:
                    end_idx = i + rise_length
                    total_rise = energies_norm[end_idx] - energies_norm[i]
                    if total_rise > BUILDUP_MIN_RISE:
                        time_sec = i * window_duration
                        confidence = min(1.0, total_rise / 0.8)
                        events.append(SpectralEvent(
                            time=round(time_sec, 2),
                            event_type="buildup",
                            energy_delta=round(float(total_rise), 4),
                            confidence=round(confidence, 3),
                        ))
                        i = end_idx  # ueberspringe den erkannten Buildup
                        continue

                i += 1
        return events

    def _detect_breakdowns(self, energies_norm, window_duration: float) -> list[SpectralEvent]:
        """Erkennt Breakdown-Events: Energie faellt >50% in 1 Fenster."""
        from services.audio_constants import (
            BREAKDOWN_MIN_PREV_ENERGY, BREAKDOWN_DROP_RATIO,
        )

        events: list[SpectralEvent] = []
        for t in range(1, len(energies_norm)):
            prev_e = energies_norm[t - 1]
            curr_e = energies_norm[t]

            if prev_e > BREAKDOWN_MIN_PREV_ENERGY and (prev_e - curr_e) / prev_e > BREAKDOWN_DROP_RATIO:
                time_sec = t * window_duration
                delta = float(curr_e - prev_e)  # negativ
                confidence = min(1.0, (prev_e - curr_e) / prev_e)
                events.append(SpectralEvent(
                    time=round(time_sec, 2),
                    event_type="breakdown",
                    energy_delta=round(delta, 4),
                    confidence=round(confidence, 3),
                ))
        return events

    def _deduplicate_events(self, events: list[SpectralEvent], min_distance: float) -> list[SpectralEvent]:
        """Dedupliziert Events die zu dicht beieinander liegen.

        Behaelt bei Konflikten das Event mit hoeherer Confidence.
        """
        if len(events) <= 1:
            return events

        deduped: list[SpectralEvent] = [events[0]]
        for ev in events[1:]:
            last = deduped[-1]
            if ev.time - last.time < min_distance:
                # Behalte das Event mit hoeherer Confidence
                if ev.confidence > last.confidence:
                    deduped[-1] = ev
            else:
                deduped.append(ev)
        return deduped

    def get_bands_json(self, result: SpectralResult) -> str:
        """Konvertiert SpectralResult in JSON für DB-Speicherung."""
        import json
        return json.dumps([{"name": b.name, "energy": b.energy} for b in result.bands])
