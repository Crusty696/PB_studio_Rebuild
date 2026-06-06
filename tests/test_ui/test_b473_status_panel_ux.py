"""B-473: Analyse-Status-Panel darf nicht "tot" wirken.

Click-log evidence (2026-06-04): user never selected a media card, so the panel
stayed on a small grey "Keine Datei ausgewählt" forever; "Aktualisieren" without
a selection silently cleared. Fixes: clear actionable hint, visible feedback on
refresh-without-selection, and auto-select of the first pool item after refresh.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover
    pytest.skip("Qt not available", allow_module_level=True)

_app = QApplication.instance() or QApplication([])

from ui.widgets.analysis_status_panel import AnalysisStatusPanel  # noqa: E402


def test_initial_placeholder_is_actionable_hint():
    panel = AnalysisStatusPanel()
    text = panel.file_info_label.text()
    assert "anklicken" in text, (
        "B-473: initial placeholder must tell the user HOW to fill the panel"
    )


def test_refresh_without_selection_shows_hint_not_silence():
    panel = AnalysisStatusPanel()
    panel.file_info_label.setText("etwas anderes")
    panel.refresh()  # no media set -> must show hint, not silently clear
    assert "anklicken" in panel.file_info_label.text()


def test_pool_refresh_autoselects_first_media():
    """Source guard: media_table refresh must feed the status panels."""
    src = Path("ui/controllers/media_table.py").read_text(encoding="utf-8")
    body = src.split("def _apply_refreshed_data", 1)[1].split("\n    def ", 1)[0]
    assert "ensure_status_panel_selection" in body, (
        "B-473: _apply_refreshed_data must auto-select the first media for the "
        "status panels"
    )
    ws = Path("ui/workspaces/media_workspace.py").read_text(encoding="utf-8")
    assert "def ensure_status_panel_selection" in ws
