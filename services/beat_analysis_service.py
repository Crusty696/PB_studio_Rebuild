"""Beat-Analyse Service mit beat_this + Chunked Processing.

Phase 1 Foundation — SEKTOR 4.
PoC-Erkenntnis R4: GTX 1060 hat 6GB VRAM. Ein 60-Min-Mix braucht ~2.9GB.
ZWINGEND: Chunked Processing fuer lange Audio-Dateien.
dbn=False verhindert madmom-Abhaengigkeit.
"""

from __future__ import annotations

import atexit
import logging
import threading
from pathlib import Path

import numpy as np

from database import AudioTrack, Beatgrid
from services.audio_constants import DEFAULT_SR, clamp_bpm

logger = logging.getLogger(__name__)

# Chunk-Groesse: 10 Minuten in Sekunden (PoC-validiert fuer 6GB VRAM)
CHUNK_DURATION_SEC = 600.0

# Overlap zwischen Chunks fuer saubere Beat-Uebergaenge (5 Sekunden)
CHUNK_OVERLAP_SEC = 5.0

# M-21 FIX: Track temp files for cleanup on exit to prevent orphaned files
_temp_files: set[str] = set()
_temp_files_lock = threading.Lock()


def _cleanup_temp_files():
    """M-21 FIX: Clean up all tracked temp files on exit."""
    with _temp_files_lock:
        for path_str in list(_temp_files):
            try:
                Path(path_str).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("[BeatAnalysis] Failed to cleanup temp file %s: %s", path_str, e)
        _temp_files.clear()


atexit.register(_cleanup_temp_files)


class BeatAnalysisService:
    """GPU-beschleunigte Beat/Downbeat-Erkennung mit beat_this.

    Verwendet Chunked Processing um auch 60+ Minuten Mixes auf
    einer GTX 1060 (6GB VRAM) analysieren zu koennen.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, device: str | None = None):
        """E-01 Fix: Thread-safe Singleton mit Lock — verhindert doppeltes GPU-Modell."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, device: str | None = None):
        if self._initialized:
            # B-141: device-Arg nach erster Init ist semantisch
            # ignoriert — Caller mit erwartung "force CPU after first
            # GPU init" bekommt ohne Warnung den GPU-Singleton zurueck.
            if device is not None and device != self._device:
                logger.warning(
                    "BeatAnalysisService(device=%r) ignoriert — Singleton "
                    "bereits mit device=%r initialisiert. Fuer Re-Init "
                    "explizit Singleton resetten.",
                    device, self._device,
                )
            return
        self._initialized = True
        self._model = None
        self._device = device
        # Private cache for audio array; populated by analyze(), consumed by analyze_and_store()
        self._last_y = None
        self._last_sr = None
        # E-02 Fix: Lock um analyze() + _last_y Zugriff in analyze_and_store() atomar zu halten
        self._analysis_lock = threading.Lock()
        # Graceful degradation: set to True when beat_this unavailable
        self._beat_this_unavailable = False
        self._beat_this_unavailable_reason = ""

    @property
    def device(self) -> str:
        if self._device is None:
            import torch
            # GPU-ZWANG: beat_this MUSS auf CUDA laufen wenn verfügbar
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    @property
    def is_available(self) -> bool:
        """True wenn beat_this einsatzbereit ist (Modell vorhanden + ladbar)."""
        return not self._beat_this_unavailable

    def _ensure_model(self) -> None:
        """Laedt das beat_this Modell (lazy, einmalig).

        WICHTIG: Entlaedt zuerst den ModelManager, damit kein anderes
        Modell gleichzeitig VRAM belegt (GTX 1060 = 6GB Budget).
        GPU_LOAD_LOCK serialisiert alle GPU-Lade-Operationen.

        Bei fehlenden Modellen oder nicht installiertem beat_this wird
        self._beat_this_unavailable gesetzt — kein crash, Fallback auf librosa.
        """
        if self._model is not None:
            return
        if self._beat_this_unavailable:
            return  # Bereits als unavailable markiert — nicht erneut versuchen
        from services.model_manager import ModelManager, GPU_LOAD_LOCK
        with GPU_LOAD_LOCK:
            if self._model is not None:  # Double-check nach Lock
                return
            # ModelManager entladen bevor beat_this GPU-Speicher beansprucht
            try:
                ModelManager().unload()
            except (RuntimeError, AttributeError) as e:
                logger.warning("ModelManager.unload() vor beat_this fehlgeschlagen: %s", e)
            import torch, gc
            try:
                from beat_this.inference import File2Beats
            except ImportError as e:
                reason = (
                    "beat_this nicht installiert. "
                    "Fallback auf librosa BPM-Erkennung aktiv. "
                    "Installation: pip install beat_this"
                )
                logger.warning("beat_this Import fehlgeschlagen — %s: %s", reason, e)
                self._beat_this_unavailable = True
                self._beat_this_unavailable_reason = reason
                return
            if torch.cuda.is_available():
                logger.info("GPU-ZWANG: beat_this wird auf CUDA geladen (%s)", torch.cuda.get_device_name(0))
            logger.info("Lade beat_this Modell (device=%s, dbn=False)...", self.device)
            try:
                self._model = File2Beats(device=self.device, dbn=False)
            except RuntimeError:
                torch.cuda.empty_cache()
                gc.collect()
                raise RuntimeError(
                    f"VRAM reicht nicht fuer beat_this auf '{self.device}'. "
                    "Bitte andere GPU-Modelle entladen."
                )
            except (OSError, EnvironmentError) as e:
                reason = (
                    "beat_this Modell nicht heruntergeladen. "
                    "Fallback auf librosa BPM-Erkennung aktiv. "
                    "Beim naechsten Start mit Internetverbindung wird das Modell automatisch geladen."
                )
                logger.warning("beat_this Modell nicht gefunden — %s: %s", reason, e)
                self._beat_this_unavailable = True
                self._beat_this_unavailable_reason = reason
                return
            logger.info("beat_this Modell geladen.")

    def unload(self) -> None:
        """Entlaedt das Modell und gibt VRAM frei."""
        if self._model is not None:
            import torch, gc
            # Model auf CPU verschieben bevor Referenz geloescht wird
            if hasattr(self._model, 'cpu'):
                try:
                    self._model.cpu()
                except (RuntimeError, AttributeError) as e:
                    logger.warning("model.cpu() VRAM-Freigabe fehlgeschlagen: %s", e)
            del self._model
            self._model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("beat_this Modell entladen, VRAM freigegeben.")

    def analyze(self, audio_path: str | Path, progress_cb=None) -> dict:
        """Analysiert eine Audio-Datei und gibt Beats + Downbeats zurueck.

        Verwendet Chunked Processing fuer Dateien laenger als CHUNK_DURATION_SEC.

        WICHTIG: Diese Methode sollte nur ueber analyze_and_store() aufgerufen werden.
        analyze_and_store() kuemmert sich um VRAM-Freigabe (self.unload()) im finally-Block.
        Ein direkter Aufruf von analyze() laesst das beat_this-Modell im VRAM geladen,
        was bei nachfolgenden GPU-Operationen zu OOM fuehren kann (B-04).

        Returns:
            {
                "beats": [float, ...],          # Beat-Zeitpunkte in Sekunden
                "downbeats": [float, ...],      # Downbeat-Zeitpunkte in Sekunden
                "bpm": float,                   # Geschaetztes BPM
                "duration": float,              # Audio-Dauer in Sekunden
                "num_beats": int,
                "num_downbeats": int,
            }
        """
        # H-12 FIX: Clear previous arrays before loading new audio to prevent memory leak
        # when analyze() is called standalone without analyze_and_store()
        self._last_y = None
        self._last_sr = None

        import librosa
        audio_path = str(audio_path)

        if progress_cb:
            progress_cb(0, "Lade Audio...")

        # Dauer bestimmen
        try:
            duration = librosa.get_duration(path=audio_path)
        except (OSError, IOError, ValueError) as e:
            raise RuntimeError(f"Audio-Dauer konnte nicht ermittelt werden: {e}") from e
        # Edge Case: Dateien <0.5s werden abgelehnt. Dateien 0.5s-2s werden verarbeitet,
        # koennen aber 0-1 Beats liefern. energy_per_beat wird dann [] (leer).
        if duration < 0.5:
            raise ValueError(f"Audio-Datei zu kurz ({duration:.2f}s): {Path(audio_path).name}")
        logger.info("Audio-Dauer: %.1fs (%s)", duration, Path(audio_path).name)

        if progress_cb:
            progress_cb(10, "Lade Audio...")

        # Audio einmalig laden (wird fuer Chunking UND Energie-Analyse wiederverwendet)
        try:
            y, sr = librosa.load(audio_path, sr=DEFAULT_SR, mono=True)
        except (OSError, IOError, ValueError, RuntimeError) as e:
            raise RuntimeError(f"Audio konnte nicht geladen werden: {e}") from e

        if progress_cb:
            progress_cb(15, "Lade beat_this Modell...")

        # Graceful degradation: fallback auf librosa wenn beat_this nicht verfuegbar
        self._ensure_model()
        if self._beat_this_unavailable:
            logger.warning(
                "beat_this nicht verfuegbar — nutze librosa BPM-Fallback: %s",
                self._beat_this_unavailable_reason,
            )
            if progress_cb:
                progress_cb(20, "Librosa BPM-Analyse (Fallback)...")
            beats, downbeats = self._analyze_librosa_fallback(y, sr)
        elif duration <= CHUNK_DURATION_SEC:
            if progress_cb:
                progress_cb(20, "Analysiere Beats...")
            # Kurze Datei: direkt analysieren
            beats, downbeats = self._analyze_full(audio_path)
        else:
            if progress_cb:
                progress_cb(20, "Chunked Beat-Analyse...")
            # Lange Datei: Chunked Processing (nutzt bereits geladenes Audio)
            beats, downbeats = self._analyze_chunked(audio_path, duration, y, sr)

        if progress_cb:
            progress_cb(80, "Berechne BPM...")

        # BPM aus Beat-Intervallen berechnen
        bpm = 0.0
        if len(beats) > 1:
            intervals = np.diff(beats)
            median_interval = float(np.median(intervals))
            if median_interval > 0:
                bpm = round(60.0 / median_interval, 1)

        if progress_cb:
            progress_cb(100, "Fertig")

        # Store audio array as private instance attribute so analyze_and_store()
        # can reuse it for energy computation without embedding a 1GB+ numpy
        # array in the public return dict (Bug-B1 fix: memory leak in public API).
        self._last_y = y
        self._last_sr = sr

        result: dict = {
            "beats": [round(float(b), 4) for b in beats],
            "downbeats": [round(float(b), 4) for b in downbeats],
            "bpm": bpm,
            "duration": round(duration, 2),
            "num_beats": len(beats),
            "num_downbeats": len(downbeats),
        }
        if self._beat_this_unavailable:
            result["fallback"] = True
            result["fallback_reason"] = self._beat_this_unavailable_reason
        return result

    def _analyze_full(self, audio_path: str) -> tuple[np.ndarray, np.ndarray]:
        """Analysiert die komplette Datei in einem Durchgang."""
        import torch
        self._ensure_model()
        with torch.no_grad():
            beats, downbeats = self._model(audio_path)
        return np.array(beats), np.array(downbeats)

    def _analyze_librosa_fallback(
        self, y: np.ndarray, sr: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Librosa-basierter BPM/Beat-Fallback wenn beat_this nicht verfuegbar.

        Qualitaet: geringer als beat_this (kein Downbeat, weniger praezise),
        aber fuer Basis-Pacing ausreichend.
        """
        import librosa
        logger.info("Librosa Beat-Fallback: Analysiere %d samples @ %d Hz...", len(y), sr)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        # Librosa liefert keine Downbeats — jeden 4. Beat als Downbeat schaetzen
        downbeat_times = beat_times[::4] if len(beat_times) >= 4 else beat_times[:1]
        logger.info(
            "Librosa Beat-Fallback: %.1f BPM, %d Beats, %d Downbeats (geschaetzt)",
            float(tempo), len(beat_times), len(downbeat_times),
        )
        return np.array(beat_times), np.array(downbeat_times)

    def _analyze_chunked(
        self, audio_path: str, total_duration: float,
        y: np.ndarray, sr: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Chunked Processing: Teilt Audio in 10-Min-Segmente.

        1. Teile bereits geladenes Audio in Chunks (mit Overlap)
        2. Analysiere jeden Chunk separat
        3. Setze Beat-Timestamps wieder zusammen (dedupliziere Overlap-Bereich)
        """
        import torch
        import tempfile
        import soundfile as sf

        self._ensure_model()

        chunk_samples = int(CHUNK_DURATION_SEC * sr)
        overlap_samples = int(CHUNK_OVERLAP_SEC * sr)
        total_samples = len(y)

        all_beats = []
        all_downbeats = []
        chunk_idx = 0
        pos = 0

        while pos < total_samples:
            chunk_end = min(pos + chunk_samples, total_samples)
            chunk_audio = y[pos:chunk_end]
            chunk_offset_sec = pos / sr

            logger.info(
                "Chunk %d: %.1fs - %.1fs (von %.1fs)",
                chunk_idx, chunk_offset_sec,
                chunk_end / sr, total_duration,
            )

            # Chunk als temporaere WAV speichern (beat_this erwartet Dateipfad)
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix=f"bt_chunk_{chunk_idx}_"
            ) as tmp:
                tmp_path = tmp.name

            # B-142 Fix: tmp_path im Modul-Set tracken, sodass atexit-Cleanup
            # auch bei Force-Quit / SIGTERM mid-`sf.write` greift. Lokales
            # try/finally deckt nur normale Exceptions; ohne Set-Tracking
            # leakte jeder gewaltsam abgebrochene 60-min-Mix ~180MB Tempfiles.
            with _temp_files_lock:
                _temp_files.add(tmp_path)

            try:
                sf.write(tmp_path, chunk_audio, sr)
                with torch.no_grad():
                    beats, downbeats = self._model(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
                with _temp_files_lock:
                    _temp_files.discard(tmp_path)

            # Timestamps zum globalen Offset addieren
            beats = np.array(beats) + chunk_offset_sec
            downbeats = np.array(downbeats) + chunk_offset_sec

            # E-04 Design Tradeoff: Overlap-Deduplizierung per Zeitstempel-Threshold.
            # Die 0.05s Toleranz ist ein Kompromiss: zu klein -> Duplikat-Beats an
            # Chunk-Grenzen, zu gross -> fehlende Beats bei hohem BPM (>300 BPM haette
            # ~0.2s Intervall). Fuer DJ-Musik (60-180 BPM) ist 0.05s sicher.
            # Alternative waere NMS (Non-Maximum Suppression), aber das erfordert
            # Beat-Confidence-Scores die beat_this nicht zurueckgibt.
            if all_beats and len(beats) > 0:
                last_beat = all_beats[-1]
                # Nur Beats behalten die mindestens 0.05s nach dem letzten sind
                mask = beats > (last_beat + 0.05)
                beats = beats[mask]
            if all_downbeats and len(downbeats) > 0:
                last_db = all_downbeats[-1]
                mask = downbeats > (last_db + 0.05)
                downbeats = downbeats[mask]
            # B-152: running-state dedup setzt strikt aufsteigende Beats voraus,
            # was beat_this an Chunk-Boundaries (±10ms tolerance bei high-BPM)
            # nicht garantiert. Final-Pass-Dedup unten haengt diese mit ab.

            all_beats.extend(beats.tolist())
            all_downbeats.extend(downbeats.tolist())

            # Naechster Chunk mit Overlap
            if chunk_end >= total_samples:
                break
            pos = chunk_end - overlap_samples
            chunk_idx += 1

        # B-152: Final-Pass-Dedup mit np.unique(np.round(...)) — robust
        # gegen leicht out-of-order Beats an Chunk-Boundaries.
        # 0.01s Granularitaet (~10ms) reicht fuer DJ-Mixes (60-300 BPM
        # entspricht 0.2-1s Beat-Intervallen) und stabilisiert die
        # Sortierung deterministisch.
        beats_arr = np.unique(np.round(np.array(all_beats), 2)) if all_beats else np.array([])
        downbeats_arr = np.unique(np.round(np.array(all_downbeats), 2)) if all_downbeats else np.array([])
        return beats_arr, downbeats_arr

    def analyze_and_store(self, track_id: int, progress_cb=None) -> dict:
        """Analysiert einen AudioTrack und speichert Beats/Downbeats in der DB.

        Aktualisiert den Beatgrid-Eintrag mit beat_this-Ergebnissen.
        Phase 3: Speichert auch Downbeats und Per-Beat-RMS-Energie.
        """
        # H19-FIX: nullpool_session() statt Session(engine) — verhindert Pool-Contention
        from database import nullpool_session as _np_session
        with _np_session() as session:
            track = session.query(AudioTrack).filter(
                AudioTrack.id == track_id, AudioTrack.deleted_at.is_(None)
            ).first()
            if track is None:
                raise ValueError(f"AudioTrack {track_id} nicht gefunden")
            file_path = track.file_path

        try:
            # E-02 Fix: Lock um analyze() + _last_y Zugriff atomar zu halten,
            # damit kein paralleler Thread zwischen analyze() und dem Lesen
            # von _last_y/_last_sr eine Race Condition verursacht.
            with self._analysis_lock:
                result = self.analyze(file_path, progress_cb=progress_cb)

                # Phase 3: Per-Beat RMS-Energie berechnen (Audio aus analyze() wiederverwenden).
                # A-06 Fix: Thread-safe — lokale Kopie sofort entnehmen und Instanz-Ref loeschen.
                y = self._last_y
                sr = self._last_sr
                self._last_y = None
                self._last_sr = None

            # Phase 3: Per-Beat RMS-Energie berechnen (nach erfolgreichem analyze())
            if y is not None and sr is not None:
                energy_per_beat = self._compute_energy_per_beat(
                    y, sr, result["beats"], result["duration"]
                )
            else:
                energy_per_beat = []
            del y  # free numpy array before DB writes

            # F-004: Stem-weighted energy computation (if stems are available)
            stem_weighted_energy = []
            try:
                from services.pacing_beat_grid import compute_stem_weighted_energy
                stem_energy = compute_stem_weighted_energy(track_id, result["beats"])
                if stem_energy:
                    stem_weighted_energy = stem_energy.weighted
                    logger.info("Stem-weighted energy computed: %d values", len(stem_weighted_energy))
            except (ImportError, ValueError, RuntimeError, OSError) as e:
                logger.info("Stem-weighted energy nicht verfuegbar (Stems nicht vorhanden oder Fehler): %s", e)

            # FIX-1.1b: NullPool-Session fuer DB-Writes — verhindert "database is locked"
            # Der Connection Pool hielt Connections offen die beim sequentiellen
            # Komplett-Analyse-Flow (BPM → Wellenform → Key → ...) zu Locks fuehrten.
            from database import nullpool_session
            import time as _time

            # B-145 Fix: Modell VOR dem DB-Retry-Loop entladen, sonst blockt
            # beat_this 2-3 GB VRAM bis 12s waehrend des Retry-Sleeps. Das
            # OOM-cascadet jeden parallelen Video-Worker (SigLIP/RAFT) auf
            # einer 6GB GTX 1060. Audio + Beat-Daten (y/sr/result) sind hier
            # bereits extrahiert; das Modell wird im Retry nicht mehr gebraucht.
            # finally:self.unload() bleibt als Sicherheitsnetz fuer Exceptions.
            try:
                self.unload()
            except Exception as _unload_err:
                logger.debug("Pre-retry unload skipped: %s", _unload_err)

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with nullpool_session() as session:
                        track = session.query(AudioTrack).filter(
                            AudioTrack.id == track_id, AudioTrack.deleted_at.is_(None)
                        ).first()
                        if track is None:
                            raise ValueError(f"AudioTrack {track_id} nicht gefunden")

                        track.bpm = clamp_bpm(result["bpm"])
                        track.duration = result["duration"]

                        # Beatgrid aktualisieren mit allen Beats + Downbeats + Energie
                        # H7-FIX: Kein json.dumps() — Spalten sind Column(JSON),
                        # SQLAlchemy serialisiert automatisch.
                        beat_positions_data = result["beats"]
                        downbeat_positions_data = result["downbeats"]
                        energy_data = energy_per_beat
                        stem_energy_data = stem_weighted_energy if stem_weighted_energy else None

                        # DB-07 Fix: Expliziter Query-Check gegen Duplikate
                        existing_bg = track.beatgrid or session.query(Beatgrid).filter_by(
                            audio_track_id=track_id
                        ).first()

                        if existing_bg:
                            existing_bg.bpm = clamp_bpm(result["bpm"])
                            existing_bg.beat_positions = beat_positions_data
                            existing_bg.downbeat_positions = downbeat_positions_data
                            existing_bg.energy_per_beat = energy_data
                            existing_bg.stem_weighted_energy = stem_energy_data
                            existing_bg.offset = result["beats"][0] if result["beats"] else 0.0
                        else:
                            bg = Beatgrid(
                                audio_track_id=track_id,
                                bpm=clamp_bpm(result["bpm"]),
                                offset=result["beats"][0] if result["beats"] else 0.0,
                                beat_positions=beat_positions_data,
                                downbeat_positions=downbeat_positions_data,
                                energy_per_beat=energy_data,
                                stem_weighted_energy=stem_energy_data,
                            )
                            session.add(bg)

                        session.commit()
                    break  # Erfolg
                except Exception as e:  # broad catch intentional — catches both SQLAlchemy and DB-lock errors for retry logic
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        logger.warning(
                            "[BeatAnalysis] DB locked bei Beatgrid-Write, Retry %d/%d...",
                            attempt + 1, max_retries,
                        )
                        _time.sleep(2 * (attempt + 1))
                    else:
                        raise

            try:
                from services.pacing_service import invalidate_pacing_caches
                invalidate_pacing_caches()
            except (ImportError, AttributeError, RuntimeError) as e:
                logger.warning("invalidate_pacing_caches() fehlgeschlagen: %s", e)

            # AUD-83: Onset Rhythm Analysis (non-blocking, nach Beat-Analyse)
            # Nutzt bereits geladenes Audio (y/sr wurden vor unload() entnommen).
            # Fehler hier unterbrechen die Beat-Analyse NICHT.
            try:
                from services.onset_rhythm_service import OnsetRhythmService
                onset_svc = OnsetRhythmService()
                onset_svc.analyze_and_store(track_id, progress_cb=None)
            except (ImportError, ValueError, RuntimeError, OSError) as e:
                logger.warning("OnsetRhythmService.analyze_and_store() fehlgeschlagen: %s", e)

        except Exception:  # broad catch intentional — re-raised after memory cleanup (B-004 fix)
            # B-004 Fix: Falls analyze() crasht, _last_y freigeben um Memory Leak zu vermeiden
            self._last_y = None
            self._last_sr = None
            raise
        finally:
            # VRAM freigeben — auch bei Exception (verhindert VRAM-Leak)
            self.unload()

        return result

    @staticmethod
    def _compute_energy_per_beat(
        y: np.ndarray, sr: int, beats: list[float], duration: float
    ) -> list[float]:
        """Berechnet RMS-Energie pro Beat-Intervall (0.0 - 1.0 normalisiert).

        Args:
            y: Audio-Signal (bereits geladen).
            sr: Sample-Rate des Audio-Signals.
            beats: Beat-Zeitpunkte in Sekunden.
            duration: Audio-Dauer in Sekunden.
        """
        if not beats or len(beats) < 2:
            return []

        # Vectorized: Beat-Grenzen als Sample-Indices berechnen
        beat_ends = list(beats[1:]) + [duration]
        starts = np.clip((np.array(beats) * sr).astype(int), 0, len(y))
        ends = np.clip((np.array(beat_ends) * sr).astype(int), 0, len(y))

        energies = np.zeros(len(beats), dtype=np.float64)
        for i in range(len(beats)):
            if ends[i] > starts[i]:
                seg = y[starts[i]:ends[i]]
                energies[i] = np.sqrt(np.mean(seg ** 2))

        # Normalisiere auf 0.0-1.0
        max_e = energies.max() if len(energies) else 1.0
        if max_e > 0:
            energies = energies / max_e
        return [round(float(e), 4) for e in energies]
