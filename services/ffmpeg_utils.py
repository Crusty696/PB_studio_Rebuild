"""Gemeinsame FFmpeg-/FFprobe-/Proxy-Helfer fuer Service-Module.

- ``sanitize_ffmpeg_error()``: stderr auf die letzten Zeilen kuerzen.
- ``proxy_dir()``: Proxy-Verzeichnis des aktuellen Projekts (lazy APP_ROOT).
- ``subprocess_kwargs()``: zentraler Ersatz fuer die Inline-Duplikate des
  CREATE_NO_WINDOW-Patterns (dict-Literal, Ternaer, getattr-Variante — auf
  win32 funktional identisch).
- ``probe_duration()``: ffprobe ``format=duration``-Probe.
- ``parse_frame_rate()``: ffprobe-Rational ("30/1") -> float fps
  (kanonische Semantik aus ``export_service._parse_frame_rate``).

Wichtig fuer Zyklusfreiheit: dieses Modul importiert auf Modul-Ebene KEINE
anderen ``services``-Module — ``services.startup_checks`` importiert
``subprocess_kwargs`` von hier (``get_ffprobe_bin`` wird nur lazy innerhalb
von ``probe_duration`` importiert).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages — strip full paths."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


def proxy_dir() -> Path:
    """Returns proxy directory for the current project (lazy APP_ROOT read)."""
    import database.session as _session
    return _session.APP_ROOT / "storage" / "proxies"


def subprocess_kwargs() -> dict:
    """Extra-kwargs fuer ``subprocess.run``/``Popen``.

    Auf Windows: ``creationflags=subprocess.CREATE_NO_WINDOW`` — verhindert
    das Aufblitzen eines Konsolenfensters bei ffmpeg/ffprobe-Aufrufen aus
    der GUI. Auf anderen Plattformen: leeres dict (entspricht dem Default
    ``creationflags=0``).

    Verwendung: ``subprocess.run(cmd, ..., **subprocess_kwargs())``.
    """
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def probe_duration(
    path: str,
    fallback: float = 0.0,
    *,
    timeout: float = 10.0,
    ffprobe_bin: str | None = None,
) -> float:
    """Ermittelt die Mediendauer in Sekunden via ffprobe (K7).

    Laeuft ``ffprobe -v error -show_entries format=duration -of
    default=noprint_wrappers=1:nokey=1``. Gibt ``fallback`` zurueck, wenn
    ffprobe mit rc != 0 endet oder keinen Wert liefert.

    Bewusst NICHT abgefangen (Callsites behalten ihre divergenten
    except-Listen, Log-Aufrufe und Fallbacks exakt):
    - ``subprocess``-Exceptions (TimeoutExpired, FileNotFoundError, OSError, ...)
    - ``ValueError`` beim float-Parse eines nicht-numerischen stdout ("N/A")

    Args:
        path: Mediendatei.
        fallback: Rueckgabewert bei rc != 0 / leerem stdout.
        timeout: Sekunden fuer ``subprocess.run``.
        ffprobe_bin: expliziter ffprobe-Pfad; None -> ``get_ffprobe_bin()``.
    """
    if ffprobe_bin is None:
        from services.startup_checks import get_ffprobe_bin
        ffprobe_bin = get_ffprobe_bin()
    result = subprocess.run(
        [
            ffprobe_bin, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
        **subprocess_kwargs(),
    )
    if result.returncode != 0:
        return fallback
    out = (result.stdout or "").strip()
    if not out:
        return fallback
    return float(out)


def parse_frame_rate(
    rate_str: str,
    default: float = 0.0,
    *,
    ndigits: int | None = None,
    strict: bool = False,
) -> float:
    """Parst ffprobe-Frame-Rate ("30/1", "30000/1001", "29.97") -> float fps (K7).

    Kanonische Semantik (ehem. ``export_service._parse_frame_rate``):
    Nenner <= 0 ("0/0", "0/1"-Zaehler bleibt regulaer) -> ``default``;
    nicht parsebar ("", "N/A") -> ``default`` bzw. bei ``strict=True``
    wird die ``ValueError``/``ZeroDivisionError`` re-raised (fuer Callsites,
    deren umgebende except-Struktur den Fehler selbst behandeln muss).

    Args:
        rate_str: Roh-String aus ffprobe (``r_frame_rate``/``avg_frame_rate``).
        default: Rueckgabe bei ungueltigem/unbekanntem Wert.
        ndigits: optionale Rundung (``round(fps, ndigits)``).
        strict: Parse-Fehler re-raisen statt ``default`` zu liefern.
    """
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            fps = float(num) / float(den) if float(den) > 0 else default
        else:
            fps = float(rate_str)
    except (ValueError, ZeroDivisionError):
        if strict:
            raise
        return default
    return round(fps, ndigits) if ndigits is not None else fps
