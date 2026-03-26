"""Auto-edit and semantic search background workers."""

import logging
import traceback

from PySide6.QtCore import QObject, Signal

from services.pacing_service import AdvancedPacingSettings, auto_edit_phase3
from .base import CancellableMixin

logger = logging.getLogger(__name__)


class AutoEditWorker(QObject, CancellableMixin):
    """Phase 3: Auto-Edit Worker mit AdvancedPacingSettings + OTIO."""
    finished = Signal(list, list)   # (segments_as_dicts, cut_points_as_dicts)
    error = Signal(str)

    def __init__(self, audio_id: int, video_ids: list[int],
                 settings: AdvancedPacingSettings):
        super().__init__()
        self.audio_id = audio_id
        self.video_ids = video_ids
        self.settings = settings

    def run(self):
        _ok = False
        try:
            segments, cut_points = auto_edit_phase3(
                self.audio_id, self.video_ids, self.settings,
            )
            # Serialize for signal transport
            seg_dicts = [
                {
                    "video_id": s.video_id, "video_path": s.video_path,
                    "start": s.start, "end": s.end,
                    "source_start": s.source_start, "source_end": s.source_end,
                    "is_anchor": s.is_anchor, "scene_id": s.scene_id,
                    "crossfade": s.crossfade_duration, "section_type": s.section_type,
                }
                for s in segments
            ]
            cp_dicts = [
                {"time": c.time, "source": c.source, "strength": c.strength}
                for c in cut_points
            ]
            self.finished.emit(seg_dicts, cp_dicts)
            _ok = True
        except Exception as e:
            logging.error("AutoEditWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit([], [])


class SemanticSearchWorker(QObject, CancellableMixin):
    """SigLIP Text-zu-Video Suche im Hintergrund."""
    finished = Signal(list)   # list of result dicts
    error = Signal(str)

    def __init__(self, query: str, top_k: int = 20):
        super().__init__()
        self.query = query
        self.top_k = top_k

    def run(self):
        _ok = False
        try:
            from services.video_analysis_service import search_videos_by_text
            results = search_videos_by_text(self.query, top_k=self.top_k)
            self.finished.emit(results)
            _ok = True
        except Exception as e:
            logging.error("SemanticSearchWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit([])
