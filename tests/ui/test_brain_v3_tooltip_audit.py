import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_feedback_popup_buttons_have_tooltips():
    """Brain-Tooltip-Task (Master-Plan Bucket 4): alle Rating-Buttons +
    Abbrechen des BrainV3FeedbackPopup brauchen Tooltips."""
    _qapp()
    from ui.widgets.brain_v3_feedback_popup import BrainV3FeedbackPopup

    popup = BrainV3FeedbackPopup(cut_id=1, service=None)
    try:
        assert popup._rating_buttons, "keine Rating-Buttons gebaut"
        for btn in popup._rating_buttons:
            assert btn.toolTip().strip(), f"Rating-Button ohne Tooltip: {btn.text()}"
        from PySide6.QtWidgets import QPushButton
        cancel_buttons = [
            b for b in popup.findChildren(QPushButton)
            if b not in popup._rating_buttons
        ]
        assert cancel_buttons, "Abbrechen-Button nicht gefunden"
        for btn in cancel_buttons:
            assert btn.toolTip().strip(), f"Button ohne Tooltip: {btn.text()}"
    finally:
        popup.close()
        popup.deleteLater()
        QApplication.processEvents()


def test_learning_dialog_controls_have_tooltips():
    """Alle interaktiven Controls des BrainV3LearningSessionDialog brauchen
    Tooltips. _load wird gestubbt — es startet sonst einen echten
    Worker-Thread im Konstruktor (Lesson B-651: keine echten Threads in
    Unit-Tests ueber Produkt-Callbacks)."""
    _qapp()
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog

    class _StubService:
        pass

    with patch.object(BrainV3LearningSessionDialog, "_load", lambda self: None):
        dlg = BrainV3LearningSessionDialog(service=_StubService())
    try:
        for name in (
            "_lbl_status",
            "_list",
            "_lbl_preview",
            "_video_preview",
            "_btn_preview_play",
            "_btn_preview_stop",
            "_btn_open",
            "_btn_close",
        ):
            widget = getattr(dlg, name)
            assert widget.toolTip().strip(), f"{name} ohne Tooltip"
    finally:
        dlg.close()
        dlg.deleteLater()
        QApplication.processEvents()
