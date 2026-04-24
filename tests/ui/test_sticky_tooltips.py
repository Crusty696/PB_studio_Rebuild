"""Tests for ui.tooltip_utils — sticky tooltip filter (idempotency)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import ui.tooltip_utils as tooltip_utils
from ui.tooltip_utils import install_sticky_tooltips


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_install_sticky_tooltips_is_idempotent() -> None:
    """Calling install_sticky_tooltips twice must not create two filter
    instances. The module-level ``_filter_instance`` must be the same object
    after both calls."""
    app = _ensure_qapp()
    # Reset any state from prior tests so this test works in isolation.
    tooltip_utils._filter_instance = None

    install_sticky_tooltips(app)
    first = tooltip_utils._filter_instance
    assert first is not None

    install_sticky_tooltips(app)
    second = tooltip_utils._filter_instance
    assert second is first
