"""B-106 / BUG-4-b regression / dismissal test:

bug-hunter trial 2026-04-25 (BUG-4-b, MEDIUM) flagged the
``VideoAnalysisPipelineWorker`` cleanup duplication: cleanup inside the
``with GPU_EXECUTION_LOCK:`` tail AND inside the outer ``finally``.
Claim: "any exception between the two cleanup blocks creates a window
for double-free."

This test asserts the structural invariant that prevents the claimed
bug: the inner cleanup unconditionally resets ``raft_model_device``
and ``siglip_model_processor`` to ``None`` (the assignment is OUTSIDE
the try/except, at the same indent level), so the outer ``finally``'s
``if X is not None`` guard always short-circuits to a no-op when the
inner block ran.

If a future refactor moves the ``= None`` assignment INSIDE the
try/except, this test will fail and B-106 must be re-opened.
"""

from __future__ import annotations

import inspect

from workers.video import VideoAnalysisPipelineWorker


def test_inner_cleanup_resets_locals_to_none_unconditionally() -> None:
    """The inner BATCH-CLEANUP block must contain
    ``raft_model_device = None`` and ``siglip_model_processor = None``
    OUTSIDE any try/except, so the outer ``finally`` is structurally
    guaranteed to be a no-op when the inner block ran.
    """
    source = inspect.getsource(VideoAnalysisPipelineWorker.run)
    # Anchor: the inner BATCH-CLEANUP comment marker.
    anchor = "BATCH-CLEANUP"
    assert anchor in source, (
        f"BUG-4-b regression: inner BATCH-CLEANUP block disappeared. "
        f"The cleanup invariant relies on it."
    )
    inner_block = source[source.index(anchor):]

    # Find the outer finally so we only inspect the inner block.
    outer_finally = inner_block.find("\n        finally:")
    if outer_finally != -1:
        inner_block = inner_block[:outer_finally]

    # Both reset assignments must be present in the inner block.
    assert "raft_model_device = None" in inner_block, (
        "BUG-4-b: inner cleanup must reset raft_model_device = None "
        "so outer finally is a no-op. Without this, double-free risk."
    )
    assert "siglip_model_processor = None" in inner_block, (
        "BUG-4-b: inner cleanup must reset siglip_model_processor = None "
        "so outer finally is a no-op. Without this, double-free risk."
    )

    # Verify the resets are NOT inside a try/except block (which would
    # be skipped on unhandled exceptions). They must be at the same
    # indent as the surrounding `if X is not None:` — that means at
    # 16 spaces of indent.
    for line in inner_block.splitlines():
        if line.lstrip().startswith("raft_model_device = None") or \
           line.lstrip().startswith("siglip_model_processor = None"):
            indent = len(line) - len(line.lstrip())
            # Must be at the if-block's body indent, not deeper (inside try).
            assert indent <= 20, (
                f"BUG-4-b regression: reset assignment '{line.strip()}' "
                f"is at indent {indent}, suggesting it lives inside a "
                f"try/except. Move it back to the if-block body level."
            )
