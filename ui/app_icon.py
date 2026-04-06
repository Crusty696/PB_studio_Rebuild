"""App icon generator for PB Studio.

Generates a waveform-style DJ icon programmatically using QPainter.
Call get_app_icon() after QApplication is created.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap, QPen, QBrush
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

_ICON_CACHE: QIcon | None = None
_RESOURCE_DIR = Path(__file__).parent.parent / "resources"


def _draw_icon(size: int) -> QPixmap:
    """Draw the PB Studio icon at the given pixel size."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size

    # ── Background circle ──────────────────────────────────────────────
    bg_color = QColor("#1a1b23")
    p.setBrush(QBrush(bg_color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, s, s)

    # ── Waveform bars (DJ / audio equaliser style) ────────────────────
    gold = QColor("#d4a44a")
    dim_gold = QColor("#8a6b2e")

    margin = s * 0.15
    waveform_w = s - 2 * margin
    center_y = s * 0.62
    bar_count = 9
    bar_gap = waveform_w / (bar_count * 1.6)
    bar_w = bar_gap * 0.7

    # Heights follow a waveform / equaliser envelope
    heights_norm = [0.30, 0.55, 0.75, 0.90, 1.00, 0.90, 0.75, 0.55, 0.30]
    max_bar_h = s * 0.30

    for i, hn in enumerate(heights_norm):
        bh = max_bar_h * hn
        bx = margin + i * (bar_w + bar_gap)
        by = center_y - bh

        # Gradient-like: bright top, dimmer bottom
        color = gold if hn >= 0.75 else dim_gold
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)

        # Rounded rect bars
        path = QPainterPath()
        radius = bar_w * 0.3
        path.addRoundedRect(bx, by, bar_w, bh, radius, radius)
        p.drawPath(path)

    # ── "PB" text ─────────────────────────────────────────────────────
    p.setPen(QPen(QColor("#d4a44a")))
    font = p.font()
    font.setPixelSize(max(8, int(s * 0.28)))
    from PySide6.QtGui import QFont
    font.setWeight(QFont.Weight.Bold)
    font.setFamily("Arial")
    p.setFont(font)
    text_rect = px.rect().adjusted(0, 0, 0, -int(s * 0.28))
    p.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "PB")

    # ── Outer ring ────────────────────────────────────────────────────
    pen = QPen(QColor("#d4a44a"), max(1, s * 0.025))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    inset = pen.widthF() / 2
    p.drawEllipse(
        int(inset), int(inset),
        int(s - pen.widthF()), int(s - pen.widthF()),
    )

    p.end()
    return px


def get_app_icon() -> QIcon:
    """Return (and cache) the PB Studio QIcon."""
    global _ICON_CACHE
    if _ICON_CACHE is not None:
        return _ICON_CACHE

    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw_icon(size))

    _ICON_CACHE = icon

    # Persist a 256px PNG so PyInstaller can convert it to .ico if needed
    png_path = _RESOURCE_DIR / "pb_studio_icon.png"
    try:
        if not png_path.exists():
            _draw_icon(256).save(str(png_path))
    except (OSError, RuntimeError) as exc:
        logger.warning("get_app_icon: failed to persist icon PNG: %s", exc)

    return _ICON_CACHE
