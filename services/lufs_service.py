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
        except json.JSONDecodeError:
            pass

    # Strategy 2: Broader — find the very last {...} block.
    brace_start = stderr.rfind("{")
    brace_end = stderr.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(stderr[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

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

    def analyze(self, file_path: str) -> LUFSResult:  # noqa: C901
        """Analysiert die Lautstaerke einer Audio-Datei.

        Uses FFmpeg's ``loudnorm`` filter (EBU R128) with
        ``print_format=json`` to obtain:
        - Integrated loudness (input_i)
        - Loudness range / LRA (input_lra)
        - True peak (input_tp)
        - Short-term maximum (estimated from integrated + LRA/2)

        Args:
            file_path: Pfad zur Audio-Datei

        Returns:
            LUFSResult mit Integrated/Short-Term/Range/TruePeak
        """
        from services.audio_constants import FFMPEG_TIMEOUT_SEC, ST_MAX_HEADROOM_DB

        fallback = LUFSResult(
            integrated=-14.0,
            short_term_max=-10.0,
            loudness_range=8.0,
            true_peak=-1.0,
        )

        try:
            # ------------------------------------------------------------------
            # 1. Run FFmpeg loudnorm analysis pass
            # ------------------------------------------------------------------
            cmd = [
                _FFMPEG,
                "-hide_banner",
                "-i", file_path,
                "-af", "loudnorm=print_format=json",
                "-f", "null",
                "-",
            ]

            log.debug("LUFS-Analyse Kommando: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=FFMPEG_TIMEOUT_SEC,
                # On Windows, hide the console window for subprocess
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            # FFmpeg writes loudnorm output to stderr (exit code may be 0 or 1
            # depending on the version — we rely on the JSON being present).
            stderr = result.stderr or ""

            if result.returncode != 0 and "input_i" not in stderr:
                log.error(
                    "FFmpeg loudnorm fehlgeschlagen (exit=%d): %s",
                    result.returncode,
                    stderr[-500:] if stderr else "(kein stderr)",
                )
                return fallback

            # ------------------------------------------------------------------
            # 2. Parse the JSON block from stderr
            # ------------------------------------------------------------------
            data = _parse_loudnorm_json(stderr)
            if data is None:
                log.error(
                    "Konnte loudnorm-JSON nicht aus FFmpeg-Ausgabe parsen. "
                    "stderr (letzte 500 Zeichen): %s",
                    stderr[-500:],
                )
                return fallback

            # ------------------------------------------------------------------
            # 3. Extract values
            # ------------------------------------------------------------------
            integrated = _safe_float(data.get("input_i"), -14.0)
            loudness_range = _safe_float(data.get("input_lra"), 8.0)
            true_peak = _safe_float(data.get("input_tp"), -1.0)

            # Short-term max: FFmpeg loudnorm doesn't directly report this.
            # A practical estimate: integrated + half the loudness range
            # gives a reasonable approximation of the short-term maximum.
            # Clamp so it doesn't exceed true peak by too much.
            short_term_max = integrated + (loudness_range / 2.0)
            # Short-term max should not exceed true peak + headroom (sanity)
            short_term_max = min(short_term_max, true_peak + ST_MAX_HEADROOM_DB)

            log.info(
                "LUFS-Analyse: integrated=%.1f, LRA=%.1f, TP=%.1f, ST_max=%.1f — %s",
                integrated, loudness_range, true_peak, short_term_max, file_path,
            )

            return LUFSResult(
                integrated=round(integrated, 2),
                short_term_max=round(short_term_max, 2),
                loudness_range=round(loudness_range, 2),
                true_peak=round(true_peak, 2),
            )

        except FileNotFoundError:
            log.error(
                "FFmpeg nicht gefunden ('%s'). Bitte FFmpeg installieren oder "
                "FFMPEG_PATH Umgebungsvariable setzen.",
                _FFMPEG,
            )
            return fallback

        except subprocess.TimeoutExpired:
            log.error("FFmpeg LUFS-Analyse Timeout (120s) fuer: %s", file_path)
            return fallback

        except Exception:
            log.exception("Unerwarteter Fehler bei LUFS-Analyse fuer: %s", file_path)
            return fallback
