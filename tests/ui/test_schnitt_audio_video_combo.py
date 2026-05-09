"""Tier-3-Sunset T3.2/T3.3: audio_combo + video_combo + btn_generate + btn_auto_edit
liegen auf dem SchnittEditorView (Header), nicht mehr auf der hidden EditWorkspace.
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_schnitt_editor_view_exposes_audio_video_combo(qapp):
    from ui.workspaces.schnitt.editor_view import SchnittEditorView

    view = SchnittEditorView()
    try:
        assert hasattr(view, "audio_combo"), "SchnittEditorView.audio_combo fehlt"
        assert hasattr(view, "video_combo"), "SchnittEditorView.video_combo fehlt"
        assert isinstance(view.audio_combo, QComboBox)
        assert isinstance(view.video_combo, QComboBox)
    finally:
        view.deleteLater()


def test_schnitt_editor_view_exposes_generate_and_auto_edit(qapp):
    from ui.workspaces.schnitt.editor_view import SchnittEditorView

    view = SchnittEditorView()
    try:
        assert hasattr(view, "btn_generate"), "SchnittEditorView.btn_generate fehlt"
        assert hasattr(view, "btn_auto_edit"), "SchnittEditorView.btn_auto_edit fehlt"
        assert isinstance(view.btn_generate, QPushButton)
        assert isinstance(view.btn_auto_edit, QPushButton)
        assert view.btn_generate.text() == "Timeline generieren"
        assert view.btn_auto_edit.text() == "Auto-Edit"
    finally:
        view.deleteLater()
