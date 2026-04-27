"""Import, export, proxy and batch conversion background workers."""

import logging
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from sqlalchemy.orm import Session as DBSession

from database import engine, VideoClip
from services.export_service import export_timeline, export_preview
from services.ingest_service import (
    ingest_audio,
    ingest_video,
    _invalidate_pacing_caches,
)
from services.timeout_constants import FFMPEG_EXPORT_TIMEOUT_SEC
from .base import CancellableMixin, format_user_error

logger = logging.getLogger(__name__)


class ExportWorker(QObject, CancellableMixin):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, project_id: int, output_name: str,
                 resolution: str = "1920x1080", fps: float = 30.0):
        super().__init__()
        self.project_id = project_id
        self.output_name = output_name
        self.resolution = resolution
        self.fps = fps

    def run(self):
        _ok = False
        try:
            path = export_timeline(
                project_id=self.project_id,
                output_name=self.output_name,
                resolution=self.resolution,
                fps=self.fps,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                # B-116 / B-121: ffmpeg subprocess kann jetzt mid-run via
                # User-Cancel terminiert werden.
                cancel_check=self.should_stop,
            )
            self.finished.emit(path)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("ExportWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit("")


class PreviewExportWorker(QObject, CancellableMixin):
    """Rendert eine Vorschau der ersten N Sekunden der Timeline."""
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, project_id: int, resolution: str = "1920x1080",
                 fps: float = 30.0, duration_limit: float = 10.0):
        super().__init__()
        self.project_id = project_id
        self.resolution = resolution
        self.fps = fps
        self.duration_limit = duration_limit

    def run(self):
        _ok = False
        try:
            path = export_preview(
                project_id=self.project_id,
                resolution=self.resolution,
                fps=self.fps,
                duration_limit=self.duration_limit,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                cancel_check=self.should_stop,
            )
            self.finished.emit(path)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("PreviewExportWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit("")


class FolderImportWorker(QObject, CancellableMixin):
    """Importiert alle Audio- und Video-Dateien aus einem Ordner im Hintergrund."""
    finished = Signal(int, list)   # (total_added, new_video_clips)
    error = Signal(str)
    progress = Signal(int, str)    # (percent, message)
    file_imported = Signal(str)    # Console-Nachricht pro Datei

    def __init__(
        self,
        paths_audio: list,
        paths_video: list,
        project_id: int | None = None,
        walk_root: str | None = None,
    ):
        """Cycle 13 BUG-B1: project_id beim Worker-Start einfangen statt
        erst pro-File aufloesen. Schutz gegen Projekt-Switch waehrend
        des Imports — sonst landen die spaeter importierten Files im
        falschen Projekt.

        B-058: ``walk_root`` ist optional. Wenn gesetzt, scannt der
        Worker den Ordnerbaum SELBST per ``os.walk`` (im Background-
        Thread) und ergaenzt die ``paths_audio``/``paths_video``-
        Listen. Vorher musste der UI-Caller ``os.walk`` im Main-Thread
        machen — bei NAS / Cloud-Sync / 1000+-File-Folders fror das UI
        mehrere Sekunden ein.
        """
        super().__init__()
        self.paths_audio = list(paths_audio)
        self.paths_video = list(paths_video)
        self.walk_root = walk_root
        if project_id is None:
            try:
                from database.session import get_active_project_id
                project_id = get_active_project_id()
            except (ImportError, AttributeError, RuntimeError):
                project_id = None
        self.project_id = project_id

    def run(self):
        _ok = False
        added = 0
        new_video_clips: list = []
        # B-058: Walk im Background-Thread wenn der Caller einen
        # ``walk_root`` gesetzt hat (UI-Pfad ``_import_folder``).
        if self.walk_root:
            import os
            from pathlib import Path
            from services.ingest_service import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
            try:
                self.progress.emit(0, "Scanne Ordner...")
                for root, _dirs, files in os.walk(self.walk_root):
                    if self.should_stop():
                        break
                    for f in files:
                        ext = Path(f).suffix.lower()
                        full = os.path.join(root, f)
                        if ext in AUDIO_EXTENSIONS:
                            self.paths_audio.append(full)
                        elif ext in VIDEO_EXTENSIONS:
                            self.paths_video.append(full)
            except OSError as walk_err:
                self.error.emit(f"Ordner-Scan fehlgeschlagen: {walk_err}")
                return
        total = len(self.paths_audio) + len(self.paths_video)
        done = 0
        try:
            for p in self.paths_audio:
                if self.should_stop():
                    break
                try:
                    # B-155 / B-151: invalidate_caches=False fuer den Loop,
                    # einmal am Ende manuell — vorher: N+1 Cache-Rebuild-Storm.
                    result = ingest_audio(
                        p,
                        project_id=self.project_id,
                        invalidate_caches=False,
                    )
                    name = Path(p).name
                    if result is None:
                        self.file_imported.emit(f"[Warnung] Bereits importiert: {name}")
                    else:
                        self.file_imported.emit(f"[Ingest] Audio importiert: {name}")
                        added += 1
                except (OSError, IOError, ValueError, RuntimeError) as e:
                    logger.error(
                        "Audio-Import fehlgeschlagen fuer '%s': %s\n%s",
                        p, e, traceback.format_exc(),
                    )
                    self.file_imported.emit(
                        f"[Fehler] Audio-Import fehlgeschlagen: {Path(p).name} — {e}"
                    )
                done += 1
                pct = int(done / total * 100) if total else 100
                self.progress.emit(pct, f"Importiere {done}/{total} ...")

            for p in self.paths_video:
                if self.should_stop():
                    break
                try:
                    result = ingest_video(
                        p,
                        project_id=self.project_id,
                        invalidate_caches=False,
                    )
                    name = Path(p).name
                    if result is None:
                        self.file_imported.emit(f"[Warnung] Bereits importiert: {name}")
                    else:
                        self.file_imported.emit(f"[Ingest] Video importiert: {name}")
                        added += 1
                        if hasattr(result, "id"):
                            new_video_clips.append(
                                (result.id, str(Path(p).resolve()), name)
                            )
                except (OSError, IOError, ValueError, RuntimeError) as e:
                    logger.error(
                        "Video-Import fehlgeschlagen fuer '%s': %s\n%s",
                        p, e, traceback.format_exc(),
                    )
                    self.file_imported.emit(
                        f"[Fehler] Video-Import fehlgeschlagen: {Path(p).name} — {e}"
                    )
                done += 1
                pct = int(done / total * 100) if total else 100
                self.progress.emit(pct, f"Importiere {done}/{total} ...")

            # B-155 / B-151: einmaliger Cache-Invalidate am Ende des Batches.
            if added > 0:
                try:
                    _invalidate_pacing_caches()
                except Exception as e:  # broad catch — Cache-Rebuild ist best-effort
                    logger.warning(
                        "FolderImportWorker: Pacing-Cache-Invalidate "
                        "fehlgeschlagen: %s", e,
                    )
            self.finished.emit(added, new_video_clips)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logger.error(
                "FolderImportWorker crashed: %s\n%s", e, traceback.format_exc()
            )
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(added, new_video_clips)


class BatchConvertWorker(QObject, CancellableMixin):
    """Konvertiert alle Videos im Hintergrund-Thread statt auf dem Main-Thread."""
    finished = Signal(int, int)      # (converted_count, total_count)
    error = Signal(str)
    progress = Signal(int, str)      # (percent, message)

    def __init__(self, videos: list, resolution: str, fps: str, vcodec: str, ext: str):
        super().__init__()
        self.videos = videos
        self.resolution = resolution
        self.fps = fps
        self.vcodec = vcodec
        self.ext = ext

    def run(self):
        # B-057: GPU_EXECUTION_LOCK serialisiert NVENC mit anderen GPU-
        # Workloads (BeatThis, Demucs, SigLIP, RAFT). Vorher konnten
        # h264_nvenc / hevc_nvenc parallel zu Audio-Analyse laufen und
        # auf 6 GB GTX 1060 Mobile NVENC-Session-Limit (max 2) sprengen
        # → "Cannot load NVENC session"-Fehler oder VRAM-OOM.
        from services.model_manager import GPU_EXECUTION_LOCK
        with GPU_EXECUTION_LOCK:
            return self._run_locked()

    def _run_locked(self):
        _ok = False
        total = len(self.videos)
        converted = 0
        try:
            # B-005 Fix: Validierung des Resolution-Formats mit Error-Handling
            try:
                parts = self.resolution.split("x")
                if len(parts) != 2:
                    raise ValueError("Format muss WIDTHxHEIGHT sein")
                w_res = int(parts[0])
                h_res = int(parts[1])
                if w_res <= 0 or h_res <= 0:
                    raise ValueError("Width und Height müssen > 0 sein")
                # Zurück zu Strings für FFmpeg-Command
                w_res = str(w_res)
                h_res = str(h_res)
            except (ValueError, IndexError) as e:
                raise ValueError(f"Ungültige Auflösung '{self.resolution}': {e}")

            # M-44 Fix: Validate FPS and vcodec parameters
            try:
                fps_float = float(self.fps)
                if fps_float <= 0 or fps_float > 240:
                    raise ValueError("FPS muss zwischen 0 und 240 liegen")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Ungültiger FPS-Wert '{self.fps}': {e}")

            # Whitelist known safe video codecs
            ALLOWED_VCODECS = {
                "libx264", "libx265", "h264_nvenc", "hevc_nvenc",
                "libvpx", "libvpx-vp9", "libaom-av1", "prores_ks", "copy"
            }
            if self.vcodec not in ALLOWED_VCODECS:
                raise ValueError(
                    f"Nicht unterstützter Codec '{self.vcodec}'. "
                    f"Erlaubte Codecs: {', '.join(sorted(ALLOWED_VCODECS))}"
                )

            for i, v in enumerate(self.videos):
                if self.should_stop():
                    break

                # B-117: zweiter Cancel-Check direkt nach dem ffmpeg-Call,
                # bevor der naechste startet. ffmpeg-Subprocess selber kann
                # nicht mid-segment cancelled werden weil hier subprocess.run
                # benutzt wird (vs. Popen+watchdog). Daher zumindest schnell
                # nach jeder Konvertierung pruefen, sodass folgende Segmente
                # gar nicht erst starten.
                src = v["file_path"]
                stem = Path(src).stem
                out_dir = Path(src).parent / "converted"
                out_dir.mkdir(exist_ok=True)
                dst = str(out_dir / f"{stem}_std{self.ext}")

                self.progress.emit(
                    int((i + 1) / total * 100),
                    f"[Convert] {i+1}/{total}: {Path(src).name} -> {self.resolution} @ {self.fps}fps"
                )

                cmd = [
                    "ffmpeg", "-y", "-i", src,
                    "-vf", f"scale={w_res}:{h_res}:force_original_aspect_ratio=decrease,"
                           f"pad={w_res}:{h_res}:(ow-iw)/2:(oh-ih)/2",
                    "-r", self.fps,
                    "-c:v", self.vcodec,
                    "-c:a", "aac",
                    "-preset", "medium",
                    "-v", "quiet",
                    dst,
                ]
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, timeout=FFMPEG_EXPORT_TIMEOUT_SEC,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                    if result.returncode == 0:
                        converted += 1
                        self.progress.emit(int((i + 1) / total * 100), f"  OK: {dst}")
                    else:
                        stderr = result.stderr.decode(errors="replace")[:200]
                        self.progress.emit(int((i + 1) / total * 100), f"  FEHLER: {stderr}")
                except subprocess.TimeoutExpired:
                    self.progress.emit(int((i + 1) / total * 100), f"  TIMEOUT: {Path(src).name}")
                except FileNotFoundError:
                    # B-103 / BUG-A9 fix: emitting BOTH error AND finished
                    # in the same branch made UI slots wired directly to
                    # ``finished`` think the run succeeded. The ``finally``
                    # block already emits a final ``finished(0, 0)`` if
                    # ``_ok`` stays False and we set ``_errored`` — let it
                    # do its job.
                    self._errored = True
                    self.error.emit("ffmpeg nicht gefunden!")
                    return

                # B-117: nach jedem fertig konvertierten Segment pruefen,
                # ob der User cancel angeklickt hat — verhindert dass das
                # naechste Segment noch startet.
                if self.should_stop():
                    break

            self.finished.emit(converted, total)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("BatchConvertWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(0, 0)


# B-056: Semaphor begrenzt parallele Proxy-Worker. Bei Batch-Import
# von 50 Videos liefen vorher 50 ffmpeg-Subprozesse parallel — alle
# konkurrierten um Disk-IO + Encoder-Sessions, im Worst Case:
# NVENC-Session-Erschoepfung (GTX 1060 Mobile = 2) + I/O-Trashing.
# 2 ist der konservative Default; entspricht der NVENC-Session-Grenze.
import threading as _threading_b056
_PROXY_CREATION_SEMAPHORE = _threading_b056.BoundedSemaphore(value=2)


class ProxyCreationWorker(QObject, CancellableMixin):
    """Erstellt NVENC 540p Edit-Proxy für ein Video."""
    finished = Signal(int, str)    # clip_id, proxy_path
    error = Signal(int, str)       # clip_id, error_msg
    progress = Signal(int, str)    # percent, status_text

    def __init__(self, clip_id: int, video_path: str):
        super().__init__()
        self.clip_id = clip_id
        self.video_path = video_path

    def run(self):
        # B-056: Semaphor blockt bis ein Slot frei wird.
        with _PROXY_CREATION_SEMAPHORE:
            return self._run_with_slot()

    def _run_with_slot(self):
        _ok = False
        try:
            from services.convert_service import convert
            # B-059: Wall-Clock-Timeout (10 min) — verhindert Orphan-Worker bei
            # haengender FFmpeg/NVENC-Encoding (korrupter Codec, Treiber-Hang).
            proxy_path = convert(
                self.video_path,
                preset_name="edit_proxy",
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
                cancel_check=self.should_stop,
                timeout=600.0,
            )
            # Proxy-Pfad in SQLite speichern (NullPool: verhindert DB-Lock)
            from database import nullpool_session
            with nullpool_session() as session:
                clip = session.get(VideoClip, self.clip_id)
                if clip:
                    clip.proxy_path = proxy_path
                    session.commit()
            self.finished.emit(self.clip_id, proxy_path)
            _ok = True
        except Exception as e:  # broad catch intentional — top-level worker safety net
            logging.error("ProxyCreationWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(self.clip_id, "")
