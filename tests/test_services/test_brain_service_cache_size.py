"""B-114 / BUG-9-b regression test:

Several BrainService caches were ``lru_cache(maxsize=32)``. A power
user hitting >32 distinct Structure-tab filter combinations within a
session starts evicting cache entries and re-hitting the DB on every
subsequent refresh — defeating the cache. Bump to 128.
"""

from __future__ import annotations

import inspect

from services.brain import BrainService


def test_kwarg_caches_are_at_least_size_128() -> None:
    """The kwarg-keyed caches (clips_with_tags, learned_patterns,
    decisions_for_pattern) must be sized for power-user filter
    exploration."""
    src = inspect.getsource(BrainService.__init__)

    # Look for `_list_clips_with_tags_cached`, `_list_learned_patterns_cached`,
    # and `list_decisions_for_pattern` lru_cache lines.
    targets = [
        "_list_clips_with_tags_cached",
        "_list_learned_patterns_cached",
        "list_decisions_for_pattern",
    ]
    for name in targets:
        idx = src.find(name)
        assert idx != -1, f"BrainService no longer defines {name}"
        # Look at the 200 chars around it for a maxsize value.
        window = src[max(0, idx - 200):idx + 200]
        assert "maxsize=32" not in window, (
            f"BUG-9-b regression: {name} still capped at maxsize=32. "
            f"Power-user filter exploration evicts cache entries. Bump "
            f"to 128 (or use functools.cache for unbounded)."
        )
