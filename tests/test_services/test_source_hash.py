from pathlib import Path

from services.storage_provenance.source_identity import compute_source_sha256


def test_source_hash_same_file_same_hash(tmp_path: Path) -> None:
    media = tmp_path / "track.wav"
    media.write_bytes(b"abc" * 1024)

    first = compute_source_sha256(media, media_type="audio", mode="fast")
    second = compute_source_sha256(media, media_type="audio", mode="fast")

    assert first == second
    assert len(first) == 64


def test_source_hash_one_bit_change_changes_hash(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_bytes(b"abc" * 1024)
    b.write_bytes(b"abc" * 1023 + b"abd")

    assert compute_source_sha256(a, media_type="video") != compute_source_sha256(b, media_type="video")


def test_source_hash_strict_full_file_distinguishes_middle_change(tmp_path: Path) -> None:
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    a.write_bytes(b"a" * 1024 + b"b" + b"c" * 1024)
    b.write_bytes(b"a" * 1024 + b"x" + b"c" * 1024)

    assert compute_source_sha256(a, media_type="audio", mode="strict") != compute_source_sha256(
        b, media_type="audio", mode="strict"
    )
