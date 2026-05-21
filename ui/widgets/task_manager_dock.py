"""Task Manager Dock: Zeigt laufende Hintergrund-Prozesse mit QProgressBars."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer

from services.task_manager import GlobalTaskManager
from ui.theme import BG0, BG1, BG2, BG3, BG4, ACCENT, ACCENT_DIM, DANGER_BG, ERR, OK, WARN, T1, T2, T3, T4


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


class TaskManagerDock(QDockWidget):
    """Verankerte Taskliste als QDockWidget am unteren Bildschirmrand.

    Zeigt alle laufenden Hintergrund-Prozesse mit echten QProgressBars an.
    Keine schwebenden Fenster — fest verankert.
    """
    cancel_requested = Signal(str)  # task_id

    def __init__(self, parent=None):
        super().__init__("TASKS", parent)
        self.setObjectName("task_manager_dock")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.setMinimumHeight(60)
        self.setMinimumSize(300, 60)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Header mit Cancel-Button und Clear-Button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_label = QLabel("HINTERGRUND-PROZESSE")
        header_label.setStyleSheet(
            f"color: {T3}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        header_row.addWidget(header_label)
        header_row.addStretch()

        self.btn_clear = QPushButton("Fertige loeschen")
        self.btn_clear.setFixedHeight(20)
        self.btn_clear.setFixedWidth(110)
        self.btn_clear.setStyleSheet(
            f"QPushButton {{ background: {BG3}; color: {T3}; border: 1px solid {BG4}; "
            f"font-size: 9px; border-radius: 3px; padding: 0 6px; }}"
            f"QPushButton:hover {{ color: {T1}; background: {BG4}; }}"
        )
        self.btn_clear.setToolTip(
            "Abgeschlossene, abgebrochene und fehlgeschlagene Tasks aus der Anzeige entfernen."
        )
        self.btn_clear.clicked.connect(self._clear_finished)
        header_row.addWidget(self.btn_clear)

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setFixedHeight(20)
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setStyleSheet(
            f"QPushButton {{ background: {BG3}; color: {ERR}; border: 1px solid {ERR}; "
            f"font-size: 10px; font-weight: bold; border-radius: 3px; padding: 0 6px; }}"
            f"QPushButton:hover {{ background: {ERR}; color: {T1}; }}"
        )
        self.btn_cancel.setToolTip(
            "Laengsten aktuell laufenden Task abbrechen. Fuer gezielten Abbruch das X in der Task-Zeile nutzen."
        )
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        header_row.addWidget(self.btn_cancel)

        layout.addLayout(header_row)

        # Scrollbarer Bereich fuer Task-Rows mit echten QProgressBars
        self._task_container = QVBoxLayout()
        self._task_container.setSpacing(2)
        self._task_container.setContentsMargins(0, 0, 0, 0)

        task_scroll_widget = QWidget()
        task_scroll_widget.setLayout(self._task_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(task_scroll_widget)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        # Placeholder fuer leeren Zustand
        self._empty_label = QLabel("Keine laufenden Tasks")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {T4}; font-size: 11px; font-style: italic; border: none; padding: 8px;"
        )
        self._task_container.addWidget(self._empty_label)

        self.setWidget(container)

        # Task-Tracking: task_id → (row_widget, progress_bar, status_label, name_label, time_label)
        self._task_rows: dict[str, dict] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed)
        self._timer.start()

        # Singleton direkt abrufen — NICHT das Modul-Level 'task_manager' (kann None sein)
        self._tm = GlobalTaskManager.instance()
        self._tm.task_added.connect(self._on_task_added)
        self._tm.task_updated.connect(self._on_task_updated)
        self._tm.task_finished.connect(self._on_task_finished)

    def _on_cancel_clicked(self):
        """Cancel the longest-running task via TaskEngine."""
        longest_tid = None
        longest_elapsed = -1
        for tid in self._task_rows:
            task = self._tm.get_task(tid)
            if task and task.status == "running" and task.elapsed > longest_elapsed:
                longest_elapsed = task.elapsed
                longest_tid = tid
        if longest_tid is not None:
            self._tm.cancel_task(longest_tid)
            self.cancel_requested.emit(longest_tid)

    def _clear_finished(self):
        """Entfernt abgeschlossene Tasks aus der Anzeige."""
        to_remove = []
        for tid, row_data in self._task_rows.items():
            task = self._tm.get_task(tid)
            if task and task.status != "running":
                to_remove.append(tid)
        for tid in to_remove:
            row_data = self._task_rows.pop(tid)
            widget = row_data["widget"]
            self._task_container.removeWidget(widget)
            widget.deleteLater()
        self._tm.clear_finished()
        if not self._task_rows:
            self._empty_label.show()

    def _on_task_added(self, task_id: str):
        task = self._tm.get_task(task_id)
        if not task:
            return

        self._empty_label.hide()

        row_widget = QWidget()
        row_widget.setStyleSheet(
            f"QWidget {{ background: {BG0}; border: 1px solid {BG2}; border-radius: 3px; }}"
        )
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(6, 3, 6, 3)
        row_layout.setSpacing(8)

        name_label = QLabel(task.name)
        name_label.setFixedWidth(200)
        name_label.setStyleSheet(f"color: {T2}; font-size: 11px; font-weight: 600; border: none;")
        row_layout.addWidget(name_label)

        status_label = QLabel("Running")
        status_label.setFixedWidth(70)
        status_label.setStyleSheet(f"color: {OK}; font-size: 11px; font-weight: bold; border: none;")
        row_layout.addWidget(status_label)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        progress_bar.setFormat("%p%")
        progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {BG1}; border: 1px solid {BG3}; border-radius: 3px; "
            f"text-align: center; color: {T1}; font-size: 11px; "
            "min-height: 18px; max-height: 18px; }"
            f"QProgressBar::chunk {{ background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_DIM}, stop:1 {ACCENT}); border-radius: 2px; }}"
        )
        row_layout.addWidget(progress_bar, stretch=1)

        msg_label = QLabel("")
        msg_label.setMinimumWidth(150)
        msg_label.setStyleSheet(f"color: {T3}; font-size: 10px; border: none;")
        row_layout.addWidget(msg_label, stretch=1)

        time_label = QLabel("0s")
        time_label.setFixedWidth(50)
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_label.setStyleSheet(f"color: {T3}; font-size: 10px; border: none;")
        row_layout.addWidget(time_label)

        # B-127: per-row Cancel-Button. Header-Button cancelt den
        # laengsten Task (verwirrende UX bei mehreren parallelen Tasks);
        # jetzt klickt der User explizit die Zeile die ihn nervt.
        row_cancel_btn = QPushButton("✕")
        row_cancel_btn.setFixedSize(20, 20)
        row_cancel_btn.setToolTip(
            f"Nur diesen Task abbrechen: {task.name}."
        )
        row_cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ERR}; "
            f"border: 1px solid {BG3}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: {ERR}; color: {T1}; }}"
        )
        row_cancel_btn.clicked.connect(
            lambda _checked=False, _tid=task_id: self._cancel_specific_task(_tid)
        )
        row_layout.addWidget(row_cancel_btn)

        self._task_container.addWidget(row_widget)

        self._task_rows[task_id] = {
            "widget": row_widget,
            "name_label": name_label,
            "status_label": status_label,
            "progress_bar": progress_bar,
            "msg_label": msg_label,
            "time_label": time_label,
            "row_cancel_btn": row_cancel_btn,
        }

    def _cancel_specific_task(self, task_id: str):
        """B-127: Cancel den explizit angeklickten Task (nicht den
        laengsten). Wird vom per-row Cancel-Button getriggert."""
        self._tm.cancel_task(task_id)
        self.cancel_requested.emit(task_id)

    def _on_task_updated(self, task_id: str):
        task = self._tm.get_task(task_id)
        row_data = self._task_rows.get(task_id)
        if not task or not row_data:
            return

        progress_bar = row_data["progress_bar"]
        msg_label = row_data["msg_label"]

        # B-128: Auch task.total == 0 sinnvoll behandeln. Worker die
        # progress ohne konsistentes total melden, sollen nicht bei
        # 0 % haengen.
        progress = _as_int(task.progress)
        total = _as_int(task.total)
        if progress is None or total is None:
            progress_bar.setRange(0, 0)
        elif total > 0:
            progress_bar.setRange(0, total)
            progress_bar.setValue(max(0, min(total, progress)))
            progress_bar.setFormat(f"{max(0, min(total, progress))}%")
        elif progress > 0:
            # Worker meldet nur progress (in 0..100) ohne total →
            # behandeln als Prozent.
            progress_bar.setRange(0, 100)
            progress_bar.setValue(min(100, progress))
            progress_bar.setFormat(f"{min(100, progress)}%")
        else:
            # Komplett unbekannt → indeterminate (Qt-marquee).
            progress_bar.setRange(0, 0)
        msg_label.setText(task.message[:60] if task.message else "")
        msg_label.setToolTip(task.message or "")

    def _on_task_finished(self, task_id: str):
        task = self._tm.get_task(task_id)
        row_data = self._task_rows.get(task_id)
        if not task or not row_data:
            return

        status_label = row_data["status_label"]
        progress_bar = row_data["progress_bar"]
        msg_label = row_data["msg_label"]
        time_label = row_data["time_label"]

        if task.status == "finished":
            status_label.setText("Fertig")
            status_label.setStyleSheet(f"color: {ACCENT}; font-size: 11px; font-weight: bold; border: none;")
            progress_bar.setValue(progress_bar.maximum())
            progress_bar.setFormat("100%")
            progress_bar.setStyleSheet(
                f"QProgressBar {{ background: {BG1}; border: 1px solid {BG3}; border-radius: 3px; "
                f"text-align: center; color: {T1}; font-size: 11px; "
                "min-height: 18px; max-height: 18px; }"
                f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}"
            )
        elif task.status == "cancelled":
            status_label.setText("Abbruch")
            status_label.setStyleSheet(f"color: {WARN}; font-size: 11px; font-weight: bold; border: none;")
        else:
            status_label.setText("Fehler")
            status_label.setStyleSheet(f"color: {ERR}; font-size: 11px; font-weight: bold; border: none;")
            progress_bar.setStyleSheet(
                f"QProgressBar {{ background: {BG1}; border: 1px solid {DANGER_BG}; border-radius: 3px; "
                f"text-align: center; color: {ERR}; font-size: 11px; "
                "min-height: 18px; max-height: 18px; }"
                f"QProgressBar::chunk {{ background: {ERR}; border-radius: 2px; }}"
            )

        msg_label.setText(task.message[:60] if task.message else "")
        msg_label.setToolTip(task.message or "")
        time_label.setText(f"{task.elapsed}s")

    def _update_elapsed(self):
        for task_id, row_data in self._task_rows.items():
            task = self._tm.get_task(task_id)
            if task and task.status == "running":
                row_data["time_label"].setText(f"{task.elapsed}s")
