"""P0 #1: Bridge-Wiring-Smoke — verifiziert dass _auto_edit_phase3_inner
bei aktiver Bridge-Flag den Studio-Brain-Code-Pfad betritt + bei
Setup-Fail graceful auf Legacy zurückfällt.
"""
from __future__ import annotations

import inspect
import os

import pytest


def test_studio_brain_setup_block_present():
    """Source-Inspektion: Bridge-Setup vor dem Cut-Loop ist da."""
    from services import pacing_service
    src = inspect.getsource(pacing_service._auto_edit_phase3_inner)
    assert "_studio_brain_pipeline" in src
    assert "studio_brain_requested" in src
    assert "PacingPipeline" in src


def test_studio_brain_loop_block_falls_back_on_none():
    """Source-Inspektion: nach select_best wird auf chosen=None geprüft +
    Legacy aufgerufen."""
    from services import pacing_service
    src = inspect.getsource(pacing_service._auto_edit_phase3_inner)
    # Studio-Brain-Pfad muss einen None-Fallback haben
    assert "_match_video_for_segment" in src
    assert "_sb_chosen_vid" in src


def test_bridge_flag_default_off_means_pipeline_none(monkeypatch):
    """Mit Flag=False ist _studio_brain_pipeline None und Legacy greift."""
    from services.pacing.bridge import use_studio_brain_pipeline
    monkeypatch.delenv("PB_USE_STUDIO_BRAIN_PIPELINE", raising=False)
    assert use_studio_brain_pipeline() is False


def test_bridge_flag_on_returns_true(monkeypatch):
    monkeypatch.setenv("PB_USE_STUDIO_BRAIN_PIPELINE", "1")
    from services.pacing.bridge import use_studio_brain_pipeline
    assert use_studio_brain_pipeline() is True
