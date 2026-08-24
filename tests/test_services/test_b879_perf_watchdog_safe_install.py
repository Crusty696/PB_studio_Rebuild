"""B-879: Produktionsstart darf QApplication.notify nicht monkey-patchen."""

from __future__ import annotations


def test_install_watchdog_leaves_qapplication_notify_native(qapp) -> None:
    from services.perf_watchdog import install_watchdog

    if "notify" in qapp.__dict__:
        del qapp.notify

    hook = install_watchdog(qapp, threshold_ms=50)

    assert hook is None
    assert "notify" not in qapp.__dict__, (
        "B-879: Python-Override von QApplication.notify wird parallel aus "
        "Qt-Workerthreads aufgerufen und verursachte native Aborts."
    )
