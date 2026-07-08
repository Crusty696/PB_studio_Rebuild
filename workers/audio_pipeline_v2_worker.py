"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

OTK-018: App-Worker, der die strict-sequential Audio-V2-Pipeline (Orchestrator)
fuer einen Track faehrt. Bindet die portierte Pipeline (Bucket A+B + Stem-Routing
+ Resume-Rehydration) in die bestehende Worker-/TaskManager-Infrastruktur ein,
ohne den bestehenden Einzel-Service-Analysepfad zu veraendern (opt-in).

Signal-Kontrakt identisch zu BaseAnalysisWorker (audio_track_id-basiert), damit
worker_dispatcher._start_worker_thread den Worker unveraendert betreiben kann.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from .base import CancellableMixin

logger = logging.getLogger(__name__)


_STAGE_TO_STEP = {
    "stem_gen": "stem_separation",
    "beat_grid": "bpm_detection",
    "key": "key_detection",
    "structure": "structure_detection",
    "lufs": "lufs_analysis",
    "spectral": "spectral_analysis",
    "classify": "mood_genre_classify",
    "waveform": "waveform_analysis",
}


class AudioPipelineV2Worker(QObject, CancellableMixin):
    """Faehrt die Audio-V2-Pipeline (8 Stages, strict-sequential) auf einem Track.

    Stages: stem_gen (Demucs) -> beat_grid -> onset -> key -> structure -> lufs
    -> spectral -> av_pacing. Stem-geroutet (Onset=drums, Key=bass+other,
    Structure=stem-bass), Resume via Checkpoint + Rehydration.
    """

    finished = Signal(int, dict)   # audio_track_id, results
    error = Signal(int, str)       # audio_track_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, audio_track_id: int, file_path: str):
        super().__init__()
        CancellableMixin.__init__(self)
        self.audio_track_id = audio_track_id
        self.file_path = file_path
        self._current_stage = None

    def run(self) -> None:
        self._errored = False
        try:
            if self.should_stop():
                return
            from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
            from services.audio_pipeline.context import PipelineContext
            from services.audio_pipeline.stages import build_default_stages
            from services.analysis_status_service import mark_started, mark_done

            stages = build_default_stages()
            total = max(1, len(stages))
            pipeline = AudioAnalysisPipeline(stages)

            done = {"n": 0}

            def _on_started(name: str) -> None:
                self._current_stage = name
                pct = int(done["n"] / total * 100)
                self.progress.emit(pct, f"Audio-V2: {name}...")
                step_key = _STAGE_TO_STEP.get(name)
                if step_key:
                    mark_started("audio", self.audio_track_id, step_key)

            def _on_done(name: str, _payload) -> None:
                done["n"] += 1
                pct = int(done["n"] / total * 100)
                self.progress.emit(pct, f"Audio-V2: {name} fertig")
                
                step_key = _STAGE_TO_STEP.get(name)
                if step_key:
                    val_summary = {}
                    if isinstance(_payload, dict):
                        if name == "beat_grid":
                            val_summary["bpm"] = _payload.get("bpm")
                        elif name == "key":
                            val_summary["key"] = _payload.get("key")
                            val_summary["confidence"] = _payload.get("confidence")
                        elif name == "lufs":
                            val_summary["lufs"] = _payload.get("integrated_lufs")
                        elif name == "classify":
                            val_summary["mood"] = _payload.get("mood")
                            val_summary["genre"] = _payload.get("genre")
                            val_summary["sub_genre"] = _payload.get("sub_genre")
                            val_summary["is_dj_mix"] = _payload.get("is_dj_mix")
                        elif name == "waveform":
                            val_summary["num_samples"] = _payload.get("num_samples")
                    mark_done("audio", self.audio_track_id, step_key, val_summary)

            def _on_sub_progress(stage_pct: int, message: str) -> None:
                stage_idx = done["n"]
                pct = int((stage_idx + (stage_pct / 100.0)) / total * 100)
                self.progress.emit(pct, f"Audio-V2: {message}")

            ctx = PipelineContext(
                track_id=self.audio_track_id,
                original_path=self.file_path,
                should_stop=self.should_stop,
                on_progress=_on_sub_progress,
            )

            pipeline.stage_started.connect(_on_started)
            pipeline.stage_done.connect(_on_done)

            # Synchron im Worker-Thread (fail-fast: Stage-Exception -> raise).
            pipeline._run_stages(ctx)

            self.progress.emit(100, "Audio-V2: fertig")
            self.finished.emit(self.audio_track_id, dict(ctx.results))
        except Exception as e:  # noqa: BLE001
            self._errored = True
            logger.error("AudioPipelineV2Worker fehlgeschlagen (track=%s): %s",
                         self.audio_track_id, e, exc_info=True)
            if self._current_stage:
                step_key = _STAGE_TO_STEP.get(self._current_stage)
                if step_key:
                    from services.analysis_status_service import mark_error
                    mark_error("audio", self.audio_track_id, step_key, str(e))
            self.error.emit(self.audio_track_id, str(e))
