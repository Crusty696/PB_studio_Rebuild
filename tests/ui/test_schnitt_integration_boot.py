"""Integration-Smoke-Tests fuer das SCHNITT-Wiring (Plan
docs/superpowers/plans/2026-05-09-schnitt-integration-wiring-fix/).

Diese Tests fangen die drei Audit-Bugs B-284 / B-285 / B-286 in Zukunft
ab. Stilistisch im selben Source-Inspection-Pattern wie
``test_bug_hunter_batch_2026_04_27.py`` — keine ganze MainWindow-
Konstruktion, dafuer harte Aussagen ueber den Production-Boot-Pfad.

R-3 des Wiring-Plans: jede Phase, die Wiring beruehrt, fuegt mindestens
einen Test hinzu, der den **Production-Boot-Pfad** belegt. R-10
verlangt, dass diese Tests die Audit-Greps replizieren.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_SETUP = REPO_ROOT / "ui" / "controllers" / "workspace_setup.py"
EDIT_WORKSPACE = REPO_ROOT / "ui" / "controllers" / "edit_workspace.py"
PROJECT_MANAGEMENT = REPO_ROOT / "ui" / "controllers" / "project_management.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# B-284 — SchnittController muss in Production instanziiert sein
# ---------------------------------------------------------------------------


def test_b284_schnitt_controller_instantiated_in_workspace_setup() -> None:
    """B-284-Regression: ohne Production-Instanziierung sind alle
    Empty-State-Klicks, Cancel, Worker-Progress-Bridges tot."""
    src = _read(WORKSPACE_SETUP)
    assert "SchnittController(" in src, (
        "B-284: ui/controllers/workspace_setup.py instanziiert keinen "
        "SchnittController. Audit hatte festgestellt, dass der Controller "
        "nur in Tests existierte. Re-Audit: bitte Phase A des "
        "Integration-Wiring-Fix-Plans erneut anwenden."
    )
    assert "self.window._schnitt_ctrl" in src, (
        "B-284: SchnittController ist konstruiert, aber nicht als "
        "self.window._schnitt_ctrl exposed. Triple-Hook "
        "(set_active_project_protected) ist darauf angewiesen."
    )


def test_b284_controller_signals_bridged_to_edit_workspace() -> None:
    """B-284-Regression: Controller-Signale ohne Production-Slot waeren
    Funkstille. Pruefen, dass Adapter-Slots verbunden sind."""
    src = _read(WORKSPACE_SETUP)
    expected_connects = [
        "request_auto_edit_with_profile.connect",
        "request_regenerate.connect",
        "request_open_settings.connect",
    ]
    for needle in expected_connects:
        assert needle in src, (
            f"B-284: workspace_setup.py verbindet '{needle}' nicht. "
            f"Empty-State-Preset-Klicks und/oder Re-Generate-Confirm-Dialog "
            f"erreichen edit_workspace nicht."
        )


def test_b284_edit_workspace_has_schnitt_adapter_slots() -> None:
    """B-284-Regression: Adapter-Slots muessen existieren, sonst sind
    die Controller-Signale aus dem vorigen Test ins Leere geroutet."""
    src = _read(EDIT_WORKSPACE)
    for slot in ("_on_schnitt_auto_edit_request", "_on_schnitt_regenerate_request"):
        assert f"def {slot}" in src, (
            f"B-284: edit_workspace.py fehlt Adapter-Slot {slot}. "
            f"SchnittController.request_*.connect zielt ins Leere."
        )


def test_b284_attach_worker_called_in_both_worker_paths() -> None:
    """B-284-Regression: Ohne attach_worker erreichen worker.progress /
    done / failed nicht die SchnittLoadingView."""
    src = _read(EDIT_WORKSPACE)
    # zwei Worker-Pfade: AutoEditWorker (in _auto_edit_to_beat) und
    # _CutsWorker (in _generate_timeline_impl). Beide muessen
    # ctrl.attach_worker rufen.
    matches = re.findall(r"ctrl\.attach_worker\s*\(", src)
    assert len(matches) >= 2, (
        f"B-284: edit_workspace.py ruft ctrl.attach_worker {len(matches)}x. "
        f"Erwartet >= 2 (je einer in _auto_edit_to_beat und "
        f"_generate_timeline_impl)."
    )


# ---------------------------------------------------------------------------
# B-285 — Triple-Hook fuer set_active_project
# ---------------------------------------------------------------------------


def test_b285_helper_defined_in_workspace_setup() -> None:
    """B-285-Regression: Helper kapselt set_active_project-Push."""
    src = _read(WORKSPACE_SETUP)
    assert "def _push_active_project_to_schnitt" in src, (
        "B-285: WorkspaceSetupController._push_active_project_to_schnitt "
        "fehlt. Ohne ihn bleibt _schnitt_ws._project_id permanent None."
    )


def test_b285_triple_hook_calls_helper() -> None:
    """B-285-Regression: Helper muss aus drei Stellen gerufen werden
    (Plan R-5: Tab-Wechsel, Cockpit-Action, ProjectManager.project_changed)."""
    setup_src = _read(WORKSPACE_SETUP)
    pm_src = _read(PROJECT_MANAGEMENT)
    workspace_calls = setup_src.count("self._push_active_project_to_schnitt()")
    pm_calls = pm_src.count("_push_active_project_to_schnitt()")
    total = workspace_calls + pm_calls
    assert total >= 3, (
        f"B-285: Triple-Hook (R-5) unvollstaendig. "
        f"_push_active_project_to_schnitt wird {total}x gerufen "
        f"(workspace_setup={workspace_calls}, project_management={pm_calls}). "
        f"Erwartet >= 3 (Tab-Wechsel + Cockpit-Action + project_changed)."
    )


def test_b285_helper_pushes_to_tab_rl_notes_too() -> None:
    """B-285-Regression: ProjectNotesService braucht ebenfalls den Pid."""
    src = _read(WORKSPACE_SETUP)
    assert "tab_rl_notes.set_active_project" in src, (
        "B-285: _push_active_project_to_schnitt informiert "
        "tab_rl_notes nicht. Notes lassen sich dann nicht persistieren."
    )


# ---------------------------------------------------------------------------
# B-286 — keine Doppel-Verdrahtung an btn_regenerate
# ---------------------------------------------------------------------------


def test_b286_no_direct_btn_regenerate_connect_in_workspace_setup() -> None:
    """B-286-Regression: btn_regenerate gehoert dem SchnittController
    (Plan A13: Confirm-Dialog mit Lock-Count + Diff-Preview vor
    destruktivem Re-Generate). Direkt-Connect waere Bypass."""
    src = _read(WORKSPACE_SETUP)
    assert "btn_regenerate.clicked.connect" not in src, (
        "B-286: workspace_setup.py haengt btn_regenerate.clicked direkt "
        "an. Damit wird der ConfirmDialog des SchnittControllers "
        "umgangen — gesperrte Clips koennen ungewollt verloren gehen."
    )


# ---------------------------------------------------------------------------
# Plan R-10 — Audit-Reproduktions-Greps zusammengefasst
# ---------------------------------------------------------------------------


def test_audit_reproduction_grep_all_three_bugs() -> None:
    """R-10: Schluss-Audit-Reproduktion. Alle drei Audit-Greps
    aus dem 2026-05-09 Initial-Audit muessen ihren Soll-Wert haben."""
    setup_src = _read(WORKSPACE_SETUP)
    pm_src = _read(PROJECT_MANAGEMENT)

    # Grep 1: SchnittController-Instanziierung in Production
    assert setup_src.count("SchnittController(") >= 1

    # Grep 2: Triple-Hook >= 3
    triple_hook = (
        setup_src.count("self._push_active_project_to_schnitt()")
        + pm_src.count("_push_active_project_to_schnitt()")
    )
    assert triple_hook >= 3

    # Grep 3: keine btn_regenerate Doppel-Verdrahtung
    assert "btn_regenerate.clicked.connect" not in setup_src
