"""AUFRAEUM B2 — Encode-Args + cancelbarer FFmpeg-Subprozess des Export-Service.

Reiner Verbatim-Code-Move aus ``services/export_service.py`` (kein
Logik-Change). Enthaelt die NVENC/libx264-Encoder-Arg-Wahl (GPU-Hartregel
GTX 1060) und den cancel-/progress-faehigen Subprozess-Runner. ``logger``
behaelt den Namen ``services.export_service`` (byte-gleiches Log-Routing).

Hinweis: ``_run_ffmpeg`` / ``_run_ffmpeg_impl`` bleiben bewusst in
``services/export_service.py`` (Monkeypatch-/caplog-Kompatibilitaet).
"""

import logging
import subprocess
import threading
import time

from services.timeout_constants import THREAD_JOIN_TIMEOUT_SEC
from services.ffmpeg_utils import subprocess_kwargs
from services.ffmpeg_utils import sanitize_ffmpeg_error as _sanitize_ffmpeg_error
from services.nvenc_policy import require_nvenc, required_message

logger = logging.getLogger("services.export_service")


def _video_encode_args() -> list[str]:
    """Video-Codec-Args fuer Export-Re-Encodes (F-7 / B-339).

    Bevorzugt ``h264_nvenc`` gemaess GPU-Hartregel (GTX 1060), faellt auf
    ``libx264`` (CPU) zurueck wenn NVENC nicht verfuegbar ist — so bleibt der
    Export ueberall lauffaehig. NVENC-Parameter spiegeln das erprobte
    ``master``-Preset aus ``convert_service``.
    """
    try:
        from services.convert_service import detect_nvenc
        nvenc_available = bool(detect_nvenc().get("h264_nvenc"))
    except Exception:
        nvenc_available = False

    if nvenc_available:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                "-cq", "18", "-b:v", "15M"]

    logger.warning("NVENC (h264_nvenc) nicht verfuegbar! Timeline-Export weicht auf CPU (libx264) aus.")

    if require_nvenc():
        raise RuntimeError(
            required_message("h264_nvenc nicht verfuegbar; Export-CPU-Fallback verboten")
        )
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]


def _run_subprocess_cancellable(
    cmd: list[str], timeout: int, cancel_check=None,
    progress_cb=None, total_duration: float = 0.0,
    progress_base_pct: int = 0, progress_range_pct: int = 100,
):
    """B-125: ``subprocess.run``-aequivalent mit Cancel-Watchdog.

    Faehrt cmd via Popen, polled cancel_check alle 200ms, terminiert
    den Process bei True. Wenn cancel_check None ist, faellt es auf
    blockierendes ``subprocess.run`` zurueck.

    B-086: optional ``progress_cb(pct, msg)`` parsed
    ``out_time_ms=...``-Lines aus stdout (FFmpeg ``-progress pipe:1``)
    und ruft den Callback waehrend des Laufs. ``total_duration`` ist
    die Audio-/Video-Dauer in Sekunden — sonst kann der Prozentwert
    nicht berechnet werden. ``progress_base_pct`` + ``progress_range_pct``
    erlauben einem Caller mit mehrphasigem Lauf (Pass1+Pass2) die
    inneren Prozente auf einen Bereich zu mappen (z.B. 50-100 fuer
    Pass2).

    Returns: subprocess.CompletedProcess (returncode/stdout/stderr).
    Raises: RuntimeError("LUFS-Normalisierung abgebrochen") bei Cancel.
    """
    kwargs: dict = subprocess_kwargs()

    if cancel_check is None and progress_cb is None:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", **kwargs,
        )

    process = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **kwargs,
    )
    cancelled = threading.Event()

    def _cancel_watch():
        while process.poll() is None:
            try:
                if cancel_check is not None and cancel_check():
                    cancelled.set()
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return
            except Exception as exc:  # broad: watchdog must keep running
                # B-167: nicht stumm zurueckkehren — sonst stirbt der Watchdog
                # bei einem temporaeren cancel_check-Fehler und der ffmpeg-Lauf
                # ist nicht mehr abbrechbar.
                logger.warning(
                    "[Cancel-Watch] cancel_check raised: %s — Watchdog endet.", exc,
                )
                return
            time.sleep(0.2)

    watchdog = threading.Thread(target=_cancel_watch, daemon=True)
    watchdog.start()

    # B-086: Progress-Stream-Reader liest stdout zeilenweise und parsed
    # ``out_time_ms`` aus dem ffmpeg ``-progress pipe:1`` Output. Laeuft
    # in einem eigenen Thread damit ``communicate`` nicht blockiert.
    stdout_lines: list[str] = []
    progress_active = (
        progress_cb is not None and total_duration > 0.0 and process.stdout is not None
    )

    def _progress_reader():
        try:
            for line in process.stdout:  # type: ignore[union-attr]
                stdout_lines.append(line)
                if not progress_active:
                    continue
                line = line.strip()
                if line.startswith("out_time_ms=") and progress_cb is not None:
                    try:
                        time_us = int(line.split("=", 1)[1])
                    except (ValueError, IndexError):
                        continue
                    current_sec = time_us / 1_000_000
                    if total_duration > 0:
                        inner_pct = max(0.0, min(1.0, current_sec / total_duration))
                        global_pct = int(
                            progress_base_pct + inner_pct * progress_range_pct
                        )
                        try:
                            progress_cb(min(99, global_pct), "")
                        except Exception as cb_exc:  # broad: ein Callback-Fehler darf den Run nicht killen
                            logger.debug("progress_cb raised: %s", cb_exc)
        except Exception as reader_exc:  # broad: Reader darf nicht crashen
            logger.debug("progress reader exited: %s", reader_exc)

    reader = None
    if progress_active or progress_cb is not None:
        reader = threading.Thread(target=_progress_reader, daemon=True)
        reader.start()

    timeout_error: subprocess.TimeoutExpired | None = None
    try:
        if reader is not None:
            # stdout wird im Reader-Thread gelesen — wir warten nur auf stderr.
            try:
                _, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                _, stderr = process.communicate()
                timeout_error = exc
            reader.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
            stdout = "".join(stdout_lines)
        else:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                stdout, stderr = process.communicate()
                timeout_error = exc
    finally:
        watchdog.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

    if cancelled.is_set():
        raise RuntimeError("LUFS-Normalisierung abgebrochen (User-Cancel)")
    if timeout_error is not None:
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output=stdout,
            stderr=stderr,
        )

    return subprocess.CompletedProcess(
        args=cmd, returncode=process.returncode,
        stdout=stdout, stderr=stderr,
    )
