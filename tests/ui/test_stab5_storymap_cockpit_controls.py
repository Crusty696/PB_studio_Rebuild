"""STAB-5 Controls #79-#81 + #125: StoryMap-Header + GraphCockpit-Refresh."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _single_button(root: QWidget, text: str) -> QPushButton:
    buttons = [b for b in root.findChildren(QPushButton) if b.text() == text]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(root) is True
    assert button.isEnabled() is True
    return button


def _header():
    from ui.story_map_dialog import _HeaderBar

    header = _HeaderBar(
        run_id=9, audio_basename="track.wav", total_duration_sec=337.1
    )
    header.show()
    QApplication.processEvents()
    return header


def test_79_export_png_button_emits_signal() -> None:
    """Control #79: 'Als PNG exportieren' emittiert exportPngClicked."""
    app = _qapp()
    header = _header()
    try:
        emitted: list[str] = []
        header.exportPngClicked.connect(lambda: emitted.append("png"))
        header.exportSvgClicked.connect(lambda: emitted.append("svg"))
        button = _single_button(header, "Als PNG exportieren")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert emitted == ["png"]
    finally:
        header.deleteLater()
        app.processEvents()


def test_80_export_svg_button_emits_signal() -> None:
    """Control #80: 'Als SVG exportieren' emittiert exportSvgClicked."""
    app = _qapp()
    header = _header()
    try:
        emitted: list[str] = []
        header.exportPngClicked.connect(lambda: emitted.append("png"))
        header.exportSvgClicked.connect(lambda: emitted.append("svg"))
        button = _single_button(header, "Als SVG exportieren")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert emitted == ["svg"]
    finally:
        header.deleteLater()
        app.processEvents()


def test_81_close_button_emits_close_signal() -> None:
    """Control #81: 'Schließen' emittiert closeClicked (Dialog verbindet
    dieses Signal produktiv mit close)."""
    app = _qapp()
    header = _header()
    try:
        emitted: list[str] = []
        header.closeClicked.connect(lambda: emitted.append("close"))
        button = _single_button(header, "Schließen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert emitted == ["close"]
        assert "Run #9" in header.label_text()
    finally:
        header.deleteLater()
        app.processEvents()


def test_125_cockpit_refresh_button_triggers_refresh_html(monkeypatch) -> None:
    """Control #125: GraphCockpit 'Aktualisieren' -> _refresh_html.

    Bound-Connect im _build_ui -> Klassen-Patch vor Instanziierung.
    QtWebEngine/-Channel werden als nicht verfuegbar gepatcht (Fallback-
    Textpfad); ViewModel ist ein Fake ohne DB."""
    app = _qapp()
    import ui.widgets.graph_cockpit_tab as gct

    monkeypatch.setattr(gct, "_try_import_qwebengine", lambda: None)
    monkeypatch.setattr(gct, "_try_import_qwebchannel", lambda: None)

    calls: list[str] = []
    monkeypatch.setattr(
        gct.GraphCockpitTab, "_refresh_html", lambda self: calls.append("refresh")
    )

    class _FakeVM:
        pass

    tab = gct.GraphCockpitTab(view_model=_FakeVM())
    try:
        tab.show()
        app.processEvents()
        init_calls = len(calls)
        assert init_calls >= 1  # Konstruktor ruft _refresh_html einmal

        button = _single_button(tab, "Aktualisieren")
        assert button is tab.btn_refresh
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(calls) == init_calls + 1
    finally:
        tab.deleteLater()
        app.processEvents()
