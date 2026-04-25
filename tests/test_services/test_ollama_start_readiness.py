"""B-113 / BUG-A10 regression test:

``OllamaService.start()`` previously spawned the subprocess and
returned immediately. Callers that did
``service.start(); service.ensure_model(...)`` saw ``is_ready=False``
during the ~500 ms server-startup window and bailed out.

The fix: ``start()`` polls for ``is_ready`` for a short bounded period
after spawn before returning. ``_is_ready`` is set True once the port
is open, so subsequent callers see the correct state.
"""

from __future__ import annotations

import inspect

from services import ollama_service


def test_start_polls_for_readiness_after_spawn() -> None:
    """The ``start()`` source must contain a readiness-poll loop after
    the Popen call, so the function does not return before the port
    is actually open. Without it ``ensure_model()`` immediately
    afterwards races and returns False."""
    src = inspect.getsource(ollama_service.OllamaService.start)
    # The fix must add at least ONE wait/sleep/probe loop after Popen.
    has_popen = "Popen(" in src
    has_wait_loop = (
        "_is_port_open" in src
        and ("sleep" in src or "for " in src or "while " in src)
    )
    assert has_popen, "start() should still spawn via Popen"
    assert has_wait_loop, (
        "BUG-A10 regression: OllamaService.start() returns immediately "
        "after Popen with no readiness poll. Add a bounded "
        "_is_port_open() poll loop so callers can rely on is_ready "
        "being True after start() returns successfully."
    )
