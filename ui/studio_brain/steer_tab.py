"""SteerTab — Studio Brain "Steer" tab (T11.3).

Design §3 (Structure / Memory / Agent) + Feasibility §7 condition 7:
the Steer tab is the hand-steering surface for the pacing agent. Users
pick an audio track + a weights profile, edit the profile YAML in an
external editor (deliberately NOT via in-app sliders — see Feasibility
§7-7), and curate per-clip overrides (pins / boosts / excludes) before
firing a run-scoped override.

T11.3 scope (this file):
  - _TrackSelector      QComboBox of ``audio_tracks`` rows.
                         Emits ``trackChanged(track_id)``.
  - _ProfilePicker      QComboBox of ``config/pacing_weights/*.yaml`` +
                         "Edit profile" QPushButton that shells out via
                         ``QDesktopServices.openUrl`` to the OS editor.
                         Emits ``profileChanged(name, path)``.
  - _OverridesLists     Three QListWidgets side-by-side: Pins / Boosts /
                         Excludes. Pins are a new in-memory concept (clip-
                         level anchors, numeric scene_id entry via
                         ``QInputDialog.getInt``); Boosts + Excludes mirror
                         the process-wide ``SteerOverrideQueue`` (from
                         T10.2e) and can only be removed from this tab
                         (adds come from the Structure tab's right-click
                         menu). DB persistence for pins is a P11+ concern.
  - _RunBar             "Run with these settings" button + transient status
                         label. Clicking fires ``runRequested(snapshot_dict)``
                         (signal-only — the pacing-agent integration lives
                         downstream) and shows a toast cleared after 5s.
  - SteerTab            Glue widget: owns the BrainService + queue, rebuilds
                         the list views on ``pendingChanged``, exposes
                         ``current_snapshot()`` for introspection by tests
                         and the downstream pacing-agent adapter.

Public signals:
  - ``runRequested(dict)``       — carries the full steer_snapshot.
  - ``trackChanged(int)``        — fires on audio-track combobox change.
  - ``profileChanged(str, str)`` — (name, absolute-path) on profile change.

Scope boundaries (T11.3):
  - Pacing-agent wiring is NOT implemented here. ``runRequested`` is the
    producer end; the consumer (pacing agent) ships later. See the plan's
    T11.3 acceptance criteria: "State archived into
    mem_pacing_run.steer_snapshot after run" is the pacing-agent layer's
    responsibility.
  - Pin persistence is in-memory only. ``current_snapshot()`` includes
    every pin the user added during the session; a DB-backed store for
    pins arrives with P11+.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import OperationalError

from services.brain import BrainService
from services.steer_override_queue import (
    PendingOverride,
    SteerOverrideQueue,
    get_default_queue,
)

logger = logging.getLogger(__name__)


# ── Layout / style constants ──────────────────────────────────────────────────

_STATUS_TOAST_MS = 5000
_DEFAULT_PROFILE_NAME = "default"

_SELECTOR_STYLE = (
    "QComboBox,QPushButton{background:#1a2030;color:#e5e7eb;"
    "border:1px solid rgba(255,255,255,0.1);border-radius:4px;"
    "padding:3px 8px;font-size:10px;}"
    "QPushButton:hover{background:#202838;}"
    "QPushButton:disabled{color:#6b7280;background:#151a23;}"
    "QLabel{color:#9ca3af;font-size:10px;}"
)

_LIST_STYLE = (
    "QListWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
    "border:1px solid rgba(255,255,255,0.06);border-radius:4px;}"
)

_HEADER_LABEL_STYLE = (
    "color:#e5e7eb;font-size:10px;font-weight:600;padding:4px 0px;"
)

_STATUS_OK_STYLE = (
    "color:#7ec77d;font-size:10px;padding:4px 8px;"
    "background:#132018;border:1px solid rgba(126,199,125,0.25);"
    "border-radius:4px;"
)

_STATUS_ERR_STYLE = (
    "color:#f5a97b;font-size:10px;padding:4px 8px;"
    "background:#2a1c0e;border:1px solid rgba(245,167,123,0.35);"
    "border-radius:4px;"
)

_RUN_BUTTON_TOAST = "Run in Warteschlange — wartet auf den Agenten."


# ── Formatting helpers ───────────────────────────────────────────────────────


def _format_track_option(track: dict[str, Any]) -> str:
    """Compact combobox label for an audio-track row."""
    basename = track.get("file_basename") or "—"
    bpm = track.get("bpm")
    duration = track.get("duration_sec")
    bits: list[str] = [str(basename)]
    if bpm is not None:
        try:
            bits.append(f"{float(bpm):.1f} BPM")
        except (TypeError, ValueError):
            pass
    if duration is not None:
        try:
            total = int(float(duration))
            m, s = divmod(max(0, total), 60)
            bits.append(f"{m}:{s:02d}")
        except (TypeError, ValueError):
            pass
    return "  ·  ".join(bits)


# ── _TrackSelector ───────────────────────────────────────────────────────────


class _TrackSelector(QWidget):
    """Top strip: "Audio track:" label + QComboBox populated from
    ``BrainService.list_audio_tracks()``."""

    trackChanged = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_SELECTOR_STYLE)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        hl.addWidget(QLabel("Audio-Track:"))
        self._combo = QComboBox(self)
        self._combo.setMinimumWidth(320)
        self._combo.setToolTip(
            "Auf welchem Audio-Track soll der naechste Run laufen? "
            "Die Liste zeigt die in der Datenbank registrierten Tracks."
        )
        self._combo.currentIndexChanged.connect(self._emit_current)
        hl.addWidget(self._combo, stretch=1)
        hl.addStretch()

        self._tracks: list[dict[str, Any]] = []

    def set_tracks(self, tracks: list[dict[str, Any]]) -> None:
        self._tracks = [dict(t) for t in tracks]
        previous = self.current_track_id()

        self._combo.blockSignals(True)
        try:
            self._combo.clear()
            if not self._tracks:
                self._combo.addItem("(keine Audio-Tracks)", userData=None)
                self._combo.setEnabled(False)
            else:
                self._combo.setEnabled(True)
                for track in self._tracks:
                    self._combo.addItem(
                        _format_track_option(track), userData=int(track["id"])
                    )
                if previous is not None:
                    restored = False
                    for i in range(self._combo.count()):
                        if self._combo.itemData(i) == previous:
                            self._combo.setCurrentIndex(i)
                            restored = True
                            break
                    if not restored:
                        self._combo.setCurrentIndex(0)
                else:
                    self._combo.setCurrentIndex(0)
        finally:
            self._combo.blockSignals(False)

        # Emit once after population so the parent tab's enable-Run logic
        # sees the current selection.
        self._emit_current()

    def current_track_id(self) -> Optional[int]:
        data = self._combo.currentData()
        if data is None:
            return None
        try:
            return int(data)
        except (TypeError, ValueError):
            return None

    def item_count(self) -> int:
        # Only counts "real" rows — the placeholder "(no audio tracks)"
        # entry isn't a track, so tests can assert cleanly.
        return len(self._tracks)

    def _emit_current(self, *_args: Any) -> None:
        tid = self.current_track_id()
        if tid is not None:
            self.trackChanged.emit(tid)


# ── _ProfilePicker ───────────────────────────────────────────────────────────


class _ProfilePicker(QWidget):
    """Strip: profile QComboBox + Edit-profile QPushButton.

    The "Edit profile" button opens the currently-selected YAML via
    ``QDesktopServices.openUrl`` — the OS decides which editor handles
    ``.yaml`` files. Per the plan brief (Feasibility §7-7) this is a
    deliberate choice: weights are tuned with a text editor, not in-app
    sliders.
    """

    profileChanged = Signal(str, str)  # (name, absolute_path)
    editRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_SELECTOR_STYLE)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        hl.addWidget(QLabel("Gewichtsprofil:"))
        self._combo = QComboBox(self)
        self._combo.setMinimumWidth(200)
        self._combo.setToolTip(
            "Gewichte der 13 Pacing-Terme. default = neutral, "
            "psytrance/house = Genre-spezifisch, dj_mix_auto = automatisch "
            "Mid-Run wechseln bei DJ-Mixen."
        )
        self._combo.currentIndexChanged.connect(self._emit_current)
        hl.addWidget(self._combo, stretch=1)

        self._edit_btn = QPushButton("Profil bearbeiten")
        self._edit_btn.setToolTip(
            "Oeffnet die YAML-Datei des gewaehlten Profils im "
            "System-Editor. Aenderungen werden beim naechsten Run gelesen. "
            "(Kein In-App-Slider per Design — YAML verhindert Versehen.)"
        )
        self._edit_btn.clicked.connect(self.editRequested)
        self._edit_btn.setEnabled(False)
        hl.addWidget(self._edit_btn)
        hl.addStretch()

        self._profiles: list[dict[str, Any]] = []

    def set_profiles(self, profiles: list[dict[str, Any]]) -> None:
        self._profiles = [dict(p) for p in profiles]
        previous_name = self.current_profile_name()

        self._combo.blockSignals(True)
        try:
            self._combo.clear()
            if not self._profiles:
                self._combo.addItem("(keine Profile)", userData=None)
                self._combo.setEnabled(False)
                self._edit_btn.setEnabled(False)
            else:
                self._combo.setEnabled(True)
                self._edit_btn.setEnabled(True)
                for profile in self._profiles:
                    self._combo.addItem(
                        str(profile["name"]), userData=str(profile["path"])
                    )
                # Restore previous selection if present; otherwise default to
                # "default" if it's in the list, else index 0.
                idx = -1
                if previous_name is not None:
                    for i in range(self._combo.count()):
                        if self._combo.itemText(i) == previous_name:
                            idx = i
                            break
                if idx < 0:
                    for i in range(self._combo.count()):
                        if self._combo.itemText(i) == _DEFAULT_PROFILE_NAME:
                            idx = i
                            break
                if idx < 0:
                    idx = 0
                self._combo.setCurrentIndex(idx)
        finally:
            self._combo.blockSignals(False)

        self._emit_current()

    def current_profile_name(self) -> Optional[str]:
        if not self._profiles:
            return None
        name = self._combo.currentText()
        return name if name else None

    def current_profile_path(self) -> Optional[str]:
        data = self._combo.currentData()
        return str(data) if data else None

    def item_count(self) -> int:
        return len(self._profiles)

    def _emit_current(self, *_args: Any) -> None:
        name = self.current_profile_name()
        path = self.current_profile_path()
        if name and path:
            self.profileChanged.emit(name, path)


# ── _OverridesLists ──────────────────────────────────────────────────────────


class _OverridesLists(QFrame):
    """Three-column strip: Pins / Boosts / Excludes.

    - Pins: in-memory list of scene_ids. ``+ add`` prompts via
      ``QInputDialog.getInt`` for a numeric scene_id (the "add by drag from
      timeline" UX is a P12+ concern).
    - Boosts / Excludes: read-only projection of ``SteerOverrideQueue``.
      The parent SteerTab calls ``set_queue_items()`` whenever the queue
      emits ``pendingChanged``. The user can only *remove* entries from
      here; adds come from the Structure tab's right-click menu.
    """

    pinAddRequested = Signal()
    pinRemoveRequested = Signal(int)   # scene_id
    boostRemoveRequested = Signal(int)  # scene_id
    excludeRemoveRequested = Signal(int)  # scene_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # Pins column.
        pins_col = QWidget(self)
        pins_layout = QVBoxLayout(pins_col)
        pins_layout.setContentsMargins(0, 0, 0, 0)
        pins_layout.setSpacing(2)
        pins_header = QLabel("Pins")
        pins_header.setStyleSheet(_HEADER_LABEL_STYLE)
        _pins_tooltip = (
            "Feste Clip-Anker: diese Szenen MUESSEN im Run vorkommen. "
            "Der Agent hat keine Wahl."
        )
        pins_header.setToolTip(_pins_tooltip)
        pins_layout.addWidget(pins_header)
        self._pins_list = QListWidget(pins_col)
        self._pins_list.setStyleSheet(_LIST_STYLE)
        self._pins_list.setToolTip(_pins_tooltip)
        pins_layout.addWidget(self._pins_list, stretch=1)
        pins_btn_row = QHBoxLayout()
        pins_btn_row.setContentsMargins(0, 0, 0, 0)
        pins_btn_row.setSpacing(4)
        self._pin_add_btn = QPushButton("+ Pin hinzufügen")
        self._pin_add_btn.setStyleSheet(_SELECTOR_STYLE)
        self._pin_add_btn.setToolTip(
            "Szenen-ID eingeben und zur Pins-Liste hinzufuegen."
        )
        self._pin_add_btn.clicked.connect(self.pinAddRequested)
        pins_btn_row.addWidget(self._pin_add_btn)
        self._pin_remove_btn = QPushButton("− Entfernen")
        self._pin_remove_btn.setStyleSheet(_SELECTOR_STYLE)
        self._pin_remove_btn.setToolTip(
            "Ausgewaehlten Pin aus der Liste nehmen."
        )
        self._pin_remove_btn.clicked.connect(self._on_pin_remove_clicked)
        pins_btn_row.addWidget(self._pin_remove_btn)
        pins_btn_row.addStretch()
        pins_layout.addLayout(pins_btn_row)
        outer.addWidget(pins_col, stretch=1)

        # Boosts column.
        boosts_col = QWidget(self)
        boosts_layout = QVBoxLayout(boosts_col)
        boosts_layout.setContentsMargins(0, 0, 0, 0)
        boosts_layout.setSpacing(2)
        boosts_header = QLabel("Boosts")
        boosts_header.setStyleSheet(_HEADER_LABEL_STYLE)
        _boosts_tooltip = (
            "Empfehlungen: diese Szenen werden BEVORZUGT (nicht erzwungen). "
            "Quelle steht in Klammern — aus welchem Tab der Boost kam."
        )
        boosts_header.setToolTip(_boosts_tooltip)
        boosts_layout.addWidget(boosts_header)
        self._boosts_list = QListWidget(boosts_col)
        self._boosts_list.setStyleSheet(_LIST_STYLE)
        self._boosts_list.setToolTip(_boosts_tooltip)
        boosts_layout.addWidget(self._boosts_list, stretch=1)
        boosts_btn_row = QHBoxLayout()
        boosts_btn_row.setContentsMargins(0, 0, 0, 0)
        boosts_btn_row.setSpacing(4)
        self._boost_remove_btn = QPushButton("− Entfernen")
        self._boost_remove_btn.setStyleSheet(_SELECTOR_STYLE)
        self._boost_remove_btn.setToolTip(
            "Ausgewaehlten Boost aus der Liste nehmen."
        )
        self._boost_remove_btn.clicked.connect(self._on_boost_remove_clicked)
        boosts_btn_row.addWidget(self._boost_remove_btn)
        boosts_btn_row.addStretch()
        boosts_layout.addLayout(boosts_btn_row)
        outer.addWidget(boosts_col, stretch=1)

        # Excludes column.
        excludes_col = QWidget(self)
        excludes_layout = QVBoxLayout(excludes_col)
        excludes_layout.setContentsMargins(0, 0, 0, 0)
        excludes_layout.setSpacing(2)
        excludes_header = QLabel("Excludes")
        excludes_header.setStyleSheet(_HEADER_LABEL_STYLE)
        _excludes_tooltip = (
            "Blockierungen: diese Szenen werden AUSGESCHLOSSEN. "
            "Der Agent nimmt sie auf keinen Fall."
        )
        excludes_header.setToolTip(_excludes_tooltip)
        excludes_layout.addWidget(excludes_header)
        self._excludes_list = QListWidget(excludes_col)
        self._excludes_list.setStyleSheet(_LIST_STYLE)
        self._excludes_list.setToolTip(_excludes_tooltip)
        excludes_layout.addWidget(self._excludes_list, stretch=1)
        excludes_btn_row = QHBoxLayout()
        excludes_btn_row.setContentsMargins(0, 0, 0, 0)
        excludes_btn_row.setSpacing(4)
        self._exclude_remove_btn = QPushButton("− Entfernen")
        self._exclude_remove_btn.setStyleSheet(_SELECTOR_STYLE)
        self._exclude_remove_btn.setToolTip(
            "Ausgewaehlten Exclude aus der Liste nehmen."
        )
        self._exclude_remove_btn.clicked.connect(self._on_exclude_remove_clicked)
        excludes_btn_row.addWidget(self._exclude_remove_btn)
        excludes_btn_row.addStretch()
        excludes_layout.addLayout(excludes_btn_row)
        outer.addWidget(excludes_col, stretch=1)

        # In-memory model for pins (sorted, deduplicated).
        self._pin_scene_ids: list[int] = []

    # ── Pins ───────────────────────────────────────────────────────────────
    def add_pin(self, scene_id: int) -> bool:
        """Add a pin in-memory. Returns True on insert, False on duplicate."""
        try:
            sid = int(scene_id)
        except (TypeError, ValueError):
            return False
        if sid in self._pin_scene_ids:
            return False
        self._pin_scene_ids.append(sid)
        self._rebuild_pins_list()
        return True

    def remove_pin(self, scene_id: int) -> bool:
        try:
            sid = int(scene_id)
        except (TypeError, ValueError):
            return False
        if sid not in self._pin_scene_ids:
            return False
        self._pin_scene_ids.remove(sid)
        self._rebuild_pins_list()
        return True

    def pin_scene_ids(self) -> list[int]:
        return list(self._pin_scene_ids)

    def _rebuild_pins_list(self) -> None:
        self._pins_list.clear()
        for sid in self._pin_scene_ids:
            item = QListWidgetItem(f"Szene #{sid}", self._pins_list)
            item.setData(Qt.ItemDataRole.UserRole, int(sid))

    def _selected_scene_id(self, list_widget: QListWidget) -> Optional[int]:
        item = list_widget.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return None

    def _on_pin_remove_clicked(self) -> None:
        sid = self._selected_scene_id(self._pins_list)
        if sid is not None:
            self.pinRemoveRequested.emit(int(sid))

    def _on_boost_remove_clicked(self) -> None:
        sid = self._selected_scene_id(self._boosts_list)
        if sid is not None:
            self.boostRemoveRequested.emit(int(sid))

    def _on_exclude_remove_clicked(self) -> None:
        sid = self._selected_scene_id(self._excludes_list)
        if sid is not None:
            self.excludeRemoveRequested.emit(int(sid))

    # ── Boosts / Excludes (read from queue) ────────────────────────────────
    def set_queue_items(self, items: list[PendingOverride]) -> None:
        """Rebuild the Boosts + Excludes lists from a queue snapshot."""
        self._boosts_list.clear()
        self._excludes_list.clear()
        for entry in items:
            label = f"Szene #{entry.scene_id}  (Quelle={entry.source})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, int(entry.scene_id))
            if entry.action == "boost":
                self._boosts_list.addItem(item)
            elif entry.action == "exclude":
                self._excludes_list.addItem(item)
            # Any other action is silently ignored — the queue's Action
            # Literal today is just boost/exclude, but future-proof.

    def boost_count(self) -> int:
        return self._boosts_list.count()

    def exclude_count(self) -> int:
        return self._excludes_list.count()

    def pin_count(self) -> int:
        return self._pins_list.count()

    def select_first_boost(self) -> None:
        if self._boosts_list.count() > 0:
            self._boosts_list.setCurrentRow(0)

    def select_first_exclude(self) -> None:
        if self._excludes_list.count() > 0:
            self._excludes_list.setCurrentRow(0)

    def select_first_pin(self) -> None:
        if self._pins_list.count() > 0:
            self._pins_list.setCurrentRow(0)


# ── _RunBar ──────────────────────────────────────────────────────────────────


class _RunBar(QWidget):
    """Bottom strip: stretch + Run button + status toast."""

    runClicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_SELECTOR_STYLE)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        self._status = QLabel("")
        self._status.setVisible(False)
        hl.addWidget(self._status, stretch=1)

        hl.addStretch()

        self._run_btn = QPushButton("Mit diesen Einstellungen starten")
        self._run_btn.setToolTip(
            "Sendet das Signal 'runRequested' mit dem aktuellen "
            "Steer-Snapshot (Track + Profil + Pins + Boosts + Excludes). "
            "Der Pacing-Agent wird dann mit diesen Run-Overrides starten."
        )
        self._run_btn.clicked.connect(self.runClicked)
        self._run_btn.setEnabled(False)
        hl.addWidget(self._run_btn)

    def set_run_enabled(self, enabled: bool) -> None:
        self._run_btn.setEnabled(bool(enabled))

    def is_run_enabled(self) -> bool:
        return self._run_btn.isEnabled()

    def set_status_ok(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(_STATUS_OK_STYLE)
        self._status.setVisible(True)

    def set_status_error(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(_STATUS_ERR_STYLE)
        self._status.setVisible(True)

    def clear_status(self) -> None:
        self._status.setText("")
        self._status.setVisible(False)

    def status_text(self) -> str:
        return self._status.text()

    def status_visible(self) -> bool:
        """Return whether the status label is in its "shown" state.

        Uses ``isVisibleTo(None)`` semantics via ``not isHidden()`` — this
        reflects the widget's own visibility flag without requiring the
        parent chain to be shown. Tests that construct the tab offscreen
        (never ``show()``-ing the QMainWindow) still get a truthful answer
        about whether the code path set the status.
        """
        return not self._status.isHidden()


# ── SteerTab ─────────────────────────────────────────────────────────────────


class SteerTab(QWidget):
    """Top-level widget placed at tab index 3 of StudioBrainWindow (T11.3)."""

    runRequested = Signal(dict)
    trackChanged = Signal(int)
    profileChanged = Signal(str, str)

    def __init__(
        self,
        brain_service: BrainService,
        override_queue: Optional[SteerOverrideQueue] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service
        self._override_queue: SteerOverrideQueue = (
            override_queue if override_queue is not None else get_default_queue()
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self._track_selector = _TrackSelector(self)
        self._track_selector.trackChanged.connect(self._on_track_changed)
        outer.addWidget(self._track_selector)

        self._profile_picker = _ProfilePicker(self)
        self._profile_picker.profileChanged.connect(self._on_profile_changed)
        self._profile_picker.editRequested.connect(self._on_edit_profile)
        outer.addWidget(self._profile_picker)

        self._overrides = _OverridesLists(self)
        self._overrides.pinAddRequested.connect(self._on_pin_add)
        self._overrides.pinRemoveRequested.connect(self._on_pin_remove)
        self._overrides.boostRemoveRequested.connect(self._on_boost_remove)
        self._overrides.excludeRemoveRequested.connect(self._on_exclude_remove)
        outer.addWidget(self._overrides, stretch=1)

        self._run_bar = _RunBar(self)
        self._run_bar.runClicked.connect(self._on_run_clicked)
        outer.addWidget(self._run_bar)

        # Subscribe to the shared queue so list projections stay fresh even
        # when the Structure tab (a different widget) pushes new entries.
        self._override_queue.pendingChanged.connect(self._refresh_queue_projection)

        # Transient status-toast timer — non-periodic; restarted on each run.
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(_STATUS_TOAST_MS)
        self._status_timer.timeout.connect(self._run_bar.clear_status)

        # Initial render.
        self.refresh()

    # ── Public API ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Invalidate the BrainService cache and reload lists + queue.

        Note: the pin list is session-scoped and NOT cleared by refresh —
        pins persist until the user explicitly removes them or restarts the
        app (in-memory by design, per T11.3 scope).
        """
        self._svc.invalidate()

        tracks: list[dict[str, Any]] = self._safe_call(
            self._svc.list_audio_tracks, default=[]
        )
        self._track_selector.set_tracks(tracks)

        profiles: list[dict[str, Any]] = self._safe_call(
            self._svc.list_weights_profiles, default=[]
        )
        self._profile_picker.set_profiles(profiles)

        self._refresh_queue_projection()
        self._update_run_enabled()

    def current_snapshot(self) -> dict[str, Any]:
        """Assemble the dict that would be emitted on "Run with these
        settings". Shape is intentionally loose — the downstream pacing-agent
        adapter is the only reader today.
        """
        track_id = self._track_selector.current_track_id()
        profile_name = self._profile_picker.current_profile_name() or ""

        boosts: list[int] = []
        excludes: list[int] = []
        for entry in self._override_queue.list():
            if entry.action == "boost":
                boosts.append(int(entry.scene_id))
            elif entry.action == "exclude":
                excludes.append(int(entry.scene_id))

        return {
            "audio_track_id": int(track_id) if track_id is not None else None,
            "weights_profile": profile_name,
            "pins": list(self._overrides.pin_scene_ids()),
            "boosts": boosts,
            "excludes": excludes,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Slot handlers ──────────────────────────────────────────────────────
    def _on_track_changed(self, track_id: int) -> None:
        try:
            tid = int(track_id)
        except (TypeError, ValueError):
            return
        self.trackChanged.emit(tid)
        self._update_run_enabled()

    def _on_profile_changed(self, name: str, path: str) -> None:
        self.profileChanged.emit(str(name), str(path))

    def _on_edit_profile(self) -> None:
        path = self._profile_picker.current_profile_path()
        if not path:
            self._run_bar.set_status_error("Kein Profil ausgewählt.")
            self._status_timer.start()
            return
        url = QUrl.fromLocalFile(str(path))
        try:
            QDesktopServices.openUrl(url)
        except Exception as exc:  # noqa: BLE001 — defensive on the OS hand-off
            logger.warning("SteerTab: openUrl failed for %s: %s", path, exc)
            self._run_bar.set_status_error(
                f"Editor konnte nicht geöffnet werden: {exc}"
            )
            self._status_timer.start()

    def _on_pin_add(self) -> None:
        """Prompt the user for a scene_id via ``QInputDialog.getInt``.

        The "add-by-drag from timeline" UX is a P12+ concern; for T11.3 we
        expose the simplest path that still lets the user curate pins by
        hand.
        """
        # B-254: PySide6 QInputDialog.getInt akzeptiert KEINE keyword-args
        # 'min'/'max' (war PyQt5-Pattern). Korrekte PySide6-Signatur:
        #   getInt(parent, title, label, value=0, minValue=..., maxValue=..., step=1, flags=...)
        # Positional uebergeben ist robust gegen Versionsunterschiede.
        scene_id, ok = QInputDialog.getInt(
            self,
            "Pin hinzufügen",
            "Szenen-ID:",
            1,           # value
            0,           # minValue
            10_000_000,  # maxValue
        )
        if not ok:
            return
        self._overrides.add_pin(int(scene_id))

    def _on_pin_remove(self, scene_id: int) -> None:
        self._overrides.remove_pin(int(scene_id))

    def _on_boost_remove(self, scene_id: int) -> None:
        self._override_queue.remove(int(scene_id))

    def _on_exclude_remove(self, scene_id: int) -> None:
        self._override_queue.remove(int(scene_id))

    def _on_run_clicked(self) -> None:
        snapshot = self.current_snapshot()
        self.runRequested.emit(snapshot)
        self._run_bar.set_status_ok(_RUN_BUTTON_TOAST)
        self._status_timer.start()

    # ── Internal ───────────────────────────────────────────────────────────
    def _refresh_queue_projection(self) -> None:
        try:
            items = self._override_queue.list()
        except Exception as exc:  # noqa: BLE001 — defensive
            logger.warning("SteerTab: queue.list() failed: %s", exc)
            items = []
        self._overrides.set_queue_items(items)

    def _update_run_enabled(self) -> None:
        """Run is only meaningful once the user has picked an audio track.

        Flagged as obvious UX in the T11.3 scope brief: an empty track
        selection has no run target, so the button is disabled.
        """
        has_track = self._track_selector.current_track_id() is not None
        self._run_bar.set_run_enabled(bool(has_track))

    @staticmethod
    def _safe_call(fn: Callable[[], T], default: T) -> T:
        try:
            return fn()
        except OperationalError as exc:
            logger.warning("SteerTab: read call failed: %s", exc)
            return default
