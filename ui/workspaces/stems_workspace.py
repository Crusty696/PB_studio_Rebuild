"""STEMS Workspace Wrapper: DAW-Ansicht + Analyse-Sub-Tabs.

P9-D: Unter dem Stem-Player (`StemWorkspaceWidget`) liegt jetzt ein
kompaktes 3-Tab-Panel fuer ENERGIE / ONSETS / SNR. Die eigentliche
DAW-Logik im inneren Widget bleibt unveraendert.

Der `StemsController` ruft bei Track-Wechsel `update_analysis(track)` auf,
damit die Sub-Tabs die vorhandenen Analyse-Daten zeichnen koennen
(`energy_curve`, `onset_*_data`; SNR wird aus `acoustic_metadata` gelesen
falls verfuegbar).
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QGridLayout,
)

from ui.widgets.stem_workspace import StemWorkspace as StemWorkspaceWidget
from ui.widgets.workflow_components import SectionTabs


# --------------------------------------------------------------------------
# Leichte Plot-Widgets (QPainter). Nichts aufwaendiges — nur lesbare Kurven.
# --------------------------------------------------------------------------

class _Sparkline(QWidget):
    """Einfache Linien-Sparkline. Range wird automatisch normalisiert."""

    def __init__(self, line_color: str = "#d4a44a", parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = []
        self._color = QColor(line_color)
        self.setMinimumHeight(60)

    def set_values(self, values: Iterable[float] | None):
        self._values = [float(v) for v in (values or [])]
        self.update()

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(400, 80)

    def paintEvent(self, _event):  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#0a0d12"))

        if len(self._values) < 2:
            p.setPen(QColor("#4b5563"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "— keine Daten —")
            return

        w, h = self.width(), self.height()
        vmin = min(self._values)
        vmax = max(self._values)
        span = vmax - vmin if vmax > vmin else 1.0
        n = len(self._values)

        pen = QPen(self._color)
        pen.setWidth(2)
        p.setPen(pen)

        last_x = 0.0
        last_y = 0.0
        for i, v in enumerate(self._values):
            x = i * w / (n - 1)
            y = h - ((v - vmin) / span) * (h - 6) - 3
            if i > 0:
                p.drawLine(int(last_x), int(last_y), int(x), int(y))
            last_x, last_y = x, y


class _OnsetTrack(QWidget):
    """Dreizeilige Strip fuer Kick/Snare/Hihat Onsets (vertikale Marker)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._kick: list[float] = []
        self._snare: list[float] = []
        self._hihat: list[float] = []
        self._duration = 0.0
        self.setMinimumHeight(80)

    def set_onsets(
        self,
        kick: list[float] | None,
        snare: list[float] | None,
        hihat: list[float] | None,
        duration: float,
    ):
        self._kick = list(kick or [])
        self._snare = list(snare or [])
        self._hihat = list(hihat or [])
        self._duration = max(float(duration or 0.0), 0.0)
        self.update()

    def paintEvent(self, _event):  # type: ignore[override]
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0a0d12"))

        if self._duration <= 0.0:
            p.setPen(QColor("#4b5563"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "— keine Onset-Daten —")
            return

        w, h = self.width(), self.height()
        lanes = [
            ("Kick",  self._kick,  "#FF9800", 0),
            ("Snare", self._snare, "#E91E63", 1),
            ("Hihat", self._hihat, "#42A5F5", 2),
        ]
        lane_h = h / 3.0
        label_w = 48
        usable_w = w - label_w - 6

        p.setPen(QColor("#9ca3af"))
        for label, times, color, idx in lanes:
            y0 = int(idx * lane_h)
            y1 = int((idx + 1) * lane_h) - 2
            p.setPen(QColor("#6b7280"))
            p.drawText(4, y0 + int(lane_h / 2) + 4, label)

            pen = QPen(QColor(color))
            pen.setWidth(1)
            p.setPen(pen)
            for t in times:
                x = label_w + (t / self._duration) * usable_w
                p.drawLine(int(x), y0 + 4, int(x), y1)


# --------------------------------------------------------------------------
# Haupt-Wrapper
# --------------------------------------------------------------------------

class StemsWorkspace(QWidget):
    """STEMS workspace container — DAW-Player + Sub-Tab-Panel.

    Attributes:
        stem_widget: Der eigentliche DAW-StemWorkspace (Tracks + Transport).
        sub_tabs: QTabWidget mit ENERGIE / ONSETS / SNR.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # DAW-Player (unveraendert)
        self.stem_widget = StemWorkspaceWidget()
        layout.addWidget(self.stem_widget, stretch=1)

        # Sub-Tabs (ENERGIE / ONSETS / SNR) — feste Gesamthoehe
        self.sub_tabs = SectionTabs()
        self.sub_tabs.setFixedHeight(150)
        self.sub_tabs.setToolTip(
            "Analyse-Ansichten fuer den geladenen Audio-Track: Energie, Onsets und Stem-SNR."
        )

        # ENERGIE
        self._energy_page = QWidget()
        e_lay = QVBoxLayout(self._energy_page)
        e_lay.setContentsMargins(8, 4, 8, 4)
        e_lay.setSpacing(3)
        self._energy_header = QLabel("Energie-Kurve — kein Track geladen")
        self._energy_header.setStyleSheet("color: #9ca3af; font-size: 10px;")
        e_lay.addWidget(self._energy_header)
        self._energy_plot = _Sparkline("#f0c866")
        e_lay.addWidget(self._energy_plot, stretch=1)
        self.sub_tabs.addTab(self._energy_page, "ENERGIE")
        self.sub_tabs.setTabToolTip(0, "Energieverlauf des Tracks, hilfreich fuer Drops und Pacing.")

        # ONSETS
        self._onsets_page = QWidget()
        o_lay = QVBoxLayout(self._onsets_page)
        o_lay.setContentsMargins(8, 4, 8, 4)
        o_lay.setSpacing(3)
        self._onsets_header = QLabel("Onsets (Kick / Snare / Hihat) — kein Track geladen")
        self._onsets_header.setStyleSheet("color: #9ca3af; font-size: 10px;")
        o_lay.addWidget(self._onsets_header)
        self._onsets_plot = _OnsetTrack()
        o_lay.addWidget(self._onsets_plot, stretch=1)
        self.sub_tabs.addTab(self._onsets_page, "ONSETS")
        self.sub_tabs.setTabToolTip(1, "Kick/Snare/Hihat-Onsets als rhythmische Marker.")

        # SNR
        self._snr_page = QWidget()
        s_lay = QVBoxLayout(self._snr_page)
        s_lay.setContentsMargins(8, 4, 8, 4)
        s_lay.setSpacing(3)
        self._snr_header = QLabel("SNR pro Stem — kein Track geladen")
        self._snr_header.setStyleSheet("color: #9ca3af; font-size: 10px;")
        s_lay.addWidget(self._snr_header)
        self._snr_grid = QGridLayout()
        self._snr_grid.setHorizontalSpacing(20)
        self._snr_grid.setVerticalSpacing(4)
        self._snr_labels: dict[str, QLabel] = {}
        for col, stem in enumerate(("vocals", "drums", "bass", "other")):
            title = QLabel(stem.upper())
            title.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: 700; letter-spacing: 1px;")
            value = QLabel("—")
            value.setStyleSheet("color: #e8e6e3; font-size: 13px; font-weight: 700;")
            self._snr_grid.addWidget(title, 0, col, alignment=Qt.AlignmentFlag.AlignCenter)
            self._snr_grid.addWidget(value, 1, col, alignment=Qt.AlignmentFlag.AlignCenter)
            self._snr_labels[stem] = value
        snr_row = QHBoxLayout()
        snr_row.addStretch()
        snr_wrap = QWidget()
        snr_wrap.setLayout(self._snr_grid)
        snr_row.addWidget(snr_wrap)
        snr_row.addStretch()
        s_lay.addLayout(snr_row)
        s_lay.addStretch(1)
        self.sub_tabs.addTab(self._snr_page, "SNR")
        self.sub_tabs.setTabToolTip(2, "Signal-Rausch-Abstand pro getrenntem Stem.")

        layout.addWidget(self.sub_tabs)

    # ------------------------------------------------------------------
    def update_analysis(self, audio_track) -> None:
        """Reicht Analyse-Daten aus einem AudioTrack in die Sub-Tabs.

        Robust gegen fehlende Felder — alles optional.
        """
        if audio_track is None:
            self._energy_header.setText("Energie-Kurve — kein Track geladen")
            self._energy_plot.set_values(None)
            self._onsets_header.setText("Onsets (Kick / Snare / Hihat) — kein Track geladen")
            self._onsets_plot.set_onsets(None, None, None, 0.0)
            self._snr_header.setText("SNR pro Stem — kein Track geladen")
            for lbl in self._snr_labels.values():
                lbl.setText("—")
            return

        title = getattr(audio_track, "title", None) or f"Track #{getattr(audio_track, 'id', '?')}"
        duration = float(getattr(audio_track, "duration", 0.0) or 0.0)

        # ENERGIE
        energy = getattr(audio_track, "energy_curve", None)
        if energy:
            self._energy_header.setText(
                f"Energie-Kurve — {title}  ({len(energy)} Samples)"
            )
        else:
            self._energy_header.setText(f"Energie-Kurve — {title}  (nicht berechnet)")
        self._energy_plot.set_values(_first_col(energy))

        # ONSETS — onset_*_data hat Form [[time, strength], ...]
        # B-355 Fix: Die onset_*_data-Spalten liegen am Beatgrid, NICHT direkt
        # am AudioTrack (OnsetRhythmService persistiert sie in der beatgrids-
        # Tabelle, siehe services/onset_rhythm_service.py). Wenn ein AudioTrack
        # uebergeben wird (Controller-Pfad), zuerst auf dem Track selbst
        # nachsehen, sonst auf dessen beatgrid-Relation zurueckfallen.
        _onset_src = audio_track
        if getattr(audio_track, "onset_kick_data", None) is None:
            _beatgrid = getattr(audio_track, "beatgrid", None)
            if _beatgrid is not None:
                _onset_src = _beatgrid
        kick = _onset_times(getattr(_onset_src, "onset_kick_data", None))
        snare = _onset_times(getattr(_onset_src, "onset_snare_data", None))
        hihat = _onset_times(getattr(_onset_src, "onset_hihat_data", None))
        total = sum(len(x) for x in (kick, snare, hihat))
        if total > 0:
            self._onsets_header.setText(
                f"Onsets — {title}  (Kick {len(kick)} / Snare {len(snare)} / Hihat {len(hihat)})"
            )
        else:
            self._onsets_header.setText(f"Onsets — {title}  (nicht berechnet)")
        self._onsets_plot.set_onsets(kick, snare, hihat, duration)

        # SNR — aus acoustic_metadata (optionales JSON-Dict)
        snr_map = _extract_snr(getattr(audio_track, "acoustic_metadata", None))
        if snr_map:
            self._snr_header.setText(f"SNR pro Stem — {title}")
        else:
            self._snr_header.setText(f"SNR pro Stem — {title}  (nicht verfuegbar)")
        for stem, lbl in self._snr_labels.items():
            value = snr_map.get(stem)
            lbl.setText(f"{value:.1f} dB" if isinstance(value, (int, float)) else "—")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _first_col(data) -> list[float] | None:
    """Toleranter Reader: nimmt flache Listen ODER [[t, v], ...] Paare."""
    if not data:
        return None
    try:
        first = data[0]
    except (TypeError, IndexError):
        return None
    if isinstance(first, (list, tuple)) and len(first) >= 1:
        # Paare — nutze zweite Spalte falls vorhanden, sonst erste
        idx = 1 if len(first) >= 2 else 0
        return [float(row[idx]) for row in data if isinstance(row, (list, tuple))]
    return [float(v) for v in data]


def _onset_times(data) -> list[float]:
    """Extrahiert die erste Spalte (Zeitstempel) aus [[time, strength], ...]."""
    if not data:
        return []
    out: list[float] = []
    for row in data:
        if isinstance(row, (list, tuple)) and row:
            try:
                out.append(float(row[0]))
            except (TypeError, ValueError):
                continue
        else:
            try:
                out.append(float(row))
            except (TypeError, ValueError):
                continue
    return out


def _extract_snr(meta) -> dict[str, float]:
    """Zieht SNR-Werte pro Stem aus acoustic_metadata (Dict oder leer)."""
    if not isinstance(meta, dict):
        return {}
    snr = meta.get("snr") or meta.get("stem_snr") or {}
    if not isinstance(snr, dict):
        return {}
    out: dict[str, float] = {}
    for stem in ("vocals", "drums", "bass", "other"):
        val = snr.get(stem)
        if isinstance(val, (int, float)):
            out[stem] = float(val)
    return out
