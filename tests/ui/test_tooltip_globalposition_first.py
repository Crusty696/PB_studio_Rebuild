"""B-109 / BUG-12-b regression test:

``ui/tooltip_utils.py`` probed deprecated ``QHelpEvent.globalPos()``
first. On Qt 6 ``hasattr(event, 'globalPos')`` is True (kept for
back-compat) but emits deprecation warnings. The PySide6-native form
``globalPosition().toPoint()`` should be tried first.
"""

from __future__ import annotations

import inspect

from ui import tooltip_utils


def test_tooltip_filter_prefers_globalposition_over_globalpos() -> None:
    src = inspect.getsource(tooltip_utils._StickyTooltipFilter.eventFilter)
    # Find the order: globalPosition() should appear in the code before
    # the globalPos() fallback (or globalPos() should be removed entirely).
    pos_index = src.find("globalPosition")
    legacy_index = src.find("globalPos()")
    if pos_index == -1:
        # If neither path exists, assertion will fail loudly.
        assert False, (
            "BUG-12-b regression: tooltip_utils.eventFilter does not "
            "use globalPosition() at all. Use it as the primary path."
        )
    if legacy_index == -1:
        return  # globalPos was removed entirely — also acceptable.
    assert pos_index < legacy_index, (
        "BUG-12-b: tooltip_utils.eventFilter probes deprecated "
        "globalPos() BEFORE the modern globalPosition().toPoint() "
        "path. Invert the order so deprecation warnings only fire on "
        "the (impossible) Qt-5 fallback path."
    )
