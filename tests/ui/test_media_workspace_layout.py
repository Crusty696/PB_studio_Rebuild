"""B-296: MEDIA-Workspace ohne Doppel-Alias-Buttons (R-15)."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")

from ui.workspaces.media_workspace import MediaWorkspace


def test_b296_no_motion_analysis_button(qapp):
    ws = MediaWorkspace()
    try:
        assert not hasattr(ws, "btn_motion_analysis"), (
            "B-296/R-15: btn_motion_analysis ist Alias auf _start_video_pipeline — sollte weg sein."
        )
    finally:
        ws.deleteLater()


def test_b296_no_siglip_embeddings_button(qapp):
    ws = MediaWorkspace()
    try:
        assert not hasattr(ws, "btn_siglip_embeddings"), (
            "B-296/R-15: btn_siglip_embeddings ist Alias — sollte weg sein."
        )
    finally:
        ws.deleteLater()


def test_b296_video_pipeline_button_remains(qapp):
    ws = MediaWorkspace()
    try:
        assert hasattr(ws, "btn_video_pipeline"), (
            "B-296: Primary-Pipeline-Button bleibt."
        )
    finally:
        ws.deleteLater()


def test_b296_video_import_button_remains(qapp):
    ws = MediaWorkspace()
    try:
        assert hasattr(ws, "btn_import_video") or hasattr(ws, "btn_import_folder"), (
            "B-296: Import-Buttons muessen bleiben."
        )
    finally:
        ws.deleteLater()
