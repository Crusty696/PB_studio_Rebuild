"""Usability shell around the SCHNITT timeline."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ui.timeline import InteractiveTimeline

logger = logging.getLogger(__name__)

# Max. Eintraege im Snapshot-Menue (Service-Retention ist 20)
RETENTION_MENU_MAX = 20


class _SnapshotRestoreWorker(QObject):
    """B-708 (Variant B): fuehrt den Snapshot-Restore (DB-Arbeit inkl.
    Retry/busy_timeout) im Hintergrund-Thread aus, damit der GUI-Thread NICHT
    einfriert. ``restore_snapshot`` fasst keine Qt-Objekte an (reine DB-Ops via
    nullpool_session) und ist damit thread-sicher. Das anschliessende
    ``load_from_db`` + ``undo_stack.clear`` bleibt im Main-Thread (Widgets)."""

    finished = Signal()
    error = Signal(str)

    def __init__(self, snapshot_id: int):
        super().__init__()
        self._snapshot_id = snapshot_id

    def run(self) -> None:
        try:
            from services.timeline_snapshot_service import restore_snapshot
            restore_snapshot(self._snapshot_id, backup_current=True)
            self.finished.emit()
        except Exception as exc:  # an den Main-Thread-Slot durchreichen
            logger.error("Snapshot-Restore (Worker) fehlgeschlagen: %s", exc)
            self.error.emit(str(exc))


class TimelineShell(QWidget):
    """Timeline plus visible zoom, status and legend controls."""

    def __init__(self, timeline: InteractiveTimeline | None = None, parent=None):
        super().__init__(parent)
        self.timeline = timeline or InteractiveTimeline()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        self.status_label = QLabel("Timeline bereit")
        self.status_label.setObjectName("schnitt_timeline_status")
        self.status_label.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
        toolbar.addWidget(self.status_label)

        toolbar.addStretch(1)

        # NEUBAU-VOLLINTEGRATION T2.3 (USE-009): Snapshot-Restore-UI.
        # Auto-Edit legt automatisch Snapshots an (timeline_service);
        # hier lassen sie sich ansehen und wiederherstellen.
        self.btn_snapshots = QToolButton()
        self.btn_snapshots.setText("Snapshots")
        self.btn_snapshots.setObjectName("schnitt_timeline_snapshots")
        self.btn_snapshots.setMinimumSize(84, 36)
        self.btn_snapshots.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_snapshots.setToolTip(
            "Wirkung: Zeigt gespeicherte Timeline-Staende (automatisch bei "
            "jedem Auto-Edit). "
            "Wann: Nutze es nach einem Fehlgriff oder App-Absturz. "
            "Ergebnis: Ein Klick stellt den gewaehlten Stand wieder her; der "
            "aktuelle Stand wird vorher automatisch gesichert."
        )
        self.btn_snapshots.setAccessibleName("Timeline-Snapshots anzeigen und wiederherstellen")
        self._snapshot_menu = QMenu(self.btn_snapshots)
        self._snapshot_menu.aboutToShow.connect(self._populate_snapshot_menu)
        self.btn_snapshots.setMenu(self._snapshot_menu)
        toolbar.addWidget(self.btn_snapshots)

        self.legend_label = QLabel("A1 Audio | V1 Video | Marker: Beats/Anker")
        self.legend_label.setObjectName("schnitt_timeline_legend")
        self.legend_label.setToolTip(
            "Wirkung: Erklaert die Spuren und Marker in der Timeline. "
            "Wann: Nutze es zur Orientierung beim Schneiden und Zoomen. "
            "Ergebnis: A1 ist Master-Audio, V1 sind Video-Clips, Marker zeigen Beats/Anker."
        )
        self.legend_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        toolbar.addWidget(self.legend_label)

        self.zoom_label = QLabel("Zoom 100%")
        self.zoom_label.setObjectName("schnitt_timeline_zoom_label")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(86)
        self.zoom_label.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
        toolbar.addWidget(self.zoom_label)

        self.btn_zoom_out = self._button(
            "-",
            "Timeline herauszoomen",
            "Wirkung: Zeigt mehr Zeit auf einmal. Wann: Nutze es fuer Ueberblick ueber lange Edits. Ergebnis: Clips werden horizontal schmaler, A1/V1 bleiben gleich hoch.",
        )
        self.btn_zoom_fit = self._button(
            "Fit",
            "Timeline auf Inhalt einpassen",
            "Wirkung: Passt die komplette Timeline horizontal in den sichtbaren Bereich. Wann: Nutze es nach Auto-Edit oder Import. Ergebnis: Zeitachse wird eingepasst, Spuren bleiben lesbar.",
        )
        self.btn_zoom_reset = self._button(
            "1:1",
            "Timeline-Zoom auf 100 Prozent zuruecksetzen",
            "Wirkung: Setzt den Zoom auf Normalansicht. Wann: Nutze es nach starkem Zoomen. Ergebnis: Ein stabiler Arbeitszoom ohne vertikale Spur-Skalierung.",
        )
        self.btn_zoom_in = self._button(
            "+",
            "Timeline hineinzoomen",
            "Wirkung: Zeigt mehr Detail pro Sekunde. Wann: Nutze es fuer genaue Cuts und Anker. Ergebnis: Clips werden horizontal breiter, A1/V1 bleiben gleich hoch.",
        )

        for button in (
            self.btn_zoom_out,
            self.btn_zoom_fit,
            self.btn_zoom_reset,
            self.btn_zoom_in,
        ):
            toolbar.addWidget(button)

        layout.addLayout(toolbar)
        layout.addWidget(self.timeline, stretch=1)

        self.btn_zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.15))
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_by(1.15))
        self.btn_zoom_fit.clicked.connect(self._fit_to_content)
        self.btn_zoom_reset.clicked.connect(self._reset_zoom)

        # B-616: Label folgt JEDEM Zoom-Pfad (auch Mausrad und dem internen
        # fit_to_content beim Projekt-Load), nicht nur den Shell-Buttons.
        self.timeline.zoom_changed.connect(lambda _scale: self._update_zoom_label())
        self._update_zoom_label()

    def _button(self, text: str, label: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumSize(48, 36)
        button.setToolTip(tooltip)
        button.setAccessibleName(label)
        button.setObjectName("schnitt_" + label.lower().replace(" ", "_"))
        return button

    def _zoom_by(self, factor: float) -> None:
        self.timeline.zoom_by_factor(factor)
        self._update_zoom_label()

    def _fit_to_content(self) -> None:
        self.timeline.fit_to_content()
        self._update_zoom_label()

    def _reset_zoom(self) -> None:
        self.timeline.reset_zoom()
        self._update_zoom_label()

    # ------------------------------------------------------------------
    # T2.3: Snapshot-Menue
    # ------------------------------------------------------------------

    def _populate_snapshot_menu(self) -> None:
        """Befuellt das Snapshot-Menue live beim Oeffnen (neueste zuerst)."""
        self._snapshot_menu.clear()
        try:
            from database import get_active_project_id
            from services.timeline_snapshot_service import list_snapshots
            project_id = get_active_project_id()
            if project_id is None:
                self._snapshot_menu.addAction("Kein aktives Projekt").setEnabled(False)
                return
            snaps = list_snapshots(project_id)
        except Exception as exc:
            logger.warning("Snapshot-Liste nicht ladbar: %s", exc)
            self._snapshot_menu.addAction("Snapshots nicht ladbar").setEnabled(False)
            return
        if not snaps:
            self._snapshot_menu.addAction(
                "Noch keine Snapshots (entstehen bei Auto-Edit)").setEnabled(False)
            return
        for snap in snaps[:RETENTION_MENU_MAX]:
            created = snap["created_at"][:16].replace("T", " ")
            text = f"v{snap['version']} — {snap['label'] or 'ohne Label'} " \
                   f"({snap['clip_count']} Clips{', ' + created if created else ''})"
            action = self._snapshot_menu.addAction(text)
            action.triggered.connect(
                lambda _=False, sid=snap["id"], ver=snap["version"]:
                self._restore_snapshot(sid, ver)
            )

    def _restore_snapshot(self, snapshot_id: int, version: int) -> None:
        """Stellt einen Snapshot her (aktueller Stand wird vorher gesichert).

        B-708 (Variant B): Die DB-Arbeit (inkl. Retry gegen "database is locked"
        + busy_timeout) laeuft jetzt in einem Hintergrund-Worker, damit der
        GUI-Thread nicht einfriert. Das UI-Update (load_from_db + undo_stack
        leeren) passiert nach Worker-Erfolg wieder im Main-Thread.
        """
        if getattr(self, "_restore_inflight", False):
            self.status_label.setText("Snapshot-Restore laeuft bereits …")
            return
        self._restore_inflight = True
        self.status_label.setText(f"Stelle Snapshot v{version} wieder her …")
        worker = _SnapshotRestoreWorker(snapshot_id)
        try:
            from services.task_manager import GlobalTaskManager
            GlobalTaskManager.instance().start_task(
                name=f"Snapshot v{version} wiederherstellen",
                worker=worker,
                description="Timeline-Snapshot wiederherstellen",
                on_finish=lambda *_a, _v=version: self._on_restore_done(_v),
                on_error=lambda msg, _v=version: self._on_restore_failed(_v, msg),
            )
        except Exception as exc:  # start_task selbst fehlgeschlagen (B-706/Q3-Muster)
            self._restore_inflight = False
            logger.error("Snapshot-Restore konnte nicht gestartet werden: %s", exc)
            self.status_label.setText(f"Snapshot-Restore fehlgeschlagen: {exc}")

    def _shell_alive(self) -> bool:
        """B-708: Der async Restore-Handler kann per QueuedConnection NACH dem
        Schliessen/Zerstoeren der Shell feuern. Zugriff auf ein dann
        C++-zerstoertes Widget (status_label/self) wuerde einen RuntimeError im
        Qt-Slot werfen -> moeglicher PySide6-Abbruch. Vorher pruefen."""
        try:
            import shiboken6
            return shiboken6.isValid(self) and shiboken6.isValid(self.status_label)
        except Exception:
            return False

    def _set_status_safe(self, text: str) -> None:
        if self._shell_alive():
            try:
                self.status_label.setText(text)
            except RuntimeError:
                pass  # C++-Objekt zwischenzeitlich zerstoert

    def _on_restore_done(self, version: int) -> None:
        """Main-Thread: Timeline neu laden + Undo-Stack leeren nach erfolgreichem Restore."""
        self._restore_inflight = False
        if not self._shell_alive():
            return  # Shell waehrend des Restores geschlossen -> nichts mehr anfassen
        try:
            from database import get_active_project_id
            project_id = get_active_project_id()
            if project_id is not None:
                self.timeline.load_from_db(project_id)
            # B-689: Der Restore schreibt neue TimelineEntry-Zeilen mit NEUEN IDs.
            # Der Undo-Stack haelt danach Commands auf tote/fremde entry_ids —
            # ein Ctrl+Z wuerde den gerade wiederhergestellten Stand zerstoeren
            # (z.B. ApplyAutoEditCommand.undo() loescht alle Video-Clips). Ein
            # Restore ist ein neuer Ausgangszustand -> Stack leeren. NICHT in
            # load_from_db selbst, weil undo/redo diese Methode aufrufen.
            undo_stack = getattr(self.timeline, "undo_stack", None)
            if undo_stack is not None:
                undo_stack.clear()
            self._set_status_safe(
                f"Snapshot v{version} wiederhergestellt — vorheriger Stand "
                f"wurde automatisch gesichert."
            )
            logger.info("Timeline-Snapshot v%d via UI wiederhergestellt", version)
        except Exception as exc:
            logger.error("Snapshot-Restore Post-Load fehlgeschlagen: %s", exc)
            self._set_status_safe(f"Snapshot-Restore fehlgeschlagen: {exc}")

    def _on_restore_failed(self, version: int, msg: str) -> None:
        """Main-Thread: Restore-Worker meldete einen Fehler."""
        self._restore_inflight = False
        logger.error("Snapshot-Restore v%d fehlgeschlagen: %s", version, msg)
        self._set_status_safe(f"Snapshot-Restore fehlgeschlagen: {msg}")

    def _update_zoom_label(self) -> None:
        zoom = int(round(self.timeline.transform().m11() * 100))
        self.zoom_label.setText(f"Zoom {zoom}%")
