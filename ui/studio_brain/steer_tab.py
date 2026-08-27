"""SteerTab — Studio Brain "Steer" tab (T11.3).

Design §3 (Structure / Memory / Agent) + Feasibility §7 condition 7:
the Steer tab is the hand-steering surface for the pacing agent. Users
pick an audio track and curate per-clip overrides (boosts / excludes)
before firing a run-scoped override.

Brain-Bereinigung 2026-08-27 (User-Entscheidung, Scope "Nur Totes +
Inaktives"): Der Gewichtsprofil-Picker (``_ProfilePicker``) und die
Pins-Spalte wurden entfernt. Beide waren Placebo — der Run-Dispatch in
``main._on_brain_run_requested`` hat ``weights_profile`` und ``pins``
nie ausgewertet (dort selbst so dokumentiert), und es gab keinerlei
Backend-Consumer. Boosts/Excludes bleiben: ihr Consumer existiert in
``services/pacing_service.py`` (T1.3/USE-004) hinter dem
Studio-Brain-Flag.

Structure (this file):
  - _TrackSelector      QComboBox of ``audio_tracks`` rows.
                         Emits ``trackChanged(track_id)``.
  - _OverridesLists     Two QListWidgets side-by-side: Boosts /
                         Excludes. They mirror the process-wide
                         ``SteerOverrideQueue`` (from T10.2e) and can only
                         be removed from this tab (adds come from the
                         Structure tab's right-click menu).
  - _RunBar             "Run with these settings" button + transient status
                         label. Clicking fires ``runRequested(snapshot_dict)``
                         and shows a toast cleared after 5s.
  - SteerTab            Glue widget: owns the BrainService + queue, rebuilds
                         the list views on ``pendingChanged``, exposes
                         ``current_snapshot()`` for introspection by tests
                         and the downstream pacing-agent adapter.

Public signals:
  - ``runRequested(dict)``       — carries the full steer_snapshot.
  - ``trackChanged(int)``        — fires on audio-track combobox change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
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

_SELECTOR_STYLE = (
    "QComboBox,QPushButton{background:#1a2030;color:#e5e7eb;"
    "border:1px solid rgba(255,255,255,0.1);border-radius:4px;"
    "padding:3px 8px;font-size:10px;}"
    "QPushButton:hover{background:#202838;}"
    "QPushButton:disabled{color:#98a2b1;background:#151a23;}"
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

_RUN_BUTTON_TOAST = "Auto-Edit-Task gestartet — Fortschritt im Tasks-Panel."


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


# ── _OverridesLists ──────────────────────────────────────────────────────────


class _OverridesLists(QFrame):
    """Two-column strip: Boosts / Excludes.

    Read-only projection of ``SteerOverrideQueue``. The parent SteerTab
    calls ``set_queue_items()`` whenever the queue emits
    ``pendingChanged``. The user can only *remove* entries from here;
    adds come from the Structure tab's right-click menu.

    Brain-Bereinigung 2026-08-27: Pins-Spalte entfernt — Pins waren rein
    in-memory und wurden vom Run-Dispatch nie ausgewertet.
    """

    boostRemoveRequested = Signal(int)  # scene_id
    excludeRemoveRequested = Signal(int)  # scene_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

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

    def _selected_scene_id(self, list_widget: QListWidget) -> Optional[int]:
        item = list_widget.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return None

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

    def select_first_boost(self) -> None:
        if self._boosts_list.count() > 0:
            self._boosts_list.setCurrentRow(0)

    def select_first_exclude(self) -> None:
        if self._excludes_list.count() > 0:
            self._excludes_list.setCurrentRow(0)


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
            "Steer-Snapshot (Track + Boosts + Excludes) und startet einen "
            "Auto-Edit-Task. Boosts/Excludes wirken nur bei aktivierter "
            "Studio-Brain-Pipeline (Schnitt > Pacing & Anker)."
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

        self._overrides = _OverridesLists(self)
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
        """Invalidate the BrainService cache and reload lists + queue."""
        self._svc.invalidate()

        tracks: list[dict[str, Any]] = self._safe_call(
            self._svc.list_audio_tracks, default=[]
        )
        self._track_selector.set_tracks(tracks)

        self._refresh_queue_projection()
        self._update_run_enabled()

    def current_snapshot(self) -> dict[str, Any]:
        """Assemble the dict that would be emitted on "Run with these
        settings". Shape is intentionally loose — the downstream pacing-agent
        adapter is the only reader today.
        """
        track_id = self._track_selector.current_track_id()

        boosts: list[int] = []
        excludes: list[int] = []
        for entry in self._override_queue.list():
            if entry.action == "boost":
                boosts.append(int(entry.scene_id))
            elif entry.action == "exclude":
                excludes.append(int(entry.scene_id))

        return {
            "audio_track_id": int(track_id) if track_id is not None else None,
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
