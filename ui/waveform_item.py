"""Rekordbox-Style Waveform Graphics Item für die Timeline.

Zeichnet eine mehrfarbige Frequenz-Wellenform (wie Rekordbox/CDJ):
    Blau   → Bass / Kicks  (20-250 Hz)
    Rosa   → Mitten / Snare (250-4000 Hz)
    Weiß   → Höhen / HiHats (4000+ Hz)

Plus halbtransparente Beatgrid-Linien.
Vollständig gecacht via QPixmap für flüssiges Scrollen.
"""

import json
from typing import Optional

from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QStyleOptionGraphicsItem, QWidget
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QPen, QLinearGradient, QImage,
)


# Rekordbox-Farbpalette
COLOR_LOW = QColor(30, 90, 220)       # Bass: Blau
COLOR_LOW_BRIGHT = QColor(60, 140, 255)
COLOR_MID = QColor(220, 50, 120)      # Mitten: Rosa/Magenta
COLOR_MID_BRIGHT = QColor(255, 80, 160)
COLOR_HIGH = QColor(240, 240, 255)    # Höhen: Weiß-Gelb
COLOR_HIGH_BRIGHT = QColor(255, 255, 200)
COLOR_BEAT_LINE = QColor(255, 255, 255, 55)  # Beatgrid: halbtransparent weiß
COLOR_DOWNBEAT = QColor(255, 255, 255, 90)   # Starke Beats (1 von 4)
COLOR_BG = QColor(8, 8, 12)                   # Dunkler Hintergrund


class WaveformGraphicsItem(QGraphicsItem):
    """Rekordbox-style mehrfarbige Wellenform mit Beatgrid-Overlay.

    Rendert die Wellenform einmalig in ein QPixmap (Cache).
    Beim Scrollen/Zoomen wird nur das Pixmap geblittet → flüssig.
    """

    def __init__(self, band_low: list[float], band_mid: list[float],
                 band_high: list[float], duration: float,
                 beat_positions: Optional[list[float]] = None,
                 pixels_per_second: float = 20.0,
                 height: float = 50.0,
                 parent: Optional[QGraphicsItem] = None):
        super().__init__(parent)

        self._band_low = band_low
        self._band_mid = band_mid
        self._band_high = band_high
        self._duration = max(0.01, duration)
        self._beat_positions = beat_positions or []
        self._pps = pixels_per_second
        self._height = height

        self._width = self._duration * self._pps
        self._pixmap: Optional[QPixmap] = None

        # Cache-Flag: nur neu rendern wenn Daten sich ändern
        self._dirty = True

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def set_pixels_per_second(self, pps: float):
        """Update bei Zoom-Änderung."""
        if abs(pps - self._pps) > 0.01:
            self._pps = pps
            self._width = self._duration * self._pps
            self._dirty = True
            self.prepareGeometryChange()
            self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None):
        if self._dirty or self._pixmap is None:
            self._render_pixmap()
            self._dirty = False

        if self._pixmap:
            painter.drawPixmap(0, 0, self._pixmap)

    def _render_pixmap(self):
        """Rendert die komplette Wellenform in ein gecachtes QPixmap."""
        w = max(1, int(self._width))
        h = max(1, int(self._height))

        # Begrenze Pixmap-Größe für Speicherschutz (max 16000px breit)
        render_w = min(w, 16000)

        img = QImage(render_w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(COLOR_BG)

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        num_samples = len(self._band_low)
        if num_samples == 0:
            p.end()
            self._pixmap = QPixmap.fromImage(img)
            return

        half_h = h / 2.0

        # Zeichne Wellenform: Von hinten nach vorne (High → Mid → Low)
        # So überlagert Bass die Mitten und Mitten die Höhen — wie Rekordbox
        for x_px in range(render_w):
            # Sample-Index für diese Pixel-Position
            t_frac = x_px / max(1, render_w - 1)
            idx = int(t_frac * (num_samples - 1))
            idx = min(idx, num_samples - 1)

            low_val = self._band_low[idx]
            mid_val = self._band_mid[idx]
            high_val = self._band_high[idx]

            # Höhen (hinterste Schicht — weiß/gelb)
            if high_val > 0.02:
                h_px = max(1, int(high_val * half_h * 0.7))
                intensity = min(1.0, high_val * 1.3)
                color = QColor(
                    int(COLOR_HIGH.red() * intensity + COLOR_HIGH_BRIGHT.red() * (1 - intensity)),
                    int(COLOR_HIGH.green() * intensity + COLOR_HIGH_BRIGHT.green() * (1 - intensity)),
                    int(COLOR_HIGH.blue() * intensity),
                    int(120 + 100 * intensity)
                )
                p.setPen(QPen(color, 1))
                y_top = int(half_h - h_px)
                y_bot = int(half_h + h_px)
                p.drawLine(x_px, y_top, x_px, y_bot)

            # Mitten (mittlere Schicht — rosa/rot)
            if mid_val > 0.02:
                m_px = max(1, int(mid_val * half_h * 0.85))
                intensity = min(1.0, mid_val * 1.2)
                color = QColor(
                    int(COLOR_MID.red() + (COLOR_MID_BRIGHT.red() - COLOR_MID.red()) * intensity),
                    int(COLOR_MID.green() + (COLOR_MID_BRIGHT.green() - COLOR_MID.green()) * intensity),
                    int(COLOR_MID.blue() + (COLOR_MID_BRIGHT.blue() - COLOR_MID.blue()) * intensity),
                    int(140 + 80 * intensity)
                )
                p.setPen(QPen(color, 1))
                y_top = int(half_h - m_px)
                y_bot = int(half_h + m_px)
                p.drawLine(x_px, y_top, x_px, y_bot)

            # Bass (vorderste Schicht — blau, dominant)
            if low_val > 0.02:
                l_px = max(1, int(low_val * half_h * 1.0))
                intensity = min(1.0, low_val * 1.1)
                color = QColor(
                    int(COLOR_LOW.red() + (COLOR_LOW_BRIGHT.red() - COLOR_LOW.red()) * intensity),
                    int(COLOR_LOW.green() + (COLOR_LOW_BRIGHT.green() - COLOR_LOW.green()) * intensity),
                    int(COLOR_LOW.blue() + (COLOR_LOW_BRIGHT.blue() - COLOR_LOW.blue()) * intensity),
                    int(180 + 75 * intensity)
                )
                p.setPen(QPen(color, 1))
                y_top = int(half_h - l_px)
                y_bot = int(half_h + l_px)
                p.drawLine(x_px, y_top, x_px, y_bot)

        # Beatgrid-Linien zeichnen
        if self._beat_positions:
            for i, beat_time in enumerate(self._beat_positions):
                bx = int((beat_time / self._duration) * render_w)
                if 0 <= bx < render_w:
                    # Jeder 4. Beat = Downbeat (stärker)
                    is_downbeat = (i % 4 == 0)
                    color = COLOR_DOWNBEAT if is_downbeat else COLOR_BEAT_LINE
                    pen_w = 2 if is_downbeat else 1
                    p.setPen(QPen(color, pen_w))
                    p.drawLine(bx, 0, bx, h)

        # Mittellinie (dezent)
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawLine(0, int(half_h), render_w, int(half_h))

        p.end()
        self._pixmap = QPixmap.fromImage(img)

    @classmethod
    def from_db_data(cls, waveform_data, beat_positions_json: str = "[]",
                     pixels_per_second: float = 20.0, height: float = 50.0,
                     parent=None) -> "WaveformGraphicsItem":
        """Factory: Erstellt ein WaveformGraphicsItem aus DB-Daten (WaveformData row)."""
        band_low = json.loads(waveform_data.band_low) if isinstance(waveform_data.band_low, str) else waveform_data.band_low
        band_mid = json.loads(waveform_data.band_mid) if isinstance(waveform_data.band_mid, str) else waveform_data.band_mid
        band_high = json.loads(waveform_data.band_high) if isinstance(waveform_data.band_high, str) else waveform_data.band_high

        if isinstance(beat_positions_json, str):
            beats = json.loads(beat_positions_json)
        else:
            beats = beat_positions_json or []

        return cls(
            band_low=band_low,
            band_mid=band_mid,
            band_high=band_high,
            duration=waveform_data.duration,
            beat_positions=beats,
            pixels_per_second=pixels_per_second,
            height=height,
            parent=parent,
        )
