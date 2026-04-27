import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from sqlalchemy.orm import Session
from database import engine, VideoClip
from services.timeout_constants import FFMPEG_PROBE_TIMEOUT_SEC, FFMPEG_RENDER_TIMEOUT_SEC
from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin
from services import analysis_status_service
from services.errors import FFmpegError

# B-156: per-proxy-path Locks gegen TOCTOU zwischen
# VideoBatchAnalysisWorker (create_proxy/unlink) und
# VideoAnalysisPipelineWorker (liest clip.proxy_path und oeffnet die
# Datei). Ohne Lock konnte der Pipeline-Worker den File-Handle
# zwischen unlink und ffmpeg-Rewrite verlieren — FileNotFoundError-
# Fallback war zwar self-healing, aber langsam.
_proxy_locks_guard = threading.Lock()
_proxy_locks: dict[str, threading.Lock] = {}


def _get_proxy_lock(proxy_path: str) -> threading.Lock:
    with _proxy_locks_guard:
        lock = _proxy_locks.get(proxy_path)
        if lock is None:
            lock = threading.Lock()
            _proxy_locks[proxy_path] = lock
        return lock

_FFMPEG = get_ffmpeg_bin()
_FFPROBE = get_ffprobe_bin()

logger = logging.getLogger(__name__)


def _proxy_dir() -> Path:
    """Returns proxy directory for the current project (lazy APP_ROOT read)."""
    import database.session as _session
    return _session.APP_ROOT / "storage" / "proxies"


def _sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


class VideoAnalyzer:
    """Extrahiert Video-Metadaten via ffprobe und erstellt Proxy-Videos."""

    def probe(self, file_path: str) -> dict:
        """Liest Auflösung, FPS, Codec und Duration aus einer Videodatei."""
        if not file_path or not Path(file_path).exists():
            logger.error("Video-Datei nicht gefunden: %s", file_path)
            return {"width": 0, "height": 0, "fps": 0.0, "codec": "unknown", "duration": 0.0}

        cmd = [
            _FFPROBE, "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            "-select_streams", "v:0",
            file_path,
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC, **kwargs)
        if result.returncode != 0:
            raise FFmpegError(
                f"ffprobe fehlgeschlagen: {_sanitize_ffmpeg_error(result.stderr)}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            raise ValueError(f"Kein Video-Stream gefunden in: {file_path}")

        s = streams[0]
        fmt = data.get("format", {})

        # FPS aus r_frame_rate parsen (z.B. "30/1" oder "24000/1001").
        # B-111 / BUG-A4: tolerate edge cases — value without "/", or
        # non-numeric ("n/a"). Crash here used to take down the whole
        # ingest pipeline for one weird file.
        raw_fps = s.get("r_frame_rate", "0/1") or "0/1"
        fps_parts = raw_fps.split("/")
        try:
            num = int(fps_parts[0])
            den = int(fps_parts[1]) if len(fps_parts) > 1 else 1
            fps = round(num / max(den, 1), 2)
        except (ValueError, IndexError):
            fps = 0.0

        # Duration: stream > format > 0
        duration = float(s.get("duration", 0) or fmt.get("duration", 0) or 0)

        return {
            "width": int(s.get("width", 0)),
            "height": int(s.get("height", 0)),
            "fps": fps,
            "codec": s.get("codec_name", "unknown"),
            "duration": round(duration, 2),
        }

    def create_proxy(self, file_path: str, target_height: int = 480, progress_cb=None,
                     should_stop=None) -> str:
        """Erstellt ein Proxy-Video mit reduzierter Auflösung.

        B-070 Fix: ``should_stop`` Callback wird in einer Poll-Loop ueber
        ``Popen.poll`` regelmaessig abgefragt; bei True wird ffmpeg
        terminiert/killed und ``RuntimeError("Proxy-Erstellung abgebrochen")``
        geworfen. Frueher blockierte ``subprocess.run`` bis zu 5 min trotz
        User-Cancel.
        """
        if progress_cb:
            progress_cb(0, "Proxy-Erstellung vorbereiten...")
        pd = _proxy_dir()
        pd.mkdir(parents=True, exist_ok=True)
        src = Path(file_path)
        proxy_path = pd / f"{src.stem}_proxy.mp4"

        # B-156: Lock haelt unlink + ffmpeg-rewrite atomar — sodass
        # parallele Pipeline-Worker die Datei nicht waehrend des Rewrites
        # oeffnen.
        proxy_lock = _get_proxy_lock(str(proxy_path.resolve()))
        with proxy_lock:
            if proxy_path.exists() and proxy_path.stat().st_size > 0:
                return str(proxy_path.resolve())
            elif proxy_path.exists():
                logger.info(f"[VideoAnalyzer] WARNUNG: 0-Byte Proxy gefunden, wird neu erstellt: {proxy_path}")
                proxy_path.unlink(missing_ok=True)

            cmd = [
                _FFMPEG, "-y", "-i", file_path,
                "-vf", f"scale=-2:{target_height}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                "-c:a", "aac", "-b:a", "128k",
                str(proxy_path),
            ]
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            if progress_cb:
                progress_cb(20, "FFmpeg Proxy-Encoding...")

            import time as _time
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **kwargs,
            )
            start = _time.monotonic()
            cancelled = False
            while proc.poll() is None:
                if should_stop is not None:
                    try:
                        if should_stop():
                            cancelled = True
                            proc.terminate()
                            try:
                                proc.wait(timeout=2.0)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            break
                    except Exception:
                        pass
                if _time.monotonic() - start > FFMPEG_RENDER_TIMEOUT_SEC:
                    proc.kill()
                    proxy_path.unlink(missing_ok=True)
                    raise subprocess.TimeoutExpired(cmd, FFMPEG_RENDER_TIMEOUT_SEC)
                _time.sleep(0.5)

            stdout, stderr = proc.communicate()

            if cancelled:
                proxy_path.unlink(missing_ok=True)
                raise RuntimeError("Proxy-Erstellung abgebrochen (User-Cancel)")

            if proc.returncode != 0:
                logger.info(f"[VideoAnalyzer] FFmpeg FEHLER (rc={proc.returncode}):")
                logger.info(f"[VideoAnalyzer] stderr: {_sanitize_ffmpeg_error(stderr)}")
                raise FFmpegError(
                    f"Proxy-Erstellung fehlgeschlagen: {_sanitize_ffmpeg_error(stderr)}",
                    returncode=proc.returncode,
                    stderr=stderr,
                )

            if not proxy_path.exists() or proxy_path.stat().st_size == 0:
                logger.info(f"[VideoAnalyzer] FFmpeg lief durch (rc=0), aber Proxy ist 0 Bytes oder fehlt!")
                logger.info(f"[VideoAnalyzer] stderr: {_sanitize_ffmpeg_error(stderr)}")
                proxy_path.unlink(missing_ok=True)
                raise FFmpegError(
                    f"Proxy ist 0 Bytes. FFmpeg stderr: {_sanitize_ffmpeg_error(stderr)}",
                    returncode=0,
                    stderr=stderr,
                )

            if progress_cb:
                progress_cb(100, "Proxy fertig")
            return str(proxy_path.resolve())

    def analyze_and_store(self, clip_id: int, create_proxy: bool = True, progress_cb=None,
                          should_stop=None) -> dict:
        """Analysiert einen VideoClip und schreibt Ergebnisse in die DB.

        [Session-Split] ffprobe-Metadaten werden sofort committed, BEVOR
        die zeitaufwändige Proxy-Erstellung (bis 300s) beginnt.
        So gehen Metadaten nicht verloren wenn der Proxy fehlschlägt.
        """
        # 1) Erste Session: file_path laden, sofort schließen
        with Session(engine) as session:
            clip = session.query(VideoClip).filter(
                VideoClip.id == clip_id, VideoClip.deleted_at.is_(None)
            ).first()
            if clip is None:
                raise ValueError(f"VideoClip {clip_id} nicht gefunden")
            file_path = clip.file_path

        # 2) ffprobe AUSSERHALB der Session (schnell, ~30ms)
        analysis_status_service.mark_started("video", clip_id, "metadata_extract")
        try:
            if progress_cb:
                progress_cb(0, "ffprobe Metadaten lesen...")
            logger.info("--> [VideoAnalyzer] ffprobe START für %s", file_path)
            info = self.probe(file_path)
            logger.info("--> [VideoAnalyzer] ffprobe FERTIG: %sx%s @ %sfps",
                        info['width'], info['height'], info['fps'])

            # 3) NullPool-Session: Metadaten sofort committen (verhindert DB-Lock)
            from database import nullpool_session
            with nullpool_session() as session:
                clip = session.query(VideoClip).filter(
                    VideoClip.id == clip_id, VideoClip.deleted_at.is_(None)
                ).first()
                if clip is None:
                    raise ValueError(f"VideoClip {clip_id} nach ffprobe nicht mehr gefunden")
                clip.width = info["width"]
                clip.height = info["height"]
                clip.fps = info["fps"]
                clip.codec = info["codec"]
                clip.duration = info["duration"]
                session.commit()
                logger.info("--> [VideoAnalyzer] Metadaten-Commit FERTIG für clip_id=%s", clip_id)

            analysis_status_service.mark_done("video", clip_id, "metadata_extract", {
                "duration": info["duration"],
                "resolution": f"{info['width']}x{info['height']}",
                "fps": info["fps"],
                "codec": info["codec"],
            })
            if progress_cb:
                progress_cb(30, "Metadaten gespeichert")
        except Exception as e:
            analysis_status_service.mark_error("video", clip_id, "metadata_extract", str(e))
            raise

        # 4) Proxy-Erstellung AUSSERHALB der Session (kann bis 300s dauern)
        if create_proxy:
            if progress_cb:
                progress_cb(40, "Erstelle Proxy-Video...")
            logger.info("--> [VideoAnalyzer] Proxy-Erstellung START...")
            proxy = self.create_proxy(file_path, progress_cb=progress_cb,
                                      should_stop=should_stop)
            logger.info("--> [VideoAnalyzer] Proxy-Erstellung FERTIG: %s", proxy)
            info["proxy_path"] = proxy

            # 5) NullPool-Session: Proxy-Pfad committen
            with nullpool_session() as session:
                clip = session.query(VideoClip).filter(
                    VideoClip.id == clip_id, VideoClip.deleted_at.is_(None)
                ).first()
                if clip is None:
                    raise ValueError(f"VideoClip {clip_id} nach Proxy-Erstellung nicht mehr gefunden")
                clip.proxy_path = proxy
                session.commit()
                logger.info("--> [VideoAnalyzer] Proxy-Pfad committed für clip_id=%s", clip_id)

        if progress_cb:
            progress_cb(100, "Fertig")
        return info
