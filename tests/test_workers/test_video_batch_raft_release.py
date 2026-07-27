"""Batch-Cleanup muss den RAFT-aux-Slot des ModelManagers mit raeumen.

Befund (Audit 2026-07-27, Bereich gpu-threads, bestaetigt):
Der Batch-Preload holt RAFT ueber ``ModelManager.load_raft()``; das
zurueckgegebene Modell IST ``ModelManager._aux_model``. Das Cleanup rief
``raft_m.cpu()`` + ``del raft_m`` direkt auf dem Objekt — die Parameter wanderten
in-place auf CPU, ``_aux_model``/``_aux_model_type='raft'`` blieben aber gesetzt.
Der naechste ``load_raft()`` traf damit auf einen Cache-Hit und lieferte ein
CPU-Modell zusammen mit ``device='cuda'`` -> Mixed-Device-RuntimeError in
``_raft_motion_score``, still abgefangen, Motion faellt auf den billigen
Frame-Diff-Score zurueck.

Kein GPU-Zugriff: der ModelManager wird durch eine Attrappe ersetzt, die nur
die Slot-Semantik von load_raft/unload_raft nachbildet.
"""

from __future__ import annotations

import sys
import types

import pytest


class _FakeRaft:
    def __init__(self) -> None:
        self.on_cpu = False

    def cpu(self):
        self.on_cpu = True
        return self


class _FakeModelManager:
    """Bildet den aux-Slot nach: load_raft() gibt das Slot-Objekt zurueck."""

    aux_model: _FakeRaft | None = None
    aux_type: str | None = None

    @classmethod
    def load_raft(cls):
        if cls.aux_type == "raft" and cls.aux_model is not None:
            return cls.aux_model, "cuda"
        cls.aux_model = _FakeRaft()
        cls.aux_type = "raft"
        return cls.aux_model, "cuda"

    def unload_raft(self) -> None:
        if type(self).aux_type == "raft":
            if type(self).aux_model is not None:
                type(self).aux_model.cpu()
            type(self).aux_model = None
            type(self).aux_type = None


@pytest.fixture
def fake_model_manager(monkeypatch):
    _FakeModelManager.aux_model = None
    _FakeModelManager.aux_type = None
    module = types.ModuleType("services.model_manager")
    module.ModelManager = _FakeModelManager
    monkeypatch.setitem(sys.modules, "services.model_manager", module)
    return _FakeModelManager


def test_release_batch_raft_clears_aux_slot(fake_model_manager) -> None:
    from workers.video import _release_batch_raft

    raft_model_device = fake_model_manager.load_raft()
    assert fake_model_manager.aux_type == "raft"

    _release_batch_raft(raft_model_device)

    assert fake_model_manager.aux_model is None, (
        "aux-Slot des ModelManagers ist nach dem Batch-Cleanup noch belegt — "
        "der naechste load_raft() liefert per Cache-Hit ein CPU-Modell mit "
        "device='cuda'."
    )
    assert fake_model_manager.aux_type is None


def test_next_load_raft_returns_fresh_model(fake_model_manager) -> None:
    """Kern-Symptom: nach dem Cleanup darf load_raft() kein auf CPU
    geschobenes Modell aus dem Cache liefern."""
    from workers.video import _release_batch_raft

    first = fake_model_manager.load_raft()
    _release_batch_raft(first)

    second_model, device = fake_model_manager.load_raft()
    assert device == "cuda"
    assert second_model is not first[0]
    assert second_model.on_cpu is False


def test_release_batch_raft_is_noop_without_model(fake_model_manager) -> None:
    from workers.video import _release_batch_raft

    _release_batch_raft(None)
    assert fake_model_manager.aux_model is None
