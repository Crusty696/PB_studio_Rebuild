"""B-597: Audio-V2 Freeze-Guardrails fuer Timing, Cancel und Refresh-Last."""
from __future__ import annotations

import inspect
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_b597_orchestrator_logs_stage_timing() -> None:
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline

    source = inspect.getsource(AudioAnalysisPipeline._run_stages)
    assert "B-597 audio_stage start" in source
    assert "B-597 audio_stage done" in source
    assert "time.perf_counter" in source


def test_b597_gpu_heavy_audio_stages_use_timed_lease() -> None:
    from services.audio_pipeline import stages

    stem_source = inspect.getsource(stages.StemGenStage.run)
    beat_source = inspect.getsource(stages.BeatGridStage.run)

    assert '_audio_gpu_execution_lease("audio_v2.stem_gen")' in stem_source
    assert '_audio_gpu_execution_lease("audio_v2.beat_grid")' in beat_source


def test_b597_heavy_audio_stages_check_cancel() -> None:
    from services.audio_pipeline import stages

    source = inspect.getsource(stages)
    for stage_name in ("onset", "lufs", "spectral", "av_pacing"):
        assert f'_raise_if_cancelled(context, "{stage_name}")' in source


def test_b597_identical_audio_items_do_not_rebuild_cards(monkeypatch):
    """B-597: identische Items -> kein Card-Rebuild (Signatur-Vergleich).

    B-596 (Freeze-Fix) baut Cards nur, wenn das Grid SICHTBAR ist — bei
    unsichtbarem Grid wird nur ``_pending_rebuild`` gesetzt und der teure
    Aufbau auf ``showEvent`` verschoben. Das Grid muss hier also sichtbar
    sein, sonst feuert ``_rebuild_cards`` nie und der eigentlich zu
    pruefende Dedup-Effekt (zweiter Call bleibt aus) ist gar nicht sichtbar.
    """
    from ui.widgets.media_grid import MediaPoolGrid

    _qapp()
    grid = MediaPoolGrid(media_type="audio")
    grid.show()
    calls: list[tuple[int, ...]] = []

    def fake_rebuild() -> None:
        calls.append(tuple(item["id"] for item in grid._all_items))

    monkeypatch.setattr(grid, "_rebuild_cards", fake_rebuild)
    items = [
        {
            "id": 1,
            "title": "Track",
            "file_path": "C:/music/track.wav",
            "bpm": 128.0,
            "key": "Am",
            "mood": "dark",
            "genre": "techno",
            "energy_curve": [0.1, 0.4, 0.2],
        }
    ]

    try:
        grid.set_items(items)
        grid.set_items([dict(items[0])])

        assert calls == [(1,)]
    finally:
        grid.deleteLater()
