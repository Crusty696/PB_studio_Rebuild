"""Rekordbox-Style Waveform Graphics Item für die Timeline.

Zeichnet eine mehrfarbige Frequenz-Wellenform (wie Rekordbox/CDJ):
    Blau   → Bass / Kicks  (20-250 Hz)
    Rosa   → Mitten / Snare (250-4000 Hz)
    Weiß   → Höhen / HiHats (4000+ Hz)

Plus halbtransparente Beatgrid-Linien mit LOD (Level of Detail).
Performance-optimiert: Tile-basiertes Caching, Culling, LOD-Beatgrid.
"""

import bisect
import json
import math
from typing import Optional

from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QPen, QImage,
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

# Tile-Konfiguration für gecachtes Rendering
TILE_WIDTH = 512  # Pixel pro Tile

# LOD-Schwellwerte
LOD_BEAT_MIN_SPACING_PX = 4    # Beats werden erst ab 4px Abstand gezeichnet
LOD_BEAT_DOWNBEAT_ONLY_PX = 12 # Unter 12px: nur Downbeats (jeder 4.) zeichnen
LOD_DOWNSAMPLE_THRESHOLD = 2   # Ab 2 Samples/Pixel wird downgesampled


# Vorberechnete Farben für Performance (vermeidet QColor-Erstellung in der Schleife)
def _precompute_band_colors(base: QColor, bright: QColor, alpha_base: int, alpha_range: int, steps: int = 32):
    """Erzeugt eine LUT (Lookup Table) für Band-Farben nach Intensität."""
    lut = []
    for i in range(steps):
        t = i / max(1, steps - 1)
        r = int(base.red() + (bright.red() - base.red()) * t)
        g = int(base.green() + (bright.green() - base.green()) * t)
        b = int(base.blue() + (bright.blue() - base.blue()) * t)
        a = int(alpha_base + alpha_range * t)
        lut.append(QColor(min(255, r), min(255, g), min(255, b), min(255, a)))
    return lut

_LUT_LOW = _precompute_band_colors(COLOR_LOW, COLOR_LOW_BRIGHT, 180, 75)
_LUT_MID = _precompute_band_colors(COLOR_MID, COLOR_MID_BRIGHT, 140, 80)
_LUT_HIGH = _precompute_band_colors(COLOR_HIGH, COLOR_HIGH_BRIGHT, 120, 100)
_LUT_STEPS = len(_LUT_LOW)


class WaveformGraphicsItem(QGraphicsItem):
    """Rekordbox-style mehrfarbige Wellenform mit Beatgrid-Overlay.

    Performance-Features:
    - Tile-basiertes Pixmap-Caching (nur sichtbare Tiles werden gerendert)
    - Culling: paint() zeichnet nur den sichtbaren Ausschnitt (exposedRect)
    - LOD-Beatgrid: Beats werden bei starkem Zoom-Out ausgeblendet
    - Farb-LUT: Keine QColor-Erstellung pro Pixel
    - Downsampling: Bei Zoom-Out werden Samples gemittelt statt übereinander gezeichnet
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
        self._tile_cache: dict[int, QPixmap] = {}  # tile_index → QPixmap

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False)
        # ItemUsesExtendedStyleOption sorgt dafür, dass exposedRect korrekt befüllt wird
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def set_pixels_per_second(self, pps: float):
        """Update bei Zoom-Änderung."""
        if abs(pps - self._pps) > 0.01:
            self._pps = pps
            self._width = self._duration * self._pps
            self._tile_cache.clear()  # Alle Tiles invalidieren
            self.prepareGeometryChange()
            self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None):
        """Zeichnet nur den sichtbaren Bereich (Culling + Tile-Cache)."""
        # exposedRect = der aktuell sichtbare Ausschnitt in Item-Koordinaten
        clip_rect = option.exposedRect
        if clip_rect.isEmpty():
            clip_rect = self.boundingRect()

        w = max(1, int(self._width))
        h = max(1, int(self._height))

        # Welche Tiles sind sichtbar?
        tile_start = max(0, int(clip_rect.left()) // TILE_WIDTH)
        tile_end = min((w - 1) // TILE_WIDTH, int(clip_rect.right()) // TILE_WIDTH)

        for tile_idx in range(tile_start, tile_end + 1):
            tile_x = tile_idx * TILE_WIDTH
            tile_w = min(TILE_WIDTH, w - tile_x)
            if tile_w <= 0:
                continue

            # Tile aus Cache holen oder rendern
            if tile_idx not in self._tile_cache:
                self._tile_cache[tile_idx] = self._render_tile(tile_idx, tile_w, h)

            pixmap = self._tile_cache[tile_idx]
            if pixmap:
                painter.drawPixmap(tile_x, 0, pixmap)

        # Beatgrid mit LOD zeichnen (direkt, nicht gecacht — reagiert auf Zoom)
        self._draw_beatgrid_lod(painter, clip_rect, h)

        # Mittellinie (dezent)
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        half_h = int(h / 2.0)
        visible_left = max(0, int(clip_rect.left()))
        visible_right = min(w, int(clip_rect.right()))
        painter.drawLine(visible_left, half_h, visible_right, half_h)

    def _render_tile(self, tile_idx: int, tile_w: int, h: int) -> Optional[QPixmap]:
        """Rendert ein einzelnes Tile der Wellenform."""
        num_samples = len(self._band_low)
        if num_samples == 0:
            return None

        # Lokale Referenzen für schnelleren Zugriff in der Schleife
        band_low = self._band_low
        band_mid = self._band_mid
        band_high = self._band_high

        tile_x_start = tile_idx * TILE_WIDTH
        w_total = max(1, int(self._width))
        half_h = h / 2.0

        img = QImage(tile_w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(COLOR_BG)

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Berechne Samples-pro-Pixel Verhältnis für Downsampling
        samples_per_pixel = num_samples / max(1, w_total)

        for local_x in range(tile_w):
            global_x = tile_x_start + local_x

            if samples_per_pixel <= LOD_DOWNSAMPLE_THRESHOLD:
                # Normales Sampling: 1 Sample pro Pixel
                t_frac = global_x / max(1, w_total - 1)
                idx = min(int(t_frac * (num_samples - 1)), num_samples - 1)
                low_val = band_low[idx]
                mid_val = band_mid[idx]
                high_val = band_high[idx]
            else:
                # Downsampling: Mittelwert über alle Samples in diesem Pixel
                # Optimiert: list slicing + sum() statt manueller Schleife
                sample_start = int((global_x / w_total) * num_samples)
                sample_end = int(((global_x + 1) / w_total) * num_samples)
                sample_start = max(0, min(sample_start, num_samples - 1))
                sample_end = max(sample_start + 1, min(sample_end, num_samples))

                count = sample_end - sample_start
                if count > 0:
                    inv_count = 1.0 / count
                    low_val = sum(band_low[sample_start:sample_end]) * inv_count
                    mid_val = sum(band_mid[sample_start:sample_end]) * inv_count
                    high_val = sum(band_high[sample_start:sample_end]) * inv_count
                else:
                    low_val = mid_val = high_val = 0.0

            # Höhen (hinterste Schicht — weiß/gelb)
            if high_val > 0.02:
                h_px = max(1, int(high_val * half_h * 0.7))
                lut_idx = min(int(min(1.0, high_val * 1.3) * (_LUT_STEPS - 1)), _LUT_STEPS - 1)
                p.setPen(QPen(_LUT_HIGH[lut_idx], 1))
                y_top = int(half_h - h_px)
                y_bot = int(half_h + h_px)
                p.drawLine(local_x, y_top, local_x, y_bot)

            # Mitten (mittlere Schicht — rosa/rot)
            if mid_val > 0.02:
                m_px = max(1, int(mid_val * half_h * 0.85))
                lut_idx = min(int(min(1.0, mid_val * 1.2) * (_LUT_STEPS - 1)), _LUT_STEPS - 1)
                p.setPen(QPen(_LUT_MID[lut_idx], 1))
                y_top = int(half_h - m_px)
                y_bot = int(half_h + m_px)
                p.drawLine(local_x, y_top, local_x, y_bot)

            # Bass (vorderste Schicht — blau, dominant)
            if low_val > 0.02:
                l_px = max(1, int(low_val * half_h * 1.0))
                lut_idx = min(int(min(1.0, low_val * 1.1) * (_LUT_STEPS - 1)), _LUT_STEPS - 1)
                p.setPen(QPen(_LUT_LOW[lut_idx], 1))
                y_top = int(half_h - l_px)
                y_bot = int(half_h + l_px)
                p.drawLine(local_x, y_top, local_x, y_bot)

        p.end()
        return QPixmap.fromImage(img)

    def _draw_beatgrid_lod(self, painter: QPainter, clip_rect: QRectF, h: int):
        """Zeichnet Beatgrid-Linien mit Multi-Level LOD und Binary-Search Culling.

        LOD-Stufen:
        - beat_spacing < 4px  → keine Beats zeichnen
        - beat_spacing < 12px → nur Downbeats (jeder 4.)
        - beat_spacing >= 12px → alle Beats zeichnen
        """
        beats = self._beat_positions
        if not beats or len(beats) < 2:
            return

        w_total = max(1.0, self._width)

        # Berechne durchschnittlichen Beat-Abstand in Pixeln
        avg_beat_interval = self._duration / len(beats)
        beat_spacing_px = avg_beat_interval * self._pps

        # LOD Level 0: Wenn Beats zu eng beieinander → gar nicht zeichnen
        if beat_spacing_px < LOD_BEAT_MIN_SPACING_PX:
            return

        # LOD Level 1: Nur Downbeats bei mittlerem Zoom
        downbeat_only = beat_spacing_px < LOD_BEAT_DOWNBEAT_ONLY_PX

        # Sichtbarer Bereich in Zeit umrechnen
        visible_left = max(0.0, clip_rect.left())
        visible_right = min(w_total, clip_rect.right())
        time_left = (visible_left / w_total) * self._duration
        time_right = (visible_right / w_total) * self._duration

        # Binary Search: Finde den ersten und letzten sichtbaren Beat
        idx_start = bisect.bisect_left(beats, time_left - 0.1)
        idx_end = bisect.bisect_right(beats, time_right + 0.1)

        # Vorbereitete Pens (vermeidet QPen-Erstellung pro Beat)
        pen_downbeat = QPen(COLOR_DOWNBEAT, 2)
        pen_normal = QPen(COLOR_BEAT_LINE, 1)

        for i in range(idx_start, idx_end):
            is_downbeat = (i % 4 == 0)

            # LOD Level 1: Bei mittlerem Zoom nur Downbeats
            if downbeat_only and not is_downbeat:
                continue

            beat_time = beats[i]
            bx = int((beat_time / self._duration) * w_total)
            painter.setPen(pen_downbeat if is_downbeat else pen_normal)
            painter.drawLine(bx, 0, bx, h)

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
