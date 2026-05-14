"""Clip-Properties Inspector Panel fuer die Timeline.

Zeigt und editiert Eigenschaften des ausgewaehlten Clips:
Start, End, Duration, Brightness, Contrast, Crossfade.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from database import nullpool_session, TimelineEntry
from ui.theme import ACCENT, BG1, BG2, BG4, T1, T2, T3, T4

logger = logging.getLogger(__name__)

_db_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inspector_db")


class ClipInspectorPanel(QWidget):
    """Inspector-Panel fuer Clip-Eigenschaften, rechts neben der Timeline."""

    clip_property_changed = Signal(int, str, float)  # entry_id, field, value
    _entry_data_loaded = Signal(dict, int)
    _entry_load_failed = Signal()
    _property_write_done = Signal(int, str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        # T4.8: setMinimumWidth statt setFixedWidth — Panel darf in breiteren
        # Layouts wachsen, behaelt aber 220px Mindestbreite fuer Lesbarkeit.
        # SizePolicy bleibt MinimumExpanding-faehig.
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
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
        header.setStyleSheet(f"color: {ACCENT}; font-size: 9px;")
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
        self._no_selection_label = QLabel("Kein Clip\nausgewaehlt\nTimeline-Clip anklicken")
        self._no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_selection_label.setStyleSheet(f"color: {T4}; font-size: 11px; margin-top: 20px;")
        self._no_selection_label.setToolTip(
            "Der Inspector zeigt Eigenschaften des aktuell ausgewaehlten Timeline-Clips."
        )
        self._no_selection_label.setAccessibleName("Kein Timeline-Clip ausgewaehlt")
        layout.addWidget(self._no_selection_label)

        self._current_entry_id: int | None = None
        self._updating = False  # prevent feedback loop

        # M2-FIX: Debounce-Timer um DB-Spam bei gehaltener SpinBox zu vermeiden
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._flush_pending_change)
        self._pending_field: str | None = None
        self._pending_value: float = 0.0
        self._entry_data_loaded.connect(self._apply_entry_data)
        self._entry_load_failed.connect(lambda: self._set_fields_visible(False))
        self._property_write_done.connect(self.clip_property_changed.emit)

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
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(80)
        row.addWidget(lbl)
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setFixedHeight(22)
        spin.setToolTip(
            f"{label_text} fuer den ausgewaehlten Timeline-Clip bearbeiten. "
            "Aenderungen werden nach kurzer Pause gespeichert."
        )
        row.addWidget(spin)
        layout.addWidget(container)
        spin._row_container = container  # store ref for visibility toggle
        return spin

    def _set_fields_visible(self, visible: bool):
        """Zeigt/versteckt die Felder je nach Selektion."""
        for w in (self._type_label, self._media_label, self._duration_label):
            w.setVisible(visible)
        for spin in (self._start_spin, self._end_spin,
                     self._brightness_spin, self._contrast_spin, self._crossfade_spin):
            if hasattr(spin, '_row_container'):
                spin._row_container.setVisible(visible)
            else:
                spin.setVisible(visible)
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

        logger.debug("ClipInspector: loading entry_id=%s (%d clips selected)", entry_id, len(clip_data_list))

        # DB-Daten im Hintergrund laden, UI im Main-Thread aktualisieren
        num_clips = len(clip_data_list)

        def _fetch():
            try:
                with nullpool_session() as session:
                    entry = session.get(TimelineEntry, entry_id)
                    if not entry:
                        logger.warning("ClipInspector: entry_id=%s not found in DB", entry_id)
                        self._entry_load_failed.emit()
                        return
                    vals = {
                        "track": entry.track,
                        "media_id": entry.media_id,
                        "start_time": entry.start_time or 0.0,
                        "end_time": entry.end_time or 0.0,
                        "brightness": entry.brightness if entry.brightness is not None else 0.0,
                        "contrast": entry.contrast if entry.contrast is not None else 1.0,
                        "crossfade": entry.crossfade_duration if entry.crossfade_duration is not None else 0.0,
                    }
                self._entry_data_loaded.emit(vals, num_clips)
            except Exception as e:
                logger.warning("ClipInspector: DB-Fehler: %s", e)

        _db_pool.submit(_fetch)

    def _apply_entry_data(self, vals: dict, num_clips: int):
        """Aktualisiert UI-Felder im Main-Thread mit vorgeladenen DB-Daten."""
        self._updating = True
        try:
            self._type_label.setText(
                f"Typ: {'Audio' if vals['track'] == 'audio' else 'Video'}"
                + (f"  |  {num_clips} Clips" if num_clips > 1 else "")
            )
            self._media_label.setText(f"Media ID: {vals['media_id']}")
            self._start_spin.setValue(vals["start_time"])
            self._end_spin.setValue(vals["end_time"])
            duration = vals["end_time"] - vals["start_time"]
            self._duration_label.setText(f"Dauer: {duration:.2f}s")
            self._brightness_spin.setValue(vals["brightness"])
            self._contrast_spin.setValue(vals["contrast"])
            self._crossfade_spin.setValue(vals["crossfade"])
        finally:
            self._updating = False

    def _on_field_changed(self, field: str, value: float):
        """Spinbox-Aenderung → Debounced DB-Write (M2-FIX).

        Statt sofort bei jedem SpinBox-Event in die DB zu schreiben,
        wird ein 300ms Timer gestartet. Bei schnellem Scrollen wird
        nur der letzte Wert geschrieben.
        """
        if self._updating or self._current_entry_id is None:
            return

        self._pending_field = field
        self._pending_value = value
        self._debounce_timer.start()  # (Re-)Start: setzt Timer auf 300ms zurueck

        # Update duration label sofort (rein visuell, kein DB-Zugriff)
        if field in ("start_time", "end_time"):
            start = self._start_spin.value()
            end = self._end_spin.value()
            self._duration_label.setText(f"Dauer: {end - start:.2f}s")

    def _flush_pending_change(self):
        """M2-FIX: Debounced DB-Write — wird 300ms nach letzter SpinBox-Aenderung aufgerufen.

        DB-Schreibvorgang im Hintergrund-Thread, Signal-Emission im Main-Thread.
        """
        field = self._pending_field
        value = self._pending_value
        entry_id = self._current_entry_id

        if field is None or entry_id is None:
            return

        self._pending_field = None

        logger.debug("ClipInspector: entry_id=%s field=%s value=%s (debounced)", entry_id, field, value)

        def _write():
            try:
                with nullpool_session() as session:
                    entry = session.get(TimelineEntry, entry_id)
                    if not entry:
                        logger.warning("ClipInspector: entry_id=%s not found when writing field=%s", entry_id, field)
                        return
                    setattr(entry, field, round(value, 3))
                    session.commit()
                self._property_write_done.emit(entry_id, field, value)
            except Exception as e:
                logger.warning("ClipInspector: DB-Write Fehler: %s", e)

        _db_pool.submit(_write)
