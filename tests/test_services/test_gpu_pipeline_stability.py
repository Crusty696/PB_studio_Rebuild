import sys
import importlib
import types

import pytest


class _RecordingLock:
    def __init__(self, name, events, state=None):
        self.name = name
        self.events = events
        self.state = state

    def __enter__(self):
        self.events.append(f"{self.name}:enter")
        if self.state is not None:
            self.state[self.name] = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.events.append(f"{self.name}:exit")
        if self.state is not None:
            self.state[self.name] = False
        return False


def _install_fake_qt(monkeypatch):
    qt_root_name = "Py" + "Side6"
    qt_core_name = qt_root_name + ".QtCore"

    class FakeSignal:
        def __init__(self, *args, **kwargs):
            self.emissions = []

        def emit(self, *args):
            self.emissions.append(args)

        def connect(self, callback):
            self._callback = callback

    class FakeQObject:
        def __init__(self, *args, **kwargs):
            super().__init__()

    qt_root = types.ModuleType(qt_root_name)
    qt_core = types.ModuleType(qt_core_name)
    qt_core.QObject = FakeQObject
    qt_core.Signal = FakeSignal
    qt_root.QtCore = qt_core
    monkeypatch.setitem(sys.modules, qt_root_name, qt_root)
    monkeypatch.setitem(sys.modules, qt_core_name, qt_core)


def test_model_manager_load_runs_under_single_gpu_resource_lease(monkeypatch):
    import services.model_manager as model_manager

    events = []
    state = {}
    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", _RecordingLock("exec", events, state))
    monkeypatch.setattr(model_manager, "GPU_LOAD_LOCK", _RecordingLock("load", events, state))

    manager = object.__new__(model_manager.ModelManager)

    def load_vision(model_id):
        events.append("load_vision")
        assert state.get("exec") is True
        assert state.get("load") is True
        return f"loaded:{model_id}"

    monkeypatch.setattr(manager, "load_vision", load_vision)

    assert manager.ensure_loaded("dummy-model", "vision") == "loaded:dummy-model"
    assert events == [
        "exec:enter",
        "load:enter",
        "load_vision",
        "load:exit",
        "exec:exit",
    ]


def test_model_manager_uses_cuda_mem_get_info_for_free_vram(monkeypatch):
    import services.model_manager as model_manager

    gb = 1024**3

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def mem_get_info(device=0):
            return 3 * gb, 6 * gb

        @staticmethod
        def memory_allocated(device=0):
            raise AssertionError("memory_allocated ignores external VRAM users")

    fake_torch = types.SimpleNamespace(cuda=FakeCuda())
    monkeypatch.setattr(model_manager, "torch", fake_torch)
    monkeypatch.setattr(model_manager.psutil, "virtual_memory", lambda: types.SimpleNamespace(available=8 * gb))

    manager = object.__new__(model_manager.ModelManager)
    status = manager.check_memory_available()

    assert status["vram_available_gb"] == pytest.approx(3.0)
    assert status["vram_total_gb"] == pytest.approx(6.0)
    assert status["vram_sufficient"] is True


def test_beatthis_full_analysis_inference_uses_execution_lock(monkeypatch):
    import numpy as np
    import services.beat_analysis_service as beat_service
    import services.model_manager as model_manager

    events = []
    state = {}
    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", _RecordingLock("exec", events, state))
    monkeypatch.setitem(
        sys.modules,
        "torch",
        types.SimpleNamespace(no_grad=lambda: _RecordingLock("no_grad", events)),
    )

    service = object.__new__(beat_service.BeatAnalysisService)
    monkeypatch.setattr(service, "_ensure_model", lambda: events.append("ensure_model"))

    def fake_model(audio_path):
        events.append("beatthis_call")
        assert state.get("exec") is True
        return np.array([0.0, 0.5]), np.array([0.0])

    service._model = fake_model

    beats, downbeats = service._analyze_full("mix.wav")

    assert beats.tolist() == [0.0, 0.5]
    assert downbeats.tolist() == [0.0]
    assert events[:4] == ["ensure_model", "exec:enter", "no_grad:enter", "beatthis_call"]


def test_demucs_apply_helper_uses_execution_lock(monkeypatch):
    import services.ai_audio_service as audio_service
    import services.model_manager as model_manager

    events = []
    state = {}
    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", _RecordingLock("exec", events, state))

    def fake_apply_model(model, chunk, **kwargs):
        events.append("demucs_apply")
        assert state.get("exec") is True
        return "estimate"

    result = audio_service.StemSeparator._apply_demucs_model_locked(
        fake_apply_model,
        "model",
        "chunk",
        shifts=1,
        split=False,
        overlap=0.1,
        progress=False,
        device="cuda",
    )

    assert result == "estimate"
    assert events == ["exec:enter", "demucs_apply", "exec:exit"]


def test_downbeat_matching_tolerates_rounding_drift():
    from services.pacing_beat_grid import AdvancedPacingSettings
    from services.pacing_edit_helpers import _select_cut_beats_advanced

    beats = [i * 0.5 for i in range(18)]
    energy = [0.6 for _ in beats]
    selected = _select_cut_beats_advanced(
        beats=beats,
        total_duration=9.0,
        settings=AdvancedPacingSettings(
            base_cut_rate=8,
            energy_reactivity=1,
            breakdown_behavior="none",
            high_energy_behavior="none",
        ),
        energy_per_beat=energy,
        downbeats=[4.02],
    )

    assert 4.0 in selected


def test_video_batch_defers_captioning_until_after_gpu_models_unloaded(monkeypatch, tmp_path):
    _install_fake_qt(monkeypatch)
    monkeypatch.delitem(sys.modules, "workers" + ".video", raising=False)

    from services.video_analysis_service import PipelineResult, SceneInfo
    import services.model_manager as model_manager
    import services.video_analysis_service as video_service
    video_worker = importlib.import_module("workers" + ".video")

    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_bytes(b"fake")
    second.write_bytes(b"fake")

    events = []
    state = {}
    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", _RecordingLock("exec", events, state))
    monkeypatch.setattr(model_manager, "GPU_LOAD_LOCK", _RecordingLock("load", events, state))

    class FakeRaft:
        def cpu(self):
            events.append("raft:cpu")

    class FakeModelManager:
        def __init__(self):
            self.device = "cuda"
            self.model_type = "siglip"

        def load_siglip(self):
            events.append("siglip:load")
            return "siglip-model", "siglip-proc"

        def load_raft(self):
            events.append("raft:load")
            return FakeRaft(), "cuda"

        def unload(self):
            events.append("siglip:unload")

    monkeypatch.setattr(model_manager, "ModelManager", FakeModelManager)
    fake_warmup = types.ModuleType("services.model_warmup")
    fake_warmup.is_siglip_cached = lambda: (True, [])
    fake_warmup.warmup_siglip = lambda progress_cb=None: None
    monkeypatch.setitem(sys.modules, "services.model_warmup", fake_warmup)

    def fake_run_full_pipeline(**kwargs):
        events.append(f"pipeline:{kwargs['video_clip_id']}:{kwargs.get('defer_captioning')}")
        assert kwargs.get("defer_captioning") is True
        return PipelineResult(
            video_path=kwargs["video_path"],
            scenes=[SceneInfo(index=0, start_time=0.0, end_time=1.0, keyframe_path="")],
            embeddings_stored=1,
        )

    def fake_run_deferred_captioning(video_clip_id, scenes, **kwargs):
        events.append(f"caption:{video_clip_id}")
        assert state.get("exec") is False
        assert "raft:cpu" in events
        assert "siglip:unload" in events
        return scenes

    monkeypatch.setattr(video_service, "run_full_pipeline", fake_run_full_pipeline)
    monkeypatch.setattr(video_service, "run_deferred_captioning", fake_run_deferred_captioning, raising=False)

    worker = video_worker.VideoAnalysisPipelineWorker(
        batch=[(1, str(first), "First"), (2, str(second), "Second")]
    )
    worker.run()

    assert events.index("raft:cpu") < events.index("caption:1")
    assert events.index("siglip:unload") < events.index("caption:1")
    assert events.count("caption:1") == 1
    assert events.count("caption:2") == 1
