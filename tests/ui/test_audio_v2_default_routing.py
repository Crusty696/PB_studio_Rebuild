"""OTK-018: _analyze_selected_audio routet bei Setting audio.v2_default auf die
Audio-V2-Pipeline, sonst auf den klassischen AnalysisWorker."""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _ctrl(monkeypatch, v2_default):
    from ui.controllers.audio_analysis import AudioAnalysisController
    import services.settings_store as ss
    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = SimpleNamespace(_console_append=lambda s: None)
    monkeypatch.setattr(ctrl, "_get_selected_audio_track", lambda: (1, "/a.wav", "T", None))
    monkeypatch.setattr(
        ss, "get_settings_store",
        lambda: SimpleNamespace(get_nested=lambda *a, **k: v2_default),
    )
    return ctrl


def test_routes_to_v2_when_default_on(monkeypatch):
    ctrl = _ctrl(monkeypatch, v2_default=True)
    calls = {}
    monkeypatch.setattr(ctrl, "_analyze_audio_v2", lambda: calls.setdefault("v2", True))
    ctrl._analyze_selected_audio()
    assert calls.get("v2") is True


def test_uses_classic_path_when_default_off(monkeypatch):
    ctrl = _ctrl(monkeypatch, v2_default=False)
    calls = {}
    monkeypatch.setattr(ctrl, "_analyze_audio_v2", lambda: calls.setdefault("v2", True))

    # Klassischer Pfad: AnalysisWorker + task + dispatch -> nur als no-op stubben.
    import ui.controllers.audio_analysis as mod
    made = {}
    _sig = lambda: SimpleNamespace(connect=lambda *a, **k: None)

    def _fake_worker(tid, title):
        made["worker"] = (tid, title)
        return SimpleNamespace(task_id=None, started=_sig(), finished=_sig(),
                               error=_sig(), progress=_sig())
    monkeypatch.setattr(mod, "AnalysisWorker", _fake_worker)
    monkeypatch.setattr(mod, "task_manager",
                        SimpleNamespace(create_task=lambda *a, **k: SimpleNamespace(task_id="t1")))
    ctrl.window.btn_analyze = SimpleNamespace(setEnabled=lambda *a: None, setText=lambda *a: None)
    ctrl.window.progress_bar = SimpleNamespace(setVisible=lambda *a: None)
    ctrl.window.worker_dispatcher = SimpleNamespace(_start_worker_thread=lambda *a, **k: None)

    ctrl._analyze_selected_audio()

    assert "v2" not in calls
    assert made.get("worker") == (1, "T")
