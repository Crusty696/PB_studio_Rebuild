"""LUFS Analysis Service — EBU R128 Loudness Measurement.

Misst die wahrgenommene Lautstaerke eines Audio-Tracks nach EBU R128 Standard.
Gibt Integrated LUFS, Short-Term LUFS Range und True Peak zurueck.

Nutzt FFmpeg's loudnorm Filter fuer praezise EBU R128 Messung.
"""

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)

# FFmpeg binary — honour env override (same convention as convert_service.py)
_FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")


@dataclass
class LUFSResult:
    """Ergebnis der LUFS-Analyse."""
    integrated: float       # Integrated LUFS (z.B. -8.2)
    short_term_max: float   # Short-Term Maximum (z.B. -5.1)
    loudness_range: float   # LRA in LU (z.B. 12.3)
    true_peak: float        # True Peak in dBTP (z.B. -0.3)
    broadcast_compliant: bool = False  # EBU R128 Broadcast-Standard (-23 LUFS ±1 LU)
    streaming_compliant: bool = False  # Streaming-konform (-16 bis -9 LUFS, TP ≤ -1 dBTP)


def _parse_loudnorm_json(stderr: str) -> dict | None:
    """Extract the JSON block that FFmpeg's loudnorm filter prints to stderr.

    The loudnorm filter emits a JSON object after the line containing
    ``Parsed_loudnorm`` (or simply as the last ``{...}`` block in the
    output).  We try both heuristics.
    """
    # Strategy 1: Find the last JSON-like block in stderr.
    # FFmpeg prints it at the very end, e.g.:
    #   {
    #       "input_i" : "-14.02",
    #       ...
    #   }
    # We grab everything from the last '{' to the last '}'.
    matches = list(re.finditer(
        r"\{[^{}]*\"input_i\"[^{}]*\}",
        stderr,
        re.DOTALL,
    ))
    if matches:
        try:
            return json.loads(matches[-1].group())
        except json.JSONDecodeError as e:
            log.warning("Parsing loudnorm JSON from regex match: %s", e)

    # Strategy 2: Broader — find the very last {...} block.
    brace_start = stderr.rfind("{")
    brace_end = stderr.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(stderr[brace_start:brace_end + 1])
        except json.JSONDecodeError as e:
            log.warning("Parsing loudnorm JSON from brace extraction: %s", e)

    return None


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float (FFmpeg may return strings or '-inf')."""
    from services.audio_constants import MIN_LUFS_DB, MAX_LUFS_DB
    try:
        f = float(value)
        if f == float("-inf"):
            return MIN_LUFS_DB
        if f == float("inf"):
            return MAX_LUFS_DB
        return f
    except (TypeError, ValueError):
        return default


class LUFSService:
    """Misst die Lautstaerke nach EBU R128 Standard via FFmpeg loudnorm."""

    def analyze(self, file_path: str) -> LUFSResult:
        """Analysiert die Lautstaerke einer Audio-Datei.

        Uses FFmpeg's ``loudnorm`` filter (EBU R128) to obtain integrated
        loudness, loudness range, true peak and an estimated short-term max.

        Args:
            file_path: Pfad zur Audio-Datei

        Returns:
            LUFSResult mit Integrated/Short-Term/Range/TruePeak
        """
        fallback = LUFSResult(
            integrated=-14.0,
            short_term_max=-10.0,
            loudness_range=8.0,
            true_peak=-1.0,
        )

        try:
            stderr = self._run_ffmpeg(file_path)
            if stderr is None:
                return fallback

            data = _parse_loudnorm_json(stderr)
            if data is None:
                log.error(
                    "Konnte loudnorm-JSON nicht aus FFmpeg-Ausgabe parsen. "
                    "stderr (letzte 500 Zeichen): %s",
                    stderr[-500:],
                )
                return fallback

            return self._extract_values(data, file_path)

        except FileNotFoundError:
            log.error(
                "FFmpeg nicht gefunden ('%s'). Bitte FFmpeg installieren oder "
                "FFMPEG_PATH Umgebungsvariable setzen.",
                _FFMPEG,
            )
            return fallback

        except subprocess.TimeoutExpired:
            log.error("FFmpeg LUFS-Analyse Timeout fuer: %s", file_path)
            return fallback

        except Exception as e:
            log.exception("Unerwarteter Fehler bei LUFS-Analyse fuer: %s", file_path)
            log.warning("analyze(): fallback result returned due to: %s", e)
            return fallback

    def _run_ffmpeg(self, file_path: str) -> str | None:
        """Fuehrt FFmpeg loudnorm Analyse-Pass aus und gibt stderr zurueck.

        Returns:
            stderr-Output bei Erfolg, None bei Fehler.
        """
        from services.audio_constants import FFMPEG_TIMEOUT_SEC

        # Dynamisches Timeout: Grosse Dateien (DJ-Sets, 2-3h) brauchen mehr Zeit.
        # Basis: FFMPEG_TIMEOUT_SEC (120s), skaliert mit Dateigroesse (~2s pro MB).
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            timeout = max(FFMPEG_TIMEOUT_SEC, int(file_size_mb * 2) + 60)
        except OSError:
            timeout = FFMPEG_TIMEOUT_SEC

        cmd = [
            _FFMPEG,
            "-hide_banner",
            "-i", file_path,
            "-af", "loudnorm=print_format=json",
            "-f", "null",
            "-",
        ]

        log.debug("LUFS-Analyse Kommando (timeout=%ds): %s", timeout, " ".join(cmd))

        # C-03 Fix: encoding + errors fuer robustes Decoding (FFmpeg kann
        # Nicht-UTF-8-Zeichen in Dateinamen/Metadaten ausgeben)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        stderr = result.stderr or ""

        # B-010 Fix: Pruefe returncode ZUERST — nur wenn returncode == 0 kann JSON geparst werden
        if result.returncode != 0:
            log.error(
                "FFmpeg loudnorm fehlgeschlagen (exit=%d): %s",
                result.returncode,
                stderr[-500:] if stderr else "(kein stderr)",
            )
            return None

        return stderr

    @staticmethod
    def _extract_values(data: dict, file_path: str) -> LUFSResult:
        """Extrahiert LUFS-Werte aus dem geparsten loudnorm-JSON.

        Args:
            data: Geparster JSON-Block von FFmpeg loudnorm
            file_path: Pfad zur Audio-Datei (fuer Logging)

        Returns:
            LUFSResult mit gerundeten Werten und EBU R128 Compliance-Status
        """
        from services.audio_constants import (
            ST_MAX_HEADROOM_DB,
            EBU_R128_BROADCAST_TARGET, EBU_R128_BROADCAST_TOLERANCE,
            EBU_R128_STREAMING_MIN, EBU_R128_STREAMING_MAX, EBU_TRUE_PEAK_MAX,
        )

        integrated = _safe_float(data.get("input_i"), -14.0)
        loudness_range = _safe_float(data.get("input_lra"), 8.0)
        true_peak = _safe_float(data.get("input_tp"), -1.0)

        # F-01: APPROXIMATION — kein exakter EBU R128 Short-Term LUFS Wert!
        # Formel: integrated + 0.8 * LRA (LRA = Differenz zwischen 10. und 95. Perzentil
        # der Short-Term Loudness nach EBU R128). Der Faktor 0.8 schaetzt das 95. Perzentil.
        # Fuer exakte Werte muesste FFmpeg mit "-af ebur128=peak=true" laufen und die
        # Short-Term LUFS Zeitreihe geparst werden. Das Feld heisst "short_term_max",
        # sollte aber als "short_term_max_approx" verstanden werden.
        short_term_max = integrated + (loudness_range * 0.8)
        short_term_max = min(short_term_max, true_peak + ST_MAX_HEADROOM_DB)

        # EBU R128 Compliance-Pruefung
        broadcast_compliant = (
            EBU_R128_BROADCAST_TARGET - EBU_R128_BROADCAST_TOLERANCE
            <= integrated
            <= EBU_R128_BROADCAST_TARGET + EBU_R128_BROADCAST_TOLERANCE
            and true_peak <= EBU_TRUE_PEAK_MAX
        )
        streaming_compliant = (
            EBU_R128_STREAMING_MIN <= integrated <= EBU_R128_STREAMING_MAX
            and true_peak <= EBU_TRUE_PEAK_MAX
        )

        log.info(
            "LUFS-Analyse: integrated=%.1f, LRA=%.1f, TP=%.1f, ST_max=%.1f, "
            "broadcast=%s, streaming=%s — %s",
            integrated, loudness_range, true_peak, short_term_max,
            broadcast_compliant, streaming_compliant, file_path,
        )

        return LUFSResult(
            integrated=round(integrated, 2),
            short_term_max=round(short_term_max, 2),
            loudness_range=round(loudness_range, 2),
            true_peak=round(true_peak, 2),
            broadcast_compliant=broadcast_compliant,
            streaming_compliant=streaming_compliant,
        )
