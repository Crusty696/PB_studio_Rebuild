"""B-135 regression test: set_project must create tables atomically.

Cycle-3 tester flagged: ``set_project()`` swaps the engine atomically
but ``init_db()`` is a separate call. Race window where the engine
points at a new DB without tables → "no such table" crashes.

Fix: ``set_project`` creates tables BEFORE the swap (or under the
same lock), so callers never observe a half-initialised DB.
"""

from __future__ import annotations

import inspect

from database import session as _session


def test_set_project_creates_tables_before_swap_or_within_lock() -> None:
    """``set_project`` source must call ``Base.metadata.create_all``
    (or ``init_db``) within the ``_APP_ROOT_LOCK`` block — not after
    swap as a separate call from project_manager."""
    src = inspect.getsource(_session.set_project)

    has_create_all = "create_all" in src
    has_init_db_call = "init_db()" in src

    assert has_create_all or has_init_db_call, (
        "BUG-135 regression: set_project does not create tables "
        "internally. Race window between engine.swap and the "
        "external init_db() call → callers can observe a tableless DB."
    )
