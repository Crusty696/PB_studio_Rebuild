"""Shared palette helpers for Studio Brain widgets.

Extracted from ``structure_tab.py`` so sibling widgets (``graph_view.py``,
``_ClipCard``, etc.) can share the deterministic bucket→color mapping
without a circular import (T10.2e, fold-in A).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QColor


_PALETTE: tuple[str, ...] = (
    "#3b4252", "#4c566a", "#5e81ac", "#81a1c1",
    "#88c0d0", "#8fbcbb", "#a3be8c", "#b48ead",
    "#d08770", "#bf616a", "#ebcb8b",
)


def bucket_color(bucket_id: Optional[int]) -> QColor:
    """Deterministic pastel colour per bucket (used for placeholder thumbs
    and graph-view node fills).

    ``None`` maps to a neutral dark shade; otherwise the palette index is
    ``bucket_id % len(_PALETTE)`` so adjacent bucket ids get visibly
    different colours.
    """
    if bucket_id is None:
        return QColor("#2e3440")
    return QColor(_PALETTE[int(bucket_id) % len(_PALETTE)])


__all__ = ["bucket_color"]
