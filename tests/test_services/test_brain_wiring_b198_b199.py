"""B-198 + B-199 regression tests — Brain-Wiring (F-1 + F-5).

- **F-1** (B-198): ``SteerTab.runRequested`` triggert via
  ``GlobalTaskManager.agent_command_signal`` einen ``auto_edit``-
  Task.
- **F-5** (B-199): ``CockpitViewModel.populate_from_brain_service``
  laedt ``BrainService.graph_nodes_and_edges()`` in den in-memory
  GraphService. Refresh-Button repopulatet via ``refresh_data``.

Tests sind GPU-frei: F-1 ueber Source-Inspection des Slot-Codes,
F-5 mit Mock-BrainService (kein echtes SQLite).
"""

from __future__ import annotations

import inspect

import pytest


# ---------------------------------------------------------------------------
# B-198 F-1: SteerTab.runRequested → auto_edit
# ---------------------------------------------------------------------------


def test_main_pbwindow_has_brain_run_slot() -> None:
    """B-198 F-1: ``PBWindow._on_brain_run_requested`` muss als Slot
    existieren und das ``agent_command_signal`` mit Action ``auto_edit``
    triggern."""
    import importlib

    main_mod = importlib.import_module("main")
    PBWindow = getattr(main_mod, "PBWindow", None)
    assert PBWindow is not None
    assert hasattr(PBWindow, "_on_brain_run_requested"), (
        "B-198 F-1: PBWindow._on_brain_run_requested fehlt — "
        "SteerTab.runRequested haette keinen Receiver."
    )
    src = inspect.getsource(PBWindow._on_brain_run_requested)
    assert "agent_command_signal" in src, (
        "B-198 F-1: _on_brain_run_requested muss "
        "tm.agent_command_signal.emit aufrufen."
    )
    assert '"auto_edit"' in src or "'auto_edit'" in src, (
        "B-198 F-1: _on_brain_run_requested muss mit der Worker-Action "
        "``auto_edit`` emittieren."
    )
    assert "audio_track_id" in src, (
        "B-198 F-1: _on_brain_run_requested muss ``audio_track_id`` aus dem "
        "Snapshot extrahieren."
    )


def test_main_open_studio_brain_connects_run_signal() -> None:
    """B-198 F-1: ``_open_studio_brain`` muss ``SteerTab.runRequested``
    mit ``_on_brain_run_requested`` verbinden — sonst feuert der Run-
    Button weiterhin ins Leere.
    """
    import importlib

    main_mod = importlib.import_module("main")
    PBWindow = getattr(main_mod, "PBWindow")

    src = inspect.getsource(PBWindow._open_studio_brain)
    assert "runRequested" in src, (
        "B-198 F-1: _open_studio_brain verbindet ``runRequested`` nicht."
    )
    assert "_on_brain_run_requested" in src


# ---------------------------------------------------------------------------
# B-199 F-5: Cockpit-Populator
# ---------------------------------------------------------------------------


class _StubBrainService:
    """Minimaler BrainService-Stub fuer F-5-Tests. Liefert ein Snapshot-
    Dict in dem Format das ``CockpitViewModel`` erwartet.
    """

    def __init__(self, snapshot: dict | None = None):
        self._snapshot = snapshot or {
            "nodes": [
                {
                    "scene_id": 1,
                    "role": "hero",
                    "mood_refined": "energetic",
                    "style_bucket_id": 7,
                    "style_bucket_name": "Drum & Bass",
                },
                {
                    "scene_id": 2,
                    "role": "filler",
                    "mood_refined": "ambient",
                    "style_bucket_id": 7,
                    "style_bucket_name": "Drum & Bass",
                },
                {
                    "scene_id": 3,
                    "role": "hero",
                    "mood_refined": "dark",
                    "style_bucket_id": None,
                    "style_bucket_name": None,
                },
            ],
            "edges": [
                {"a": 1, "b": 2, "similarity": 0.85},
                {"a": 1, "b": 3, "similarity": 0.42},
            ],
            "scene_count": 3,
        }

    def graph_nodes_and_edges(self) -> dict:
        return self._snapshot


def test_cockpit_view_model_populate_from_brain_service() -> None:
    """B-199 F-5: ``populate_from_brain_service`` muss Knoten + Kanten
    in den in-memory GraphService schieben.
    """
    from services.graph.cockpit_view_model import CockpitViewModel

    vm = CockpitViewModel()
    assert vm.stats() == {"n_nodes": 0, "n_edges": 0}

    result = vm.populate_from_brain_service(_StubBrainService())

    assert result["nodes"] == 3, f"erwartet 3 Knoten, bekommen {result}"
    # Jede Kante wird bidirektional eingefuegt → 2 Snapshot-Edges → 4 GraphService-Edges.
    assert result["edges"] == 4
    assert result["scene_count"] == 3
    assert vm.stats() == {"n_nodes": 3, "n_edges": 4}


def test_cockpit_view_model_populate_is_atomic_swap() -> None:
    """B-199 F-5: erneutes Populate ersetzt den Graph komplett —
    keine Duplikate.
    """
    from services.graph.cockpit_view_model import CockpitViewModel

    vm = CockpitViewModel()
    vm.populate_from_brain_service(_StubBrainService())
    first_nodes = vm.stats()["n_nodes"]

    # Re-populate mit den gleichen Daten — Counts duerfen sich nicht
    # verdoppeln.
    vm.populate_from_brain_service(_StubBrainService())
    assert vm.stats()["n_nodes"] == first_nodes


def test_cockpit_view_model_refresh_data_uses_data_source() -> None:
    """B-199 F-5: ``set_data_source`` + ``refresh_data`` ist die
    Refresh-Button-API. Ohne Data-Source ist es no-op.
    """
    from services.graph.cockpit_view_model import CockpitViewModel

    vm = CockpitViewModel()
    # Ohne Source → no-op-Result.
    result = vm.refresh_data()
    assert result["nodes"] == 0

    vm.set_data_source(_StubBrainService())
    result = vm.refresh_data()
    assert result["nodes"] == 3


def test_cockpit_view_model_handles_brain_service_failure() -> None:
    """B-199 F-5: wenn ``graph_nodes_and_edges`` raised, faengt das
    ViewModel das ab und liefert einen Error-Hinweis statt zu crashen.
    """
    from services.graph.cockpit_view_model import CockpitViewModel

    class _BrokenBrainService:
        def graph_nodes_and_edges(self) -> dict:
            raise RuntimeError("simulated DB outage")

    vm = CockpitViewModel()
    result = vm.populate_from_brain_service(_BrokenBrainService())
    assert "error" in result
    assert vm.stats() == {"n_nodes": 0, "n_edges": 0}


def test_studio_brain_window_calls_populate_on_open() -> None:
    """B-199 F-5: ``StudioBrainWindow`` muss beim Cockpit-Tab-Bau den
    ViewModel ueber den BrainService befuellen — sonst ist der Tab leer.
    """
    import inspect as _inspect

    from ui import studio_brain_window as sbw

    # B-222 F4: Cockpit-VM-Setup ist jetzt LAZY — populate +
    # set_data_source passieren in `_on_tab_changed_lazy_load` beim ersten
    # User-Klick auf Tab 5, NICHT mehr im `__init__`. Wir scannen daher
    # die ganze Klasse statt nur `__init__`.
    src = _inspect.getsource(sbw.StudioBrainWindow)
    assert "populate_from_brain_service" in src, (
        "B-199 F-5: StudioBrainWindow muss den Cockpit-VM befuellen "
        "(in __init__ ODER im Lazy-Loader, B-222 F4)."
    )
    assert "set_data_source" in src, (
        "B-199 F-5: StudioBrainWindow muss die BrainService-Daten-Quelle "
        "im Cockpit-VM merken (Refresh-Button-Pfad)."
    )


def test_graph_cockpit_tab_refresh_calls_refresh_data() -> None:
    """B-199 F-5: ``GraphCockpitTab._refresh_html`` muss
    ``self._vm.refresh_data()`` aufrufen — sonst ist der Refresh-Button
    nur ein Sigma-Re-Render auf veralteten Daten.
    """
    import inspect as _inspect

    from ui.widgets.graph_cockpit_tab import GraphCockpitTab

    src = _inspect.getsource(GraphCockpitTab._refresh_html)
    assert "refresh_data" in src, (
        "B-199 F-5: _refresh_html muss self._vm.refresh_data() rufen."
    )
