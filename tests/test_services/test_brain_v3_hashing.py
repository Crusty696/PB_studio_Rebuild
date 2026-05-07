"""Tests fuer services.brain_v3.hashing.

Plan-Doc 06 Phase 1 / R-Doc 07 R07 (Modell-Update macht alte Embeddings
inkompatibel) sind beide hash-abhaengig — daher sicherheitskritisch dass
identische Bytes immer denselben Hash liefern.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from services.brain_v3.hashing import (
    compute_media_hash, hash_iterable, quick_fingerprint, CHUNK_BYTES,
)


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(payload)
    return p


# ---------------------------------------------------------------------------
# compute_media_hash
# ---------------------------------------------------------------------------
def test_idempotent_small_file(tmp_path: Path):
    p = _write(tmp_path, "tiny.bin", b"hello world")
    h1 = compute_media_hash(p)
    h2 = compute_media_hash(p)
    assert h1 == h2
    assert len(h1) == 64
    # Vergleich gegen offizielles sha256
    assert h1 == hashlib.sha256(b"hello world").hexdigest()


def test_different_content_different_hash(tmp_path: Path):
    a = _write(tmp_path, "a.bin", b"AAA")
    b = _write(tmp_path, "b.bin", b"BBB")
    assert compute_media_hash(a) != compute_media_hash(b)


def test_streaming_matches_one_shot_for_large_file(tmp_path: Path):
    """Streaming-Hash (Chunks à 4 MB) muss byte-identisches Ergebnis
    liefern wie ein One-Shot-Hash auf demselben Buffer.
    Wir testen mit 5 MB damit mindestens ein Chunk-Wechsel passiert."""
    size = 5 * 1024 * 1024  # 5 MB
    payload = os.urandom(size)
    p = _write(tmp_path, "big.bin", payload)

    streamed = compute_media_hash(p, chunk_bytes=CHUNK_BYTES)
    one_shot = hashlib.sha256(payload).hexdigest()
    assert streamed == one_shot


def test_chunk_size_invariant(tmp_path: Path):
    """Verschiedene Chunk-Sizes muessen identisches Ergebnis liefern."""
    payload = os.urandom(2 * 1024 * 1024 + 17)  # 2 MB + 17 bytes
    p = _write(tmp_path, "x.bin", payload)
    h_default = compute_media_hash(p)
    h_64k = compute_media_hash(p, chunk_bytes=64 * 1024)
    h_1byte = compute_media_hash(p, chunk_bytes=1)
    assert h_default == h_64k == h_1byte


def test_progress_callback_called(tmp_path: Path):
    payload = os.urandom(1024 * 1024 + 100)  # ~1 MB
    p = _write(tmp_path, "y.bin", payload)
    calls: list[tuple[int, int]] = []
    h = compute_media_hash(p, chunk_bytes=64 * 1024,
                           progress_cb=lambda r, t: calls.append((r, t)))
    assert len(h) == 64
    assert len(calls) > 0
    last_read, total = calls[-1]
    assert last_read == total == p.stat().st_size


def test_progress_callback_exception_does_not_kill_hash(tmp_path: Path):
    p = _write(tmp_path, "z.bin", b"defensive")
    def bad_cb(_r, _t):
        raise RuntimeError("ignored by hashing")
    h = compute_media_hash(p, progress_cb=bad_cb)
    assert h == hashlib.sha256(b"defensive").hexdigest()


def test_missing_file_raises_filenotfound(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        compute_media_hash(tmp_path / "nonexistent.bin")


def test_directory_raises_isadirectory(tmp_path: Path):
    with pytest.raises(IsADirectoryError):
        compute_media_hash(tmp_path)


# ---------------------------------------------------------------------------
# quick_fingerprint
# ---------------------------------------------------------------------------
def test_quick_fingerprint_format(tmp_path: Path):
    p = _write(tmp_path, "fp.bin", b"abc")
    fp = quick_fingerprint(p)
    parts = fp.split("|")
    assert len(parts) == 3
    assert parts[0] == p.resolve().as_posix()
    assert parts[1] == "3"  # 3 bytes
    int(parts[2])  # mtime_ns parsable


def test_quick_fingerprint_changes_when_content_grows(tmp_path: Path):
    p = _write(tmp_path, "grow.bin", b"x")
    fp1 = quick_fingerprint(p)
    p.write_bytes(b"xx")
    fp2 = quick_fingerprint(p)
    assert fp1 != fp2  # size geaendert


# ---------------------------------------------------------------------------
# hash_iterable
# ---------------------------------------------------------------------------
def test_hash_iterable_preserves_order_and_handles_errors(tmp_path: Path):
    a = _write(tmp_path, "a.bin", b"A")
    b = _write(tmp_path, "b.bin", b"B")
    missing = tmp_path / "missing.bin"
    result = hash_iterable([a, missing, b])
    keys = list(result.keys())
    assert keys == [a.resolve().as_posix(),
                    missing.resolve().as_posix(),
                    b.resolve().as_posix()]
    assert result[a.resolve().as_posix()] == hashlib.sha256(b"A").hexdigest()
    assert result[missing.resolve().as_posix()] == ""  # Fehler → leer
    assert result[b.resolve().as_posix()] == hashlib.sha256(b"B").hexdigest()
