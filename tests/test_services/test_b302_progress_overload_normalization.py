"""B-302 Restluecke (2026-08-11): Der Signal-Overload war nur konsumentenseitig
entschaerft (``task_manager_dock._as_int``). Der vertauschte Payload
``("audio_load", 0.1)`` lief weiterhin durch die ganze Kette: ``TaskInfo.progress``
wurde ein ``str``, ``TaskInfo.message`` ein ``float`` — der User sah eine
Endlos-Marquee und "0.1" als Meldung.

Erwartung: Normalisierung an der Quelle -> (int Prozent, str Stage-Key).
"""
from __future__ import annotations

import pytest

from services.task_manager import (
    GlobalTaskManager,
    coerce_progress_int,
    normalize_progress_args,
)


def test_stage_overload_is_turned_back_into_pct_and_message():
    """(str, float) = Stage-Overload -> Fraction wird Prozent, Key wird Meldung."""
    assert normalize_progress_args("audio_load", 0.1) == (10, "audio_load")
    assert normalize_progress_args("db_write", 1.0) == (100, "db_write")


def test_regular_overload_is_untouched():
    """(int, str) = Regelfall bleibt unveraendert."""
    assert normalize_progress_args(42, "rendere") == (42, "rendere")
    assert normalize_progress_args(0, "") == (0, "")


def test_broken_types_never_produce_a_non_int_progress():
    assert isinstance(normalize_progress_args(None, None)[0], int)
    assert coerce_progress_int("nonsense") == 0
    assert coerce_progress_int("7") == 7
    assert coerce_progress_int(3.9) == 3


def test_update_task_stores_int_progress_even_for_broken_worker(qapp):
    """Zweite Ebene: update_task darf nie einen str in TaskInfo.progress legen.

    Ohne Coercion landete ``t.progress = "audio_load"`` in der TaskInfo und
    ``QProgressBar.setValue(str)`` warf die Qt-TypeError aus dem C++-Slot
    (kein Python-except-Frame) -> Reentrancy -> 0xC0000005.
    """
    tm = GlobalTaskManager()
    task = tm._register_unstarted_task(
        "task_b302", "B-302", "", "running", ""
    )
    tm.update_task("task_b302", "audio_load", message=0.1)

    stored = tm._tasks["task_b302"]
    assert isinstance(stored.progress, int), stored.progress
    assert isinstance(stored.total, int)
    assert isinstance(stored.message, str), stored.message
