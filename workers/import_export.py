"""Import, export, proxy and batch conversion background workers."""

import logging
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from sqlalchemy.orm import Session as DBSession

from database import engine, VideoClip
from services.export_service import export_timeline
from services.ingest_service import ingest_audio, ingest_video
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
            )
            self.finished.emit(path)
            _ok = True
        except Exception as e:
            logging.error("ExportWorker crashed: %s\n%s", e, traceback.format_exc())
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

    def __init__(self, paths_audio: list, paths_video: list):
        super().__init__()
        self.paths_audio = paths_audio
        self.paths_video = paths_video

    def run(self):
        _ok = False
        added = 0
        new_video_clips: list = []
        total = len(self.paths_audio) + len(self.paths_video)
        done = 0
        try:
            for p in self.paths_audio:
                if self.should_stop():
                    break
                try:
                    result = ingest_audio(p)
                    name = Path(p).name
                    if result is None:
                        self.file_imported.emit(f"[Warnung] Bereits importiert: {name}")
                    else:
                        self.file_imported.emit(f"[Ingest] Audio importiert: {name}")
                        added += 1
                except Exception as e:
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
                    result = ingest_video(p)
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
                except Exception as e:
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

            self.finished.emit(added, new_video_clips)
            _ok = True
        except Exception as e:
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
        _ok = False
        total = len(self.videos)
        converted = 0
        try:
            w_res, h_res = self.resolution.split("x")

            for i, v in enumerate(self.videos):
                if self.should_stop():
                    break

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
                        cmd, capture_output=True, timeout=600,
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
                    self._errored = True
                    self.error.emit("ffmpeg nicht gefunden!")
                    return

            self.finished.emit(converted, total)
            _ok = True
        except Exception as e:
            logging.error("BatchConvertWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(0, 0)


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
        _ok = False
        try:
            from services.convert_service import convert
            proxy_path = convert(
                self.video_path,
                preset_name="edit_proxy",
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            # Proxy-Pfad in SQLite speichern
            with DBSession(engine) as session:
                clip = session.get(VideoClip, self.clip_id)
                if clip:
                    clip.proxy_path = proxy_path
                    session.commit()
            self.finished.emit(self.clip_id, proxy_path)
            _ok = True
        except Exception as e:
            logging.error("ProxyCreationWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, format_user_error(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(self.clip_id, "")
