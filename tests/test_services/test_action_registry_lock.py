"""B-132 regression test: ActionRegistry must be thread-safe.

Cycle-2 tester flagged: ``_actions`` dict mutated/read without lock.
Currently masked by startup-only register pattern, but structurally
brittle for runtime plugin loading or concurrent test re-registration.
"""

from __future__ import annotations

import inspect

from services.action_registry import ActionRegistry


def test_action_registry_has_lock_attribute() -> None:
    """An ActionRegistry instance must own a Lock-like attribute that
    serialises mutations on _actions."""
    reg = ActionRegistry()
    lock_attrs = [
        a for a in dir(reg)
        if not a.startswith("__") and "lock" in a.lower()
    ]
    assert lock_attrs, (
        "BUG-132 regression: ActionRegistry has no Lock-like attribute. "
        "Mutations on _actions are unprotected."
    )
    has_acquire = any(
        hasattr(getattr(reg, a), "acquire") and hasattr(getattr(reg, a), "release")
        for a in lock_attrs
    )
    assert has_acquire, (
        f"BUG-132: lock-named attribute is not a real lock: {lock_attrs}"
    )


def test_action_registry_methods_use_lock() -> None:
    """Public methods that mutate or read _actions must reference
    self._lock (or whatever the lock attr is named)."""
    src = inspect.getsource(ActionRegistry)
    # Loose: at least one ``with self._lock`` block must exist on the
    # mutate path.
    assert "with self._lock" in src or "with self._actions_lock" in src, (
        "BUG-132: ActionRegistry methods do not appear to acquire any "
        "lock around _actions access. Add ``with self._lock:`` around "
        "register / unregister / list / execute lookup."
    )
