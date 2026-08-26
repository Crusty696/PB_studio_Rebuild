from __future__ import annotations

import os
import warnings
from types import MethodType

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from main import PBWindow


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _banner_host() -> QWidget:
    host = QWidget()
    host._build_update_banner = MethodType(PBWindow._build_update_banner, host)
    host._on_update_available = MethodType(PBWindow._on_update_available, host)
    host._update_banner = host._build_update_banner()
    return host


def test_download_control_opens_latest_release_url(monkeypatch) -> None:
    app = _qapp()
    host = _banner_host()
    opened_urls: list[str] = []
    monkeypatch.setattr("webbrowser.open", opened_urls.append)

    assert host._update_banner.isHidden()
    assert host._update_banner_link.isHidden()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        host._on_update_available("0.5.1", "https://example.invalid/old")
        host._on_update_available("0.5.2", "https://example.invalid/latest")
    app.processEvents()

    assert host._update_banner_label.text() == "Update verfügbar: PB Studio v0.5.2"
    assert not host._update_banner.isHidden()
    assert not host._update_banner_link.isHidden()
    QTest.mouseClick(host._update_banner_link, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert opened_urls == ["https://example.invalid/latest"]
    assert not [
        warning
        for warning in caught
        if "Failed to disconnect" in str(warning.message)
    ]
