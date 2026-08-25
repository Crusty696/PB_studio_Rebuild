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
from services.video_encode_args import nvenc_video_args, libx264_fallback_args


class ExportCancelled(RuntimeError):
    """Expected cooperative user cancel; never eligible for render fallback."""

logger = logging.getLogger("services.export_service")


# 10-bit-Schutz: h264_nvenc auf Pascal (GTX 1060) ist 8-bit-only — eine
# 10-bit-Quelle (yuv420p10le / p010le / HEVC Main10) laesst den NVENC-Init
# mit "10 bit encode not supported" scheitern. Der Convert-Pfad erzwingt
# deshalb seit B-584 ``-pix_fmt yuv420p`` (services/convert_service.py).
# Der Export hatte diesen Schutz nie. Hier wird er unkonditional an JEDEN
# Export-Re-Encode gehaengt (nicht an Stream-Copy — ``_video_encode_args``
# wird ausschliesslich auf echten Re-Encode-Pfaden benutzt):
#   * 8-bit yuv420p-Quelle  -> No-Op (Ziel == Ist)
#   * 10-bit / 422 / 444    -> Downconvert auf 8-bit 4:2:0
# Das entspricht ausserdem ``_CONCAT_TARGET_PIX_FMT`` ("yuv420p") aus
# services/export/_common.py — nur so bleibt der anschliessende
# ``-c:v copy``-Concat pixelformat-konsistent (auch im libx264-CPU-Fallback,
# der sonst je nach Quelle einen 10-bit-Temp erzeugen wuerde).
_PIX_FMT_ARGS = ["-pix_fmt", "yuv420p"]


# Export-Presets: bis dato war die UI-Combo eine Attrappe — Bitrate/Qualitaet
# waren hart auf "p4 / cq 18 / 15M" verdrahtet, "Draft" und "Hohe Qualitaet"
# erzeugten dieselbe Datei. Die Keys entsprechen der ``userData`` der
# ``preset_combo`` in ui/workspaces/deliver_workspace.py.
#
# "standard" traegt bewusst EXAKT die bisherigen Werte (p4/cq18/15M bzw.
# libx264 fast/crf23) — Default-Verhalten bleibt damit unveraendert.
_EXPORT_PRESETS: dict[str, dict] = {
    "standard": {
        "nvenc_preset": "p4", "cq": 18, "bitrate": "15M",
        "x264_preset": "fast", "crf": 23,
    },
    "high": {
        "nvenc_preset": "p6", "cq": 16, "bitrate": "25M",
        "x264_preset": "slow", "crf": 18,
    },
    "draft": {
        "nvenc_preset": "p1", "cq": 28, "bitrate": "6M",
        "x264_preset": "veryfast", "crf": 28,
    },
}
_DEFAULT_EXPORT_PRESET = "standard"

# Modul-globaler aktiver Preset-Key. Wird vom ExportController unmittelbar
# VOR dem Worker-Start gesetzt (GUI-Thread) und im Worker-Thread beim Bauen
# der ffmpeg-Kommandos gelesen. Ein sauberes Durchreichen als Parameter
# (Controller -> ExportWorker -> export_timeline) wuerde workers/import_export.py
# beruehren; das steht fuer diese Aufgabe nicht zur Verfuegung.
_active_export_preset = _DEFAULT_EXPORT_PRESET


def set_export_preset(preset_key: str | None) -> str:
    """Setzt den aktiven Export-Preset-Key. Unbekannt/None -> "standard"."""
    global _active_export_preset
    key = (preset_key or "").strip().lower()
    if key not in _EXPORT_PRESETS:
        if key:
            logger.warning(
                "Unbekanntes Export-Preset '%s' — falle auf '%s' zurueck.",
                preset_key, _DEFAULT_EXPORT_PRESET,
            )
        key = _DEFAULT_EXPORT_PRESET
    _active_export_preset = key
    return key


def get_export_preset() -> str:
    """Liefert den aktuell aktiven Export-Preset-Key."""
    return _active_export_preset


def _video_encode_args(preset_key: str | None = None) -> list[str]:
    """Video-Codec-Args fuer Export-Re-Encodes (F-7 / B-339).

    Bevorzugt ``h264_nvenc`` gemaess GPU-Hartregel (GTX 1060), faellt auf
    ``libx264`` (CPU) zurueck wenn NVENC nicht verfuegbar ist — so bleibt der
    Export ueberall lauffaehig. NVENC-Parameter spiegeln das erprobte
    ``master``-Preset aus ``convert_service``.

    ``preset_key`` waehlt die Qualitaetsstufe (siehe ``_EXPORT_PRESETS``);
    ohne Angabe gilt der via ``set_export_preset`` gesetzte aktive Key.
    Haengt in jedem Fall ``-pix_fmt yuv420p`` an (10-bit-Schutz, s.o.).
    """
    params = _EXPORT_PRESETS.get(
        (preset_key or _active_export_preset), _EXPORT_PRESETS[_DEFAULT_EXPORT_PRESET],
    )

    try:
        from services.convert_service import detect_nvenc
        nvenc_available = bool(detect_nvenc().get("h264_nvenc"))
    except Exception:
        nvenc_available = False

    if nvenc_available:
        return nvenc_video_args(
            params["nvenc_preset"], params["cq"], bitrate=params["bitrate"],
        ) + _PIX_FMT_ARGS

    logger.warning("NVENC (h264_nvenc) nicht verfuegbar! Timeline-Export weicht auf CPU (libx264) aus.")

    if require_nvenc():
        raise RuntimeError(
            required_message("h264_nvenc nicht verfuegbar; Export-CPU-Fallback verboten")
        )
    return libx264_fallback_args(params["x264_preset"], params["crf"]) + _PIX_FMT_ARGS


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
    Raises: ExportCancelled bei kooperativem User-Cancel.
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
            # B-706/F5: stdout wird bereits vom _progress_reader-Thread konsumiert.
            # ``communicate()`` wuerde stdout PARALLEL mitlesen -> die beiden Leser
            # teilen sich die Progress-Zeilen (ruckelnder LUFS-Balken). Stattdessen
            # stderr in einem EIGENEN Thread draINen und nur auf den Prozess warten:
            # beide Pipes werden nebenlaeufig geleert (kein 64KB-Pipe-Deadlock),
            # und stdout gehoert exklusiv dem _progress_reader.
            stderr_chunks: list[str] = []

            def _stderr_reader():
                try:
                    if process.stderr is not None:
                        for line in process.stderr:
                            stderr_chunks.append(line)
                except Exception as stderr_exc:  # broad: Reader darf nicht crashen
                    logger.debug("stderr reader exited: %s", stderr_exc)

            stderr_thread = threading.Thread(target=_stderr_reader, daemon=True)
            stderr_thread.start()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait()
                timeout_error = exc
            reader.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
            stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_chunks)
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
        raise ExportCancelled("LUFS-Normalisierung abgebrochen (User-Cancel)")
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
