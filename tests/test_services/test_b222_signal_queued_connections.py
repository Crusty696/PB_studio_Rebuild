"""B-222 — Verifikation dass Worker-Signal-Connects QueuedConnection nutzen.

Cross-Thread-Sweep: Signal-Slots an UI-Code (lambdas auf self.window.*,
bound methods auf nicht-QObject-Controllern) muessen `Qt.QueuedConnection`
explizit setzen — sonst fallen sie auf DirectConnection zurueck und
laufen im Worker-Thread (UAF-Risiko, B-222 Crash).

Tests pruefen Source-Inspect: pro modifiziertem File mind. 1
`Qt.QueuedConnection` oder `Qt.ConnectionType.QueuedConnection` im
relevanten Bereich.
"""
from __future__ import annotations

import inspect


def _count_queued_connections(module_or_func) -> int:
    src = inspect.getsource(module_or_func)
    return src.count("Qt.ConnectionType.QueuedConnection") + src.count("Qt.QueuedConnection")


def test_b222_worker_dispatcher_uses_queued_connection() -> None:
    """F2: worker_dispatcher Drehscheibe — alle worker.<signal>.connect-
    Calls haben QueuedConnection."""
    from ui.controllers.worker_dispatcher import WorkerDispatcherController

    src = inspect.getsource(WorkerDispatcherController._start_worker_thread)
    # Zaehle QueuedConnection-Marker UND den `qc`-Alias (definiert als
    # `qc = Qt.ConnectionType.QueuedConnection`). Beides zaehlt als
    # explizite Connection-Type-Angabe.
    n_full = src.count("Qt.ConnectionType.QueuedConnection") + src.count("Qt.QueuedConnection")
    n_alias = sum(1 for line in src.splitlines() if line.strip().endswith(", qc,") or line.strip().endswith(", qc)"))
    n = n_full + n_alias
    # Erwartet: mind. 5 connect-Calls mit explizitem Type
    # (worker.finished, worker.error*2, worker.progress, thread.finished
    # cleanup, thread.finished _on_thread_done).
    assert n >= 5, (
        f"B-222 F2: worker_dispatcher hat nur {n} explizite QueuedConnection-Markierungen "
        f"(full={n_full}, qc-alias={n_alias}), erwartet >= 5."
    )


def test_b222_task_manager_callbacks_use_queued_connection() -> None:
    """TaskManager ist der Default-Pfad fuer Import-/Projekt-Worker.

    Plain Python callbacks muessen explizit queued sein, sonst laufen
    UI-Refresh-Callbacks im Worker-Thread.
    """
    from services.task_manager import GlobalTaskManager

    src = inspect.getsource(GlobalTaskManager._start_in_main_thread)
    for marker in (
        "worker.progress.connect(",
        "worker.finished.connect(\n                _guarded_finish",
        "worker.error.connect(\n                _task_error_handler",
        "worker.error.connect(\n                    on_error",
    ):
        assert marker in src
    assert src.count("Qt.ConnectionType.QueuedConnection") >= 4


def test_b222_audio_analysis_controller_uses_queued() -> None:
    from ui.controllers import audio_analysis as ac

    n = _count_queued_connections(ac)
    # Source-Inspect: erwarten mind. 10 (mehrere Worker-Setups mit
    # progress/finished/error pro Step).
    assert n >= 10, (
        f"B-222 F1: audio_analysis hat nur {n} QueuedConnection-Marker, erwartet >= 10."
    )


def test_b222_video_analysis_controller_uses_queued() -> None:
    from ui.controllers import video_analysis as va

    n = _count_queued_connections(va)
    assert n >= 5, (
        f"B-222 F1: video_analysis hat nur {n} QueuedConnection-Marker, erwartet >= 5."
    )


def test_b222_media_workspace_uses_queued() -> None:
    from ui.workspaces import media_workspace as mw

    n = _count_queued_connections(mw)
    # 8 step_keys * (progress + finished) + error + 3 video = ~20
    assert n >= 15, (
        f"B-222 F1: media_workspace hat nur {n} QueuedConnection-Marker, erwartet >= 15."
    )


def test_b222_studio_brain_lazy_loads_graph_cockpit() -> None:
    """F4: StudioBrainWindow konstruiert GraphCockpitTab nicht mehr
    synchron im __init__ — der echte Aufruf steht in
    `_on_tab_changed_lazy_load`."""
    from ui import studio_brain_window as sbw

    cls_src = inspect.getsource(sbw.StudioBrainWindow)
    init_src = inspect.getsource(sbw.StudioBrainWindow.__init__)

    # GraphCockpitTab(...) darf NICHT im __init__ direkt aufgerufen werden,
    # nur im Lazy-Loader.
    init_calls = init_src.count("GraphCockpitTab(")
    assert init_calls == 0, (
        f"B-222 F4: __init__ ruft GraphCockpitTab() {init_calls}x auf — sollte 0 sein "
        "(Lazy-Loading in `_on_tab_changed_lazy_load`)."
    )

    # Aber irgendwo in der Klasse muss GraphCockpitTab konstruierbar bleiben.
    cls_calls = cls_src.count("GraphCockpitTab(")
    assert cls_calls >= 1, (
        f"B-222 F4: GraphCockpitTab darf nicht komplett verschwinden, "
        f"erwartet >= 1 Aufruf in der Klasse, gefunden {cls_calls}."
    )

    # Lazy-Loader-Methode muss existieren.
    assert hasattr(sbw.StudioBrainWindow, "_on_tab_changed_lazy_load"), (
        "B-222 F4: `_on_tab_changed_lazy_load`-Methode fehlt."
    )


def test_b222_studio_brain_lazy_flag_initialized() -> None:
    """F4: __init__ setzt `_graph_cockpit_lazy` Flag."""
    from ui import studio_brain_window as sbw

    init_src = inspect.getsource(sbw.StudioBrainWindow.__init__)
    assert "_graph_cockpit_lazy" in init_src, (
        "B-222 F4: __init__ muss _graph_cockpit_lazy-Flag setzen."
    )


def test_b222_studio_brain_currentchanged_connected() -> None:
    """F4: __init__ connectet `currentChanged` an den Lazy-Loader."""
    from ui import studio_brain_window as sbw

    init_src = inspect.getsource(sbw.StudioBrainWindow.__init__)
    assert "currentChanged.connect" in init_src
    assert "_on_tab_changed_lazy_load" in init_src, (
        "B-222 F4: __init__ muss currentChanged an _on_tab_changed_lazy_load verdrahten."
    )
