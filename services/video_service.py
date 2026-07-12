import json
import logging
import subprocess
import sys
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from database import VideoClip, engine
from services import analysis_status_service
from services.errors import FFmpegError
from services.ffmpeg_utils import proxy_dir as _proxy_dir, sanitize_ffmpeg_error as _sanitize_ffmpeg_error
from services.nvenc_policy import require_nvenc
from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin
from services.timeout_constants import FFMPEG_PROBE_TIMEOUT_SEC, FFMPEG_RENDER_TIMEOUT_SEC

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


# B-219: WinError 32 ("Datei wird von anderem Prozess verwendet") tritt auf,
# wenn Pipeline-Worker gerade eine cv2.VideoCapture released hat oder ein
# FFmpeg-Subprocess gerade beendet wurde — der Windows-Kernel braucht
# einige ms, bis der File-Handle wirklich frei ist. Auch Antivirus/
# Search-Indexer halten Files kurz nach Schreiben offen. Retry-mit-Backoff
# ist die Standard-Loesung. Auf Linux/macOS no-op (keine Share-Locks).
import time as _time_for_retry


def _is_windows_file_lock_error(exc: BaseException) -> bool:
    """Detect WinError 32 (sharing-violation) — Windows-only file lock."""
    if not isinstance(exc, OSError):
        return False
    # Windows: PermissionError mit winerror==32 (ERROR_SHARING_VIOLATION).
    winerr = getattr(exc, "winerror", None)
    return winerr == 32 or getattr(exc, "errno", None) == 13  # EACCES als Fallback


def _retry_on_file_lock(
    operation: str,
    func,
    *args,
    attempts: int = 5,
    base_delay_s: float = 0.1,
    **kwargs,
):
    """Ruft `func(*args, **kwargs)` mit Retry auf WinError 32.

    Backoff: 100ms, 200ms, 400ms, 800ms, 1600ms (sum ~3.1s). Wenn nach
    `attempts` Versuchen weiterhin Lock: re-raise. Bei nicht-lock-OSError
    sofort durchlassen (kein Retry, kein Verstecken).
    """
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return func(*args, **kwargs)
        except OSError as exc:
            if not _is_windows_file_lock_error(exc):
                raise
            last_exc = exc
            if i == attempts - 1:
                break
            delay = base_delay_s * (2 ** i)
            logger.warning(
                "B-219 Retry %d/%d nach WinError 32 fuer %s (warte %.0fms): %s",
                i + 1, attempts, operation, delay * 1000, exc,
            )
            _time_for_retry.sleep(delay)
    # Alle Retries erschoepft.
    assert last_exc is not None
    raise last_exc


# B-505: stderr-Signaturen, die auf einen NVENC-/Treiber-Fehler hindeuten
# (Sessions erschoepft, nvcuda.dll nicht ladbar, kein NVENC-Device) — nur
# dann ist ein libx264-CPU-Retry sinnvoll; andere FFmpeg-Fehler (kaputte
# Quelle etc.) wuerden auf CPU genauso scheitern.
_NVENC_FAILURE_SIGNATURES = (
    "openencodesessionex",
    "nvcuda",
    "no nvenc capable devices",
    "cannot load nvenc",
)


def _is_nvenc_failure(stderr: str) -> bool:
    """True wenn FFmpeg-stderr eine bekannte NVENC-Fehlersignatur enthaelt."""
    low = (stderr or "").lower()
    return any(sig in low for sig in _NVENC_FAILURE_SIGNATURES)


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
            # B-219: stat() + unlink() koennen mit WinError 32 fehlschlagen,
            # wenn Pipeline-Worker den Handle gerade noch hält (cv2.release
            # ist auf Windows nicht-instantan, FFmpeg-Subprocess flush, AV-
            # Scanner). Retry-mit-Backoff loest das transient.
            def _stat_safe():
                return proxy_path.stat()
            try:
                if proxy_path.exists():
                    info = _retry_on_file_lock("proxy stat", _stat_safe)
                    if info.st_size > 0:
                        return str(proxy_path.resolve())
                    # 0-byte proxy: muss unlink'd werden um neu zu erstellen.
                    logger.info(
                        "[VideoAnalyzer] WARNUNG: 0-Byte Proxy gefunden, wird neu erstellt: %s",
                        proxy_path,
                    )
                    _retry_on_file_lock(
                        "proxy unlink (0-byte)",
                        proxy_path.unlink, missing_ok=True,
                    )
            except OSError as exc:
                if _is_windows_file_lock_error(exc):
                    # Endgueltig blockiert: Datei ist auch nach Retries gelockt.
                    # Best effort: gib den vorhandenen Pfad zurueck wenn er
                    # nicht-leer ist; sonst raise als FFmpegError.
                    if proxy_path.exists():
                        try:
                            if proxy_path.stat().st_size > 0:
                                logger.warning(
                                    "B-219: Proxy %s persistent gelockt, aber size>0 — "
                                    "verwende vorhandenen Proxy.", proxy_path,
                                )
                                return str(proxy_path.resolve())
                        except OSError:
                            pass
                    raise FFmpegError(
                        f"Proxy-Datei dauerhaft gelockt von anderem Prozess "
                        f"(Antivirus/Indexer?): {proxy_path}",
                        returncode=-1,
                        stderr=str(exc),
                    ) from exc
                raise

            if progress_cb:
                progress_cb(20, "FFmpeg Proxy-Encoding...")

            nvenc_cmd = [
                _FFMPEG, "-y", "-i", file_path,
                "-vf", f"scale=-2:{target_height}",
                "-c:v", "h264_nvenc", "-preset", "p1",
                "-rc", "vbr", "-cq", "28", "-b:v", "0",
                "-c:a", "aac", "-b:a", "128k",
                str(proxy_path),
            ]

            # B-505: NVENC-Encode app-weit serialisieren — gleicher
            # GpuSerializer wie export_service._run_ffmpeg und
            # convert_service. Die GTX 1060 (Pascal) erlaubt nur 2-3
            # NVENC-Sessions; parallele Encodes enden in
            # "OpenEncodeSessionEx failed". Lock NUR um den
            # Subprocess-Lauf — die Datei-Checks oben bleiben lockfrei.
            try:
                from services.brain.gpu_serializer import get_default_serializer
                with get_default_serializer().acquire("proxy_encode"):
                    self._run_proxy_encode(nvenc_cmd, proxy_path, should_stop)
            except FFmpegError as exc:
                if not _is_nvenc_failure(getattr(exc, "stderr", None) or ""):
                    raise
                if require_nvenc():
                    raise
                # B-505: einmaliger CPU-Retry bei NVENC-Signatur (Sessions
                # erschoepft / nvcuda nicht ladbar). libx264 ist CPU-only
                # und braucht keinen GPU-Lock (GPU-Hartregel: kein CUDA-
                # Backend verfuegbar -> CPU erlaubt).
                logger.warning(
                    "B-505: NVENC-Proxy-Encode fehlgeschlagen (NVENC-Signatur "
                    "in stderr) -> einmaliger libx264-CPU-Retry fuer %s",
                    file_path,
                )
                if progress_cb:
                    progress_cb(20, "FFmpeg Proxy-Encoding (CPU-Fallback)...")
                cpu_cmd = [
                    _FFMPEG, "-y", "-i", file_path,
                    "-vf", f"scale=-2:{target_height}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                    "-c:a", "aac", "-b:a", "128k",
                    str(proxy_path),
                ]
                self._run_proxy_encode(cpu_cmd, proxy_path, should_stop)

            if progress_cb:
                progress_cb(100, "Proxy fertig")
            return str(proxy_path.resolve())

    def _run_proxy_encode(self, cmd: list, proxy_path: Path, should_stop) -> None:
        """Fuehrt einen Proxy-FFmpeg-Encode aus (Popen + Cancel/Timeout-Loop).

        B-505: aus ``create_proxy`` extrahiert, damit NVENC-Lauf und
        libx264-CPU-Retry denselben Lauf-/Fehlerpfad nutzen. Wirft
        ``FFmpegError`` (rc != 0 oder 0-Byte-Output),
        ``subprocess.TimeoutExpired`` (Render-Timeout) oder
        ``RuntimeError`` (User-Cancel).
        """
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        import tempfile as _tempfile
        import time as _time
        stderr_file = _tempfile.TemporaryFile(
            mode="w+",
            encoding="utf-8",
            errors="replace",
        )
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
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
                try:
                    proc.wait(timeout=2.0)
                except (subprocess.TimeoutExpired, AttributeError):
                    pass
                # B-219: unlink kann mit WinError 32 failen wenn FFmpeg
                # den Handle noch nicht freigegeben hat. Retry.
                try:
                    _retry_on_file_lock(
                        "proxy unlink (timeout)",
                        proxy_path.unlink, missing_ok=True,
                    )
                except OSError:
                    pass  # Best effort — Timeout ist eh schon der Fehler.
                stderr_file.close()
                raise subprocess.TimeoutExpired(cmd, FFMPEG_RENDER_TIMEOUT_SEC)
            _time.sleep(0.5)

        proc.communicate()
        stderr_file.seek(0)
        stderr = stderr_file.read()
        stderr_file.close()

        if cancelled:
            # B-219: gleiches Pattern, retry-with-backoff
            try:
                _retry_on_file_lock(
                    "proxy unlink (cancel)",
                    proxy_path.unlink, missing_ok=True,
                )
            except OSError:
                pass
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
            logger.info("[VideoAnalyzer] FFmpeg lief durch (rc=0), aber Proxy ist 0 Bytes oder fehlt!")
            logger.info(f"[VideoAnalyzer] stderr: {_sanitize_ffmpeg_error(stderr)}")
            # B-219: retry-on-lock — gleiches Problem.
            try:
                _retry_on_file_lock(
                    "proxy unlink (0-byte after ffmpeg)",
                    proxy_path.unlink, missing_ok=True,
                )
            except OSError:
                pass
            raise FFmpegError(
                f"Proxy ist 0 Bytes. FFmpeg stderr: {_sanitize_ffmpeg_error(stderr)}",
                returncode=0,
                stderr=stderr,
            )

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
