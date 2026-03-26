"""Drawable pacing density curve for manual cut-density override."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QPen


class PacingCurveWidget(QWidget):
    """Drawable pacing density curve for manual cut-density override."""
    curve_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setMaximumHeight(200)
        self.setToolTip(
            "Pacing-Kurve: Klicke und ziehe um die Schnitt-Dichte ueber die Zeit "
            "zu zeichnen. Oben = viele Schnitte, Unten = wenige"
        )
        self._num_samples = 200
        self._density = [0.5] * self._num_samples
        self._drawing = False
        self._total_duration = 60.0
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def set_duration(self, duration: float):
        self._total_duration = max(1.0, duration)
        self.update()

    def reset_curve(self):
        self._density = [0.5] * self._num_samples
        self.curve_changed.emit()
        self.update()

    def get_density_at(self, time_sec: float) -> float:
        if self._total_duration <= 0:
            return 0.5
        idx = int((time_sec / self._total_duration) * (self._num_samples - 1))
        idx = max(0, min(idx, self._num_samples - 1))
        return self._density[idx]

    def get_all_densities(self) -> list[float]:
        return list(self._density)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(10, 10, 10))

        # Subtle grid
        p.setPen(QPen(QColor(25, 25, 25), 1))
        for i in range(1, 4):
            y = int(h * i / 4)
            p.drawLine(0, y, w, y)

        # Time markers
        p.setPen(QPen(QColor(50, 50, 50), 1))
        p.setFont(QFont("Segoe UI", 7))
        if self._total_duration > 0:
            step = max(5.0, self._total_duration / 10)
            t = 0.0
            while t <= self._total_duration:
                x = int((t / self._total_duration) * w)
                p.drawLine(x, h - 8, x, h)
                p.drawText(x + 2, h - 1, f"{t:.0f}s")
                t += step

        # Build smooth point list
        points = []
        for i, d in enumerate(self._density):
            x = (i / (self._num_samples - 1)) * w
            y = h - (d * (h - 10))
            points.append((x, y))

        # Filled area under curve (smooth cubic spline)
        path = QPainterPath()
        path.moveTo(0, h)
        if points:
            path.lineTo(points[0][0], points[0][1])
            for i in range(1, len(points)):
                x0, y0 = points[i - 1]
                x1, y1 = points[i]
                cx = (x0 + x1) / 2.0
                path.cubicTo(cx, y0, cx, y1, x1, y1)
            path.lineTo(w, h)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 180, 212, 35))
        p.drawPath(path)

        # Curve line (smooth cubic spline)
        line_path = QPainterPath()
        if points:
            line_path.moveTo(points[0][0], points[0][1])
            for i in range(1, len(points)):
                x0, y0 = points[i - 1]
                x1, y1 = points[i]
                cx = (x0 + x1) / 2.0
                line_path.cubicTo(cx, y0, cx, y1, x1, y1)
        p.setPen(QPen(QColor(0, 212, 230, 160), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line_path)

        # Label
        p.setPen(QColor(60, 60, 60))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(4, 11, "PACING DENSITY")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._paint_at(event.position())

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._paint_at(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = False
            self.curve_changed.emit()

    def _paint_at(self, pos):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        x_ratio = max(0.0, min(1.0, pos.x() / w))
        y_ratio = max(0.0, min(1.0, 1.0 - (pos.y() / h)))
        idx = int(x_ratio * (self._num_samples - 1))
        idx = max(0, min(idx, self._num_samples - 1))
        # Wider brush radius for organic, smooth drawing
        radius = 6
        for offset in range(-radius, radius + 1):
            j = idx + offset
            if 0 <= j < self._num_samples:
                weight = 1.0 - abs(offset) / (radius + 1.0)
                weight = weight * weight  # quadratic falloff for smoother feel
                self._density[j] = self._density[j] * (1 - weight) + y_ratio * weight
        self.update()
