from __future__ import annotations

from pathlib import Path

from services.brain.storage.media_hash_registry import MediaHashRegistry
from workers.brain_v3_hashing import BrainV3HashingWorker


def test_hashing_worker_emits_embedding_signal_for_known_hash(tmp_path: Path):
    media_path = tmp_path / "track.wav"
    media_path.write_bytes(b"same bytes")
    registry = MediaHashRegistry(tmp_path / "embedding_cache.db")

    first_seen: list[tuple[str, str, str]] = []
    first = BrainV3HashingWorker([str(media_path)], [], registry=registry)
    first.hash_registered.connect(lambda *args: first_seen.append(args))
    first.run()

    known_seen: list[tuple[str, str, str]] = []
    messages: list[str] = []
    second = BrainV3HashingWorker([str(media_path)], [], registry=registry)
    second.hash_registered.connect(lambda *args: known_seen.append(args))
    second.file_hashed.connect(messages.append)
    second.run()

    assert len(first_seen) == 1
    assert len(known_seen) == 1
    assert known_seen[0] == first_seen[0]
    assert known_seen[0][2] == "audio"
    assert any("bekannt" in msg for msg in messages)
