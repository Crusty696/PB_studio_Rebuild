"""B-576 Restluecke (2026-08-11): ``EmbeddingScheduler.job_skipped`` hatte
keinen UI-Konsumenten. Ein nicht oeffnbares Video wurde sauber uebersprungen —
der User erfuhr davon nichts.

Erwartung: Skip landet in der Konsole; ein ECHTER Skip (unlesbares Medium)
zusaetzlich in der Fehler-Statuszeile. Cache-Hits (Normalfall B-707) duerfen
die Statuszeile NICHT belegen.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal


class _SchedulerStub(QObject):
    job_skipped = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._running = True

    def is_running(self):
        return self._running

    def submit_path(self, media_hash, source_path, media_type):
        return "job-1"


class _ConsoleStub:
    def __init__(self):
        self.lines: list[str] = []

    def append(self, text):
        self.lines.append(text)


class _WindowStub:
    def __init__(self, scheduler):
        self.console_text = _ConsoleStub()
        self._brain_v3_scheduler = scheduler
        self.status_errors: list[str] = []

    def show_status_error(self, text, timeout_ms=15000):
        self.status_errors.append(text)


@pytest.fixture()
def wired(qapp):
    from ui.controllers.import_media import ImportMediaController

    scheduler = _SchedulerStub()
    window = _WindowStub(scheduler)
    ctrl = ImportMediaController.__new__(ImportMediaController)
    ctrl.window = window
    ctrl._on_hash_registered_for_embedding("a" * 16, "x.mp4", "video")
    return ctrl, window, scheduler


def test_unreadable_media_skip_reaches_console_and_statusbar(wired):
    ctrl, window, scheduler = wired

    scheduler.job_skipped.emit("deadbeefcafe0001", "Video nicht oeffnbar: x.mp4")

    joined = " | ".join(window.console_text.lines)
    assert "uebersprungen" in joined, joined
    assert "Video nicht oeffnbar" in joined
    assert window.status_errors, "echter Skip muss den User erreichen"
    assert "Video nicht oeffnbar" in window.status_errors[0]


def test_cache_hit_skip_does_not_raise_a_status_error(wired):
    ctrl, window, scheduler = wired

    scheduler.job_skipped.emit("deadbeefcafe0002", "cache-hit (siglip2/1)")

    assert window.status_errors == [], "Cache-Hit ist der Normalfall, kein Fehler"


def test_bridge_connects_only_once_per_scheduler(wired):
    ctrl, window, scheduler = wired

    # Zweiter Import mit demselben Scheduler darf nicht erneut connecten.
    ctrl._on_hash_registered_for_embedding("b" * 16, "y.mp4", "video")
    window.console_text.lines.clear()
    scheduler.job_skipped.emit("deadbeefcafe0003", "Video nicht oeffnbar: y.mp4")

    skip_lines = [l for l in window.console_text.lines if "uebersprungen" in l]
    assert len(skip_lines) == 1, window.console_text.lines
