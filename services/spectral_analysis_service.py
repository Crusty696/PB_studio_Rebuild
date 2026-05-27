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

# Band-Indizes fuer zielgerichtete Event-Erkennung
SUB_BASS_BAND_IDX: int = 0    # "Sub Bass" (20-60Hz)
BRILLIANCE_BAND_IDX: int = 6  # "Brilliance" (6-12kHz)

# Genre-Referenz-Spektralkurven (normalisiert 0-1, 8 Baender)
# Reihenfolge: Sub Bass, Bass, Low Mid, Mid, Upper Mid, Presence, Brilliance, Air
GENRE_REFERENCE_CURVES: dict[str, list[float]] = {
    "psytrance": [0.85, 0.75, 0.45, 0.70, 0.60, 0.55, 0.45, 0.20],
    "techno":    [0.80, 0.85, 0.55, 0.60, 0.45, 0.35, 0.25, 0.10],
    "house":     [0.70, 0.80, 0.65, 0.70, 0.55, 0.50, 0.35, 0.20],
}


@dataclass
class SpectralBand:
    """Energie eines einzelnen Frequenzbands.

    L-11 FIX: freq_low/freq_high are float (Nyquist clamp can produce fractional Hz).
    """
    name: str
    freq_low: float
    freq_high: float
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


@dataclass
class TemporalBandEnergy:
    """Band-Energie fuer ein 1-Sekunden-Fenster."""
    time_sec: float
    band_energies: dict[str, float]  # band_name -> normalisierte Energie 0-1


@dataclass
class TimbralEvolution:
    """Zeitliche Entwicklung der Klangfarbe (1-Sekunden-Hops)."""
    times_sec: list[float]
    spectral_centroids: list[float]   # Spektraler Schwerpunkt in Hz pro Sekunde
    brightness_curve: list[float]     # Energie >3kHz / Gesamt (0-1) pro Sekunde
    bass_treble_ratio: list[float]    # (Sub+Bass) / (Presence+Brilliance+Air)
    spectral_flux: list[float]        # Energie-Differenz zum vorherigen Fenster


@dataclass
class GenreSpectralMatch:
    """Vergleich mit Genre-Referenz-Spektralkurve (Kosinus-Aehnlichkeit)."""
    genre: str
    similarity: float                  # 0-1 (1.0 = perfekte Uebereinstimmung)
    band_deviations: dict[str, float]  # band_name -> Abweichung von Referenz (-1 bis 1)


@dataclass
class DynamicRangeInfo:
    """Dynamik-Kennzahlen aus dem Audiosignal."""
    crest_factor_db: float    # Peak/RMS in dB (hoeher = mehr Dynamik)
    dynamic_class: str        # "compressed" (<8dB), "moderate" (8-15dB), "wide" (>15dB)
    peak_level: float         # Linearer Spitzenpegel (0-1+)
    rms_level: float          # Linearer RMS-Pegel


@dataclass
class MasteringReport:
    """Mastering-Grade Analyse-Bericht fuer ein Audio-File."""
    spectral: SpectralResult
    temporal_bands: list[TemporalBandEnergy]
    timbral_evolution: TimbralEvolution
    ebu_r128_integrated: float    # Integrated LUFS
    ebu_r128_lra: float           # Loudness Range in LU
    ebu_r128_true_peak: float     # True Peak in dBTP
    broadcast_compliant: bool     # EBU R128 Broadcast-Standard (-23 LUFS ±1 LU)
    streaming_compliant: bool     # Streaming-konform (-16 bis -9 LUFS, TP ≤ -1 dBTP)
    dynamic_range: DynamicRangeInfo
    genre_matches: list[GenreSpectralMatch]  # Sortiert nach Aehnlichkeit absteigend
    best_genre_match: str         # Top-Genre
    recommendations: list[str]   # Mastering-Empfehlungen auf Deutsch


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
        # B-231: ``analyze`` delegiert an ``_analyze_with_buffers``, das das
        # geladene ``y`` und das Power-Spektrogramm mitliefert. ``analyze``
        # verwirft die Buffer und behaelt seinen oeffentlichen Vertrag (gibt
        # nur ``SpectralResult`` zurueck). ``analyze_extended`` nutzt denselben
        # Helper, um Audio-Load + STFT nicht ein zweites Mal zu berechnen.
        result, _y, _power_spec = self._analyze_with_buffers(file_path, bpm)
        return result

    def _analyze_with_buffers(
        self, file_path: str, bpm: float | None = None
    ) -> tuple[SpectralResult, object, object]:
        """B-231: Interner Analyse-Helper im B-062-Tuple-Return-Pattern.

        Laedt das Audio + STFT genau einmal und liefert ``(SpectralResult,
        y, power_spec)`` zurueck, damit ``analyze_extended`` die teuren Buffer
        wiederverwenden kann statt ``librosa.load`` und ``librosa.stft`` ein
        zweites Mal aufzurufen (Peak-RAM-Halbierung bei langen Tracks).

        ``y``/``power_spec`` sind ``None`` im librosa/numpy-Fehlerpfad bzw.
        bei leerem Audio.
        """
        if not _HAS_LIBROSA or not _HAS_NUMPY:
            log.error(
                "librosa/numpy nicht verfuegbar — Spektral-Analyse uebersprungen. "
                "Installiere mit: pip install librosa numpy"
            )
            return (
                SpectralResult(
                    bands=[SpectralBand(name=n, freq_low=lo, freq_high=hi, energy=0.0)
                           for n, lo, hi in FREQUENCY_BANDS],
                    events=[],
                    dominant_band="",
                    spectral_centroid_mean=0.0,
                ),
                None,
                None,
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
                return (
                    SpectralResult(
                        bands=[SpectralBand(name=n, freq_low=lo, freq_high=hi, energy=0.0)
                               for n, lo, hi in FREQUENCY_BANDS],
                        events=[],
                        dominant_band="",
                        spectral_centroid_mean=0.0,
                    ),
                    None,
                    None,
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

            return (
                SpectralResult(
                    bands=bands,
                    events=events,
                    dominant_band=dominant_band,
                    spectral_centroid_mean=round(spectral_centroid_mean, 2),
                ),
                y,
                power_spec,
            )

        except Exception as e:  # B-230: librosa kann audioread.NoBackendError + soundfile.LibsndfileError werfen — broad catch + log
            log.exception("Fehler bei Spektral-Analyse von %s", file_path)
            log.warning("analyze(): fallback result returned due to: %s", e)
            return (
                SpectralResult(
                    bands=[SpectralBand(name=n, freq_low=lo, freq_high=hi, energy=0.0)
                           for n, lo, hi in FREQUENCY_BANDS],
                    events=[],
                    dominant_band="",
                    spectral_centroid_mean=0.0,
                ),
                None,
                None,
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

            # B-228: Threshold von 0.01 auf 0.05 erhoeht. Bei 0.01 wurden
            # Intros mit Fade-In-aus-Stille (-60dB → -50dB) als false-
            # positive Drop erkannt, weil der Ratio-Verstaerker fuer
            # Werte nahe Noise-Floor extreme Spruenge produziert. 0.05
            # entspricht ~-26dB normalisierter Energie und liegt sicher
            # ueber typischem Aufnahme-Noise-Floor.
            if prev_e > 0.05 and curr_e / prev_e > DROP_ENERGY_RATIO:
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

    # ──────────────────────────────────────────────────────────────────────────
    # Mastering-Grade Analyse (AUD-80)
    # ──────────────────────────────────────────────────────────────────────────

    def analyze_extended(
        self,
        file_path: str,
        bpm: float | None = None,
        lufs_integrated: float = -14.0,
        lufs_lra: float = 8.0,
        lufs_true_peak: float = -1.0,
    ) -> MasteringReport:
        """Mastering-Grade Analyse: temporale Bänder, Timbral-Evolution, EBU-Compliance.

        Args:
            file_path: Pfad zur Audio-Datei
            bpm: Bekannter BPM-Wert (optional)
            lufs_integrated: Integrated LUFS aus LUFSService.analyze()
            lufs_lra: Loudness Range in LU aus LUFSService.analyze()
            lufs_true_peak: True Peak in dBTP aus LUFSService.analyze()

        Returns:
            MasteringReport mit allen Mastering-Kennzahlen
        """
        # B-231: ``MAX_DURATION_SPECTRAL`` wird hier nicht mehr gebraucht —
        # das Audio wird einmal in ``_analyze_with_buffers`` mit diesem Limit
        # geladen und ueber den Tuple-Return wiederverwendet.
        from services.audio_constants import (
            DEFAULT_SR, N_FFT, HOP_LENGTH,
            EBU_R128_BROADCAST_TARGET, EBU_R128_BROADCAST_TOLERANCE,
            EBU_R128_STREAMING_MIN, EBU_R128_STREAMING_MAX, EBU_TRUE_PEAK_MAX,
        )

        # 1. Standard-Analyse (Bänder, Events, Centroid)
        # B-231: Audio + Power-Spektrogramm aus ``_analyze_with_buffers``
        # wiederverwenden statt ``librosa.load`` + ``librosa.stft`` doppelt
        # aufzurufen (halbiert Peak-RAM bei langen Tracks).
        spectral, y, power_spec = self._analyze_with_buffers(file_path, bpm)
        sr = DEFAULT_SR

        if not _HAS_LIBROSA or not _HAS_NUMPY:
            return MasteringReport(
                spectral=spectral,
                temporal_bands=[],
                timbral_evolution=TimbralEvolution([], [], [], [], []),
                ebu_r128_integrated=lufs_integrated,
                ebu_r128_lra=lufs_lra,
                ebu_r128_true_peak=lufs_true_peak,
                broadcast_compliant=False,
                streaming_compliant=False,
                dynamic_range=DynamicRangeInfo(0.0, "unknown", 0.0, 0.0),
                genre_matches=[],
                best_genre_match="unknown",
                recommendations=["librosa/numpy nicht verfuegbar — erweiterte Analyse uebersprungen."],
            )

        try:
            # B-231: ``y``/``power_spec`` stammen aus ``_analyze_with_buffers``.
            # ``None`` heisst leeres Audio oder librosa/soundfile-Fehler im
            # Standard-Analyse-Lauf — gleiche Semantik wie der frueher hier
            # geworfene ValueError("Audio-Datei ist leer").
            if y is None or power_spec is None or len(y) == 0:
                raise ValueError("Audio-Datei ist leer")

            # 2. Temporale Band-Energien (1s Hops)
            temporal_bands = self._compute_temporal_bands(power_spec, sr, HOP_LENGTH, N_FFT)

            # 3. Timbral Evolution (Centroid, Brightness, Bass/Treble, Flux)
            timbral_evo = self._compute_timbral_evolution(power_spec, sr, HOP_LENGTH, N_FFT)

            # 4. Dynamik-Kennzahlen (Crest Factor)
            dynamic_range = self._compute_crest_factor(y)

            # 5. Band-spezifische Event-Erkennung (Sub-Bass + Brilliance)
            # B-067 Fix: Events MERGEN statt ueberschreiben — frueher gingen
            # generelle Drops/Buildups aus analyze() verloren, sobald
            # _detect_events_band_specific irgendetwas zurueckgab.
            band_events = self._detect_events_band_specific(
                power_spec, sr, HOP_LENGTH, N_FFT, bpm, len(y) / sr
            )
            if band_events:
                combined = list(spectral.events) + list(band_events)
                combined.sort(key=lambda e: e.time)
                spectral.events = self._deduplicate_events(combined, min_distance=2.0)

            # 6. Genre-Referenz-Matching (Kosinus-Aehnlichkeit)
            genre_matches = self._match_genre_references(spectral.bands)
            best_genre = genre_matches[0].genre if genre_matches else "unknown"

            # 7. EBU R128 Compliance
            broadcast_compliant = (
                EBU_R128_BROADCAST_TARGET - EBU_R128_BROADCAST_TOLERANCE
                <= lufs_integrated
                <= EBU_R128_BROADCAST_TARGET + EBU_R128_BROADCAST_TOLERANCE
                and lufs_true_peak <= EBU_TRUE_PEAK_MAX
            )
            streaming_compliant = (
                EBU_R128_STREAMING_MIN <= lufs_integrated <= EBU_R128_STREAMING_MAX
                and lufs_true_peak <= EBU_TRUE_PEAK_MAX
            )

            # 8. Mastering-Empfehlungen
            recommendations = self._generate_recommendations(
                spectral, dynamic_range, genre_matches,
                broadcast_compliant, streaming_compliant,
                lufs_integrated, lufs_true_peak, lufs_lra,
            )

            log.info(
                "Mastering-Report: genre=%s, crest=%.1fdB, broadcast=%s, streaming=%s, %d events",
                best_genre, dynamic_range.crest_factor_db,
                broadcast_compliant, streaming_compliant, len(spectral.events),
            )

            return MasteringReport(
                spectral=spectral,
                temporal_bands=temporal_bands,
                timbral_evolution=timbral_evo,
                ebu_r128_integrated=lufs_integrated,
                ebu_r128_lra=lufs_lra,
                ebu_r128_true_peak=lufs_true_peak,
                broadcast_compliant=broadcast_compliant,
                streaming_compliant=streaming_compliant,
                dynamic_range=dynamic_range,
                genre_matches=genre_matches,
                best_genre_match=best_genre,
                recommendations=recommendations,
            )

        except Exception as e:  # B-230: librosa kann audioread.NoBackendError + soundfile.LibsndfileError werfen — broad catch + log
            log.exception("Fehler bei erweiterter Mastering-Analyse von %s", file_path)
            log.warning("analyze_extended(): fallback MasteringReport wegen: %s", e)
            return MasteringReport(
                spectral=spectral,
                temporal_bands=[],
                timbral_evolution=TimbralEvolution([], [], [], [], []),
                ebu_r128_integrated=lufs_integrated,
                ebu_r128_lra=lufs_lra,
                ebu_r128_true_peak=lufs_true_peak,
                broadcast_compliant=False,
                streaming_compliant=False,
                dynamic_range=DynamicRangeInfo(0.0, "unknown", 0.0, 0.0),
                genre_matches=[],
                best_genre_match="unknown",
                recommendations=[f"Analyse-Fehler: {e}"],
            )

    def _compute_temporal_bands(
        self, power_spec, sr: int, hop_length: int, n_fft: int
    ) -> list[TemporalBandEnergy]:
        """Berechnet Band-Energie pro 1-Sekunden-Fenster (8 Baender).

        Gibt eine zeitliche Band-Matrix zurueck, die den Spektral-Verlauf
        des Tracks in 1s-Aufloesung zeigt (Timbral Evolution Tracking).
        """
        frames_per_sec = max(1, int(sr / hop_length))
        n_frames = power_spec.shape[1]
        n_seconds = n_frames // frames_per_sec
        nyquist = sr / 2.0

        # B-229: track-globale Normalisierung statt per-Window. Erst alle
        # Roh-Band-Energien sammeln + den track-globalen Max bestimmen, dann
        # jedes Fenster durch diesen einen Max teilen. So bleibt temporal_bands
        # ueber die Zeit vergleichbar (leiser Breakdown vs lauter Drop bleiben
        # unterscheidbar) — vorher machte per-Window-Normalisierung jeden
        # Moment gleich laut. Option 1 aus B-229.
        raw_windows: list[tuple[int, dict[str, float]]] = []
        global_max = 0.0
        for s in range(n_seconds):
            start = s * frames_per_sec
            end = min(start + frames_per_sec, n_frames)
            window = power_spec[:, start:end]

            band_energies: dict[str, float] = {}
            for name, freq_low, freq_high in FREQUENCY_BANDS:
                fh = min(freq_high, nyquist)
                if fh <= freq_low:
                    band_energies[name] = 0.0
                    continue
                bl = max(0, int(freq_low * n_fft / sr))
                bh = min(window.shape[0], max(bl + 1, int(fh * n_fft / sr)))
                e = float(np.mean(window[bl:bh, :]))
                band_energies[name] = e
                if e > global_max:
                    global_max = e
            raw_windows.append((s, band_energies))

        norm = global_max if global_max > 0 else 1.0
        result: list[TemporalBandEnergy] = [
            TemporalBandEnergy(
                time_sec=float(s),
                band_energies={k: round(v / norm, 4) for k, v in be.items()},
            )
            for s, be in raw_windows
        ]

        return result

    def _compute_timbral_evolution(
        self, power_spec, sr: int, hop_length: int, n_fft: int
    ) -> TimbralEvolution:
        """Berechnet zeitliche Klangfarben-Kennzahlen (1s Hops).

        Tracks:
        - Spektraler Schwerpunkt (Hz) — wo liegt das Energie-Gewicht
        - Brightness — Energie-Anteil oberhalb 3 kHz
        - Bass/Treble-Ratio — Wärme vs. Luftigkeit
        - Spectral Flux — Wie schnell aendert sich das Spektrum
        """
        frames_per_sec = max(1, int(sr / hop_length))
        n_frames = power_spec.shape[1]
        n_seconds = n_frames // frames_per_sec

        # Frequenzachse in Hz pro FFT-Bin
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)[:power_spec.shape[0]]
        freq_3khz_bin = min(power_spec.shape[0] - 1, int(3000 * n_fft / sr))
        bass_bin_high = min(power_spec.shape[0], int(250 * n_fft / sr))   # Sub+Bass ≤ 250Hz
        treble_bin_low = min(power_spec.shape[0], int(4000 * n_fft / sr)) # Presence+ ≥ 4kHz

        times: list[float] = []
        centroids: list[float] = []
        brightness: list[float] = []
        bass_treble: list[float] = []
        flux: list[float] = []
        prev_mean_power = None

        for s in range(n_seconds):
            start = s * frames_per_sec
            end = min(start + frames_per_sec, n_frames)
            window = power_spec[:, start:end]
            mean_power = np.mean(window, axis=1)   # (n_bins,)
            total = float(np.sum(mean_power)) + 1e-10

            centroid_hz = float(np.dot(freqs, mean_power) / total)
            brightness_val = float(np.sum(mean_power[freq_3khz_bin:])) / total
            bass_power = float(np.sum(mean_power[:bass_bin_high]))
            treble_power = float(np.sum(mean_power[treble_bin_low:])) + 1e-10
            bt_ratio = min(10.0, bass_power / treble_power)

            if prev_mean_power is not None:
                flux_val = float(np.mean((mean_power - prev_mean_power) ** 2))
            else:
                flux_val = 0.0
            prev_mean_power = mean_power

            times.append(float(s))
            centroids.append(round(centroid_hz, 1))
            brightness.append(round(min(1.0, brightness_val), 4))
            bass_treble.append(round(bt_ratio, 4))
            flux.append(round(flux_val, 8))

        return TimbralEvolution(
            times_sec=times,
            spectral_centroids=centroids,
            brightness_curve=brightness,
            bass_treble_ratio=bass_treble,
            spectral_flux=flux,
        )

    def _compute_crest_factor(self, y) -> DynamicRangeInfo:
        """Berechnet Crest Factor (Peak/RMS) als Mastering-Dynamik-Indikator.

        Niedrig (<8dB): Stark komprimiert / hyperkomprimierter DJ-Master.
        Mittel (8-15dB): Typisches EDM-Mastering.
        Hoch (>15dB): Weite Dynamik, klingt gut aber pruefen auf Streaming.
        """
        from services.audio_constants import CREST_FACTOR_COMPRESSED_DB, CREST_FACTOR_WIDE_DB

        if not _HAS_NUMPY or len(y) == 0:
            return DynamicRangeInfo(0.0, "unknown", 0.0, 0.0)

        peak = float(np.max(np.abs(y)))
        rms = float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))

        if rms < 1e-10:
            return DynamicRangeInfo(0.0, "silent", round(peak, 4), 0.0)

        crest_db = float(20.0 * np.log10(peak / rms))

        if crest_db < CREST_FACTOR_COMPRESSED_DB:
            dyn_class = "compressed"
        elif crest_db > CREST_FACTOR_WIDE_DB:
            dyn_class = "wide"
        else:
            dyn_class = "moderate"

        return DynamicRangeInfo(
            crest_factor_db=round(crest_db, 2),
            dynamic_class=dyn_class,
            peak_level=round(peak, 4),
            rms_level=round(rms, 6),
        )

    def _detect_events_band_specific(
        self,
        power_spec,
        sr: int,
        hop_length: int,
        n_fft: int,
        bpm: float | None,
        duration_sec: float,
    ) -> list[SpectralEvent]:
        """Praezisere Event-Erkennung via Sub-Bass (Drops) und Brilliance (Buildups).

        Sub-Bass-Surge → Drop: Kick kommt rein (typisch EDM-Drop-Moment)
        Brilliance-Anstieg → Buildup: Filter oeffnet nach oben (Sweep)
        Sub-Bass-Einbruch → Breakdown: Kick wird herausgenommen
        """
        from services.audio_constants import (
            DROP_ENERGY_RATIO, BUILDUP_MIN_WINDOWS, BUILDUP_MIN_RISE,
            BUILDUP_MAX_START_ENERGY, BUILDUP_JITTER_TOLERANCE,
            BREAKDOWN_MIN_PREV_ENERGY, BREAKDOWN_DROP_RATIO,
        )

        if not _HAS_NUMPY:
            return []

        frames_per_sec = max(1, int(sr / hop_length))
        n_frames = power_spec.shape[1]
        n_seconds = n_frames // frames_per_sec

        if n_seconds < 4:
            return []

        nyquist = sr / 2.0

        def _band_bins(freq_low: float, freq_high: float) -> tuple[int, int]:
            fh = min(freq_high, nyquist)
            if fh <= freq_low:
                return 0, 1
            bl = max(0, int(freq_low * n_fft / sr))
            bh = min(power_spec.shape[0], max(bl + 1, int(fh * n_fft / sr)))
            return bl, bh

        _, sb_low, sb_high = FREQUENCY_BANDS[SUB_BASS_BAND_IDX]
        _, br_low, br_high = FREQUENCY_BANDS[BRILLIANCE_BAND_IDX]
        sb_bl, sb_bh = _band_bins(sb_low, sb_high)
        br_bl, br_bh = _band_bins(br_low, br_high)

        sub_bass_e: list[float] = []
        brilliance_e: list[float] = []

        for s in range(n_seconds):
            start = s * frames_per_sec
            end = min(start + frames_per_sec, n_frames)
            w = power_spec[:, start:end]
            sub_bass_e.append(float(np.mean(w[sb_bl:sb_bh, :])))
            brilliance_e.append(float(np.mean(w[br_bl:br_bh, :])))

        sub_bass_n = np.array(sub_bass_e) / (max(sub_bass_e) + 1e-10)
        brilliance_n = np.array(brilliance_e) / (max(brilliance_e) + 1e-10)

        events: list[SpectralEvent] = []
        min_buildup_sec = max(4, BUILDUP_MIN_WINDOWS // 2)

        # Sub-Bass Drops (Kick kommt rein)
        for t in range(1, n_seconds):
            prev_sb = sub_bass_n[t - 1]
            curr_sb = sub_bass_n[t]
            if prev_sb > 0.01 and curr_sb / (prev_sb + 1e-10) > DROP_ENERGY_RATIO:
                delta = float(curr_sb - prev_sb)
                confidence = min(1.0, (curr_sb / (prev_sb + 1e-10) - 1.0) / 3.0)
                events.append(SpectralEvent(
                    time=round(float(t), 2),
                    event_type="drop",
                    energy_delta=round(delta, 4),
                    confidence=round(confidence, 3),
                ))

        # Brilliance Buildups (Filter-Sweep nach oben)
        i = 0
        while i < n_seconds - min_buildup_sec:
            if brilliance_n[i] > BUILDUP_MAX_START_ENERGY:
                i += 1
                continue
            rise_len = 0
            for j in range(i + 1, n_seconds):
                if brilliance_n[j] >= brilliance_n[j - 1] * BUILDUP_JITTER_TOLERANCE:
                    rise_len += 1
                else:
                    break
            if rise_len >= min_buildup_sec:
                end_idx = i + rise_len
                total_rise = float(brilliance_n[end_idx] - brilliance_n[i])
                if total_rise > BUILDUP_MIN_RISE * 0.5:
                    confidence = min(1.0, total_rise / 0.6)
                    events.append(SpectralEvent(
                        time=round(float(i), 2),
                        event_type="buildup",
                        energy_delta=round(total_rise, 4),
                        confidence=round(confidence, 3),
                    ))
                    i = end_idx
                    continue
            i += 1

        # Sub-Bass Breakdowns (Kick raus)
        for t in range(1, n_seconds):
            prev_sb = sub_bass_n[t - 1]
            curr_sb = sub_bass_n[t]
            if (prev_sb > BREAKDOWN_MIN_PREV_ENERGY
                    and (prev_sb - curr_sb) / (prev_sb + 1e-10) > BREAKDOWN_DROP_RATIO):
                delta = float(curr_sb - prev_sb)
                confidence = min(1.0, (prev_sb - curr_sb) / (prev_sb + 1e-10))
                events.append(SpectralEvent(
                    time=round(float(t), 2),
                    event_type="breakdown",
                    energy_delta=round(delta, 4),
                    confidence=round(confidence, 3),
                ))

        events.sort(key=lambda e: e.time)
        return self._deduplicate_events(events, 2.0)

    def _match_genre_references(self, bands: list[SpectralBand]) -> list[GenreSpectralMatch]:
        """Vergleicht das Spektralprofil mit Genre-Referenzkurven (Kosinus-Aehnlichkeit).

        Psytrance: Heavy Sub-Bass, offene Brilliance-Schicht.
        Techno: Dominanter Bass, dunkler Charakter, wenig Air.
        House: Ausgeglichen, warme Mitte, punchy Bass.
        """
        if not _HAS_NUMPY or not bands:
            return []

        current = np.array([b.energy for b in bands], dtype=np.float64)
        results: list[GenreSpectralMatch] = []

        for genre, ref_curve in GENRE_REFERENCE_CURVES.items():
            ref = np.array(ref_curve, dtype=np.float64)
            denom = (np.linalg.norm(current) * np.linalg.norm(ref)) + 1e-10
            similarity = float(np.dot(current, ref) / denom)

            deviations: dict[str, float] = {}
            for i, band in enumerate(bands):
                if i < len(ref_curve):
                    deviations[band.name] = round(float(current[i]) - ref_curve[i], 4)

            results.append(GenreSpectralMatch(
                genre=genre,
                similarity=round(similarity, 4),
                band_deviations=deviations,
            ))

        results.sort(key=lambda g: g.similarity, reverse=True)
        return results

    def _generate_recommendations(
        self,
        spectral: SpectralResult,
        dynamic_range: DynamicRangeInfo,
        genre_matches: list[GenreSpectralMatch],
        broadcast_compliant: bool,
        streaming_compliant: bool,
        lufs_integrated: float,
        lufs_true_peak: float,
        lufs_lra: float,
    ) -> list[str]:
        """Generiert Mastering-Empfehlungen basierend auf allen Analyse-Ergebnissen."""
        from services.audio_constants import (
            EBU_R128_BROADCAST_TARGET, EBU_R128_BROADCAST_TOLERANCE,
            EBU_R128_STREAMING_MIN, EBU_R128_STREAMING_MAX, EBU_TRUE_PEAK_MAX,
        )

        recs: list[str] = []

        # Lautstaerke / Streaming
        if lufs_integrated > EBU_R128_STREAMING_MAX:
            recs.append(
                f"LAUTSTAERKE: {lufs_integrated:.1f} LUFS ist zu laut fuer Streaming "
                f"(Ziel: {EBU_R128_STREAMING_MIN} bis {EBU_R128_STREAMING_MAX} LUFS). "
                "Reduziere Limiting oder Ausgangspegel."
            )
        elif lufs_integrated < EBU_R128_STREAMING_MIN:
            recs.append(
                f"LAUTSTAERKE: {lufs_integrated:.1f} LUFS ist zu leise fuer Streaming "
                f"(Ziel: {EBU_R128_STREAMING_MIN} bis {EBU_R128_STREAMING_MAX} LUFS). "
                "Normalisiere oder erhoehe Masterlevel."
            )

        # True Peak
        if lufs_true_peak > EBU_TRUE_PEAK_MAX:
            recs.append(
                f"TRUE PEAK: {lufs_true_peak:.1f} dBTP liegt ueber dem Grenzwert von "
                f"{EBU_TRUE_PEAK_MAX} dBTP. Aktiviere einen True Peak Limiter."
            )

        # Dynamik / Crest Factor
        if dynamic_range.dynamic_class == "compressed":
            recs.append(
                f"DYNAMIK: Crest Factor {dynamic_range.crest_factor_db:.1f} dB — stark "
                "komprimiert. Mehr Dynamik gibt dem Mix mehr Punch und Energie auf der Tanzflaeche."
            )
        elif dynamic_range.dynamic_class == "wide":
            recs.append(
                f"DYNAMIK: Crest Factor {dynamic_range.crest_factor_db:.1f} dB — sehr weite "
                "Dynamik. Pruefen ob laute Passagen auf kleinen Anlagen clipping verursachen."
            )

        # Sub-Bass
        sub_bass_band = next((b for b in spectral.bands if b.name == "Sub Bass"), None)
        if sub_bass_band:
            if sub_bass_band.energy < 0.2:
                recs.append(
                    "SUB-BASS (20-60Hz): Sehr wenig Energie. Low-Shelf-Boost oder "
                    "Sub-Bass-Enhancement fuer besseren Kick auf Grossanlagen empfehlenswert."
                )
            elif sub_bass_band.energy > 0.95:
                recs.append(
                    "SUB-BASS (20-60Hz): Dominiert den Mix. Pruefe Mono-Kompatibilitaet "
                    "und Verhalten auf kleinen Lautsprechern (Phone, Laptop)."
                )

        # LRA (Loudness Range)
        if lufs_lra < 3.0:
            recs.append(
                f"LRA: {lufs_lra:.1f} LU — sehr enge Loudness Range. "
                "Erwaege weniger Multiband-Kompression fuer natuerlicheren Klang."
            )
        elif lufs_lra > 20.0:
            recs.append(
                f"LRA: {lufs_lra:.1f} LU — sehr weite Loudness Range. "
                "Leise Passagen koennen auf Streaming-Plattformen zu leise klingen."
            )

        # Genre-Matching
        if genre_matches:
            top = genre_matches[0]
            if top.similarity >= 0.8:
                recs.append(
                    f"GENRE: Sehr gute Uebereinstimmung mit {top.genre.upper()} "
                    f"({top.similarity:.2f} Kosinus-Aehnlichkeit). Spektralprofil passt zur Referenz."
                )
            elif top.similarity >= 0.65:
                recs.append(
                    f"GENRE: Gute Uebereinstimmung mit {top.genre.upper()} "
                    f"({top.similarity:.2f}). Kleine Abweichungen vom Referenz-Spektrum."
                )
            else:
                recs.append(
                    f"GENRE: Geringe Uebereinstimmung mit allen Referenz-Genres "
                    f"(bestes: {top.genre} mit {top.similarity:.2f}). "
                    "Ungewoehnliches Spektralprofil — moeglicherweise experimentelles Genre."
                )

        # EBU R128 Broadcast
        if not broadcast_compliant:
            target_low = EBU_R128_BROADCAST_TARGET - EBU_R128_BROADCAST_TOLERANCE
            target_high = EBU_R128_BROADCAST_TARGET + EBU_R128_BROADCAST_TOLERANCE
            recs.append(
                f"EBU R128 BROADCAST: Nicht konform (Ziel: {target_low} bis {target_high} LUFS, "
                f"aktuell: {lufs_integrated:.1f} LUFS). Relevant fuer TV/Radio-Auslieferung."
            )

        if not recs:
            recs.append(
                "MASTERING: Alle Werte im optimalen Bereich. "
                f"Mix klingt fuer {genre_matches[0].genre.upper() if genre_matches else 'das Genre'} "
                "ausgewogen und streaming-bereit."
            )

        return recs
