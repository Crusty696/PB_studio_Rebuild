"""PeakWorker-Leseverhalten.

Historie:
- B-321 fuehrte Sampling ein (512 Frames je Bucket), um Langdateien nicht
  komplett zu lesen. Ziel war LAUFZEIT.
- B-614 (2026-07-10, Watchdog-Beweis workspace_switch_perf Lauf 3+4):
  Das Sampling machte 8000 seek+read-Zyklen PRO Stem — auf HDD ein
  Seek-Sturm (Minuten) und via Python-Schleife massiver GIL-Druck, der
  den ersten Workspace-Zyklus nach Projekt-Open einfror. Jetzt liest der
  Worker SEQUENTIELL in grossen Bloecken (1 seek gesamt) und rechnet die
  Buckets numpy-vektorisiert — schneller UND Main-Thread-schonend.

Guards hier: kein Seek-Sturm (seek_calls <= 1), vollstaendige Peak-Zahl,
exakte min/max-Werte gegen eine naive Referenz.
"""
from __future__ import annotations

import numpy as np

from ui.widgets.stem_track_widget import PeakWorker


class FakeSeqSoundFile:
    """Deterministische Fake-Datei: Rampe 0..frames-1 (mono skaliert)."""

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
        FakeSeqSoundFile.seek_calls += 1
        self._pos = min(max(0, int(frame)), self.frames)

    def read(self, frames: int, dtype: str = "float32", always_2d: bool = True):
        read_n = min(int(frames), self.frames - self._pos)
        start = self._pos
        self._pos += read_n
        FakeSeqSoundFile.total_read_frames += read_n
        # Beide Kanaele identisch -> mono-mean == Rampe.
        ramp = (np.arange(start, start + read_n, dtype=np.float32)
                / np.float32(self.frames))
        return np.stack([ramp, ramp], axis=1)


def test_b614_peak_worker_reads_sequentially_without_seek_storm(monkeypatch) -> None:
    FakeSeqSoundFile.total_read_frames = 0
    FakeSeqSoundFile.seek_calls = 0
    monkeypatch.setattr("soundfile.SoundFile", FakeSeqSoundFile)

    emitted = []
    worker = PeakWorker("vocals", "long.wav", target_peaks=1000)
    worker.finished.connect(lambda stem, peaks: emitted.append((stem, peaks)))

    worker.run()

    assert emitted
    stem, peaks = emitted[0]
    assert stem == "vocals"
    assert len(peaks) == 1000

    # B-614-Kern: EIN initialer seek(0), danach nur sequentielle reads —
    # kein seek+read pro Bucket mehr (vorher: 1000 Seeks).
    assert FakeSeqSoundFile.seek_calls <= 1

    # Korrektheit gegen naive Referenz: Rampe -> Bucket-min = erster,
    # Bucket-max = letzter Frame des Buckets.
    fpp = 1_000_000 // 1000
    ref = np.arange(1_000_000, dtype=np.float32) / np.float32(1_000_000)
    ref_min = ref.reshape(1000, fpp).min(axis=1)
    ref_max = ref.reshape(1000, fpp).max(axis=1)
    assert np.allclose(peaks[:, 0], ref_min, atol=1e-6)
    assert np.allclose(peaks[:, 1], ref_max, atol=1e-6)


def test_b614_peak_worker_cancel_between_blocks(monkeypatch) -> None:
    FakeSeqSoundFile.total_read_frames = 0
    FakeSeqSoundFile.seek_calls = 0
    monkeypatch.setattr("soundfile.SoundFile", FakeSeqSoundFile)

    emitted = []
    worker = PeakWorker("drums", "long.wav", target_peaks=1000)
    worker.finished.connect(lambda stem, peaks: emitted.append((stem, peaks)))
    worker.cancel()

    worker.run()

    assert emitted == []  # cancelled -> kein Emit, kein Crash
