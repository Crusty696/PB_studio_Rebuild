"""Video analysis and frame extraction background workers."""

import gc
import logging
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from sqlalchemy.orm import Session as DBSession

from database import engine, VideoClip
from services.video_service import VideoAnalyzer
from .base import CancellableMixin

logger = logging.getLogger(__name__)


class VideoAnalysisWorker(QObject, CancellableMixin):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)
    progress = Signal(int, str)   # Echte Qt-Signale statt print()

    def __init__(self, clip_id: int, title: str):
        super().__init__()
        self.clip_id = clip_id
        self.title = title
        self.analyzer = VideoAnalyzer()

    def run(self):
        _ok = False
        self.started.emit(self.clip_id, self.title)
        self.progress.emit(0, f"Video-Analyse: {self.title}")
        try:
            self.progress.emit(10, f"ffprobe + Proxy fuer {self.title}...")
            result = self.analyzer.analyze_and_store(self.clip_id)
            self.progress.emit(100, f"Analyse fertig: {self.title}")
            self.finished.emit(self.clip_id, result)
            _ok = True
        except Exception as e:
            logging.error("VideoAnalysisWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, str(e))
        finally:
            # VRAM-Schutz: GPU-Speicher freigeben
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            gc.collect()
            if not _ok and not self._errored:
                self.finished.emit(self.clip_id, {})


class VideoBatchAnalysisWorker(QObject, CancellableMixin):
    """Analysiert eine Liste von Videos SEQUENTIELL in einem einzigen Thread.

    Verhindert OpenGL/QPainter-Crashes die bei parallelen Workern auftreten.
    Signals melden Fortschritt pro Video an den Main-Thread.
    """
    item_done = Signal(int, str)    # clip_id, info_str
    item_error = Signal(int, str)   # clip_id, error_msg
    error = Signal(str)             # GlobalTaskManager braucht dieses Signal
    finished = Signal(int, int)     # total_done, total_errors
    progress = Signal(int, str)     # percent, message

    def __init__(self, batch: list):
        """Args: batch = Liste von (clip_id, title) Tupeln."""
        super().__init__()
        self._batch = batch

    def run(self):
        analyzer = VideoAnalyzer()
        total = len(self._batch)
        done = 0
        errors = 0

        for idx, (clip_id, title) in enumerate(self._batch, start=1):
            if self.should_stop():
                break
            self.progress.emit(
                int((idx - 1) / total * 100),
                f"[{idx}/{total}] {title}..."
            )
            try:
                result = analyzer.analyze_and_store(clip_id)
                done += 1
                if result:
                    info = (f"{result.get('width', '?')}x{result.get('height', '?')} "
                            f"{result.get('fps', '?')}fps")
                else:
                    info = "OK"
                self.item_done.emit(clip_id, info)
            except Exception as e:
                errors += 1
                logger.error("BatchAnalysis[%d] '%s' failed: %s\n%s",
                             clip_id, title, e, traceback.format_exc())
                self.item_error.emit(clip_id, str(e))
            finally:
                gc.collect()

        self.progress.emit(100, f"Batch fertig: {done}/{total}")
        self.finished.emit(done, errors)


class VideoAnalysisPipelineWorker(QObject, CancellableMixin):
    """Führt die 3-Schritt Video-Analyse-Pipeline im Hintergrund aus.

    Unterstützt Batch-Verarbeitung: Nimmt eine Liste von (clip_id, video_path)
    und arbeitet diese STRIKT SEQUENZIELL ab (6GB VRAM Limit).
    """
    finished = Signal(int, dict)   # last_clip_id, batch_result_dict
    error = Signal(int, str)       # clip_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, clip_id: int = 0, video_path: str = "",
                 batch: list | None = None):
        """Args:
            clip_id / video_path: Einzelnes Video (Rückwärtskompatibel).
            batch: Liste von (clip_id, title) Tupeln für Batch-Modus.
                   file_path wird in run() aus der DB geladen (Worker-Thread).
        """
        super().__init__()
        if batch:
            self._batch = batch
        else:
            self._batch = [(clip_id, video_path, "")]

    def run(self):
        _ok = False
        # file_paths aus DB laden, falls batch nur (clip_id, title) Tupel enthält
        # (läuft im Worker-Thread, nicht im Main-Thread)
        if self._batch and len(self._batch[0]) == 2:
            resolved_batch = []
            with DBSession(engine) as session:
                for clip_id, title in self._batch:
                    clip = session.get(VideoClip, clip_id)
                    if clip:
                        # Proxy-First: KI-Analyse nutzt Proxy wenn verfügbar, sonst Original
                        if clip.proxy_path and Path(clip.proxy_path).exists():
                            analysis_path = clip.proxy_path
                            logger.info("[Proxy-First] Clip %d: Nutze Proxy → %s", clip_id, analysis_path)
                        else:
                            analysis_path = clip.file_path
                            logger.info("[Proxy-First] Clip %d: Kein Proxy → nutze Original", clip_id)
                        resolved_batch.append((clip_id, analysis_path, title))
                    else:
                        logger.warning("VideoClip %d nicht gefunden, überspringe.", clip_id)
            self._batch = resolved_batch

        total_videos = len(self._batch)
        last_clip_id = self._batch[-1][0] if self._batch else 0
        if not self._batch:
            self.error.emit(0, "Keine gültigen VideoClips zum Verarbeiten gefunden.")
            self.finished.emit(0, {})
            return
        try:
            from services.video_analysis_service import run_full_pipeline

            total_scenes = 0
            total_embeddings = 0
            idx = 0

            for idx, (clip_id, video_path, title) in enumerate(self._batch, start=1):
                if self.should_stop():
                    break

                label = title or Path(video_path).stem
                batch_base_pct = int((idx - 1) / total_videos * 100)
                batch_range = int(100 / total_videos)
                self.progress.emit(
                    batch_base_pct,
                    f"Video {idx}/{total_videos}: '{label}' wird analysiert..."
                )

                try:
                    result = run_full_pipeline(
                        video_path=video_path,
                        video_clip_id=clip_id,
                        progress_cb=lambda pct, msg, _base=batch_base_pct, _range=batch_range, _i=idx, _tv=total_videos: (
                            self.progress.emit(
                                min(99, _base + int(pct / 100 * _range)),
                                f"[{_i}/{_tv}] {msg}"
                            )
                        ),
                        should_stop=self.should_stop,
                    )
                    total_scenes += len(result.scenes)
                    total_embeddings += result.embeddings_stored

                except Exception as e:
                    logging.error("VideoAnalysisPipelineWorker[%s] video %d/%d '%s' crashed: %s\n%s",
                                  clip_id, idx, total_videos, label, e, traceback.format_exc())
                    self._errored = True
                    self.error.emit(clip_id, f"Video {idx}/{total_videos} '{label}': {e}")
                    # finished MUSS emittiert werden damit thread.quit() aufgerufen wird
                    self.finished.emit(last_clip_id, {})
                    return
                finally:
                    # VRAM-Schutz: GPU-Speicher nach JEDEM Video freigeben (6GB Limit)
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                            logging.info("VRAM-Cleanup nach Video %d/%d: torch.cuda.empty_cache()", idx, total_videos)
                    except ImportError:
                        pass
                    gc.collect()

            self.finished.emit(last_clip_id, {
                "scenes": total_scenes,
                "embeddings": total_embeddings,
                "videos_processed": idx if self.should_stop() else total_videos,
            })
            _ok = True
        except Exception as e:
            logging.error("VideoAnalysisPipelineWorker crashed (outer): %s\n%s",
                          e, traceback.format_exc())
            self._errored = True
            self.error.emit(last_clip_id, str(e))
        finally:
            # finished MUSS immer emittiert werden damit thread.quit() greift
            if not _ok:
                self.finished.emit(last_clip_id, {})


class FrameExtractWorker(QObject, CancellableMixin):
    frame_ready = Signal(bytes, int, int)
    finished = Signal()   # Required by GlobalTaskManager contract (thread.quit)
    error = Signal(str)

    def __init__(self, file_path: str, time_sec: float, width: int = 320,
                 height: int = 180, vf_extra: str = ""):
        super().__init__()
        self.file_path = file_path
        self.time_sec = time_sec
        self.width = width
        self.height = height
        self.vf_extra = vf_extra

    def run(self):
        try:
            vf = f"scale={self.width}:{self.height}"
            if self.vf_extra:
                vf = f"{self.vf_extra},{vf}"
            cmd = [
                "ffmpeg", "-ss", str(self.time_sec), "-i", self.file_path,
                "-frames:v", "1", "-vf", vf,
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-v", "quiet", "-y", "pipe:1"
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            expected = self.width * self.height * 3
            if result.returncode == 0 and len(result.stdout) == expected:
                self.frame_ready.emit(result.stdout, self.width, self.height)
            else:
                stderr_hint = result.stderr[:200].decode(errors="replace") if result.stderr else ""
                self.error.emit(f"Frame @ {self.time_sec:.1f}s nicht verfuegbar: {stderr_hint}")
        except Exception as e:
            logging.error("FrameExtractWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            # Always emit finished so TaskEngine can quit the thread cleanly.
            self.finished.emit()
