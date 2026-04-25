"""B-145 regression test: BeatAnalysis must unload model before retry-sleep.

Cycle-4 tester: ``analyze_and_store`` retry-loop sleeps 2/4/6s on
"database is locked". Until B-145 the model stayed in VRAM during
those sleeps because ``self.unload()`` was only in the outer
``finally``. On a 6GB GTX 1060 that 12s VRAM-block OOM-cascades any
concurrent SigLIP/RAFT load.

Fix: call ``self.unload()`` BEFORE entering the retry-loop. y/sr/
result are already extracted; the model is not needed for DB writes.
"""

from __future__ import annotations

import inspect

from services.beat_analysis_service import BeatAnalysisService


def test_unload_called_before_retry_loop() -> None:
    """In ``analyze_and_store``, ``self.unload()`` must appear BEFORE
    the ``for attempt in range(max_retries):`` line."""
    src = inspect.getsource(BeatAnalysisService.analyze_and_store)
    retry_idx = src.find("for attempt in range(max_retries)")
    assert retry_idx > 0, "retry-loop marker not found"

    # Look for self.unload() between top of method and retry-loop.
    pre_retry = src[:retry_idx]
    assert "self.unload()" in pre_retry, (
        "BUG-145 regression: ``self.unload()`` is not called before "
        "the DB-retry loop. Model stays in VRAM 12s during retry-sleep "
        "and OOM-cascades concurrent GPU workers."
    )
