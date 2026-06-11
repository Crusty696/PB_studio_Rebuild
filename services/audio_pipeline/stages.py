"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T1.3 + T2.1/T2.2: Pipeline-Stages (Stem-Generierung + Beat-Grid + 6 DSP).

Service-Mapping siehe A-8 + RED-Pre-Check-Updates aus T1.0-Migration:
- StemGenStage          StemSeparator.separate_to (T2.1)
- BeatGridStage         BeatAnalysisService.analyze_and_store(trigger_onset=False)
- OnsetStage            OnsetRhythmService.analyze_and_store(track_id)
                        (drums-Pfad aus DB-Field stem_drums_path; T2.1 schreibt)
- KeyStage              KeyDetectionService.detect_key(original, bass_path, other_path)
- StructureStage        StructureDetectionService.detect(original, stem_paths=dict)
- LUFSStage             LUFSService.analyze(original)
- SpectralStage         SpectralAnalysisService.analyze(original)
- AVPacingStage         AVPacingService.analyze(original)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.audio_pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


# Lazy imports zum Stage-Modul-Load-Time vermeiden.
# T2.1: GPU_EXECUTION_LOCK + torch + nullpool_session werden zur Test-Zeit mockbar
# wenn als Modul-Level-Symbol importiert.
try:
    from services.model_manager import GPU_EXECUTION_LOCK
except ImportError:
    import threading as _t
    GPU_EXECUTION_LOCK = _t.RLock()

try:
    from database import nullpool_session
except ImportError:
    nullpool_session = None

try:
    import torch
except ImportError:
    torch = None


class StageInputMissingError(RuntimeError):
    """A-1 / fixt R-01: Stage benoetigt Stem das fehlt -> Pipeline-Stop."""


class Stage:
    """Abstract base. Subclass muss .name setzen und .run(context) implementieren."""
    name: str = "abstract"

    def run(self, context: PipelineContext) -> None:
        raise NotImplementedError("Stage.run must be implemented by subclass")

    def rehydrate(self, context: PipelineContext) -> None:
        """Resume-Hook: wird vom Orchestrator aufgerufen, wenn die Stage per
        Checkpoint uebersprungen wird (bereits erfolgreich gelaufen). Default no-op.

        OTK-018: StemGenStage ueberschreibt dies, um ``context.stem_paths`` aus
        Cache/DB zu rehydrieren — sonst stehen nachfolgende stem-geroutete Stages
        (Onset/Key/Structure) nach einem Resume ohne Stem-Pfade da und brechen ab.
        """
        return None


def _require_stems(context: PipelineContext, names: tuple[str, ...], stage_name: str) -> None:
    missing = [n for n in names if n not in context.stem_paths]
    if missing:
        raise StageInputMissingError(
            f"{stage_name}: erforderliche Stems fehlen in Context: {missing}"
        )


_DEMUCS_VERSION = "htdemucs_ft"
_TARGET_WAV_SUBTYPE = "PCM_24"


class StemGenStage(Stage):
    """T2.1 + T3.2: Demucs-First-Stage mit GPU-Lock + PCM_24 + track-id-Layout
    + DB-Write + Reuse via Hash-Cache.

    - T3.2 Pre-Check: wenn Cache-Meta + 4 WAVs + all-hash-match + Subtype OK
      -> skip Demucs, set context.stem_paths aus Existing.
    - Sonst: Acquires GPU_EXECUTION_LOCK, ruft StemSeparator.separate_to,
      schreibt PCM_24 nach storage/stems/<track_id>/, setzt DB stem_*_path,
      schreibt Cache-Meta mit Stem-Hashes.
    """
    name = "stem_gen"

    _stems_root: Path | None = None  # test-override

    def __init__(self, separator_cls: Any = None):
        self._separator_cls = separator_cls

    def _resolve_stems_dir(self, track_id: int) -> Path:
        root = self._stems_root if self._stems_root is not None else Path("storage") / "stems"
        return root / str(track_id)

    def _try_reuse(self, context: PipelineContext) -> dict[str, str] | None:
        """T3.2 Pre-Check. Returns Stem-Pfad-Dict bei Reuse, sonst None."""
        from services.audio_pipeline import stem_cache

        meta = stem_cache.load_cache_meta(context.track_id)
        if not meta:
            return None
        # Subtype-Check (Q-C Migration)
        if meta.get("wav_subtype") != _TARGET_WAV_SUBTYPE:
            return None
        # Demucs-Version-Check
        if meta.get("demucs_version") != _DEMUCS_VERSION:
            return None
        # Original-Hash-Check
        try:
            orig_hash = stem_cache.compute_audio_hash(context.original_path)
        except OSError:
            return None
        if meta.get("original_hash") != orig_hash:
            return None
        # 4 WAVs existieren + Hash-Match (fixt R-07 partial-Crash)
        stems_dir = self._resolve_stems_dir(context.track_id)
        cached_stem_hashes = meta.get("stem_hashes", {})
        result_paths: dict[str, str] = {}
        for name in ("drums", "bass", "vocals", "other"):
            p = stems_dir / f"{name}.wav"
            if not p.exists():
                return None
            cached = cached_stem_hashes.get(name)
            actual = stem_cache.compute_stem_wav_hash(str(p))
            if cached != actual:
                return None
            result_paths[name] = str(p.resolve())
        return result_paths

    def _persist_cache_meta(self, context: PipelineContext, result: dict[str, str]) -> None:
        from services.audio_pipeline import stem_cache
        try:
            orig_hash = stem_cache.compute_audio_hash(context.original_path)
            stem_hashes = {n: stem_cache.compute_stem_wav_hash(p) for n, p in result.items()}
        except OSError:
            return
        meta = {
            "version": 1,
            "original_hash": orig_hash,
            "stem_hashes": stem_hashes,
            "demucs_version": _DEMUCS_VERSION,
            "wav_subtype": _TARGET_WAV_SUBTYPE,
            "stages_done": ["stem_gen"],
        }
        stem_cache.save_cache_meta(context.track_id, meta)

    def run(self, context: PipelineContext) -> None:
        # T3.2 Reuse-Check
        reuse = self._try_reuse(context)
        if reuse is not None:
            context.stem_paths.update(reuse)
            context.set_result(self.name, {"stem_paths": dict(reuse), "reused": True})
            return

        if self._separator_cls is None:
            from services.ai_audio_service import StemSeparator
            self._separator_cls = StemSeparator

        out_dir = str(self._resolve_stems_dir(context.track_id))

        # T2.1: GPU-Lock + Demucs + VRAM-Cleanup
        with GPU_EXECUTION_LOCK:
            try:
                separator = self._separator_cls()
                result = separator.separate_to(
                    file_path=context.original_path,
                    out_dir=out_dir,
                    subtype=_TARGET_WAV_SUBTYPE,
                )
            finally:
                if torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()

        # Context + DB-Write nur bei Erfolg.
        context.stem_paths.update(result)
        context.set_result(self.name, {"stem_paths": dict(result), "reused": False})

        # T2.1 / R-09 Vorbereitung: Stem-Pfade in DB schreiben
        self._persist_stem_paths_to_db(context.track_id, result)

        # T3.2: Cache-Meta + Stem-Hashes persistieren
        self._persist_cache_meta(context, result)

    @staticmethod
    def _persist_stem_paths_to_db(track_id: int, stem_paths: dict[str, str]) -> None:
        if nullpool_session is None:
            return  # DB nicht verfuegbar (z.B. headless-Test)
        try:
            from database import AudioTrack
        except ImportError:
            return
        with nullpool_session() as sess:
            track = sess.query(AudioTrack).filter(AudioTrack.id == track_id).first()
            if track is None:
                return
            if "drums" in stem_paths:
                track.stem_drums_path = stem_paths["drums"]
            if "bass" in stem_paths:
                track.stem_bass_path = stem_paths["bass"]
            if "vocals" in stem_paths:
                track.stem_vocals_path = stem_paths["vocals"]
            if "other" in stem_paths:
                track.stem_other_path = stem_paths["other"]
            sess.commit()


    def rehydrate(self, context: PipelineContext) -> None:
        """Resume: stem_gen war schon erfolgreich -> Stem-Pfade in den frischen
        Context zurueckholen, damit Onset/Key/Structure nicht an fehlenden Stems
        scheitern. Erst Cache-Reuse (Hash-validiert), sonst DB-Fallback."""
        reuse = self._try_reuse(context)
        if reuse is not None:
            context.stem_paths.update(reuse)
            return
        # DB-Fallback: persistierte stem_*_path-Felder.
        if nullpool_session is None:
            return
        try:
            from database import AudioTrack
        except ImportError:
            return
        try:
            with nullpool_session() as sess:
                track = sess.query(AudioTrack).filter(AudioTrack.id == context.track_id).first()
                if track is None:
                    return
                mapping = {
                    "drums": getattr(track, "stem_drums_path", None),
                    "bass": getattr(track, "stem_bass_path", None),
                    "vocals": getattr(track, "stem_vocals_path", None),
                    "other": getattr(track, "stem_other_path", None),
                }
                for name, path in mapping.items():
                    if path:
                        context.stem_paths[name] = path
        except Exception as e:  # noqa: BLE001
            logger.warning("StemGenStage.rehydrate DB-Fallback fehlgeschlagen: %s", e)


class BeatGridStage(Stage):
    """A-7 + T2.2: ruft BeatAnalysisService.analyze_and_store(trigger_onset=False).

    GPU-Lock pflichtig (beat_this nutzt CUDA). Sequenz garantiert NACH StemGen-Release
    (Orchestrator-Reihenfolge); kein Race mit Demucs.
    Onset wird durch OnsetStage separat ausgefuehrt (drums-Stem-Routing).
    """
    name = "beat_grid"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        if self._service_cls is None:
            from services.beat_analysis_service import BeatAnalysisService
            self._service_cls = BeatAnalysisService

        with GPU_EXECUTION_LOCK:
            try:
                svc = self._service_cls()
                result = svc.analyze_and_store(context.track_id, trigger_onset=False)
            finally:
                if torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()

        context.set_result(self.name, {"bpm": (result or {}).get("bpm")})


class OnsetStage(Stage):
    """C-01: Service zieht drums-Pfad aus DB. Pre-Condition: T2.1 schrieb stem_drums_path."""
    name = "onset"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _require_stems(context, ("drums",), self.name)
        if self._service_cls is None:
            from services.onset_rhythm_service import OnsetRhythmService
            self._service_cls = OnsetRhythmService
        svc = self._service_cls()
        result = svc.analyze_and_store(context.track_id)
        context.set_result(self.name, {"ok": result is not None})


class KeyStage(Stage):
    """C-02: detect_key(original, bass_path=..., other_path=...). Service mischt intern."""
    name = "key"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _require_stems(context, ("bass", "other"), self.name)
        if self._service_cls is None:
            from services.key_detection_service import KeyDetectionService
            self._service_cls = KeyDetectionService
        svc = self._service_cls()
        result = svc.detect_key(
            context.original_path,
            bass_path=context.stem_paths["bass"],
            other_path=context.stem_paths["other"],
        )
        # result = KeyResult dataclass
        context.set_result(self.name, {
            "key": getattr(result, "key", None),
            "camelot": getattr(result, "camelot", None),
            "confidence": getattr(result, "confidence", None),
        })


class StructureStage(Stage):
    """C-03 fuer Structure: dict-arg ohne 'other'-Stem."""
    name = "structure"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _require_stems(context, ("bass", "drums", "vocals"), self.name)
        if self._service_cls is None:
            from services.structure_detection_service import StructureDetectionService
            self._service_cls = StructureDetectionService
        svc = self._service_cls()
        filtered = {k: context.stem_paths[k] for k in ("bass", "drums", "vocals")}
        bpm = context.results.get("beat_grid", {}).get("bpm")
        result = svc.detect(context.original_path, bpm=bpm, stem_paths=filtered)
        context.set_result(self.name, {"segments_count": len(getattr(result, "segments", []) or [])})


class LUFSStage(Stage):
    name = "lufs"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        if self._service_cls is None:
            from services.lufs_service import LUFSService
            self._service_cls = LUFSService
        svc = self._service_cls()
        result = svc.analyze(context.original_path)
        context.set_result(self.name, {
            "integrated_lufs": getattr(result, "integrated_lufs", None),
            "true_peak_db": getattr(result, "true_peak_db", None),
        })


class SpectralStage(Stage):
    name = "spectral"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        if self._service_cls is None:
            from services.spectral_analysis_service import SpectralAnalysisService
            self._service_cls = SpectralAnalysisService
        svc = self._service_cls()
        bpm = context.results.get("beat_grid", {}).get("bpm")
        result = svc.analyze(context.original_path, bpm=bpm)
        context.set_result(self.name, {
            "centroid_mean": getattr(result, "centroid_mean", None),
        })


class AVPacingStage(Stage):
    name = "av_pacing"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        if self._service_cls is None:
            from services.av_pacing_service import AVPacingService
            self._service_cls = AVPacingService
        svc = self._service_cls()
        result = svc.analyze(context.original_path)
        context.set_result(self.name, {
            "samples": len(getattr(result, "times_sec", []) or []),
        })


# Plan-Reihenfolge fuer Default-Pipeline.
DEFAULT_STAGE_ORDER: tuple[type, ...] = (
    StemGenStage,
    BeatGridStage,
    OnsetStage,
    KeyStage,
    StructureStage,
    LUFSStage,
    SpectralStage,
    AVPacingStage,
)


def build_default_stages() -> list[Stage]:
    """Default-Pipeline-Stage-Liste in Plan-Reihenfolge."""
    return [cls() for cls in DEFAULT_STAGE_ORDER]
