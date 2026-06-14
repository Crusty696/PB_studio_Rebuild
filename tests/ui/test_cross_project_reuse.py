from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_status_panel_shows_cross_project_reuse_tooltip() -> None:
    _qapp()
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    panel = AnalysisStatusPanel()
    panel._media_type = "audio"
    panel._media_id = 7

    tooltip = "Erzeugt am 2026-06-14 13:00 in Projekt Projekt A, Modell Demucs"
    panel._apply_status_data(
        {
            "stem_separation": SimpleNamespace(
                status="done",
                value_summary={
                    "reuse_source_project": "Projekt A",
                    "provenance_tooltip": tooltip,
                },
                error_message=None,
            )
        }
    )

    stem_row = None
    for row in range(panel.table.rowCount()):
        item = panel.table.item(row, 1)
        if item and item.data(0x0100) == "stem_separation":
            stem_row = row
            break

    assert stem_row is not None
    assert panel.table.item(stem_row, 1).toolTip() == tooltip
    assert panel.table.item(stem_row, 2).toolTip() == tooltip
    assert panel.table.cellWidget(stem_row, 3).toolTip() == tooltip


def test_import_reuse_notice_has_project_scoped_mute_setting() -> None:
    controller = Path("ui/controllers/import_media.py").read_text(encoding="utf-8")
    widget = Path("ui/widgets/cross_project_reuse_toast.py").read_text(encoding="utf-8")
    assert "reuse_notifications/muted_project_" in controller
    assert "Nicht mehr fragen" in widget


def test_import_reuse_notice_stores_project_scoped_mute(monkeypatch) -> None:
    _qapp()
    from PySide6.QtCore import QSettings, Qt
    from ui.widgets.cross_project_reuse_toast import show_cross_project_reuse_toast

    settings_path = Path.cwd() / "test_reports" / "qt-settings-otk021"
    settings_path.mkdir(parents=True, exist_ok=True)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(settings_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)

    mute_key = "reuse_notifications/muted_project_123"
    QSettings("PB Studio", "Rebuild").setValue(mute_key, False)

    notice = show_cross_project_reuse_toast(None, "reuse message", mute_key)
    assert notice is not None
    checkbox = notice.checkBox()
    assert checkbox is not None
    assert notice.windowModality() == Qt.WindowModality.NonModal
    notice._pb_reuse_checkbox.setChecked(True)
    assert QSettings("PB Studio", "Rebuild").value(mute_key, False, type=bool) is True
    notice.close()
