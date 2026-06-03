"""B-469 Gap-2 / Plan Phase 1 — single-flight media-DB reload.

`MediaTableController._refresh_media_table` must NOT start a fresh
"Medien-DB laden" worker per call while one is already in flight. Concurrent
calls coalesce: at most one worker runs; if calls arrive during an in-flight
run, exactly ONE trailing reload runs after it finishes (dirty flag).

This reduces the task pile-up seen in B-469 (defensive — not a crash proof).
"""

from types import SimpleNamespace

from ui.controllers.media_table import MediaTableController


def _make_controller():
    c = object.__new__(MediaTableController)  # bypass PBComponent.__init__
    c.window = SimpleNamespace()  # bare window: no model/grid/combo attrs
    return c


class _FakeTM:
    def __init__(self):
        self.workers = []

    def start_task(self, name, worker, description=""):
        assert name == "Medien-DB laden"
        self.workers.append(worker)
        return "task_fake"


def _patch_tm(monkeypatch):
    from services import task_manager
    fake = _FakeTM()
    monkeypatch.setattr(
        task_manager.GlobalTaskManager, "instance", staticmethod(lambda: fake)
    )
    return fake


def test_single_call_starts_one_worker(monkeypatch):
    fake = _patch_tm(monkeypatch)
    c = _make_controller()

    c._refresh_media_table(False)

    assert len(fake.workers) == 1
    assert getattr(c, "_reload_inflight", False) is True


def test_concurrent_calls_coalesce_to_one_worker(monkeypatch):
    fake = _patch_tm(monkeypatch)
    c = _make_controller()

    c._refresh_media_table(False)
    c._refresh_media_table(False)
    c._refresh_media_table(False)

    # Only ONE worker despite three rapid calls.
    assert len(fake.workers) == 1
    assert getattr(c, "_reload_dirty", False) is True


def test_one_trailing_reload_after_inflight_finishes(monkeypatch):
    fake = _patch_tm(monkeypatch)
    c = _make_controller()

    c._refresh_media_table(False)      # starts worker #1
    c._refresh_media_table(False)      # in-flight -> marks dirty
    assert len(fake.workers) == 1

    # Simulate worker #1 completion.
    c._on_media_reload_done([], [], False)

    # Exactly one trailing reload started.
    assert len(fake.workers) == 2
    assert getattr(c, "_reload_inflight", False) is True
    assert getattr(c, "_reload_dirty", False) is False

    # Simulate trailing completion -> no further work, idle.
    c._on_media_reload_done([], [], False)
    assert len(fake.workers) == 2
    assert getattr(c, "_reload_inflight", False) is False
    assert getattr(c, "_reload_dirty", False) is False


def test_error_path_clears_inflight(monkeypatch):
    fake = _patch_tm(monkeypatch)
    c = _make_controller()

    c._refresh_media_table(False)
    assert getattr(c, "_reload_inflight", False) is True

    # Worker errored: inflight must clear so future reloads can run.
    c._on_media_reload_failed()
    assert getattr(c, "_reload_inflight", False) is False

    c._refresh_media_table(False)
    assert len(fake.workers) == 2
