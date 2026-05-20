from __future__ import annotations

from pathlib import Path

from services.stem_player import StemPlayer


class FakeSoundFile:
    open_count = 0
    close_count = 0

    def __init__(self, path: str, mode: str = "r") -> None:
        self.path = path
        self.mode = mode
        self.samplerate = 44100
        self.channels = 2
        self.frames = 441000
        self.closed = False
        FakeSoundFile.open_count += 1

    def close(self) -> None:
        self.closed = True
        FakeSoundFile.close_count += 1


def test_b321_load_stems_is_idempotent_for_same_paths(qapp, monkeypatch, tmp_path) -> None:
    """Completion-refresh darf dieselben langen Stems nicht erneut synchron oeffnen."""
    FakeSoundFile.open_count = 0
    FakeSoundFile.close_count = 0
    monkeypatch.setattr("services.stem_player.sf.SoundFile", FakeSoundFile)

    player = StemPlayer()
    files = {
        "vocals": tmp_path / "vocals.wav",
        "drums": tmp_path / "drums.wav",
        "bass": tmp_path / "bass.wav",
        "other": tmp_path / "other.wav",
    }
    for file_path in files.values():
        file_path.touch()
    paths = {name: str(file_path) for name, file_path in files.items()}

    assert player.load_stems(paths) is True
    assert FakeSoundFile.open_count == 4

    assert player.load_stems(dict(paths)) is True

    assert FakeSoundFile.open_count == 4
    assert FakeSoundFile.close_count == 0
    player.cleanup()


def test_b321_load_stems_reloads_when_paths_change(qapp, monkeypatch, tmp_path) -> None:
    FakeSoundFile.open_count = 0
    FakeSoundFile.close_count = 0
    monkeypatch.setattr("services.stem_player.sf.SoundFile", FakeSoundFile)

    player = StemPlayer()
    first_file = tmp_path / "vocals.wav"
    second_file = tmp_path / "vocals-v2.wav"
    first_file.touch()
    second_file.touch()
    first = {"vocals": str(first_file)}
    second = {"vocals": str(second_file)}

    assert player.load_stems(first) is True
    assert player.load_stems(second) is True

    assert FakeSoundFile.open_count == 2
    assert FakeSoundFile.close_count == 1
    player.cleanup()
