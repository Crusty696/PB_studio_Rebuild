"""B-765: Story-Map-Oeffnen darf den GUI-Thread nie blockieren.

Live-Incident 2026-08-06 22:47: `StoryMapDialog.__init__` rief
`svc.story_map_data(run_id)` synchron im GUI-Thread (story_map_dialog.py:328).
Unter DB-Last (laufende Auto-Edit-Writes) wartete der SELECT unbegrenzt auf
den SQLite-Lock — Windows meldete `AppHangB1`, die App wurde beendet
(Exit 255), der laufende Auto-Edit ging mit verloren.

Vertraege:
1. `open_story_map_async` kehrt sofort zurueck (laedt im Worker) und
   liefert den fertigen Dialog per Callback im GUI-Thread.
2. `StoryMapDialog(..., data=payload)` ruft den Service NICHT mehr auf.
3. Rueckwaerts-Vertrag: ohne `data` laedt der Konstruktor wie bisher.
"""
from __future__ import annotations

import threading
import time

import pytest

pytest.importorskip("PySide6")


class _SlowService:
    """Fake-BrainService: story_map_data blockiert messbar."""

    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.calls = 0
        self.call_threads: list[str] = []

    def story_map_data(self, run_id: int):
        self.calls += 1
        self.call_threads.append(threading.current_thread().name)
        time.sleep(self.delay)
        return {
            "run": {"id": int(run_id), "audio_track_id": 1,
                    "total_duration_sec": 10.0, "is_dj_mix": False,
                    "started_at": None, "completed_at": None},
            "audio_track": {"id": 1, "file_path": "x.wav",
                            "file_basename": "x.wav"},
            "decisions": [],
            "structure_segments": [],
            "tension_curve": [],
            "mood_curve": [],
            "waveform_energy": [],
        }


def _payload():
    return _SlowService(delay=0.0).story_map_data(7)


def test_dialog_with_prefetched_data_never_calls_service(qapp):
    from ui.story_map_dialog import StoryMapDialog

    svc = _SlowService()
    dlg = StoryMapDialog(svc, 7, data=_payload())
    try:
        assert svc.calls == 0, (
            "Konstruktor rief story_map_data trotz vorab geladener Daten — "
            "genau der B-765-GUI-Thread-Block"
        )
        assert dlg.data() is not None
    finally:
        dlg.deleteLater()


def test_open_async_returns_immediately_and_delivers_dialog(qapp, qtbot):
    from ui.story_map_dialog import open_story_map_async

    svc = _SlowService(delay=0.3)
    delivered: list = []

    t0 = time.monotonic()
    open_story_map_async(svc, 7, parent=None,
                         on_ready=lambda d: delivered.append(d))
    elapsed = time.monotonic() - t0
    assert elapsed < 0.15, (
        f"open_story_map_async blockierte {elapsed:.2f}s im GUI-Thread — "
        f"muss sofort zurueckkehren (Worker laedt)"
    )

    qtbot.waitUntil(lambda: len(delivered) == 1, timeout=5000)
    dlg = delivered[0]
    try:
        assert svc.calls == 1
        assert "MainThread" not in svc.call_threads, (
            f"story_map_data lief im GUI-Thread: {svc.call_threads}"
        )
        assert dlg.data() is not None
        assert dlg.isVisible(), "Dialog muss nach Lieferung sichtbar sein"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_legacy_constructor_still_loads(qapp):
    from ui.story_map_dialog import StoryMapDialog

    svc = _SlowService(delay=0.0)
    dlg = StoryMapDialog(svc, 7)
    try:
        assert svc.calls == 1
        assert dlg.data() is not None
    finally:
        dlg.deleteLater()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
