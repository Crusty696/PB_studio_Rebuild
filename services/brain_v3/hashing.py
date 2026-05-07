"""Brain V3 — Streaming-Hash fuer Audio/Video-Dateien.

Plan-Doc 06 Phase 1: media_hash (sha256) bei Audio/Video-Import.
Streaming-Hash fuer grosse Dateien (Chunks à 4 MB).

Der Hash dient als projekt-uebergreifender Cache-Key (siehe
embedding_cache.db). Identische Dateien → identischer Hash → kein
Re-Embedding noetig.

Diese Funktion ist V3-isoliert: sie modifiziert KEINE bestehenden
ClipInfo-Strukturen aus V1/V2, sondern berechnet rein und gibt zurueck.
Hooks im Audio/Video-Import-Pfad rufen das auf und persistieren das
Ergebnis in V3-eigene Tabellen.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

CHUNK_BYTES = 4 * 1024 * 1024  # 4 MB — Plan-Doc 06 Phase 1


def compute_media_hash(
    path: Path | str,
    chunk_bytes: int = CHUNK_BYTES,
    progress_cb: Optional[callable] = None,
) -> str:
    """sha256 ueber den vollstaendigen Datei-Inhalt, streaming.

    Args:
        path: Pfad zur Datei (Audio oder Video). Muss existieren und readable sein.
        chunk_bytes: Chunk-Groesse fuer streaming. Default 4 MB (Plan-Spec).
        progress_cb: optional callback(bytes_read: int, total_bytes: int) — fuer UI-Progress.

    Returns:
        Hex-String, 64 Zeichen (sha256).

    Raises:
        FileNotFoundError, IsADirectoryError, PermissionError — wie open() ueblich.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"media_hash: Datei existiert nicht: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"media_hash: Pfad ist Verzeichnis, nicht Datei: {p}")

    h = hashlib.sha256()
    total = p.stat().st_size
    bytes_read = 0
    with p.open("rb") as f:
        while True:
            chunk = f.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
            bytes_read += len(chunk)
            if progress_cb is not None:
                try:
                    progress_cb(bytes_read, total)
                except Exception as exc:  # progress darf Hash nicht killen
                    logger.debug("progress_cb raised, ignoring: %s", exc)
    return h.hexdigest()


def quick_fingerprint(path: Path | str) -> str:
    """Quick-Identifier ohne vollstaendigen Hash (path + size + mtime_ns).

    KEIN Ersatz fuer compute_media_hash() — nur fuer In-Session-Caches
    wo zwei Datei-Aufrufe in kurzer Folge wahrscheinlich dieselbe Datei
    sind. Format: '<absolute_path>|<size_bytes>|<mtime_ns>'.

    Verwendung: vor compute_media_hash() pruefen ob bereits in
    In-Memory-Cache → spart Disk-IO bei wiederholten Lookups.
    """
    p = Path(path).resolve()
    st = p.stat()
    return f"{p.as_posix()}|{st.st_size}|{st.st_mtime_ns}"


def hash_iterable(paths: Iterable[Path | str]) -> dict[str, str]:
    """Convenience: Liste von Pfaden → dict[absolute_path, sha256].

    Reihenfolge wird beibehalten (Python 3.7+ dict ordered).
    Fehler einzelner Files werden geloggt aber stoppen den Batch nicht.
    """
    results: dict[str, str] = {}
    for raw in paths:
        p = Path(raw).resolve()
        try:
            results[p.as_posix()] = compute_media_hash(p)
        except Exception as exc:
            logger.warning("hash_iterable: skip %s wegen %s", p, exc)
            results[p.as_posix()] = ""
    return results
