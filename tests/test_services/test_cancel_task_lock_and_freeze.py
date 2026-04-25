"""B-119 + B-120 regression tests:

- cancel_task must read task.worker / task.thread under _tasks_lock
  (not after releasing). Currently the read happens after the lock
  is dropped — Lock-contract bruch.
- cancel_task must not block the UI thread on thread.wait(2000).
  Currently it blocks up to 2s.
"""

from __future__ import annotations

import inspect
import time
from unittest.mock import MagicMock

from services.task_manager import GlobalTaskManager


def test_cancel_task_reads_task_fields_under_lock() -> None:
    """Source-inspection: the worker/thread reads must happen INSIDE
    the with-block of _tasks_lock, not after."""
    src = inspect.getsource(GlobalTaskManager.cancel_task)

    # Heuristic: find ``with self._tasks_lock:`` and assert that
    # ``worker = task.worker`` and ``thread = task.thread`` happen
    # within the same with-block, not afterwards.
    lines = src.splitlines()
    in_lock_block = False
    found_worker_read_in_lock = False
    found_thread_read_in_lock = False
    lock_indent = None

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if "with self._tasks_lock:" in line:
            in_lock_block = True
            lock_indent = indent
            continue
        if in_lock_block:
            if stripped and indent <= (lock_indent or 0):
                in_lock_block = False
                continue
            if "worker = task.worker" in stripped or "task.worker" in stripped:
                found_worker_read_in_lock = True
            if "thread = task.thread" in stripped or "task.thread" in stripped:
                found_thread_read_in_lock = True

    assert found_worker_read_in_lock, (
        "BUG-119: cancel_task must read task.worker INSIDE the "
        "_tasks_lock with-block. Lock-contract violation."
    )
    assert found_thread_read_in_lock, (
        "BUG-119: cancel_task must read task.thread INSIDE the "
        "_tasks_lock with-block."
    )


def test_cancel_task_does_not_block_main_thread() -> None:
    """Compile the function source and assert it never calls thread.wait()
    at runtime. AST analysis is robust against comments / docstrings."""
    import ast
    src = inspect.getsource(GlobalTaskManager.cancel_task)
    tree = ast.parse(src.lstrip())  # function-source needs leading dedent

    class _WaitFinder(ast.NodeVisitor):
        def __init__(self):
            self.found = False
        def visit_Call(self, node):  # type: ignore[no-untyped-def]
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "wait":
                # Heuristic: any .wait(...) call inside cancel_task is
                # the blocking pattern we want gone.
                self.found = True
            self.generic_visit(node)

    finder = _WaitFinder()
    finder.visit(tree)
    assert not finder.found, (
        "BUG-120: cancel_task still calls .wait(...) somewhere. Use "
        "thread.quit() and let _safe_cleanup handle async cleanup."
    )
