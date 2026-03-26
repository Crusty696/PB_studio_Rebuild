"""Task Manager Dock: Zeigt laufende Hintergrund-Prozesse mit QProgressBars."""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer

from services.task_manager import GlobalTaskManager


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
            "color: #808080; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        header_row.addWidget(header_label)
        header_row.addStretch()

        self.btn_clear = QPushButton("Fertige loeschen")
        self.btn_clear.setFixedHeight(20)
        self.btn_clear.setFixedWidth(110)
        self.btn_clear.setStyleSheet(
            "QPushButton { background: #1E1E1E; color: #606060; border: 1px solid #333; "
            "font-size: 9px; border-radius: 3px; padding: 0 6px; }"
            "QPushButton:hover { color: #C0C0C0; background: #282828; }"
        )
        self.btn_clear.setToolTip("Abgeschlossene Tasks aus der Liste entfernen")
        self.btn_clear.clicked.connect(self._clear_finished)
        header_row.addWidget(self.btn_clear)

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setFixedHeight(20)
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #3A1010; color: #FF5050; border: 1px solid #FF3030; "
            "font-size: 10px; font-weight: bold; border-radius: 3px; padding: 0 6px; }"
            "QPushButton:hover { background: #FF3030; color: #FFFFFF; }"
        )
        self.btn_cancel.setToolTip("Laufenden Task abbrechen")
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
            "color: #505050; font-size: 11px; font-style: italic; border: none; padding: 8px;"
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
            "QWidget { background: #0E0E14; border: 1px solid #1E1E2E; border-radius: 3px; }"
        )
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(6, 3, 6, 3)
        row_layout.setSpacing(8)

        name_label = QLabel(task.name)
        name_label.setFixedWidth(180)
        name_label.setStyleSheet("color: #C0C0C0; font-size: 10px; font-weight: 600; border: none;")
        row_layout.addWidget(name_label)

        status_label = QLabel("Running")
        status_label.setFixedWidth(70)
        status_label.setStyleSheet("color: #00E676; font-size: 10px; font-weight: bold; border: none;")
        row_layout.addWidget(status_label)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        progress_bar.setFormat("%p%")
        progress_bar.setFixedHeight(16)
        progress_bar.setStyleSheet(
            "QProgressBar { background: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 3px; "
            "text-align: center; color: #B0B0B0; font-size: 9px; }"
            "QProgressBar::chunk { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, stop:0 #7A6010, stop:1 #D4AF37); border-radius: 2px; }"
        )
        row_layout.addWidget(progress_bar, stretch=1)

        msg_label = QLabel("")
        msg_label.setFixedWidth(200)
        msg_label.setStyleSheet("color: #707070; font-size: 9px; border: none;")
        row_layout.addWidget(msg_label)

        time_label = QLabel("0s")
        time_label.setFixedWidth(50)
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_label.setStyleSheet("color: #505050; font-size: 9px; border: none;")
        row_layout.addWidget(time_label)

        self._task_container.addWidget(row_widget)

        self._task_rows[task_id] = {
            "widget": row_widget,
            "name_label": name_label,
            "status_label": status_label,
            "progress_bar": progress_bar,
            "msg_label": msg_label,
            "time_label": time_label,
        }

    def _on_task_updated(self, task_id: str):
        task = self._tm.get_task(task_id)
        row_data = self._task_rows.get(task_id)
        if not task or not row_data:
            return

        progress_bar = row_data["progress_bar"]
        msg_label = row_data["msg_label"]

        if task.total > 0:
            progress_bar.setRange(0, task.total)
            progress_bar.setValue(task.progress)
            progress_bar.setFormat(f"{task.progress}%")
        msg_label.setText(task.message[:40] if task.message else "")
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
            status_label.setStyleSheet("color: #D4AF37; font-size: 10px; font-weight: bold; border: none;")
            progress_bar.setValue(progress_bar.maximum())
            progress_bar.setFormat("100%")
            progress_bar.setStyleSheet(
                "QProgressBar { background: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 3px; "
                "text-align: center; color: #B0B0B0; font-size: 9px; }"
                "QProgressBar::chunk { background: #D4AF37; border-radius: 2px; }"
            )
        elif task.status == "cancelled":
            status_label.setText("Abbruch")
            status_label.setStyleSheet("color: #FFB040; font-size: 10px; font-weight: bold; border: none;")
        else:
            status_label.setText("Fehler")
            status_label.setStyleSheet("color: #FF5050; font-size: 10px; font-weight: bold; border: none;")
            progress_bar.setStyleSheet(
                "QProgressBar { background: #1A1A1A; border: 1px solid #3A1010; border-radius: 3px; "
                "text-align: center; color: #FF5050; font-size: 9px; }"
                "QProgressBar::chunk { background: #CC3333; border-radius: 2px; }"
            )

        msg_label.setText(task.message[:40] if task.message else "")
        msg_label.setToolTip(task.message or "")
        time_label.setText(f"{task.elapsed}s")

    def _update_elapsed(self):
        for task_id, row_data in self._task_rows.items():
            task = self._tm.get_task(task_id)
            if task and task.status == "running":
                row_data["time_label"].setText(f"{task.elapsed}s")
