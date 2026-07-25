"""B-695: Latente Projekt-State-Leaks.

D1 — steer_override_queue-Singleton ueberlebte Projektwechsel: open_project /
create_project leeren die prozessweite Queue jetzt, damit Override-Eintraege aus
Projekt A nicht in Projekt B sichtbar bleiben.

D2 — pacing_beat_grid lru_caches ohne Engine-Identitaet: _get_audio_duration /
_get_audio_path / _get_video_info nehmen die Engine-Identitaet in den Cache-Key
auf (analog dem bereits gehaerteten _get_bpm), damit ein Projektwechsel keinen
Stale-Treffer aus dem alten Projekt/alter Engine liefert.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ── D2: Engine-Identitaet im Cache-Key ────────────────────────────────────────
class _FakeResult:
    def first(self):
        return None

    def all(self):
        return []


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return _FakeResult()


def test_b695_d2_engine_identity_in_audio_duration_cache_key(monkeypatch):
    from services import pacing_beat_grid as pbg

    monkeypatch.setattr(pbg, "Session", lambda _e: _FakeSession())
    ident = {"v": (1, "engineA")}
    monkeypatch.setattr(pbg, "_engine_cache_identity", lambda: ident["v"])

    pbg._get_audio_duration.cache_clear()
    pbg._get_audio_duration(5)
    misses1 = pbg._get_audio_duration.cache_info().misses

    # Gleiche Engine + gleiche audio_id -> Cache-HIT (kein neuer Miss).
    pbg._get_audio_duration(5)
    assert pbg._get_audio_duration.cache_info().misses == misses1

    # Engine-Identitaet aendert sich (Projektwechsel) -> muss MISSEN, sonst
    # kaeme die Dauer aus dem alten Projekt zurueck (B-695 D2).
    ident["v"] = (2, "engineB")
    pbg._get_audio_duration(5)
    assert pbg._get_audio_duration.cache_info().misses == misses1 + 1, (
        "Stale-Cache-Treffer ueber Engine-Wechsel hinweg -> B-695 D2 nicht behoben"
    )


def test_b695_d2_engine_identity_in_video_info_cache_key(monkeypatch):
    from services import pacing_beat_grid as pbg

    monkeypatch.setattr(pbg, "Session", lambda _e: _FakeSession())
    ident = {"v": (1, "engineA")}
    monkeypatch.setattr(pbg, "_engine_cache_identity", lambda: ident["v"])

    pbg._get_video_info_cached.cache_clear()
    pbg._get_video_info([7])
    misses1 = pbg._get_video_info_cached.cache_info().misses

    pbg._get_video_info([7])
    assert pbg._get_video_info_cached.cache_info().misses == misses1

    ident["v"] = (2, "engineB")
    pbg._get_video_info([7])
    assert pbg._get_video_info_cached.cache_info().misses == misses1 + 1, (
        "Stale Video-Info ueber Engine-Wechsel hinweg -> B-695 D2 nicht behoben"
    )


# ── D1: Steer-Override-Queue beim Projektwechsel leeren ───────────────────────
class _StopBeforeSwap(Exception):
    """Sentinel: bricht open_project genau am Engine-Swap ab — nach dem
    B-695-Queue-Clear, vor jeder echten DB-Arbeit."""


def test_b695_d1_open_project_clears_steer_override_queue(monkeypatch, tmp_path: Path):
    from services.project_manager import ProjectManager
    from services.steer_override_queue import (
        get_default_queue,
        reset_default_queue_for_test,
    )

    reset_default_queue_for_test()
    queue = get_default_queue()
    queue.add(1, "boost", "projekt-A")
    queue.add(2, "exclude", "projekt-A")
    assert queue.count() == 2

    project_path = tmp_path / "proj"
    project_path.mkdir()
    (project_path / "pb_studio.db").write_bytes(b"kein echtes sqlite")

    manager = ProjectManager()
    monkeypatch.setattr(
        ProjectManager, "_wait_for_tasks_idle", staticmethod(lambda *a, **k: True)
    )
    monkeypatch.setattr(ProjectManager, "_validate_pb_studio_db", lambda self, p: None)

    def _stop(*a, **k):
        raise _StopBeforeSwap()

    monkeypatch.setattr("database.set_project", _stop)

    with pytest.raises(_StopBeforeSwap):
        manager.open_project(project_path)

    # B-695 D1: Queue muss VOR dem Engine-Swap geleert worden sein.
    assert get_default_queue().count() == 0, (
        "Steer-Override-Queue nicht beim Projektwechsel geleert -> B-695 D1"
    )
    reset_default_queue_for_test()
