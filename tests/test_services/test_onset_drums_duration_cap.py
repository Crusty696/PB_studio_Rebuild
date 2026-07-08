"""B-359 regression test — RAM-Schutz bei langen Drums-Stems.

Historie:
- B-359 (M-17): ``analyze_and_store`` lud raw + drums mit
  ``duration=MAX_DURATION_SEC``, damit ein langer Drums-Stem nicht das
  30-Minuten-RAM-Budget des Mel-Spektrogramms sprengt.
- NEUBAU-VOLLINTEGRATION T2.5.1 (PIPE-016): der harte Load-Cap wurde
  ENTFERNT, damit auch die zweite Haelfte langer DJ-Mixe Onsets bekommt.
  Der RAM-Schutz wandert von "Load kappen" zu "pro Chunk analysieren":
  ``_analyze_long_chunked`` schneidet Signal + Drums-Stem in
  ``MAX_DURATION_SEC``-Chunks und ruft ``analyze()`` je Slice — es haelt nie
  mehr als EIN Chunk-Spektrogramm (<= alter Cap) im RAM.

Diese Tests sichern die NEUE Schutz-Mechanik:
  1. Kurzes Audio (< Cap): EIN analyze()-Aufruf, kein Chunking, voller Load
     ohne duration-Cap (Coverage-Ziel von PIPE-016).
  2. Langes Audio (> Cap): mehrere analyze()-Aufrufe, und KEIN einzelner
     Aufruf sieht mehr Samples als ``MAX_DURATION_SEC`` — d.h. das
     Spektrogramm-RAM bleibt <= alter B-359-Grenze.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest


def _fake_env(monkeypatch, *, raw_seconds: float):
    """Baut die gemockte DB/Session-Umgebung + fake librosa.load, die ein
    Signal von ``raw_seconds`` Laenge liefert. Gibt (load_calls,
    analyze_calls) zurueck."""
    import librosa

    from services import onset_rhythm_service as ors

    load_calls: list[dict] = []

    def fake_load(path, *args, **kwargs):  # noqa: ANN001
        load_calls.append({"path": path, "kwargs": dict(kwargs)})
        n = int(raw_seconds * ors.DEFAULT_SR)
        return np.zeros(n, dtype=np.float32), ors.DEFAULT_SR

    monkeypatch.setattr(librosa, "load", fake_load)

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

    import sqlalchemy.orm as _orm
    monkeypatch.setattr(_orm, "Session", _fake_session_ctx)
    monkeypatch.setattr(ors.Path, "exists", lambda self: True)

    import services.pacing_beat_grid as pbg
    monkeypatch.setattr(pbg, "_get_beat_positions", lambda track_id: [])

    # analyze() durch einen Spy ersetzen, der die Sample-Anzahl je Aufruf
    # protokolliert (RAM-Proxy) und eine leere RhythmAnalysis liefert.
    analyze_calls: list[int] = []

    def fake_analyze(self, y, sr, beats, drums_y=None, structure_segments=None):
        signal = drums_y if drums_y is not None else y
        analyze_calls.append(len(signal))
        return ors.RhythmAnalysis()

    monkeypatch.setattr(ors.OnsetRhythmService, "analyze", fake_analyze)
    return ors, load_calls, analyze_calls


def test_b359_short_audio_single_uncapped_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kurzes Audio: EIN analyze()-Aufruf, Load ohne duration-Cap (PIPE-016
    laedt voll; RAM unkritisch weil < Cap)."""
    ors, load_calls, analyze_calls = _fake_env(monkeypatch, raw_seconds=0.5)

    svc = ors.OnsetRhythmService()
    monkeypatch.setattr(svc, "_store", lambda *a, **k: None)
    svc.analyze_and_store(track_id=1)

    assert len(load_calls) == 2  # raw + drums
    # PIPE-016: kein harter duration-Cap mehr beim Laden
    assert "duration" not in load_calls[0]["kwargs"]
    assert "duration" not in load_calls[1]["kwargs"]
    # kurzes Audio -> genau ein analyze()-Aufruf (kein Chunking)
    assert len(analyze_calls) == 1


def test_b359_long_audio_is_chunked_ram_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Langes Audio (> Cap): Chunked-Analyse — mehrere analyze()-Aufrufe,
    und KEIN Aufruf sieht mehr Samples als MAX_DURATION_SEC (Spektrogramm-
    RAM bleibt <= alter B-359-Grenze)."""
    cap = None
    from services.onset_rhythm_service import MAX_DURATION_SEC
    cap = MAX_DURATION_SEC
    # 2.5x Cap -> muss in mehrere Chunks zerlegt werden
    ors, load_calls, analyze_calls = _fake_env(
        monkeypatch, raw_seconds=cap * 2.5)

    svc = ors.OnsetRhythmService()
    monkeypatch.setattr(svc, "_store", lambda *a, **k: None)
    svc.analyze_and_store(track_id=1)

    assert len(analyze_calls) >= 3, (
        f"erwartete Chunking in >=3 Analysen, war {len(analyze_calls)}")
    max_samples = max(analyze_calls)
    cap_samples = int(cap * ors.DEFAULT_SR)
    assert max_samples <= cap_samples, (
        "B-359: kein analyze()-Aufruf darf mehr als MAX_DURATION_SEC Samples "
        f"sehen (war {max_samples} > {cap_samples})")
