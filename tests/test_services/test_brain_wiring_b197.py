"""B-197 regression tests — Brain-Wiring-Quickfixes.

Schliesst die drei kleinsten Lücken aus dem Brain-Audit
(``wiki/synthesis/brain-audit-2026-04-27.md``):

- **F-2** ``StudioBrainWindow.timelineNavigationRequested(float)`` →
  ``main._on_brain_timeline_nav`` → ``timeline.set_playhead_time`` +
  ``video_preview.seek_to``.
- **F-3** ``ui/timeline.py``-Feedback-Pfade rufen jetzt
  ``MemoryUpdaterWorker.notify_feedback()`` über einen modulweiten
  Singleton (``workers.memory_updater.get_memory_updater``).
- **F-4** ``services/pacing_service.py:720`` instantiiert
  ``PacingPipeline`` jetzt mit ``decision_recorder=DecisionRecorder(...)``
  → ``mem_decision``-Persistenz aktiv im Feature-Flag-Pfad.

Die Tests sind Source-Inspection-basiert (kein App-Lauf nötig). Sie
verhindern, dass jemand die Wiring-Stellen unbeabsichtigt entfernt.
"""

from __future__ import annotations

import inspect


# ---------------------------------------------------------------------------
# F-2: timelineNavigationRequested wiring
# ---------------------------------------------------------------------------


def test_main_pbwindow_has_brain_timeline_nav_slot() -> None:
    """B-197 F-2: ``PBWindow._on_brain_timeline_nav`` muss als Slot
    existieren und ``timeline.set_playhead_time`` + ``video_preview.seek_to``
    in seinem Source enthalten.
    """
    import importlib

    main_mod = importlib.import_module("main")
    PBWindow = getattr(main_mod, "PBWindow", None)
    assert PBWindow is not None, "main.PBWindow nicht gefunden"
    assert hasattr(PBWindow, "_on_brain_timeline_nav"), (
        "B-197 F-2: PBWindow._on_brain_timeline_nav fehlt — "
        "timelineNavigationRequested haette keinen Receiver."
    )
    src = inspect.getsource(PBWindow._on_brain_timeline_nav)
    assert "set_playhead_time" in src, (
        "B-197 F-2: _on_brain_timeline_nav muss timeline.set_playhead_time rufen."
    )
    assert "seek_to" in src, (
        "B-197 F-2: _on_brain_timeline_nav muss video_preview.seek_to rufen."
    )


def test_main_open_studio_brain_connects_timeline_nav_signal() -> None:
    """B-197 F-2: ``_open_studio_brain`` muss
    ``win.timelineNavigationRequested.connect(self._on_brain_timeline_nav)``
    rufen — sonst hat das Signal keinen Subscriber.
    """
    import importlib

    main_mod = importlib.import_module("main")
    PBWindow = getattr(main_mod, "PBWindow")

    src = inspect.getsource(PBWindow._open_studio_brain)
    assert "timelineNavigationRequested.connect" in src, (
        "B-197 F-2: _open_studio_brain verbindet "
        "timelineNavigationRequested nicht."
    )
    assert "_on_brain_timeline_nav" in src


# ---------------------------------------------------------------------------
# F-3: FeedbackService → MemoryUpdaterWorker
# ---------------------------------------------------------------------------


def test_memory_updater_has_module_singleton() -> None:
    """B-197 F-3: ``workers.memory_updater.get_memory_updater`` existiert
    und ist ein lazy module-singleton (idempotent bei Mehrfachaufruf
    ohne Side-Effects, mit Lock-Schutz)."""
    from workers import memory_updater as mu

    assert hasattr(mu, "get_memory_updater"), (
        "B-197 F-3: workers/memory_updater.py braucht get_memory_updater()."
    )
    src = inspect.getsource(mu.get_memory_updater)
    # Idempotenz-Marker
    assert "is None" in src, (
        "B-197 F-3: get_memory_updater() muss bereits-erstellte Instanz "
        "wiederverwenden."
    )
    # Lock-geschuetzt
    assert "_singleton_lock" in src or "Lock" in src, (
        "B-197 F-3: get_memory_updater() muss Thread-safe sein."
    )


def test_timeline_notify_memory_updater_exists() -> None:
    """B-197 F-3: ``InteractiveTimeline._notify_memory_updater`` ruft
    ``get_memory_updater().notify_feedback()``.
    """
    from ui.timeline import InteractiveTimeline

    assert hasattr(InteractiveTimeline, "_notify_memory_updater"), (
        "B-197 F-3: InteractiveTimeline._notify_memory_updater fehlt."
    )
    src = inspect.getsource(InteractiveTimeline._notify_memory_updater)
    assert "get_memory_updater" in src
    assert "notify_feedback" in src


def test_timeline_feedback_paths_call_notify_memory_updater() -> None:
    """B-197 F-3: Beide Feedback-Pfade in ``InteractiveTimeline``
    (``record_verdict`` und ``record_rating``) muessen nach einem
    erfolgreichen DB-Write den MemoryUpdater notifizieren — sonst
    wird ``mem_learned_pattern`` nie aktualisiert.
    """
    from ui.timeline import InteractiveTimeline

    src = inspect.getsource(InteractiveTimeline)
    # zaehle die _notify_memory_updater()-Aufrufe — wir erwarten >=2
    # (einer fuer record_verdict, einer fuer record_rating).
    occurrences = src.count("self._notify_memory_updater()")
    assert occurrences >= 2, (
        f"B-197 F-3: erwarte mindestens 2 ``self._notify_memory_updater()``-"
        f"Aufrufe (record_verdict + record_rating), gefunden: {occurrences}."
    )


# ---------------------------------------------------------------------------
# F-4: PacingPipeline + DecisionRecorder
# ---------------------------------------------------------------------------


def test_pacing_pipeline_construction_includes_decision_recorder() -> None:
    """B-197 F-4: ``services/pacing_service.py`` baut die ``PacingPipeline``
    jetzt mit ``decision_recorder=DecisionRecorder(...)``. Ohne diesen
    Parameter blieb ``mem_decision`` leer — die Brain-Tabs zeigten dann
    nichts.
    """
    import services.pacing_service as ps

    src = inspect.getsource(ps)
    # Beide Marker muessen vorkommen, in dem Block der die Pipeline
    # konstruiert.
    assert "PacingPipeline(" in src
    assert "DecisionRecorder(" in src, (
        "B-197 F-4: pacing_service.py muss DecisionRecorder importieren "
        "und an PacingPipeline weitergeben."
    )
    assert "decision_recorder=" in src, (
        "B-197 F-4: PacingPipeline muss explizit "
        "``decision_recorder=DecisionRecorder(...)`` bekommen."
    )


def test_pacing_pipeline_construction_includes_run_id() -> None:
    """B-326: ``DecisionRecorder`` schreibt nur wenn ``PacingPipeline``
    einen ``run_id`` hat. Der Auto-Edit-Feature-Flag-Pfad muss deshalb
    vor ``select_best()`` eine ``mem_pacing_run``-Zeile anlegen und deren
    ID an die Pipeline weitergeben.
    """
    import services.pacing_service as ps

    src = inspect.getsource(ps)
    assert "INSERT INTO mem_pacing_run" in src, (
        "B-326: auto_edit_phase3 muss fuer Studio-Brain einen "
        "mem_pacing_run anlegen."
    )
    assert "run_id=" in src, (
        "B-326: PacingPipeline muss die mem_pacing_run-ID als run_id "
        "bekommen, sonst bleibt mem_decision leer."
    )


def test_auto_edit_finish_sets_active_pacing_run_for_feedback() -> None:
    """B-326: Nach Auto-Edit muss die Timeline den neuesten
    ``mem_pacing_run`` kennen, sonst erreichen A/R/S/1-5-Feedback-Hotkeys
    keine ``mem_decision``.
    """
    from ui.controllers.edit_workspace import EditWorkspaceController

    src = inspect.getsource(EditWorkspaceController._on_auto_edit_finished)
    assert "set_active_pacing_run" in src, (
        "B-326: _on_auto_edit_finished muss timeline_view.set_active_pacing_run(...) "
        "aufrufen."
    )
    assert "mem_pacing_run" in src, (
        "B-326: _on_auto_edit_finished muss den neuesten mem_pacing_run fuer "
        "den Audio-Track aufloesen."
    )
