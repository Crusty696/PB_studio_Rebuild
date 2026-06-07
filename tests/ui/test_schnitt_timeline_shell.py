import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton


def _qapp():
    return QApplication.instance() or QApplication([])


def test_timeline_shell_exposes_labeled_controls():
    _qapp()
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    shell = TimelineShell()

    for name in (
        "btn_zoom_out",
        "btn_zoom_fit",
        "btn_zoom_reset",
        "btn_zoom_in",
        "zoom_label",
        "legend_label",
        "status_label",
    ):
        assert hasattr(shell, name), name

    for button in shell.findChildren(QPushButton):
        assert button.toolTip().strip(), button.objectName()
        assert button.accessibleName().strip(), button.objectName()


def test_timeline_shell_zoom_buttons_call_timeline_methods():
    _qapp()
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    shell = TimelineShell()
    calls = []
    shell.timeline.zoom_by_factor = lambda factor: calls.append(("zoom", factor))
    shell.timeline.fit_to_content = lambda: calls.append(("fit", None))
    shell.timeline.reset_zoom = lambda: calls.append(("reset", None))

    shell.btn_zoom_in.click()
    shell.btn_zoom_out.click()
    shell.btn_zoom_fit.click()
    shell.btn_zoom_reset.click()

    assert calls == [
        ("zoom", 1.15),
        ("zoom", 1 / 1.15),
        ("fit", None),
        ("reset", None),
    ]
