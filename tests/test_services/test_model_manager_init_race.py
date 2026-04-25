"""B-122 regression test:

``ModelManager.__init__`` sets ``_initialized=True`` early and then
performs ~12 operations (incl. lazy torch import) before assigning
``self._swap_lock = RLock()``. A second thread that calls
``ModelManager()`` in that window sees ``_initialized`` and early-
returns from ``__init__`` — without ``_swap_lock`` being set yet.
Subsequent ``unload()`` raises AttributeError.

The fix: state initialisation happens in ``__new__`` (under ``cls._lock``)
so the singleton instance is fully constructed before ``__init__`` runs.
"""

from __future__ import annotations

import inspect

from services import model_manager as mm_mod
from services.model_manager import ModelManager


def test_swap_lock_attribute_exists_immediately_after_new() -> None:
    """When __new__ returns, _swap_lock must already exist on the
    instance — not be deferred to __init__."""
    # Reset the singleton so we observe the cold-start path.
    mm_mod.ModelManager._instance = None

    # Bypass __init__ to inspect __new__'s output directly.
    inst = ModelManager.__new__(ModelManager)
    try:
        assert hasattr(inst, "_swap_lock"), (
            "BUG-122 regression: ModelManager.__new__ must set "
            "_swap_lock before returning. Otherwise a second-thread "
            "early-return from __init__ leaves the lock missing."
        )
    finally:
        # Restore: let regular __init__ run on next ModelManager() call.
        mm_mod.ModelManager._instance = None


def test_init_does_not_set_initialized_before_lock() -> None:
    """The fix moves state into __new__. __init__ should NOT set
    ``_initialized = True`` BEFORE ``_swap_lock``. Either both happen
    in __new__ atomically, or _swap_lock is set BEFORE the early-exit
    sentinel is set."""
    src = inspect.getsource(ModelManager.__init__)
    # If __init__ still mutates _initialized + _swap_lock, the order
    # must be: _swap_lock first, _initialized second. AST-walk:
    import ast
    tree = ast.parse(src.lstrip())

    init_idx = None
    swap_idx = None
    seen = []
    for i, node in enumerate(ast.walk(tree)):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute):
                    if tgt.attr == "_initialized":
                        seen.append(("init", node.lineno))
                    if tgt.attr == "_swap_lock":
                        seen.append(("swap", node.lineno))

    if not seen:
        # __init__ doesn't touch either — perfect (state moved to __new__).
        return

    # If both appear, _swap_lock must come first.
    inits = [n for n in seen if n[0] == "init"]
    swaps = [n for n in seen if n[0] == "swap"]
    if inits and swaps:
        assert min(s[1] for s in swaps) < min(i[1] for i in inits), (
            "BUG-122: in ModelManager.__init__, ``_swap_lock`` must be "
            "assigned BEFORE ``_initialized = True`` so a parallel "
            "second-call doesn't early-return into a no-lock state. "
            f"Order seen: {seen}."
        )
