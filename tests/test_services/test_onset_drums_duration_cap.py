"""B-359 regression test.

``OnsetRhythmService.analyze_and_store`` loaded the optional drums stem
*without* a duration cap, while the raw audio was capped at
``MAX_DURATION_SEC`` (M-17). Because ``analyze`` uses the drums stem as the
signal for the Mel-spectrogram when it is present, a long drums stem could
bypass the 30-minute RAM guard.

This test mocks ``librosa.load`` and asserts BOTH the raw-audio load and the
drums-stem load pass ``duration=MAX_DURATION_SEC``.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest


def test_b359_drums_stem_load_is_duration_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    import librosa

    from services import onset_rhythm_service as ors
    from services.onset_rhythm_service import MAX_DURATION_SEC, OnsetRhythmService

    load_calls: list[dict] = []

    def fake_load(path, *args, **kwargs):  # noqa: ANN001
        load_calls.append({"path": path, "kwargs": dict(kwargs)})
        y = np.zeros(int(0.1 * ors.DEFAULT_SR), dtype=np.float32)
        return y, ors.DEFAULT_SR

    monkeypatch.setattr(librosa, "load", fake_load)

    # Fake DB track with a drums stem path.
    fake_track = SimpleNamespace(
        file_path="C:/fake/raw.wav",
        stem_drums_path="C:/fake/drums.wav",
    )

    class _FakeQuery:
        def filter(self, *a, **k):  # noqa: ANN001
            return self

        def first(self):
            return fake_track

    class _FakeSession:
        def query(self, *a, **k):  # noqa: ANN001
            return _FakeQuery()

    @contextmanager
    def _fake_session_ctx(*a, **k):  # noqa: ANN001
        yield _FakeSession()

    # ``analyze_and_store`` does ``from sqlalchemy.orm import Session`` and
    # ``with Session(engine) as session:`` — patch the constructor to our ctx.
    import sqlalchemy.orm as _orm

    monkeypatch.setattr(_orm, "Session", _fake_session_ctx)

    # Drums-stem existence check must pass.
    monkeypatch.setattr(ors.Path, "exists", lambda self: True)

    # Beat positions lookup -> empty list (avoids DB).
    import services.pacing_beat_grid as pbg

    monkeypatch.setattr(pbg, "_get_beat_positions", lambda track_id: [])

    svc = OnsetRhythmService()
    # Avoid the heavy real analysis + DB write.
    monkeypatch.setattr(
        svc, "analyze", lambda *a, **k: SimpleNamespace(),  # noqa: ANN001
    )
    monkeypatch.setattr(svc, "_store", lambda *a, **k: None)  # noqa: ANN001

    svc.analyze_and_store(track_id=1)

    # Exactly two loads: raw audio + drums stem.
    assert len(load_calls) == 2, f"expected 2 librosa.load calls, got {load_calls}"

    raw_call, drums_call = load_calls
    assert raw_call["path"] == "C:/fake/raw.wav"
    assert raw_call["kwargs"].get("duration") == MAX_DURATION_SEC

    assert drums_call["path"] == "C:/fake/drums.wav"
    assert drums_call["kwargs"].get("duration") == MAX_DURATION_SEC, (
        "B-359: drums stem load must be capped at MAX_DURATION_SEC"
    )
