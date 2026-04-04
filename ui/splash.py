"""Splash screen for PB Studio.

Usage in main():
    splash = PBSplashScreen(app_version)
    splash.show_message("Initialisiere Datenbank...")
    # ... do startup work ...
    splash.finish(window)
"""

from __future__ import annotations

from PySide6.QtWidgets import QSplashScreen
from PySide6.QtGui import QPainter, QColor, QFont, QPainterPath, QBrush, QPixmap
from PySide6.QtCore import Qt, QRect


_W, _H = 480, 300


def _build_splash_pixmap(version: str) -> QPixmap:
    """Render the splash screen image."""
    px = QPixmap(_W, _H)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # ── Background ────────────────────────────────────────────────────
    p.fillRect(0, 0, _W, _H, QColor("#12131a"))

    # ── Subtle gradient accent at top ────────────────────────────────
    from PySide6.QtGui import QLinearGradient
    grad = QLinearGradient(0, 0, _W, 0)
    grad.setColorAt(0.0, QColor(0, 0, 0, 0))
    grad.setColorAt(0.5, QColor("#d4a44a"))
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    grad.setColorAt(0.5, QColor(212, 164, 74, 60))
    p.fillRect(0, 0, _W, 3, grad)

    # ── Waveform decoration (bottom area) ────────────────────────────
    _draw_mini_waveform(p, x0=30, y_center=220, width=_W - 60, height=40)

    # ── Title ─────────────────────────────────────────────────────────
    title_font = QFont("Arial", 42, QFont.Weight.Bold)
    p.setFont(title_font)
    p.setPen(QColor("#d4a44a"))
    p.drawText(QRect(0, 40, _W, 80), Qt.AlignmentFlag.AlignCenter, "PB Studio")

    # ── Tagline ───────────────────────────────────────────────────────
    tag_font = QFont("Arial", 13)
    tag_font.setWeight(600)
    p.setFont(tag_font)
    p.setPen(QColor("#808080"))
    p.drawText(QRect(0, 110, _W, 30), Qt.AlignmentFlag.AlignCenter,
               "Director's Cockpit  —  Beat-Synchronized Video Editor")

    # ── "Powered by AI" badge ─────────────────────────────────────────
    badge_font = QFont("Arial", 10)
    badge_font.setWeight(600)
    p.setFont(badge_font)
    bw, bh = 120, 22
    bx, by = (_W - bw) // 2, 152
    path = QPainterPath()
    path.addRoundedRect(bx, by, bw, bh, 6, 6)
    p.fillPath(path, QColor("#1e3a5f"))
    p.setPen(QColor("#5eaeff"))
    p.drawText(QRect(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, "✦ Powered by AI")

    # ── Version ───────────────────────────────────────────────────────
    ver_font = QFont("Arial", 10)
    p.setFont(ver_font)
    p.setPen(QColor("#505060"))
    p.drawText(QRect(0, _H - 28, _W - 12, 20),
               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
               f"v{version}")

    p.end()
    return px


def _draw_mini_waveform(painter: QPainter, x0: int, y_center: int, width: int, height: int):
    """Draw a small decorative waveform."""
    import math
    bar_count = 32
    bar_w = width / (bar_count * 1.7)
    bar_gap = width / (bar_count * 1.7) * 0.7

    gold = QColor(212, 164, 74, 90)
    painter.setBrush(QBrush(gold))
    painter.setPen(Qt.PenStyle.NoPen)

    for i in range(bar_count):
        t = i / (bar_count - 1)
        # sinusoidal envelope
        env = math.sin(t * math.pi)
        # waveform ripple
        wave = abs(math.sin(t * math.pi * 4 + 0.5))
        bh = max(3, (height * 0.15 + height * 0.85 * env * wave))
        bx = x0 + i * (bar_w + bar_gap)
        by = y_center - bh / 2
        path = QPainterPath()
        path.addRoundedRect(bx, by, bar_w, bh, bar_w * 0.3, bar_w * 0.3)
        painter.drawPath(path)


class PBSplashScreen(QSplashScreen):
    """PB Studio startup splash screen."""

    def __init__(self, app_version: str = "0.5.0"):
        pixmap = _build_splash_pixmap(app_version)
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self._version = app_version

    def show_message(self, text: str) -> None:
        """Update the loading message shown at the bottom of the splash."""
        self.showMessage(
            f"  {text}",
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            QColor("#606070"),
        )
        # Force repaint so user sees the update
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
