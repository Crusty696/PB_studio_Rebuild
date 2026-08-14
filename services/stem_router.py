"""Stem Router — central routing table + streaming mix helper.

audio-analysis-v2: Hybride Architektur mit zielgerichtetem Stem-Routing.
Entscheidet pro Service ob Original-Mix oder welche Stem-Kombination
verwendet wird. Mix-Helper streamt Stems chunk-weise um RAM-Limit
(Original + N Stems gleichzeitig im Speicher = verboten) einzuhalten.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import soundfile as sf  # type: ignore
    _HAS_SOUNDFILE = True
except ImportError:
    sf = None  # type: ignore[assignment]
    _HAS_SOUNDFILE = False

from services.audio_constants import STEM_NAMES

log = logging.getLogger(__name__)

# Service-Name -> benoetigte Stem-Liste. None == Original-Mix.
SERVICE_ROUTING: dict[str, tuple[str, ...] | None] = {
    "beat_this":          None,
    "lufs":               None,
    "audio_classify":     None,
    "spectral_mastering": None,
    "av_pacing":          None,
    "waveform":           None,
    "onset_rhythm":       ("drums",),
    "key_detection":      ("bass", "other"),
    "drop_detection":     ("bass", "drums", "vocals"),
}


def select_input(
    service: str,
    original_path: str,
    stem_paths: dict[str, str] | None,
) -> str | dict[str, str]:
    """Liefert entweder Original-Pfad (str) oder dict mit benoetigten Stem-Pfaden.

    Fallback-Verhalten: wenn Stems fehlen oder unvollstaendig sind, geben wir
    den Original-Pfad zurueck und loggen Warning. Kein hard-fail (Q-E Default).
    """
    needed = SERVICE_ROUTING.get(service)
    if needed is None:
        return original_path
    if not stem_paths:
        return original_path
    missing = [s for s in needed if s not in stem_paths]
    if missing:
        log.warning(
            "stem_router: service=%s missing stems %s -> fallback original",
            service, missing,
        )
        return original_path
    return {s: stem_paths[s] for s in needed}


def _active_project_root() -> Path | None:
    """Aktuelles Projekt-Root, oder None wenn die Session nicht importierbar ist."""
    try:
        import database.session as _session
    except ImportError:  # pragma: no cover - nur in kaputter Umgebung
        log.warning("stem_router: database.session nicht importierbar")
        return None
    root = getattr(_session, "APP_ROOT", None)
    return Path(root) if root else None


def resolve_stem_path(stored_path: str | Path | None) -> str | None:
    """Bindet einen gespeicherten Stem-Pfad an das aktive Projekt (B-822).

    ``audio_tracks.stem_*_path`` speichert absolute Pfade. Wird ein Projekt
    kopiert oder verschoben, zeigen sie weiter auf den alten Ort — und weil die
    Dateien dort meist noch liegen, greifen alle ``Path(p).exists()``-Pruefungen
    beherzt daneben. Im Live-Run vom 2026-08-14 las ein isoliertes Testprojekt
    dadurch Stems aus einem Host-Ordner, obwohl dieselben Dateien im Projekt
    lagen.

    Regeln:

    - Pfad liegt im aktiven Projekt und existiert -> unveraendert zurueck.
    - Pfad liegt ausserhalb, aber dieselbe projektrelative Ablage existiert
      unterhalb des aktiven Projekts -> der projektinterne Pfad.
    - Sonst ``None``. Bewusst kein Zugriff nach draussen: ein fehlendes
      Artefakt ist ehrlicher als ein fremdes, und die Stem-Stage heilt sich
      ohnehin selbst.

    Ohne bekanntes Projekt-Root faellt die Funktion auf reine
    Existenzpruefung zurueck, damit headless-Tests und Skripte weiterlaufen.
    """
    if not stored_path:
        return None
    path = Path(stored_path)
    root = _active_project_root()
    if root is None:
        return str(path) if path.is_file() else None

    try:
        inside = path.is_relative_to(root)
    except (OSError, ValueError):  # pragma: no cover - exotische Pfade
        inside = False
    if inside:
        return str(path) if path.is_file() else None

    # Ausserhalb: dieselbe Ablage unterhalb des aktiven Projekts suchen.
    parts = path.parts
    for idx in range(len(parts) - 1, -1, -1):
        if parts[idx].lower() == "storage":
            candidate = root.joinpath(*parts[idx:])
            if candidate.is_file():
                log.info(
                    "stem_router: B-822 Stem-Pfad auf aktives Projekt umgebogen: %s -> %s",
                    path, candidate,
                )
                return str(candidate)
            break

    log.warning(
        "stem_router: B-822 Stem-Pfad liegt ausserhalb des aktiven Projekts und "
        "hat dort keine Entsprechung — wird als fehlend behandelt: %s",
        path,
    )
    return None


def points_outside_project(stored_path: str | Path | None) -> bool:
    """True, wenn ein gespeicherter Pfad nachweislich aus dem Projekt herausfuehrt.

    Schwaechere Variante von :func:`resolve_stem_path` fuer Stellen, die nur
    beurteilen, ob ein Artefakt zu diesem Projekt *gehoert*, ohne es zu oeffnen
    — etwa die Statusinferenz. Sie prueft bewusst NICHT, ob die Datei existiert:
    ein relativer oder projektinterner Pfad gilt weiter als zugehoerig, auch
    wenn die Datei gerade fehlt (B-461 reconciled solche Faelle absichtlich).

    Nur ein absoluter Pfad ausserhalb des aktiven Projekt-Roots ist fremd.
    """
    if not stored_path:
        return False
    path = Path(stored_path)
    if not path.is_absolute():
        return False
    root = _active_project_root()
    if root is None:
        return False
    try:
        return not path.is_relative_to(root)
    except (OSError, ValueError):  # pragma: no cover - exotische Pfade
        return False


def resolve_stem_paths(
    stored: dict[str, str | None] | None,
) -> dict[str, str]:
    """``resolve_stem_path`` fuer ein ganzes Stem-Mapping.

    Nicht aufloesbare Eintraege fallen raus statt als fremder Pfad
    durchgereicht zu werden.
    """
    if not stored:
        return {}
    resolved: dict[str, str] = {}
    for name, value in stored.items():
        actual = resolve_stem_path(value)
        if actual:
            resolved[name] = actual
    return resolved


def get_stem_paths(track_id: int) -> dict[str, str] | None:
    """Liefert dict mit existierenden Stem-Pfaden fuer einen Track, oder None.

    Erwartet Layout: <APP_ROOT>/storage/stems/<track_id>/{vocals,drums,bass,other}.wav
    (= aktueller Demucs-Output von StemSeparator.separate()).
    """
    try:
        from database.session import APP_ROOT
    except ImportError:
        log.warning("stem_router: database.session.APP_ROOT not importable")
        return None
    stems_dir = Path(APP_ROOT) / "storage" / "stems" / str(track_id)
    if not stems_dir.exists():
        return None
    paths: dict[str, str] = {}
    for name in STEM_NAMES:
        p = stems_dir / f"{name}.wav"
        if p.exists():
            paths[name] = str(p)
    if len(paths) != len(STEM_NAMES):
        log.debug("stem_router: only %d/%d stems present for track %s",
                  len(paths), len(STEM_NAMES), track_id)
        return paths if paths else None
    return paths


def mix_stems_streaming(
    stem_paths: Iterable[str],
    out_path: str,
    chunk_sec: float = 30.0,
) -> str:
    """Mischt N Stem-WAVs in eine neue WAV-Datei via Streaming-Chunks.

    Hartregel: nie >1 Stem-Chunk gleichzeitig komplett im RAM. Liest chunk_sec
    parallel aus allen Stems, summiert (Soft-Clip via tanh), schreibt.

    Returns: out_path.
    Raises: ValueError wenn Stems unterschiedliche sr/channels haben,
            RuntimeError wenn soundfile fehlt.
    """
    if not _HAS_SOUNDFILE:
        raise RuntimeError("mix_stems_streaming requires soundfile package")

    paths = list(stem_paths)
    if not paths:
        raise ValueError("mix_stems_streaming: empty stem_paths")

    readers = [sf.SoundFile(p) for p in paths]
    try:
        sr = readers[0].samplerate
        channels = readers[0].channels
        for r in readers[1:]:
            if r.samplerate != sr or r.channels != channels:
                raise ValueError(
                    f"Stem sr/channels mismatch: {r.samplerate}/{r.channels} vs {sr}/{channels}"
                )
        frames_per_chunk = max(1, int(chunk_sec * sr))
        out_dir = Path(out_path).parent
        if out_dir and not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
        with sf.SoundFile(out_path, mode="w", samplerate=sr,
                          channels=channels, subtype="PCM_16") as out:
            while True:
                chunks = [
                    r.read(frames_per_chunk, dtype="float32", always_2d=True)
                    for r in readers
                ]
                length = min(c.shape[0] for c in chunks)
                if length == 0:
                    break
                stacked = np.stack([c[:length] for c in chunks], axis=0)
                mix = np.sum(stacked, axis=0)
                # Soft-Clip auf [-1, 1] um Clipping nach Summation zu vermeiden
                mix = np.tanh(mix)
                out.write(mix)
    finally:
        for r in readers:
            try:
                r.close()
            except Exception:  # noqa: BLE001
                pass
    return out_path


def mix_bass_other(
    stem_paths: dict[str, str],
    out_path: str,
    chunk_sec: float = 30.0,
) -> str:
    """Spezieller Mixer fuer Key-Detection: bass + other Sum (Q3 Sub-Antwort).

    Voraussetzung: stem_paths enthaelt mindestens 'bass' und 'other'.
    """
    needed = ("bass", "other")
    missing = [s for s in needed if s not in stem_paths]
    if missing:
        raise KeyError(f"mix_bass_other: missing stems {missing}")
    return mix_stems_streaming([stem_paths[s] for s in needed], out_path, chunk_sec=chunk_sec)
