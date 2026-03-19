import json
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session
from database import engine, VideoClip

PROXY_DIR = Path("storage/proxies")


class VideoAnalyzer:
    """Extrahiert Video-Metadaten via ffprobe und erstellt Proxy-Videos."""

    def probe(self, file_path: str) -> dict:
        """Liest Auflösung, FPS, Codec und Duration aus einer Videodatei."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            "-select_streams", "v:0",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe fehlgeschlagen: {result.stderr.strip()}")

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

    def create_proxy(self, file_path: str, target_height: int = 480) -> str:
        """Erstellt ein Proxy-Video mit reduzierter Auflösung."""
        PROXY_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(file_path)
        proxy_path = PROXY_DIR / f"{src.stem}_proxy.mp4"

        if proxy_path.exists():
            return str(proxy_path.resolve())

        cmd = [
            "ffmpeg", "-y", "-i", file_path,
            "-vf", f"scale=-2:{target_height}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            str(proxy_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Proxy-Erstellung fehlgeschlagen: {result.stderr.strip()}")

        return str(proxy_path.resolve())

    def analyze_and_store(self, clip_id: int, create_proxy: bool = True) -> dict:
        """Analysiert einen VideoClip und schreibt Ergebnisse in die DB."""
        with Session(engine) as session:
            clip = session.get(VideoClip, clip_id)
            if clip is None:
                raise ValueError(f"VideoClip {clip_id} nicht gefunden")

            info = self.probe(clip.file_path)
            clip.width = info["width"]
            clip.height = info["height"]
            clip.fps = info["fps"]
            clip.codec = info["codec"]
            clip.duration = info["duration"]

            if create_proxy:
                proxy = self.create_proxy(clip.file_path)
                clip.proxy_path = proxy
                info["proxy_path"] = proxy

            session.commit()

        return info
