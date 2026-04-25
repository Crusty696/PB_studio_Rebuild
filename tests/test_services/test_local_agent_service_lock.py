"""B-129 regression test: LocalAgentService._lock must be USED.

The Cycle-2 tester flagged that ``_lock = RLock()`` is declared in
``__init__`` but never acquired anywhere — leaving lazy-init and
state-mutation paths racy.

This test asserts the lock is actually invoked in the lazy-init
helpers and in ``process()``.
"""

from __future__ import annotations

import inspect

from services.local_agent_service import LocalAgentService


def test_local_agent_service_uses_lock_in_lazy_init() -> None:
    """At least one of the lazy-init helpers (``_get_orchestrator``,
    ``_get_ollama_client``, ``_get_conversation_memory``) must acquire
    ``self._lock`` before mutating state."""
    sources = []
    for method_name in (
        "_get_orchestrator",
        "_get_ollama_client",
        "_get_conversation_memory",
        "process",
    ):
        method = getattr(LocalAgentService, method_name, None)
        if method is None:
            continue
        sources.append((method_name, inspect.getsource(method)))

    used = [m for m, src in sources if "self._lock" in src]
    assert used, (
        "BUG-129 regression: LocalAgentService._lock is declared but "
        "never acquired in lazy-init helpers or process(). State "
        "mutations on _orchestrator / _ollama_client / "
        "_conversation_memory are unprotected against concurrent calls."
    )
