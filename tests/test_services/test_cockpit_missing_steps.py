"""B-292/Phase-D: CockpitReadiness liefert missing_steps_per_card,
ProjectDashboard rendert Tooltip mit fehlenden Step-Namen."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from services import cockpit_orchestrator


def test_cockpit_readiness_has_missing_steps_field(test_engine, project, video_clip):
    readiness = cockpit_orchestrator.get_cockpit_readiness(project.id)
    msf = getattr(readiness, "missing_steps_per_card", None)
    assert msf is not None, (
        "B-292/D: CockpitReadiness.missing_steps_per_card fehlt — "
        "Tooltip kann nicht gefuellt werden."
    )
    assert "video" in msf
    assert isinstance(msf["video"], list)
    assert "scene_detection" in msf["video"], (
        "video-Card muss scene_detection als fehlend listen."
    )


def test_dashboard_tooltip_lists_missing_steps(qapp, test_engine, project, video_clip):
    from ui.workspaces.workflow_pages import ProjectDashboard
    dashboard = ProjectDashboard()
    dashboard.refresh(project.id)
    tip = dashboard.video_card.toolTip()
    assert "scene_detection" in tip or "Szenen" in tip, (
        f"Dashboard video_card.toolTip enthaelt fehlende Steps nicht: {tip!r}"
    )
