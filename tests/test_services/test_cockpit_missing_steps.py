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


def test_missing_required_steps_empty_status_returns_all_required():
    """Phase-D-fix: leeres status_by_media -> alle required Steps fehlen.
    Vorher: leeres dict -> [] (Tooltip log "Bereit." trotz audio_ready=False)."""
    from services.cockpit_orchestrator import (
        _missing_required_steps, AUDIO_STEP_SPECS, VIDEO_STEP_SPECS,
    )

    audio_missing = _missing_required_steps({}, AUDIO_STEP_SPECS)
    assert audio_missing  # nicht leer
    audio_required = sorted(s.key for s in AUDIO_STEP_SPECS if s.required_for_auto_edit)
    assert audio_missing == audio_required

    video_missing = _missing_required_steps({}, VIDEO_STEP_SPECS)
    assert video_missing
    video_required = sorted(s.key for s in VIDEO_STEP_SPECS if s.required_for_auto_edit)
    assert video_missing == video_required


def test_b458_cockpit_audio_specs_cover_all_audio_steps():
    """B-458: Cockpit darf Audio nicht nach Teilmenge als bereit melden."""
    from services.analysis_status_service import AUDIO_STEPS
    from services.cockpit_orchestrator import AUDIO_STEP_SPECS

    assert [spec.key for spec in AUDIO_STEP_SPECS] == AUDIO_STEPS
    assert all(spec.required_for_auto_edit for spec in AUDIO_STEP_SPECS)
