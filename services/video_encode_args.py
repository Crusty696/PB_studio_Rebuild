"""AUFRAEUM B3 — zentrale Video-Encode-Argument-Bauer (h264_nvenc / libx264).

Konsolidiert die zuvor mehrfach inline gebauten Encoder-Arg-Listen
(``video_service`` Proxy-Encode, ``export/ffmpeg_runner`` Timeline-Export)
in EINE parametrisierte Quelle. Jeder Aufrufer uebergibt seine EXAKTEN
Parameter, sodass die erzeugten Listen byte-identisch zu vorher bleiben.

GPU-Hartregel (GTX 1060): ``h264_nvenc`` ist der einzige GPU-Encoder;
``libx264`` ist der reine CPU-Fallback. Diese Funktionen aendern KEINE
Default-Parameter — sie bauen nur die exakt uebergebenen Args.
"""

from __future__ import annotations


def nvenc_video_args(
    preset: str,
    cq: int | str,
    *,
    bitrate: str | None = None,
    maxrate: str | None = None,
    bufsize: str | None = None,
) -> list[str]:
    """Baut die ``h264_nvenc``-Video-Codec-Args (VBR/CQ).

    Reihenfolge exakt wie bisher inline: ``-c:v h264_nvenc -preset <preset>
    -rc vbr -cq <cq>`` gefolgt von den optionalen ``-b:v`` / ``-maxrate`` /
    ``-bufsize`` — nur wenn der Aufrufer sie uebergibt.
    """
    args = ["-c:v", "h264_nvenc", "-preset", preset, "-rc", "vbr", "-cq", str(cq)]
    if bitrate is not None:
        args += ["-b:v", bitrate]
    if maxrate is not None:
        args += ["-maxrate", maxrate]
    if bufsize is not None:
        args += ["-bufsize", bufsize]
    return args


def libx264_fallback_args(preset: str, crf: int | str) -> list[str]:
    """Baut die ``libx264``-CPU-Fallback-Args: ``-c:v libx264 -preset <preset>
    -crf <crf>``."""
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
