"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T3.1: Stem-Cache - Hash-Funktionen + Cache-Meta-Persistenz.

sha256 ueber (first 1MB || last 1MB || filesize-bytes).
Cache-Meta-JSON unter ``storage/pipeline_state/<track_id>.json``
(ueberlappend mit Checkpoint A-4 - gleiche Datei, JSON-Schema-Erweiterung).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_STORAGE_ROOT = Path("storage")
_CHUNK = 1_000_000  # 1 MB


def _hash_file_bytes(path: str) -> str:
    h = hashlib.sha256()
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(min(_CHUNK, size))
        h.update(head)
        if size > _CHUNK:
            f.seek(max(0, size - _CHUNK))
            tail = f.read(_CHUNK)
            h.update(tail)
    h.update(str(size).encode("ascii"))
    return h.hexdigest()


def compute_audio_hash(path: str) -> str:
    """Hash der Original-Audio-Datei (Reuse-Check)."""
    return _hash_file_bytes(path)


def compute_stem_wav_hash(path: str) -> str:
    """Hash eines Stem-WAVs (fixt R-07: partial-Crash-Detection)."""
    return _hash_file_bytes(path)


def cache_meta_path(track_id: int) -> Path:
    return _STORAGE_ROOT / "pipeline_state" / f"{track_id}.json"


def load_cache_meta(track_id: int) -> dict | None:
    p = cache_meta_path(track_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_cache_meta(track_id: int, meta: dict) -> None:
    """Atomic-write via tmp+os.replace (Windows-safe)."""
    p = cache_meta_path(track_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    os.replace(str(tmp), str(p))
