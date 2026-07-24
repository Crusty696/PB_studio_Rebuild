"""B-679: oom_recovery(unload_scope="aux") darf bei anhaltendem OOM NUR RAFT/aux
entladen, nicht das main-Modell.

Vorher rief oom_recovery im 2. Versuch immer ``ModelManager().unload()`` (main +
aux). Fuer RAFT-Operationen (``_raft_motion_score``) schob das die im Batch
gehaltene SigLIP-Referenz auf CPU -> alle folgenden Clips crashten mit einem
Mixed-Device-RuntimeError.
"""

import time

import pytest

from services.model_manager import ModelManager, oom_recovery


@pytest.fixture(autouse=True)
def _fast_and_spied(monkeypatch):
    """Kein echtes Sleep; unload/unload_raft protokollieren statt ausfuehren."""
    calls = []
    monkeypatch.setattr(ModelManager, "unload", lambda self: calls.append("unload"))
    monkeypatch.setattr(ModelManager, "unload_raft", lambda self: calls.append("unload_raft"))
    # oom_recovery macht intern ``import time as _time; _time.sleep(...)`` —
    # das Patchen von time.sleep greift dort (selbes Modulobjekt).
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)
    return calls


def test_aux_scope_unloads_only_raft(_fast_and_spied):
    @oom_recovery(unload_scope="aux")
    def _always_oom():
        raise RuntimeError("CUDA error: out of memory")

    with pytest.raises(RuntimeError, match="out of memory"):
        _always_oom()

    # B-679: RAFT/aux wird entladen, main-Modell (unload) NICHT.
    assert "unload_raft" in _fast_and_spied
    assert "unload" not in _fast_and_spied


def test_default_scope_still_unloads_all(_fast_and_spied):
    """Rueckwaerts-Kompatibilitaet: bare @oom_recovery entlaedt weiter alles."""
    @oom_recovery
    def _always_oom():
        raise RuntimeError("out of memory")

    with pytest.raises(RuntimeError, match="out of memory"):
        _always_oom()

    assert "unload" in _fast_and_spied
    assert "unload_raft" not in _fast_and_spied


def test_non_oom_error_passes_through_without_unload(_fast_and_spied):
    """Ein Nicht-OOM-Fehler wird sofort durchgereicht, ohne Unload."""
    @oom_recovery(unload_scope="aux")
    def _boom():
        raise ValueError("kein OOM")

    with pytest.raises(ValueError, match="kein OOM"):
        _boom()

    assert _fast_and_spied == []
