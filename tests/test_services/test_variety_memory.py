"""FR-S3-3 / Task-S3-3: Project-Wide Variety-Memory.

In-Memory + DB-agnostic Variant. Markiert Clip-IDs als "kürzlich verwendet"
mit Timestamp und liefert Penalty wenn dieselbe ID innerhalb des Fensters
wieder gefragt wird.
"""
import pytest

from services.pacing.variety_memory import VarietyMemory


def test_recent_clip_within_window_blocks():
    vm = VarietyMemory(window_sec=30.0)
    vm.record(clip_id=42, t_sec=0.0)
    assert vm.is_recent(clip_id=42, t_sec=10.0)
    assert vm.is_recent(clip_id=42, t_sec=29.99)


def test_clip_outside_window_is_not_recent():
    vm = VarietyMemory(window_sec=30.0)
    vm.record(clip_id=42, t_sec=0.0)
    assert not vm.is_recent(clip_id=42, t_sec=30.0)
    assert not vm.is_recent(clip_id=42, t_sec=60.0)


def test_unknown_clip_is_not_recent():
    vm = VarietyMemory(window_sec=30.0)
    assert not vm.is_recent(clip_id=99, t_sec=10.0)


def test_window_configurable():
    vm = VarietyMemory(window_sec=5.0)
    vm.record(clip_id=1, t_sec=0.0)
    assert vm.is_recent(1, 4.99)
    assert not vm.is_recent(1, 5.0)


def test_record_updates_timestamp():
    vm = VarietyMemory(window_sec=10.0)
    vm.record(clip_id=7, t_sec=0.0)
    vm.record(clip_id=7, t_sec=20.0)  # Re-Use nach Fenster
    # Der zweite Record ersetzt den ersten
    assert vm.is_recent(7, 25.0)


def test_penalty_score():
    vm = VarietyMemory(window_sec=30.0)
    vm.record(clip_id=1, t_sec=0.0)
    # Direkt am Anfang Penalty=1.0
    assert vm.penalty(1, 0.0) == 1.0
    # Linearer Decay → 0 bei window_sec
    p_mid = vm.penalty(1, 15.0)
    assert 0.4 < p_mid < 0.6
    assert vm.penalty(1, 30.0) == 0.0


def test_penalty_for_unknown_is_zero():
    vm = VarietyMemory(window_sec=30.0)
    assert vm.penalty(999, 5.0) == 0.0


def test_clear():
    vm = VarietyMemory(window_sec=30.0)
    vm.record(1, 0.0)
    vm.clear()
    assert not vm.is_recent(1, 5.0)
    assert vm.penalty(1, 5.0) == 0.0


def test_window_must_be_positive():
    with pytest.raises(ValueError):
        VarietyMemory(window_sec=0.0)
    with pytest.raises(ValueError):
        VarietyMemory(window_sec=-1.0)
