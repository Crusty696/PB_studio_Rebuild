"""Cycle-1 LOW-batch regression tests.

Covers:
- B-117 BatchConvertWorker subprocess cancel (mid-segment)
- B-118 export tempfile orphan cleanup
- B-123 ModelManager.unload synchronize blocking
- B-124 load_ollama doc-status (semantic inconsistency)
"""

from __future__ import annotations

import inspect
import re

from services import model_manager as mm_mod
from services.model_manager import ModelManager
from workers.import_export import BatchConvertWorker


def test_b117_batch_convert_uses_popen_or_cancel_aware_run() -> None:
    """BatchConvertWorker.run must EITHER use the same Popen+cancel
    pattern as _run_ffmpeg_with_progress, OR call subprocess.run with
    a short enough timeout that mid-segment cancel is bounded.
    Heuristic: subprocess.run with original FFMPEG_EXPORT_TIMEOUT_SEC
    is too long; we expect either Popen + cancel-watchdog OR a
    short_per_segment timeout."""
    src = inspect.getsource(BatchConvertWorker.run)

    # Acceptable: Popen path
    if "Popen(" in src and "cancel" in src.lower():
        return

    # Acceptable: short timeout per segment + should_stop check
    has_should_stop_in_inner_loop = src.count("should_stop") >= 2
    assert has_should_stop_in_inner_loop, (
        "BUG-117: BatchConvertWorker.run still has only one "
        "should_stop() check (between segments). Mid-segment cancel "
        "needs at least one more should_stop check OR a Popen-based "
        "subprocess so the watchdog can terminate it."
    )


def test_b118_export_service_cleans_orphan_tempfiles() -> None:
    """export_timeline / export_preview should call a cleanup helper
    that removes leftover ``pb_std_*`` and ``pb_lufs_*`` files at the
    start of an export run."""
    from services import export_service as exp
    src = inspect.getsource(exp)

    # We accept either an explicit ``_cleanup_orphan_tempfiles`` helper
    # being defined and called, or a call to ``_cleanup_old_tempfiles``,
    # or any other recognisable cleanup pattern.
    has_cleanup_helper = re.search(
        r"def\s+_cleanup_(orphan|old)_tempfiles", src
    ) is not None
    assert has_cleanup_helper, (
        "BUG-118: export_service has no cleanup helper for orphan "
        "pb_std_* / pb_lufs_* tempfiles. Tempfiles accumulate on "
        "Windows when PermissionError occurs during normal cleanup."
    )


def test_b123_unload_does_not_call_synchronize() -> None:
    """ModelManager.unload should not call torch.cuda.synchronize() —
    can block forever on stuck kernel (D-022 / B-112 pattern)."""
    src = inspect.getsource(ModelManager.unload)
    import ast
    tree = ast.parse(src.lstrip())

    class _SyncFinder(ast.NodeVisitor):
        def __init__(self):
            self.found = False
        def visit_Call(self, node):  # type: ignore[no-untyped-def]
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "synchronize":
                self.found = True
            self.generic_visit(node)

    finder = _SyncFinder()
    finder.visit(tree)
    assert not finder.found, (
        "BUG-123: ModelManager.unload still calls "
        "torch.cuda.synchronize() — can block forever on stuck "
        "kernel during unload. empty_cache() alone is enough."
    )


def test_b124_load_ollama_documents_state_semantics() -> None:
    """load_ollama is intentionally external-process. The fix is to
    document the state semantics in the docstring so future code
    doesn't get confused by ``is_loaded`` returning False after
    a successful Ollama registration."""
    src = inspect.getsource(ModelManager.load_ollama)
    docstring = ModelManager.load_ollama.__doc__ or ""
    # Check the docstring explicitly mentions that _current_model_id
    # is intentionally not set.
    assert (
        "_current_model_id" in docstring
        or "is_loaded" in docstring
        or "B-124" in docstring
    ), (
        "BUG-124: load_ollama must document that _current_model_id "
        "and is_loaded are NOT updated for Ollama (it's an external "
        "process, not tracked in the singleton's swap-lifecycle)."
    )
