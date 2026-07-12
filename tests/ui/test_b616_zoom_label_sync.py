"""B-616 regression tests: zoom label must track the REAL view scale.

Live-Sichtung 2026-07-11: label started at 'Zoom 100%' although the
project-load path calls ``InteractiveTimeline.fit_to_content()`` directly
(ui/timeline.py load_from_db), which scales the view to e.g. 0.25 without
going through ``TimelineShell._fit_to_content``. First '+' click then
jumped the label 100% -> 29% (0.25 * 1.15 = 0.2875).

Contract pinned here:
- InteractiveTimeline emits ``zoom_changed`` on every zoom path
  (zoom_by_factor / reset_zoom / fit_to_content / wheelEvent).
- TimelineShell keeps its label in sync via that signal, no matter who
  triggered the zoom.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_shell():
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    shell = TimelineShell()
    shell.resize(800, 400)
    return shell


def test_zoom_by_factor_emits_zoom_changed() -> None:
    _ensure_qapp()
    shell = _make_shell()

    received: list[float] = []
    shell.timeline.zoom_changed.connect(received.append)

    shell.timeline.zoom_by_factor(0.5)

    assert received, "B-616: zoom_by_factor must emit zoom_changed"
    assert abs(received[-1] - shell.timeline.transform().m11()) < 1e-6


def test_internal_fit_to_content_updates_label() -> None:
    """The bug path: timeline zooms itself (load_from_db -> fit_to_content)
    WITHOUT the shell button — label must still follow."""
    app = _ensure_qapp()
    shell = _make_shell()
    shell.show()
    app.processEvents()

    # Give the scene real content so fit_to_content computes a scale.
    shell.timeline._scene.setSceneRect(0, 0, 20000, 200)

    shell.timeline.fit_to_content()  # direct call, NOT shell._fit_to_content
    app.processEvents()

    real = int(round(shell.timeline.transform().m11() * 100))
    label = shell.zoom_label.text()
    assert label == f"Zoom {real}%", (
        f"B-616: label ({label!r}) out of sync with real scale {real}% "
        f"after an internal fit_to_content."
    )
    assert label != "Zoom 100%" or real == 100

    shell.close()


def test_reset_zoom_updates_label() -> None:
    app = _ensure_qapp()
    shell = _make_shell()
    shell.show()
    app.processEvents()

    shell.timeline.zoom_by_factor(0.5)
    shell.timeline.reset_zoom()
    app.processEvents()

    assert shell.zoom_label.text() == "Zoom 100%"
    shell.close()


def test_label_initialized_from_real_transform() -> None:
    """Shell built around an already-zoomed timeline must not claim 100%."""
    app = _ensure_qapp()
    from ui.timeline import InteractiveTimeline
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    timeline = InteractiveTimeline()
    timeline.scale(0.5, 1.0)

    shell = TimelineShell(timeline=timeline)
    app.processEvents()

    assert shell.zoom_label.text() == "Zoom 50%", (
        f"B-616: initial label must reflect the real transform, "
        f"got {shell.zoom_label.text()!r}"
    )
    shell.close()
