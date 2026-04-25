"""Sticky tooltips: stay visible as long as the cursor is on the widget.

Qt-Default zeigt Tooltips fuer 10 s und blendet sie dann aus, auch wenn
der Cursor noch draufsteht. Fuer ein lehrreiches UI soll ein Tooltip
bleiben, solange der User lesen will — erst verschwinden, wenn er den
Cursor woanders hinbewegt.

Implementation:
- Global QApplication event filter fuer QEvent.Type.ToolTip.
- Zeigt den Tooltip via QToolTip.showText mit 24h-Timeout.
- Qt's interne QTipLabel blendet automatisch aus, sobald die Maus das
  Widget verlaesst (Leave-Event) — das uebernehmen wir nicht selbst.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtWidgets import QApplication, QToolTip, QWidget


# 24 h — praktisch unendlich. Qt intern hidet frueher wenn Leave-Event kommt.
_STICKY_DURATION_MS: int = 24 * 60 * 60 * 1000


class _StickyTooltipFilter(QObject):
    """Event filter that keeps tooltips visible as long as the cursor hovers."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.ToolTip:
            return False
        if not isinstance(obj, QWidget):
            return False
        tip = obj.toolTip()
        if not tip:
            return False
        # B-109 / BUG-12-b: try modern PySide6 globalPosition().toPoint()
        # first; fall back to legacy globalPos() only if not present
        # (Qt 5 path that PySide6 will never actually take).
        if hasattr(event, "globalPosition"):
            pos = event.globalPosition().toPoint()  # type: ignore[attr-defined]
        else:
            pos = event.globalPos()  # type: ignore[attr-defined]
        QToolTip.showText(pos, tip, obj, QRect(), _STICKY_DURATION_MS)
        return True


_filter_instance: _StickyTooltipFilter | None = None


def install_sticky_tooltips(app: QApplication) -> None:
    """Install the sticky tooltip filter on the running QApplication.

    Idempotent — safe to call multiple times; the filter is installed only
    once per application instance.
    """
    global _filter_instance
    if _filter_instance is not None:
        return
    _filter_instance = _StickyTooltipFilter(app)
    app.installEventFilter(_filter_instance)
