from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_about_documentation_button_click_opens_readme_or_warns(
    monkeypatch, tmp_path
) -> None:
    app = _qapp()
    from ui.dialogs import about

    readme = tmp_path / "README.md"
    readme.write_text("PB Studio", encoding="utf-8")
    opened: list[str] = []
    warnings: list[tuple] = []

    monkeypatch.setattr(about, "_gpu_info", lambda: "NVIDIA GeForce GTX 1060")
    monkeypatch.setattr(about, "_documentation_path", lambda: readme)
    monkeypatch.setattr(
        about.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    monkeypatch.setattr(
        about.QMessageBox,
        "warning",
        lambda *_args: warnings.append(_args),
    )

    dialog = about.AboutDialog()
    try:
        dialog.show()
        app.processEvents()
        docs_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Dokumentation"
        ]
        assert len(docs_buttons) == 1
        button = docs_buttons[0]
        assert button.isVisibleTo(dialog) is True
        assert button.isEnabled() is True

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert [Path(path) for path in opened] == [readme]
        assert warnings == []

        readme.unlink()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert [Path(path) for path in opened] == [readme]
        assert len(warnings) == 1
        assert warnings[0][1] == "Dokumentation fehlt"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
