"""Cycle 13 / Bug-Hunter Session A+B follow-up.

Session A (services/):
- BUG-A1: action_registry.clear_signature_cache() Helper
- BUG-A2: action_registry.unregister droppt _signature_cache-Eintrag

Session B (ui/):
- BUG-B1: FolderImportWorker faengt project_id beim Init ein
"""
from __future__ import annotations

import inspect

import pytest


# ── BUG-A1 + A2: action_registry signature-cache cleanup ──────────────────


def test_action_registry_has_clear_signature_cache():
    from services.action_registry import ActionRegistry
    assert hasattr(ActionRegistry, "clear_signature_cache")
    assert callable(ActionRegistry.clear_signature_cache)


def test_action_registry_unregister_drops_signature_cache():
    from services.action_registry import ActionRegistry, _signature_cache

    reg = ActionRegistry()

    def my_action(x: int) -> int:
        return x * 2

    reg.register_function(
        name="my-action", description="test",
        handler=my_action,
        param_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
    )
    # Triggern via execute → fuellt _signature_cache
    reg.execute("my-action", {"x": 5})
    assert my_action in _signature_cache

    reg.unregister("my-action")
    # _signature_cache-Eintrag fuer den Handler muss weg sein
    assert my_action not in _signature_cache


def test_clear_signature_cache_empties_cache():
    from services.action_registry import ActionRegistry, _signature_cache

    reg = ActionRegistry()

    def h1(): pass
    def h2(): pass
    reg.register_function("h1", "h1", h1, {"type": "object"})
    reg.register_function("h2", "h2", h2, {"type": "object"})
    reg.execute("h1")
    reg.execute("h2")
    assert h1 in _signature_cache and h2 in _signature_cache

    ActionRegistry.clear_signature_cache()
    assert _signature_cache == {}


# ── BUG-B1: FolderImportWorker faengt project_id ein ───────────────────────


def test_folder_import_worker_accepts_project_id():
    from workers.import_export import FolderImportWorker
    sig = inspect.signature(FolderImportWorker.__init__)
    assert "project_id" in sig.parameters
    assert sig.parameters["project_id"].default is None


def test_folder_import_worker_resolves_project_at_init(monkeypatch):
    """Wenn project_id=None passed wird, soll der Worker beim Init
    get_active_project_id() abrufen und einfrieren — nicht erst beim Import."""
    captured = {"calls": 0}

    def _fake_active():
        captured["calls"] += 1
        return 42

    monkeypatch.setattr("database.session.get_active_project_id", _fake_active)

    from workers.import_export import FolderImportWorker
    worker = FolderImportWorker(paths_audio=[], paths_video=[])
    assert worker.project_id == 42
    # Active-Project-Lookup darf nur EINMAL passieren (beim Init)
    assert captured["calls"] == 1


def test_folder_import_worker_explicit_project_id_wins():
    from workers.import_export import FolderImportWorker
    worker = FolderImportWorker(paths_audio=[], paths_video=[], project_id=7)
    assert worker.project_id == 7


def test_folder_import_worker_passes_project_id_to_ingest():
    """Source-Inspektion: ingest_audio + ingest_video muessen mit
    project_id=self.project_id aufgerufen werden."""
    from workers import import_export
    src = inspect.getsource(import_export.FolderImportWorker.run)
    assert "project_id=self.project_id" in src
