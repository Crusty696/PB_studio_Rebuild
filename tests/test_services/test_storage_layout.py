from pathlib import Path

from services.storage_provenance.layout import (
    StorageLayout,
    create_directory_link,
)


def test_storage_layout_uses_two_digit_sha_prefix(tmp_path: Path) -> None:
    source_sha = "ab" + "1" * 62
    layout = StorageLayout(tmp_path)

    source_root = layout.source_root(source_sha)

    assert source_root == tmp_path / "by_sha" / "ab" / source_sha
    assert layout.relative_artifact_path(source_sha, source_root / "audio" / "beats.json") == "audio/beats.json"


def test_storage_layout_rejects_invalid_sha(tmp_path: Path) -> None:
    layout = StorageLayout(tmp_path)

    for bad_sha in ("", "abc", "g" * 64, "../" + "a" * 61):
        try:
            layout.source_root(bad_sha)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid sha accepted: {bad_sha!r}")


def test_directory_link_resolves_legacy_v2_stems(tmp_path: Path) -> None:
    legacy_stems = tmp_path / "project" / "storage" / "stems" / "track-1"
    legacy_stems.mkdir(parents=True)
    vocals = legacy_stems / "vocals.flac"
    vocals.write_bytes(b"fake-vocals")

    source_sha = "cd" + "2" * 62
    layout = StorageLayout(tmp_path / "global_storage")
    source_root = layout.ensure_source_root(source_sha)
    link_path = source_root / "audio" / "stems"

    create_directory_link(link_path, legacy_stems)

    assert (link_path / "vocals.flac").read_bytes() == b"fake-vocals"
