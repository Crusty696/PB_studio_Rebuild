"""Video analysis and frame extraction background workers."""

import logging
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from sqlalchemy.orm import Session as DBSession

from database import engine, VideoClip
from services.timeout_constants import FFMPEG_THUMBNAIL_TIMEOUT_SEC
from services.video_service import VideoAnalyzer
from .base import CancellableMixin, format_user_error

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
            result = self.analyzer.analyze_and_store(
                self.clip_id,
                progress_cb=lambda pct, msg: self.progress.emit(pct, f"{self.title}: {msg}"),
            )
            self.progress.emit(100, f"Analyse fertig: {self.title}")
            self.finished.emit(self.clip_id, result)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("VideoAnalysisWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, format_user_error(e))
        finally:
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
        done = 0
        errors = 0
        _ok = False
        try:
            analyzer = VideoAnalyzer()
            total = len(self._batch)

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
                except (ValueError, RuntimeError, OSError) as e:
                    errors += 1
                    logger.error("BatchAnalysis[%d] '%s' failed: %s\n%s",
                                 clip_id, title, e, traceback.format_exc())
                    self.item_error.emit(clip_id, format_user_error(e))

            self.progress.emit(100, f"Batch fertig: {done}/{total}")
            self.finished.emit(done, errors)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logger.error("VideoBatchAnalysisWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
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
            # NullPool: Verhindert QueuePool-Exhaustion bei vielen parallelen Reads
            from database import nullpool_session
            with nullpool_session() as session:
                for clip_id, title in self._batch:
                    clip = session.get(VideoClip, clip_id)
                    if clip:
                        # Proxy-First: KI-Analyse nutzt Proxy wenn verfügbar, sonst Original
                        # B-012 Fix: TOCTOU — Proxy-Existenz wird spater geprueft bevor verwendet
                        if clip.proxy_path:
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

        # ── Progress-Throttle: max 1 Signal pro 500ms um Event-Loop-Flooding zu verhindern ──
        _last_progress_time = [0.0]  # mutable für closure

        def _throttled_progress(pct: int, msg: str):
            now = time.monotonic()
            # Immer senden bei: 0%, 100%, oder wenn 500ms vergangen
            if pct == 0 or pct >= 99 or (now - _last_progress_time[0]) >= 0.5:
                self.progress.emit(pct, msg)
                _last_progress_time[0] = now

        # Phase-basierter Batch: RAFT einmal fuer Phase A, SigLIP einmal fuer Phase B.
        # Spart (N-1)×4.5s Model-Swap-Overhead gegenueber Per-Video-Load.
        try:
            from services.video_analysis_service import run_motion_phase, run_embedding_phase
            from services.model_manager import ModelManager, GPU_LOAD_LOCK, GPU_EXECUTION_LOCK

            total_scenes = 0
            total_embeddings = 0
            processed = 0
            mm = ModelManager()
            # Map: clip_id -> (video_path, original_path, scenes) aus Phase A
            phase_a_results: dict[int, tuple[str, str, list]] = {}

            def _resolve_fallback_path(clip_id: int) -> str | None:
                """TOCTOU-Recovery: Proxy geloescht → Original aus DB."""
                from database import nullpool_session as _ns
                with _ns() as _s:
                    _c = _s.get(VideoClip, clip_id)
                    return _c.file_path if _c and _c.file_path else None

            with GPU_EXECUTION_LOCK:
                # ── Phase A: Scene-Detect + Motion (RAFT shared) ──
                with GPU_LOAD_LOCK:
                    mm.load_raft()

                for idx, (clip_id, video_path, title) in enumerate(self._batch, start=1):
                    if self.should_stop():
                        break
                    label = title or Path(video_path).stem
                    # Phase A belegt 0-40% der Batch-Progress
                    base_pct = int((idx - 1) / total_videos * 40)
                    _throttled_progress(base_pct,
                                        f"[A {idx}/{total_videos}] '{label}' Szenen+Motion...")
                    current_path = video_path
                    try:
                        try:
                            scenes, original_path = run_motion_phase(
                                video_path=current_path,
                                video_clip_id=clip_id,
                                should_stop=self.should_stop,
                            )
                        except FileNotFoundError as e:
                            logger.warning("[Proxy-First] Clip %d: Datei geloescht (TOCTOU) — Fallback: %s", clip_id, e)
                            fallback_path = _resolve_fallback_path(clip_id)
                            if not fallback_path:
                                raise RuntimeError(f"VideoClip {clip_id}: Original-Pfad nicht verfuegbar") from e
                            current_path = fallback_path
                            scenes, original_path = run_motion_phase(
                                video_path=current_path,
                                video_clip_id=clip_id,
                                should_stop=self.should_stop,
                            )
                        phase_a_results[clip_id] = (current_path, original_path, scenes)
                        total_scenes += len(scenes)
                    except (RuntimeError, OSError, ValueError) as e:
                        logging.error("VideoAnalysisPipelineWorker[%s] Phase A %d/%d '%s' crashed: %s\n%s",
                                      clip_id, idx, total_videos, label, e, traceback.format_exc())
                        self.progress.emit(base_pct, f"[A {idx}/{total_videos}] FEHLER: {e}")
                        continue
                    finally:
                        if idx % 25 == 0:
                            from services.task_manager import GlobalTaskManager
                            GlobalTaskManager.instance().request_gc_signal.emit()

                # ── Phase B: Keyframes + SigLIP + Vector-DB + Captions + SQLite (SigLIP shared) ──
                # H17: load_siglip() unload()t RAFT — OK, wir brauchen RAFT nicht mehr.
                if phase_a_results and not self.should_stop():
                    with GPU_LOAD_LOCK:
                        mm.load_siglip()

                    for idx, (clip_id, (current_path, original_path, scenes)) in enumerate(
                        phase_a_results.items(), start=1
                    ):
                        if self.should_stop():
                            break
                        label = Path(current_path).stem
                        # Phase B belegt 40-99% der Batch-Progress
                        base_pct = 40 + int((idx - 1) / total_videos * 59)
                        range_pct = int(59 / total_videos)
                        _throttled_progress(base_pct,
                                            f"[B {idx}/{total_videos}] '{label}' Embeddings+Captions...")
                        try:
                            result = run_embedding_phase(
                                video_path=current_path,
                                video_clip_id=clip_id,
                                scenes=scenes,
                                original_video_path=original_path,
                                progress_cb=lambda pct, msg, _b=base_pct, _r=range_pct, _i=idx, _tv=total_videos: (
                                    _throttled_progress(
                                        min(99, _b + int(pct / 100 * _r)),
                                        f"[B {_i}/{_tv}] {msg}"
                                    )
                                ),
                                should_stop=self.should_stop,
                                is_batch=True,
                            )
                            total_embeddings += result.embeddings_stored
                            
                            # VAD-59: Structure Enrichment (Role, Mood, Style, Graph)
                            _throttled_progress(base_pct + int(0.9 * range_pct),
                                                f"[B {idx}/{total_videos}] '{label}' Enrichment...")
                            from workers.enrichment import StructureEnrichmentWorker
                            enricher = StructureEnrichmentWorker(clip_id)
                            enricher.run()
                            
                            processed += 1
                        except (RuntimeError, OSError, ValueError) as e:
                            logging.error("VideoAnalysisPipelineWorker[%s] Phase B %d/%d '%s' crashed: %s\n%s",
                                          clip_id, idx, total_videos, label, e, traceback.format_exc())
                            self.progress.emit(base_pct, f"[B {idx}/{total_videos}] FEHLER: {e}")
                            continue
                        finally:
                            if idx % 25 == 0:
                                from services.task_manager import GlobalTaskManager
                                GlobalTaskManager.instance().request_gc_signal.emit()

            self.finished.emit(last_clip_id, {
                "scenes": total_scenes,
                "embeddings": total_embeddings,
                "videos_processed": processed,
            })
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("VideoAnalysisPipelineWorker crashed (outer): %s\n%s",
                          e, traceback.format_exc())
            self._errored = True
            self.error.emit(last_clip_id, format_user_error(e))
        finally:
            # VRAM muss vor thread.quit() freigegeben sein — sonst kann der
            # naechste Worker ins OOM laufen.
            try:
                from services.model_manager import ModelManager
                ModelManager().unload()
            except (RuntimeError, AttributeError) as e:
                logger.warning("[BATCH] ModelManager unload failed: %s", e)
            if not _ok:
                self.finished.emit(last_clip_id, {})


class VisionAnalysisWorker(QObject, CancellableMixin):
    """Background-Worker fuer Video-Inhaltsanalyse via Moondream2."""
    finished = Signal(int, dict)   # clip_id, {"descriptions": [...], "summary": ...}
    error = Signal(int, str)       # clip_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, clip_id: int, video_path: str,
                 interval_sec: float = 5.0, max_frames: int = 10):
        super().__init__()
        self.clip_id = clip_id
        self.video_path = video_path
        self.interval_sec = interval_sec
        self.max_frames = max_frames

    def run(self):
        _ok = False
        try:
            from services.vision_analysis_service_moondream import VisionAnalysisService
            from services.model_manager import GPU_EXECUTION_LOCK
            svc = VisionAnalysisService()
            
            # F-041 Fix: Inferenz-Phase global locken
            with GPU_EXECUTION_LOCK:
                result = svc.analyze(
                    self.video_path,
                    interval_sec=self.interval_sec,
                    max_frames=self.max_frames,
                    progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                )
            
            self.finished.emit(self.clip_id, {
                "descriptions": result.descriptions,
                "summary": result.summary,
                "frame_count": result.frame_count,
            })
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("VisionAnalysisWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(self.clip_id, {})


class FrameExtractWorker(QObject, CancellableMixin):
    frame_ready = Signal(bytes, int, int)
    finished = Signal()   # Required by GlobalTaskManager contract (thread.quit)
    error = Signal(str)

    # Whitelist: nur sichere Zeichen in FFmpeg-Filterstrings erlauben
    _VF_SAFE_PATTERN = re.compile(r'^[a-zA-Z0-9=:.,_\-\s/]*$')

    def __init__(self, file_path: str, time_sec: float, width: int = 320,
                 height: int = 180, vf_extra: str = ""):
        super().__init__()
        self.file_path = file_path
        self.time_sec = time_sec
        self.width = width
        self.height = height
        # SEC-02 Fix: Whitelist-Validierung gegen FFmpeg-Filter-Injection
        if vf_extra and not self._VF_SAFE_PATTERN.match(vf_extra):
            import logging
            logging.warning("[FrameExtract] Unsicherer vf_extra ignoriert: %s", vf_extra[:80])
            vf_extra = ""
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
                cmd, capture_output=True, timeout=FFMPEG_THUMBNAIL_TIMEOUT_SEC,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            expected = self.width * self.height * 3
            if result.returncode == 0 and len(result.stdout) == expected:
                self.frame_ready.emit(result.stdout, self.width, self.height)
            else:
                stderr_hint = result.stderr[:200].decode(errors="replace") if result.stderr else ""
                self.error.emit(f"Frame @ {self.time_sec:.1f}s nicht verfuegbar: {stderr_hint}")
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logging.error("FrameExtractWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            # Always emit finished so TaskEngine can quit the thread cleanly.
            self.finished.emit()
