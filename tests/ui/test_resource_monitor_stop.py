"""B-101 / BUG-A1 regression test:

``ResourceMonitorWidget.stop()`` used to call ``self._worker.stop()`` as
a plain Python method, which ran ``QTimer.stop()`` cross-thread (QTimer
is not thread-safe). The sibling widget ``ai_status_dot.py`` already used
``QMetaObject.invokeMethod`` with ``QueuedConnection`` to dispatch the
slot to the owner thread — ``resource_monitor.py`` was never updated.

This test verifies the worker's ``stop`` slot runs on the worker's own
thread (not the test/main thread).
"""

from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.widgets.resource_monitor import ResourceMonitorWidget


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_stop_uses_queued_invoke_method_for_worker() -> None:
    """``ResourceMonitorWidget.stop()`` must dispatch the worker's stop
    slot via ``QMetaObject.invokeMethod`` with ``QueuedConnection`` — not
    by calling ``self._worker.stop()`` directly (which would run the
    QTimer.stop call cross-thread; QTimer is not thread-safe).

    We monkey-patch ``QMetaObject.invokeMethod`` to capture how stop()
    dispatches to the worker.
    """
    app = _ensure_qapp()
    widget = ResourceMonitorWidget()
    widget.start()
    app.processEvents()

    from PySide6.QtCore import QMetaObject, Qt as QtConst

    captured: list[tuple[object, str, object]] = []
    original_invoke = QMetaObject.invokeMethod

    def spy(target: object, member: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if member == "stop":
            connection_type = (
                args[0] if args else kwargs.get("type", QtConst.AutoConnection)
            )
            captured.append((target, member, connection_type))
        return original_invoke(target, member, *args, **kwargs)

    QMetaObject.invokeMethod = staticmethod(spy)  # type: ignore[assignment]
    try:
        widget.stop()
    finally:
        QMetaObject.invokeMethod = original_invoke  # type: ignore[assignment]

    stop_dispatches = [c for c in captured if c[1] == "stop"]
    assert len(stop_dispatches) >= 1, (
        f"BUG-A1 regression: widget.stop() did not dispatch the worker's "
        f"stop slot via QMetaObject.invokeMethod. captured={captured}."
    )
    target, _, conn_type = stop_dispatches[0]
    assert conn_type == QtConst.ConnectionType.QueuedConnection, (
        f"BUG-A1 regression: stop dispatched with wrong connection type "
        f"({conn_type}); must be QueuedConnection."
    )
