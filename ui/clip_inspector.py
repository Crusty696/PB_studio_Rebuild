"""Clip-Properties Inspector Panel fuer die Timeline.

Zeigt und editiert Eigenschaften des ausgewaehlten Clips:
Start, End, Duration, Brightness, Contrast, Crossfade.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from database import nullpool_session, TimelineEntry
from ui.theme import ACCENT, BG1, BG2, BG4, T1, T2, T3, T4


class ClipInspectorPanel(QWidget):
    """Inspector-Panel fuer Clip-Eigenschaften, rechts neben der Timeline."""

    clip_property_changed = Signal(int, str, float)  # entry_id, field, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(
            f"QWidget {{ background-color: {BG1}; color: {T2}; }}"
            f"QLabel {{ font-size: 10px; color: {T3}; }}"
            f"QDoubleSpinBox {{ background: {BG2}; color: {T1}; border: 1px solid {BG4}; "
            f"  border-radius: 3px; padding: 2px 4px; font-size: 10px; }}"
            f"QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Header
        header = QLabel("CLIP INSPECTOR")
        header.setFont(QFont("Segoe UI Variable Text", 9, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {ACCENT}; letter-spacing: 2px; font-size: 9px;")
        layout.addWidget(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {BG4}; max-height: 1px;")
        layout.addWidget(sep)

        # Info labels (read-only)
        self._type_label = QLabel("Typ: --")
        self._type_label.setStyleSheet(f"font-size: 11px; color: {T2};")
        layout.addWidget(self._type_label)

        self._media_label = QLabel("Media: --")
        self._media_label.setStyleSheet(f"font-size: 10px; color: {T3};")
        self._media_label.setWordWrap(True)
        layout.addWidget(self._media_label)

        # Editable fields
        self._start_spin = self._add_spin_row(layout, "Start (s)", 0.0, 36000.0, 3, 0.1)
        self._end_spin = self._add_spin_row(layout, "Ende (s)", 0.0, 36000.0, 3, 0.1)
        self._duration_label = QLabel("Dauer: --")
        self._duration_label.setStyleSheet(f"font-size: 10px; color: {T3}; margin-bottom: 4px;")
        layout.addWidget(self._duration_label)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"background-color: {BG4}; max-height: 1px;")
        layout.addWidget(sep2)

        self._brightness_spin = self._add_spin_row(layout, "Helligkeit", -1.0, 1.0, 2, 0.05)
        self._contrast_spin = self._add_spin_row(layout, "Kontrast", 0.0, 3.0, 2, 0.1)
        self._crossfade_spin = self._add_spin_row(layout, "Crossfade (s)", 0.0, 10.0, 2, 0.1)

        layout.addStretch()

        # No-selection placeholder
        self._no_selection_label = QLabel("Kein Clip\nausgewaehlt")
        self._no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_selection_label.setStyleSheet(f"color: {T4}; font-size: 11px; margin-top: 20px;")
        layout.addWidget(self._no_selection_label)

        self._current_entry_id: int | None = None
        self._updating = False  # prevent feedback loop

        # Connect spinbox changes
        self._start_spin.valueChanged.connect(lambda v: self._on_field_changed("start_time", v))
        self._end_spin.valueChanged.connect(lambda v: self._on_field_changed("end_time", v))
        self._brightness_spin.valueChanged.connect(lambda v: self._on_field_changed("brightness", v))
        self._contrast_spin.valueChanged.connect(lambda v: self._on_field_changed("contrast", v))
        self._crossfade_spin.valueChanged.connect(lambda v: self._on_field_changed("crossfade_duration", v))

        self._set_fields_visible(False)

    def _add_spin_row(self, layout: QVBoxLayout, label_text: str,
                      min_val: float, max_val: float, decimals: int,
                      step: float) -> QDoubleSpinBox:
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setFixedHeight(22)
        row.addWidget(spin)
        layout.addLayout(row)
        return spin

    def _set_fields_visible(self, visible: bool):
        """Zeigt/versteckt die Felder je nach Selektion."""
        for w in (self._type_label, self._media_label, self._duration_label):
            w.setVisible(visible)
        for spin in (self._start_spin, self._end_spin,
                     self._brightness_spin, self._contrast_spin, self._crossfade_spin):
            spin.setVisible(visible)
            spin.parent().setVisible(visible) if spin.parent() else None
        self._no_selection_label.setVisible(not visible)

    def update_from_selection(self, clip_data_list: list[dict]):
        """Wird von timeline.selection_changed aufgerufen."""
        if not clip_data_list:
            self._current_entry_id = None
            self._set_fields_visible(False)
            return

        # Zeige den ersten ausgewaehlten Clip
        data = clip_data_list[0]
        entry_id = data["entry_id"]
        self._current_entry_id = entry_id
        self._set_fields_visible(True)

        # DB-Daten laden
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                self._set_fields_visible(False)
                return

            self._updating = True

            self._type_label.setText(
                f"Typ: {'Audio' if entry.track == 'audio' else 'Video'}"
                + (f"  |  {len(clip_data_list)} Clips" if len(clip_data_list) > 1 else "")
            )
            self._media_label.setText(f"Media ID: {entry.media_id}")

            self._start_spin.setValue(entry.start_time or 0.0)
            self._end_spin.setValue(entry.end_time or 0.0)

            duration = (entry.end_time - entry.start_time) if entry.end_time else 0.0
            self._duration_label.setText(f"Dauer: {duration:.2f}s")

            self._brightness_spin.setValue(entry.brightness if entry.brightness is not None else 0.0)
            self._contrast_spin.setValue(entry.contrast if entry.contrast is not None else 1.0)
            self._crossfade_spin.setValue(entry.crossfade_duration if entry.crossfade_duration is not None else 0.0)

            self._updating = False

    def _on_field_changed(self, field: str, value: float):
        """Spinbox-Aenderung → DB schreiben."""
        if self._updating or self._current_entry_id is None:
            return

        with nullpool_session() as session:
            entry = session.get(TimelineEntry, self._current_entry_id)
            if not entry:
                return
            setattr(entry, field, round(value, 3))
            session.commit()

        # Update duration label
        if field in ("start_time", "end_time"):
            start = self._start_spin.value()
            end = self._end_spin.value()
            self._duration_label.setText(f"Dauer: {end - start:.2f}s")

        self.clip_property_changed.emit(self._current_entry_id, field, value)
