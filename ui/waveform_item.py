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
from typing import Optional

from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QPainter, QColor, QPen, QImage, QPainterPath, QBrush,
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
TILE_CACHE_MAX = 256  # Max gecachte Tiles (~50MB bei 512×50px×4B)

# LOD-Schwellwerte
LOD_BEAT_MIN_SPACING_PX = 4    # Beats werden erst ab 4px Abstand gezeichnet
LOD_BEAT_DOWNBEAT_ONLY_PX = 12 # Unter 12px: nur Downbeats (jeder 4.) zeichnen
LOD_DOWNSAMPLE_THRESHOLD = 2   # Ab 2 Samples/Pixel wird downgesampled




class WaveformGraphicsItem(QGraphicsItem):
    """Rekordbox-style mehrfarbige Wellenform mit Beatgrid-Overlay.

    Performance-Features:
    - Tile-basiertes Pixmap-Caching (nur sichtbare Tiles werden gerendert)
    - Culling: paint() zeichnet nur den sichtbaren Ausschnitt (exposedRect)
    - LOD-Beatgrid: Beats werden bei starkem Zoom-Out ausgeblendet
    - Farb-LUT: Keine QColor-Erstellung pro Pixel
    - Peak-Downsampling: Bei Zoom-Out wird max() statt Durchschnitt verwendet (Peaks bleiben)
    - QPainterPath: 3 gefüllte Pfade statt tausender drawLine-Aufrufe
    """

    def __init__(self, band_low: list[float], band_mid: list[float],
                 band_high: list[float], duration: float,
                 beat_positions: Optional[list[float]] = None,
                 pixels_per_second: float = 20.0,
                 height: float = 50.0,
                 parent: Optional[QGraphicsItem] = None):
        super().__init__(parent)

        # B-386: num_samples wird aus len(band_low) abgeleitet, band_mid/high
        # werden mit demselben Index gelesen. Korrupte/teilgeschriebene Daten
        # mit ungleichen Bandlaengen → IndexError beim Paint. Daher band_mid/high
        # auf die Laenge von band_low normalisieren (kuerzen oder mit 0.0 padden).
        self._band_low = list(band_low or [])
        _n = len(self._band_low)
        self._band_mid = self._fit_band_length(band_mid, _n)
        self._band_high = self._fit_band_length(band_high, _n)
        self._duration = max(0.01, duration or 0.0)
        self._beat_positions = beat_positions or []
        self._pps = pixels_per_second
        self._height = height

        self._width = self._duration * self._pps
        self._tile_cache: dict[int, QImage] = {}  # tile_index → QImage (thread-safe)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False)
        # ItemUsesExtendedStyleOption sorgt dafür, dass exposedRect korrekt befüllt wird
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)

    @staticmethod
    def _fit_band_length(band, target_len: int) -> list[float]:
        """B-386: bringt ein Frequenzband auf ``target_len`` (kuerzen/0.0-padden)."""
        band = list(band or [])
        if len(band) < target_len:
            band = band + [0.0] * (target_len - len(band))
        elif len(band) > target_len:
            band = band[:target_len]
        return band

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

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

            # Tile aus Cache holen oder rendern (LRU: Cache-Hit → ans Ende schieben)
            if tile_idx in self._tile_cache:
                # LRU: Genutzten Eintrag ans Ende verschieben
                self._tile_cache[tile_idx] = self._tile_cache.pop(tile_idx)
            else:
                self._tile_cache[tile_idx] = self._render_tile(tile_idx, tile_w, h)
                # LRU-Eviction: älteste (am längsten ungenutzte) Tiles entfernen
                while len(self._tile_cache) > TILE_CACHE_MAX:
                    self._tile_cache.pop(next(iter(self._tile_cache)))

            tile_img = self._tile_cache[tile_idx]
            if tile_img:
                painter.drawImage(tile_x, 0, tile_img)

        # Beatgrid mit LOD zeichnen (direkt, nicht gecacht — reagiert auf Zoom)
        self._draw_beatgrid_lod(painter, clip_rect, h)

        # Mittellinie (dezent)
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        half_h = int(h / 2.0)
        visible_left = max(0, int(clip_rect.left()))
        visible_right = min(w, int(clip_rect.right()))
        painter.drawLine(visible_left, half_h, visible_right, half_h)

    def _get_peak_values(self, band: list[float], global_x: int,
                         w_total: int, num_samples: int,
                         samples_per_pixel: float) -> float:
        """Ermittelt den Peak-Wert (Maximum) für ein Pixel — bewahrt Transienten."""
        if samples_per_pixel <= LOD_DOWNSAMPLE_THRESHOLD:
            # 1:1 oder weniger → direktes Sample
            t_frac = global_x / max(1, w_total - 1)
            idx = min(int(t_frac * (num_samples - 1)), num_samples - 1)
            return band[idx]
        else:
            # Downsampling: MAX statt Durchschnitt → Peaks bleiben erhalten
            sample_start = int((global_x / w_total) * num_samples)
            sample_end = int(((global_x + 1) / w_total) * num_samples)
            sample_start = max(0, min(sample_start, num_samples - 1))
            sample_end = max(sample_start + 1, min(sample_end, num_samples))
            return max(band[sample_start:sample_end])

    def _render_tile(self, tile_idx: int, tile_w: int, h: int) -> Optional[QImage]:
        """Rendert ein Tile via QPainterPath — performant UND detailliert.

        Zeichnet drei überlappende Frequenz-Schichten als gefüllte Pfade:
        1. Bass (Blau) — hinterste Schicht, größte Amplitude
        2. Mitten (Rosa) — mittlere Schicht
        3. Höhen (Weiß) — vorderste Schicht, kleinste Amplitude
        Jede Schicht besteht aus zwei Pfaden (oben + unten), die zusammen
        eine symmetrische Wellenform um die Mittellinie bilden.
        """
        num_samples = len(self._band_low)
        if num_samples == 0:
            return None

        band_low = self._band_low
        band_mid = self._band_mid
        band_high = self._band_high

        tile_x_start = tile_idx * TILE_WIDTH
        w_total = max(1, int(self._width))
        half_h = h / 2.0
        samples_per_pixel = num_samples / max(1, w_total)

        img = QImage(tile_w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(COLOR_BG)

        p = QPainter(img)
        # B-644: AA an fuer die Wellenform-Kurven (glatte 3-Band-Optik wie
        # Rekordbox/DaVinci/Studio One statt treppiger "8-Bit"-Kanten). Anders
        # als die Beat-Linien ist dieses Tile GECACHT (self._tile_cache) — die
        # AA-Kosten fallen einmalig pro Tile an, nicht pro Frame. Der P8-B1-Lag
        # (ui/timeline.py:1276) entstand durch AA JEDEN Frame bei vielen
        # sichtbaren Items, nicht durch einmaliges Tile-Rendering.
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)

        # --- Peak-Werte für alle Pixel im Tile berechnen ---
        low_peaks = []
        mid_peaks = []
        high_peaks = []

        for local_x in range(tile_w):
            global_x = tile_x_start + local_x
            low_peaks.append(self._get_peak_values(band_low, global_x, w_total, num_samples, samples_per_pixel))
            mid_peaks.append(self._get_peak_values(band_mid, global_x, w_total, num_samples, samples_per_pixel))
            high_peaks.append(self._get_peak_values(band_high, global_x, w_total, num_samples, samples_per_pixel))

        # --- QPainterPath pro Band erstellen ---
        # Jedes Band: oberer Rand (links→rechts), dann unterer Rand (rechts→links)
        # → ergibt ein geschlossenes Polygon, das mit fillPath gefüllt wird.

        # Skalierungsfaktoren: Bass nutzt volle Höhe, Mitten 70%, Höhen 45%
        # So entsteht die typische Rekordbox-Schichtung
        band_configs = [
            (low_peaks,  0.95, COLOR_LOW,  COLOR_LOW_BRIGHT,  200),   # Bass: blau, groß
            (mid_peaks,  0.65, COLOR_MID,  COLOR_MID_BRIGHT,  180),   # Mitten: rosa, mittel
            (high_peaks, 0.40, COLOR_HIGH, COLOR_HIGH_BRIGHT, 160),   # Höhen: weiß, klein
        ]

        for peaks, scale, color_base, color_bright, alpha in band_configs:
            path = QPainterPath()

            # Oberer Rand: links → rechts (von Mittellinie nach oben)
            path.moveTo(0.0, half_h)
            for x in range(tile_w):
                val = min(1.0, peaks[x])
                y_offset = val * half_h * scale
                path.lineTo(float(x), half_h - y_offset)

            # Unterer Rand: rechts → links (von Mittellinie nach unten, gespiegelt)
            for x in range(tile_w - 1, -1, -1):
                val = min(1.0, peaks[x])
                y_offset = val * half_h * scale
                path.lineTo(float(x), half_h + y_offset)

            path.closeSubpath()

            # Farbe: Blend zwischen base und bright, mit Alpha
            fill_color = QColor(
                (color_base.red() + color_bright.red()) // 2,
                (color_base.green() + color_bright.green()) // 2,
                (color_base.blue() + color_bright.blue()) // 2,
                alpha,
            )
            p.setBrush(QBrush(fill_color))
            p.drawPath(path)

        p.end()
        return img  # QImage direkt zurueckgeben (thread-safe, kein QPixmap noetig)

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

        # Vorbereitete Pens (vermeidet QPen-Erstellung pro Beat).
        # B-644: setCosmetic(True) — der Zoom laeuft ueber view.scale()
        # (ui/timeline.py:3148/3648/3682), also skaliert eine normale
        # (geometrische) Pen-Breite MIT dem Zoom: bei hohem Zoom dicker, bei
        # Zoom-Out duenner/mit AA fast unsichtbar. Ein kosmetischer Pen bleibt
        # dagegen immer exakt 1 Geraetepixel breit — konstante, saubere
        # Grid-Linien unabhaengig vom Zoom-Level, wie bei DaVinci/Rekordbox.
        pen_downbeat = QPen(COLOR_DOWNBEAT, 2)
        pen_downbeat.setCosmetic(True)
        pen_normal = QPen(COLOR_BEAT_LINE, 1)
        pen_normal.setCosmetic(True)

        # B-644: AA NUR lokal fuer diesen Block, gescoped auf DIESEN Painter-
        # Aufruf — nicht global am QGraphicsView (ui/timeline.py:1280, das war
        # der P8-B1-Lag: AA fuer ALLE Items JEDEN Frame). Beat-Linien werden
        # zwar weiterhin pro Frame neu gezeichnet (nicht gecacht wie die
        # Wellenform-Tiles), aber Linien-AA ist deutlich billiger als
        # Pfad-Fill-AA, und LOD (Level 0/1 oben) haelt die Anzahl der
        # gleichzeitig sichtbaren Linien ohnehin niedrig. Zustand danach
        # zurueckgesetzt, damit die Mittellinie (direkt nach diesem Aufruf,
        # gleicher Painter) unveraendert bleibt.
        was_aa = painter.testRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for i in range(idx_start, idx_end):
            is_downbeat = (i % 4 == 0)

            # LOD Level 1: Bei mittlerem Zoom nur Downbeats
            if downbeat_only and not is_downbeat:
                continue

            beat_time = beats[i]
            # B-644: round() statt int() — int() schneidet immer AB (Richtung 0),
            # nicht zum naechsten Pixel. Bei vielen Beats systematischer Drift
            # bis zu 1px pro Linie ("Beatgrid sitzt ungenau").
            bx = round((beat_time / self._duration) * w_total)
            painter.setPen(pen_downbeat if is_downbeat else pen_normal)
            painter.drawLine(bx, 0, bx, h)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, was_aa)

    @classmethod
    def from_db_data(cls, waveform_data, beat_positions_json: str = "[]",
                     pixels_per_second: float = 20.0, height: float = 50.0,
                     parent=None) -> "WaveformGraphicsItem":
        """Factory: Erstellt ein WaveformGraphicsItem aus DB-Daten (WaveformData row)."""
        try:
            band_low = json.loads(waveform_data.band_low) if isinstance(waveform_data.band_low, str) else waveform_data.band_low
        except (json.JSONDecodeError, TypeError):
            band_low = []
        try:
            band_mid = json.loads(waveform_data.band_mid) if isinstance(waveform_data.band_mid, str) else waveform_data.band_mid
        except (json.JSONDecodeError, TypeError):
            band_mid = []
        try:
            band_high = json.loads(waveform_data.band_high) if isinstance(waveform_data.band_high, str) else waveform_data.band_high
        except (json.JSONDecodeError, TypeError):
            band_high = []

        try:
            beats = json.loads(beat_positions_json) if isinstance(beat_positions_json, str) else (beat_positions_json or [])
        except (json.JSONDecodeError, TypeError):
            beats = []

        return cls(
            band_low=band_low,
            band_mid=band_mid,
            band_high=band_high,
            duration=waveform_data.duration or 0.0,
            beat_positions=beats,
            pixels_per_second=pixels_per_second,
            height=height,
            parent=parent,
        )
