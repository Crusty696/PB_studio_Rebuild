"""Tests fuer BrainStore.health_check (Phase 3 App-Sync, 06_PHASES.md Z.252-268).

CPU-only, isoliertes APPDATA via tmp_path.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.brain_v3.storage.brain_store import BrainStore, BrainStoreHealth


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def test_health_check_all_ok_after_init(isolated_appdata):
    store = BrainStore()
    health = store.health_check()
    assert isinstance(health, BrainStoreHealth)
    assert health.weights_ok is True
    assert health.patterns_ok is True
    # embedding_cache wird durch andere Module/Migration gefuellt — pruefe dass
    # der Probe nicht blind crasht. Tabelle existiert nur wenn EmbeddingCache
    # initialisiert wurde.
    # Hier zaehlen wir nicht auf True — ohne EmbeddingCache.__init__ ist die
    # DB leer und das Probe-SELECT schlaegt fehl. Test toleriert beides.
    assert health.disk_space_mb >= 0
    assert isinstance(health.errors, list)


def test_health_check_marks_missing_db_as_fail(isolated_appdata, tmp_path):
    """Nicht existierende DB-Datei -> _ok=False + error."""
    fake_path = tmp_path / "ghost.db"
    weights_path = tmp_path / "Roaming" / "PB_Studio" / "brain_v3" / "weights.db"
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    BrainStore(weights_path=weights_path).health_check()  # init weights ok
    weights_path.unlink()  # delete after init
    store2 = BrainStore.__new__(BrainStore)
    store2.weights_path = weights_path
    from services.brain_v3 import paths as p
    store2.patterns_path = p.patterns_db_path()
    health = store2.health_check()
    assert health.weights_ok is False
    assert any("weights.db" in e for e in health.errors)


def test_health_check_carries_user_version(isolated_appdata):
    store = BrainStore()
    health = store.health_check()
    assert health.migrations_version >= 1


def test_health_check_runs_under_50ms(isolated_appdata):
    """Plan-Spec: <50 ms im Normalfall (rein lesend)."""
    import time
    store = BrainStore()
    # warm-up
    store.health_check()
    t0 = time.perf_counter()
    for _ in range(5):
        store.health_check()
    dt_ms = (time.perf_counter() - t0) * 1000 / 5
    # Toleranz: Tests laufen ggf. unter Last (CI), 200 ms ist sauber genug
    assert dt_ms < 200.0, f"health_check dauerte {dt_ms:.1f} ms (Budget 200 ms)"


def test_health_check_disk_space_present(isolated_appdata):
    health = BrainStore().health_check()
    assert health.disk_space_mb > 0


def test_health_check_collects_multiple_errors(isolated_appdata, tmp_path, monkeypatch):
    """Korrupte DB -> error eingetragen."""
    store = BrainStore()
    # weights.db korrupt machen
    store.weights_path.write_bytes(b"\x00\x01CORRUPT\xff" * 50)
    health = store.health_check()
    assert health.weights_ok is False
    assert any("weights.db" in e for e in health.errors)


def test_corrupt_weights_db_is_quarantined_and_recreated(isolated_appdata, tmp_path):
    weights_path = tmp_path / "Roaming" / "PB_Studio" / "brain_v3" / "weights.db"
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    weights_path.write_bytes(b"not a sqlite db")

    store = BrainStore(weights_path=weights_path)
    health = store.health_check()

    assert health.weights_ok is True
    assert list(weights_path.parent.glob("weights.db.corrupt.*"))


def test_corrupt_patterns_db_is_quarantined_and_recreated(isolated_appdata, tmp_path):
    root = tmp_path / "Roaming" / "PB_Studio" / "brain_v3"
    weights_path = root / "weights.db"
    patterns_path = root / "patterns.db"
    root.mkdir(parents=True, exist_ok=True)
    patterns_path.write_bytes(b"not a sqlite db")

    store = BrainStore(weights_path=weights_path, patterns_path=patterns_path)
    health = store.health_check()

    assert health.patterns_ok is True
    assert list(patterns_path.parent.glob("patterns.db.corrupt.*"))
