import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session
from database import engine, VideoClip

_FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
_FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")

logger = logging.getLogger(__name__)


def _proxy_dir() -> Path:
    """Returns proxy directory for the current project (lazy APP_ROOT read)."""
    from database import APP_ROOT
    return APP_ROOT / "storage" / "proxies"


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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kwargs)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe fehlgeschlagen: {_sanitize_ffmpeg_error(result.stderr)}")

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            raise ValueError(f"Kein Video-Stream gefunden in: {file_path}")

        s = streams[0]
        fmt = data.get("format", {})

        # FPS aus r_frame_rate parsen (z.B. "30/1" oder "24000/1001")
        fps_parts = s.get("r_frame_rate", "0/1").split("/")
        fps = round(int(fps_parts[0]) / max(int(fps_parts[1]), 1), 2)

        # Duration: stream > format > 0
        duration = float(s.get("duration", 0) or fmt.get("duration", 0) or 0)

        return {
            "width": int(s.get("width", 0)),
            "height": int(s.get("height", 0)),
            "fps": fps,
            "codec": s.get("codec_name", "unknown"),
            "duration": round(duration, 2),
        }

    def create_proxy(self, file_path: str, target_height: int = 480, progress_cb=None) -> str:
        """Erstellt ein Proxy-Video mit reduzierter Auflösung."""
        if progress_cb:
            progress_cb(0, "Proxy-Erstellung vorbereiten...")
        pd = _proxy_dir()
        pd.mkdir(parents=True, exist_ok=True)
        src = Path(file_path)
        proxy_path = pd / f"{src.stem}_proxy.mp4"

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                stdin=subprocess.DEVNULL, **kwargs)
        if result.returncode != 0:
            logger.info(f"[VideoAnalyzer] FFmpeg FEHLER (rc={result.returncode}):")
            logger.info(f"[VideoAnalyzer] stderr: {_sanitize_ffmpeg_error(result.stderr)}")
            raise RuntimeError(f"Proxy-Erstellung fehlgeschlagen: {_sanitize_ffmpeg_error(result.stderr)}")

        if not proxy_path.exists() or proxy_path.stat().st_size == 0:
            logger.info(f"[VideoAnalyzer] FFmpeg lief durch (rc=0), aber Proxy ist 0 Bytes oder fehlt!")
            logger.info(f"[VideoAnalyzer] stderr: {_sanitize_ffmpeg_error(result.stderr)}")
            proxy_path.unlink(missing_ok=True)
            raise RuntimeError(f"Proxy ist 0 Bytes. FFmpeg stderr: {_sanitize_ffmpeg_error(result.stderr)}")

        if progress_cb:
            progress_cb(100, "Proxy fertig")
        return str(proxy_path.resolve())

    def analyze_and_store(self, clip_id: int, create_proxy: bool = True, progress_cb=None) -> dict:
        """Analysiert einen VideoClip und schreibt Ergebnisse in die DB.

        [Session-Split] ffprobe-Metadaten werden sofort committed, BEVOR
        die zeitaufwändige Proxy-Erstellung (bis 300s) beginnt.
        So gehen Metadaten nicht verloren wenn der Proxy fehlschlägt.
        """
        # 1) Erste Session: file_path laden, sofort schließen
        with Session(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                raise ValueError(f"VideoClip {clip_id} nicht gefunden")
            file_path = clip.file_path

        # 2) ffprobe AUSSERHALB der Session (schnell, ~30ms)
        if progress_cb:
            progress_cb(0, "ffprobe Metadaten lesen...")
        logger.info("--> [VideoAnalyzer] ffprobe START für %s", file_path)
        info = self.probe(file_path)
        logger.info("--> [VideoAnalyzer] ffprobe FERTIG: %sx%s @ %sfps",
                    info['width'], info['height'], info['fps'])

        # 3) NullPool-Session: Metadaten sofort committen (verhindert DB-Lock)
        from database import nullpool_session
        with nullpool_session() as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                raise ValueError(f"VideoClip {clip_id} nach ffprobe nicht mehr gefunden")
            clip.width = info["width"]
            clip.height = info["height"]
            clip.fps = info["fps"]
            clip.codec = info["codec"]
            clip.duration = info["duration"]
            session.commit()
            logger.info("--> [VideoAnalyzer] Metadaten-Commit FERTIG für clip_id=%s", clip_id)
        if progress_cb:
            progress_cb(30, "Metadaten gespeichert")

        # 4) Proxy-Erstellung AUSSERHALB der Session (kann bis 300s dauern)
        if create_proxy:
            if progress_cb:
                progress_cb(40, "Erstelle Proxy-Video...")
            logger.info("--> [VideoAnalyzer] Proxy-Erstellung START...")
            proxy = self.create_proxy(file_path, progress_cb=progress_cb)
            logger.info("--> [VideoAnalyzer] Proxy-Erstellung FERTIG: %s", proxy)
            info["proxy_path"] = proxy

            # 5) NullPool-Session: Proxy-Pfad committen
            with nullpool_session() as session:
                clip = session.get(VideoClip, clip_id)
                if clip is None:
                    raise ValueError(f"VideoClip {clip_id} nach Proxy-Erstellung nicht mehr gefunden")
                clip.proxy_path = proxy
                session.commit()
                logger.info("--> [VideoAnalyzer] Proxy-Pfad committed für clip_id=%s", clip_id)

        if progress_cb:
            progress_cb(100, "Fertig")
        return info
