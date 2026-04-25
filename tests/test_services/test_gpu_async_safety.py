"""B-112 / BUG-A7 + BUG-14-b regression tests:

GPU / async safety in two places:
- ``services/ai_audio_service.py`` called ``torch.cuda.empty_cache()``
  inside an ``except RuntimeError`` without checking
  ``torch.cuda.is_available()``. On a CPU-only torch build that raises
  AssertionError, masking the real RuntimeError.
- ``main.py::_cuda_atexit_cleanup`` calls ``torch.cuda.synchronize()``
  with no timeout. If a kernel is stuck (e.g. dead GPU after Code-47),
  synchronize blocks forever — the Python process never exits.
"""

from __future__ import annotations

import inspect


def test_ai_audio_service_demucs_load_oom_path_is_cpu_safe() -> None:
    """Bug-hunter BUG-A7: the OOM-handling path around ``demucs_model.to(device)``
    runs ``torch.cuda.empty_cache()`` inside ``except RuntimeError``. On a
    CPU-only torch build this raises AssertionError, masking the original
    RuntimeError. Guard the call with ``torch.cuda.is_available()``.
    """
    from services import ai_audio_service

    src = inspect.getsource(ai_audio_service)
    # Locate the `demucs_model.to(device)` block.
    anchor = "demucs_model.to(device)"
    assert anchor in src, "demucs_model.to(device) not found"
    block_start = src.index(anchor)
    block = src[block_start:block_start + 600]

    # The except branch around to() must guard empty_cache with
    # is_available, OR avoid the call entirely.
    if "torch.cuda.empty_cache()" in block:
        assert "is_available()" in block, (
            "BUG-A7: empty_cache() in the demucs to(device) except "
            "branch is unguarded. CPU-only torch builds will raise "
            "AssertionError. Wrap with `if torch.cuda.is_available():`."
        )


def test_main_cuda_atexit_does_not_call_synchronize() -> None:
    """``_cuda_atexit_cleanup`` must NOT call ``torch.cuda.synchronize()``
    — it can block forever on a stuck kernel and prevent process exit.
    ``empty_cache()`` is enough as a safety-net release."""
    import inspect as _inspect
    from pathlib import Path

    main_path = Path(__file__).resolve().parent.parent.parent / "main.py"
    src = main_path.read_text(encoding="utf-8")

    # Find the _cuda_atexit_cleanup definition.
    anchor = "def _cuda_atexit_cleanup"
    assert anchor in src, "main._cuda_atexit_cleanup not found"
    body_start = src.index(anchor)
    # Body extends until the next top-level def or end of definition
    # (we approximate with a generous window).
    body = src[body_start:body_start + 1200]

    # Match an actual call (e.g. ``torch.cuda.synchronize()``) — exclude
    # comments / docstrings that mention the word.
    import re
    has_call = bool(re.search(r"^\s+torch\.cuda\.synchronize\(\)", body, re.MULTILINE))
    assert not has_call, (
        "BUG-14-b regression: _cuda_atexit_cleanup calls "
        "torch.cuda.synchronize() — that can block forever on a "
        "stuck kernel during interpreter shutdown. Remove it; "
        "empty_cache() alone is the safety-net release."
    )
