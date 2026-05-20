from __future__ import annotations

import numpy as np

from ui.widgets.stem_track_widget import PeakWorker


class FakeLongSoundFile:
    total_read_frames = 0
    seek_calls = 0

    def __init__(self, path: str, mode: str = "r") -> None:
        self.path = path
        self.mode = mode
        self.frames = 1_000_000
        self.channels = 2
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def seek(self, frame: int) -> None:
        FakeLongSoundFile.seek_calls += 1
        self._pos = min(max(0, int(frame)), self.frames)

    def read(self, frames: int, dtype: str = "float32", always_2d: bool = True):
        read_n = min(int(frames), self.frames - self._pos)
        self._pos += read_n
        FakeLongSoundFile.total_read_frames += read_n
        return np.zeros((read_n, self.channels), dtype=np.float32)


def test_b321_peak_worker_samples_preview_instead_of_reading_entire_long_file(monkeypatch) -> None:
    FakeLongSoundFile.total_read_frames = 0
    FakeLongSoundFile.seek_calls = 0
    monkeypatch.setattr("soundfile.SoundFile", FakeLongSoundFile)

    emitted = []
    worker = PeakWorker("vocals", "long.wav", target_peaks=1000)
    worker.finished.connect(lambda stem, peaks: emitted.append((stem, peaks)))

    worker.run()

    assert emitted
    assert emitted[0][0] == "vocals"
    assert len(emitted[0][1]) == 1000
    assert FakeLongSoundFile.total_read_frames <= 512_000
    assert FakeLongSoundFile.total_read_frames < FakeLongSoundFile("long.wav").frames
