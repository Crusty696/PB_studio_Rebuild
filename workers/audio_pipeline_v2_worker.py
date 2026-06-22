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

    def run(self) -> None:
        self._errored = False
        try:
            if self.should_stop():
                return
            from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
            from services.audio_pipeline.context import PipelineContext
            from services.audio_pipeline.stages import build_default_stages

            stages = build_default_stages()
            total = max(1, len(stages))
            pipeline = AudioAnalysisPipeline(stages)
            ctx = PipelineContext(
                track_id=self.audio_track_id,
                original_path=self.file_path,
                should_stop=self.should_stop,
            )

            done = {"n": 0}

            def _on_started(name: str) -> None:
                pct = int(done["n"] / total * 100)
                self.progress.emit(pct, f"Audio-V2: {name}...")

            def _on_done(name: str, _payload) -> None:
                done["n"] += 1
                pct = int(done["n"] / total * 100)
                self.progress.emit(pct, f"Audio-V2: {name} fertig")

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
            self.error.emit(self.audio_track_id, str(e))
