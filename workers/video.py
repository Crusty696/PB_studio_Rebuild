"""Video analysis and frame extraction background workers."""

import gc
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
                should_stop=self.should_stop,  # B-070: Cancel-Propagation
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
                    result = analyzer.analyze_and_store(
                        clip_id,
                        should_stop=self.should_stop,  # B-070: Cancel-Propagation
                    )
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
        # Bug A Fix: Flag um zu verhindern, dass error UND finished beide emittiert
        # werden (Race: Main-Thread quit() bei finished waehrend error noch laeuft
        # → "QThread: Destroyed while thread is still running" → 0xC0000409).
        _emitted_terminal = False
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
            _emitted_terminal = True
            return

        # ── Progress-Throttle: max 1 Signal pro 500ms um Event-Loop-Flooding zu verhindern ──
        _last_progress_time = [0.0]  # mutable für closure

        def _throttled_progress(pct: int, msg: str):
            now = time.monotonic()
            # Immer senden bei: 0%, 100%, oder wenn 500ms vergangen
            if pct == 0 or pct >= 99 or (now - _last_progress_time[0]) >= 0.5:
                self.progress.emit(pct, msg)
                _last_progress_time[0] = now

        siglip_model_processor = None  # Vor try-Block definiert für finally-Zugriff
        raft_model_device = None       # RAFT-Cache fuer Batch-Modus
        try:
            from services.video_analysis_service import run_full_pipeline

            total_scenes = 0
            total_embeddings = 0
            idx = 0
            # B-149: dedizierter Counter — vorher emittierte ``videos_processed``
            # ``idx if should_stop() else total_videos``, was bei Cancel VOR
            # erster Iteration ``idx=0`` ergab obwohl die Loop nie startete.
            # Downstream-Math ``progress / videos_processed`` div-zero crashte.
            videos_processed = 0

            # ── BATCH-OPTIMIERUNG: SigLIP + RAFT EINMAL laden fuer alle Videos ──
            # Verhindert VRAM-Fragmentierung durch wiederholtes Laden/Entladen.
            # GPU_LOAD_LOCK serialisiert mit allen anderen GPU-Operationen (Demucs,
            # beat_this, text_to_embedding) und verhindert Race Conditions.
            if total_videos > 1:
                from services.model_manager import ModelManager, GPU_LOAD_LOCK
                # AUD-35 Fix: SigLIP + RAFT muessen innerhalb eines einzigen GPU_LOAD_LOCK-Blocks
                # geladen werden. Ein Gap zwischen den beiden Locks erlaubt anderen Threads
                # (z.B. BeatAnalysisService), GPU_LOAD_LOCK zu akquirieren und ein anderes Modell
                # zu laden, was unload() triggert und SigLIP-Tensoren auf CPU verschiebt.
                # Die siglip_model_processor-Referenz zeigte danach auf CPU-Tensoren waehrend
                # Inputs auf CUDA lagen → CUDA RuntimeError.
                # Fix: mm.load_raft() direkt aufrufen (nutzt nur _swap_lock intern),
                # statt _load_raft_model() (wuerde GPU_LOAD_LOCK nested re-akquirieren → Deadlock).
                # B-02 Design: SigLIP (~2.5 GB) + RAFT (~0.1 GB) = ~2.6 GB — passt auf GTX 1060.
                with GPU_LOAD_LOCK:
                    mm = ModelManager()
                    try:
                        logger.info("[BATCH] Lade SigLIP einmalig fuer %d Videos...", total_videos)
                        siglip_model_processor = mm.load_siglip()
                        logger.info("[BATCH] SigLIP vorgeladen auf %s", mm.device)
                    except (RuntimeError, OSError, MemoryError) as e:
                        logger.warning("[BATCH] SigLIP Vorladen fehlgeschlagen (%s) — Fallback: pro Video laden", e)
                        siglip_model_processor = None
                    try:
                        raft_result = mm.load_raft()
                        if raft_result[0] is not None:
                            raft_model_device = raft_result
                            logger.info("[BATCH] RAFT vorgeladen — wird fuer alle %d Videos wiederverwendet", total_videos)
                        else:
                            raft_model_device = None
                    except (RuntimeError, OSError, MemoryError) as e:
                        logger.warning("[BATCH] RAFT Vorladen fehlgeschlagen (%s) — Fallback: pro Video laden", e)
                        raft_model_device = None
                        # RAFT-OOM-Pfad kann SigLIP evictet haben — Referenz invalidieren
                        if siglip_model_processor is not None and mm.model_type != "siglip":
                            logger.warning("[BATCH] RAFT-OOM hat SigLIP evictet — SigLIP-Referenz invalidiert")
                            siglip_model_processor = None

            # H-25 FIX: Hold GPU_EXECUTION_LOCK for entire batch to prevent model invalidation mid-batch
            # (prevents other threads from unloading SigLIP/RAFT between video iterations)
            from services.model_manager import GPU_EXECUTION_LOCK
            with GPU_EXECUTION_LOCK:
                for idx, (clip_id, video_path, title) in enumerate(self._batch, start=1):
                    if self.should_stop():
                        break

                    label = title or Path(video_path).stem
                    batch_base_pct = int((idx - 1) / total_videos * 100)
                    batch_range = int(100 / total_videos)
                    _throttled_progress(
                        batch_base_pct,
                        f"Video {idx}/{total_videos}: '{label}' wird analysiert..."
                    )

                    try:
                        result = run_full_pipeline(
                            video_path=video_path,
                            video_clip_id=clip_id,
                            progress_cb=lambda pct, msg, _base=batch_base_pct, _range=batch_range, _i=idx, _tv=total_videos: (
                                _throttled_progress(
                                    min(99, _base + int(pct / 100 * _range)),
                                    f"[{_i}/{_tv}] {msg}"
                                )
                            ),
                            should_stop=self.should_stop,
                            siglip_model_processor=siglip_model_processor,
                            raft_model_device=raft_model_device,
                        )
                        total_scenes += len(result.scenes)
                        total_embeddings += result.embeddings_stored
                        videos_processed += 1  # B-149: nach erfolgreichem Pipeline-Call

                    except FileNotFoundError as e:
                        # B-012 Fix: TOCTOU — Proxy existierte bei Check aber wurde geloescht
                        # Fallback zu Original-Datei
                        logger.warning("[Proxy-First] Clip %d: Datei geloescht (TOCTOU) — Fallback: %s", clip_id, e)
                        from database import nullpool_session as fallback_session
                        try:
                            with fallback_session() as fb_session:
                                fb_clip = fb_session.get(VideoClip, clip_id)
                                if fb_clip and fb_clip.file_path:
                                    result = run_full_pipeline(
                                        video_path=fb_clip.file_path,
                                        video_clip_id=clip_id,
                                        progress_cb=lambda pct, msg, _base=batch_base_pct, _range=batch_range, _i=idx, _tv=total_videos: (
                                            _throttled_progress(
                                                min(99, _base + int(pct / 100 * _range)),
                                                f"[{_i}/{_tv}] {msg}"
                                            )
                                        ),
                                        should_stop=self.should_stop,
                                        siglip_model_processor=siglip_model_processor,
                                        raft_model_device=raft_model_device,
                                    )
                                    total_scenes += len(result.scenes)
                                    total_embeddings += result.embeddings_stored
                                    videos_processed += 1  # B-149
                                else:
                                    raise RuntimeError(f"VideoClip {clip_id}: Original-Pfad nicht verfuegbar")
                        except (RuntimeError, OSError) as fallback_err:
                            raise RuntimeError(f"Clip {clip_id}: Proxy + Original fehlgeschlagen — {fallback_err}") from fallback_err
                    except (RuntimeError, OSError, ValueError) as e:
                        logging.error("VideoAnalysisPipelineWorker[%s] video %d/%d '%s' crashed: %s\n%s",
                                      clip_id, idx, total_videos, label, e, traceback.format_exc())
                        # C-04 Fix: Einzelner Fehler bricht nicht mehr die ganze Pipeline ab
                        self.progress.emit(
                            min(99, batch_base_pct + batch_range),
                            f"[{idx}/{total_videos}] FEHLER: {e}"
                        )
                        continue  # naechstes Video statt Abbruch
                    finally:
                        # F-036 Fix: Cleanup sicher via Main-Thread anfordern
                        if idx % 25 == 0:
                            from services.task_manager import GlobalTaskManager
                            GlobalTaskManager.instance().request_gc_signal.emit()

                # ── BATCH-CLEANUP: SigLIP + RAFT am Ende der gesamten Batch entladen ──
                if raft_model_device is not None:
                    try:
                        import torch
                        raft_m, _ = raft_model_device
                        if raft_m is not None:
                            raft_m.cpu()
                            del raft_m
                        gc.collect()
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        logger.info("[BATCH] RAFT nach Batch-Verarbeitung entladen")
                    except (RuntimeError, AttributeError) as e:
                        logger.warning("[BATCH] RAFT Entladen fehlgeschlagen: %s", e)
                    raft_model_device = None

                if siglip_model_processor is not None:
                    try:
                        from services.model_manager import ModelManager
                        mm = ModelManager()
                        mm.unload()
                        logger.info("[BATCH] SigLIP nach Batch-Verarbeitung entladen")
                    except (RuntimeError, AttributeError) as e:
                        logger.warning("[BATCH] SigLIP Entladen fehlgeschlagen: %s", e)
                    siglip_model_processor = None

            self.finished.emit(last_clip_id, {
                "scenes": total_scenes,
                "embeddings": total_embeddings,
                "videos_processed": videos_processed,
            })
            _emitted_terminal = True
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("VideoAnalysisPipelineWorker crashed (outer): %s\n%s",
                          e, traceback.format_exc())
            self._errored = True
            self.error.emit(last_clip_id, format_user_error(e))
            _emitted_terminal = True
        finally:
            # RAFT + SigLIP Cleanup auch bei unerwarteten Exceptions
            if raft_model_device is not None:
                try:
                    import torch
                    raft_m, _ = raft_model_device
                    if raft_m is not None:
                        raft_m.cpu()
                        del raft_m
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except (RuntimeError, AttributeError) as e:
                    logger.warning("RAFT cleanup failed during finally block: %s", e)
            if siglip_model_processor is not None:
                try:
                    from services.model_manager import ModelManager
                    ModelManager().unload()
                except (RuntimeError, AttributeError) as e:
                    logger.warning("SigLIP cleanup failed during finally block: %s", e)
            # finished MUSS immer emittiert werden damit thread.quit() greift —
            # ABER nur wenn weder finished noch error bereits emittiert wurde.
            # Bug A Fix: Verhindert Race zwischen error.emit + finished.emit, der
            # zu "QThread: Destroyed while thread is still running" → 0xC0000409 fuehrt.
            if not _emitted_terminal:
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
