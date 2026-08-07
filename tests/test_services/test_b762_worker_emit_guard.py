"""B-762: Shutdown-Crash — Signal-Emits auf geloeschtem Qt-Objekt.

Beim App-Schliessen waehrend laufender Videoanalyse wurde das Qt-C++-Objekt
VideoAnalysisPipelineWorker geloescht, waehrend der Python-Thread weiterlief.
Ungeschuetzte ``self.<signal>.emit(...)``-Aufrufe warfen dann
``RuntimeError: Internal C++ object (VideoAnalysisPipelineWorker) already
deleted`` — auch im Fehlerpfad selbst — Prozess starb mit Exit 9.

Fix: Modul-Level-Helper ``_emit_shielded`` in workers/video.py, der den
Emit-Aufruf (als Lambda, weil schon der Attributzugriff wirft) ausfuehrt
und RuntimeError schluckt.
"""

import inspect
import re

import pytest
import shiboken6  # noqa: F401 — direkter delete()-Zugriff in Test B

from workers.video import VideoAnalysisPipelineWorker, _emit_shielded


# ── Test A: Helper-Vertrag ────────────────────────────────────────────────

def test_emit_shielded_swallows_runtimeerror():
    """RuntimeError aus dem Callable wird geschluckt, Rueckgabe False."""
    def _boom():
        raise RuntimeError("Internal C++ object (X) already deleted")

    assert _emit_shielded(_boom, "progress") is False


def test_emit_shielded_returns_true_on_success():
    calls = []
    assert _emit_shielded(lambda: calls.append(1), "progress") is True
    assert calls == [1]


def test_emit_shielded_does_not_swallow_other_exceptions():
    """Nur RuntimeError (Qt-deleted) wird geschluckt — andere Fehler propagieren."""
    def _boom():
        raise ValueError("anderer Fehler")

    with pytest.raises(ValueError):
        _emit_shielded(_boom, "progress")


# ── Test B: echtes geloeschtes Qt-Objekt ──────────────────────────────────

def test_emit_shielded_on_deleted_worker(qapp):
    """Emit auf shiboken-geloeschtem Worker darf nicht crashen -> False."""
    w = VideoAnalysisPipelineWorker(batch=[(1, "t")])
    shiboken6.delete(w)
    assert not shiboken6.isValid(w)
    assert _emit_shielded(lambda: w.progress.emit(1, "x"), "progress") is False


# ── Test C: Quellcode-Vertrag fuer run() ─────────────────────────────────

def test_run_source_has_no_naked_terminal_emits():
    """Die vier B-762-Stellen in run() duerfen nur noch via _emit_shielded
    emittieren — kein nackter error/finished-Emit im outer except bzw.
    finally-Fallback."""
    src = inspect.getsource(VideoAnalysisPipelineWorker.run)

    # Stelle 3: outer except — kein nacktes self.error.emit(last_clip_id
    assert not re.search(r"(?<!lambda: )self\.error\.emit\(last_clip_id", src), (
        "nackter self.error.emit(last_clip_id ...) in run() gefunden (B-762)"
    )
    # Stelle 4: finally-Fallback — kein nacktes self.finished.emit(last_clip_id, {})
    assert not re.search(
        r"(?<!lambda: )self\.finished\.emit\(last_clip_id, \{\}\)", src
    ), "nackter self.finished.emit(last_clip_id, {}) in run() gefunden (B-762)"
    # Helper muss in run() verwendet werden
    assert "_emit_shielded" in src
