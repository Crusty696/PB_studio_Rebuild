"""B-884: shutdown must not leave PB Studio or frame FFmpeg alive."""

from __future__ import annotations

import inspect

import main as app_main


def test_lingering_hard_exit_happens_before_qt_base_close() -> None:
    """Qt/COM teardown must not strand an in-process delayed watchdog."""
    source = inspect.getsource(app_main.PBWindow.closeEvent)

    hard_exit_branch = source.index("if lingering_shutdown_threads:")
    qt_base_close = source.index("super().closeEvent(event)")

    assert hard_exit_branch < qt_base_close


def test_hard_exit_kills_child_processes_before_parent() -> None:
    """A forced parent exit must not orphan frame/export FFmpeg children."""
    source = inspect.getsource(app_main.PBWindow.closeEvent)
    hard_exit_scope = source[source.index("if lingering_shutdown_threads:"):]

    child_tree_cleanup = hard_exit_scope.index("children(recursive=True)")
    parent_exit = hard_exit_scope.index("_os._exit(0)")

    assert child_tree_cleanup < parent_exit
