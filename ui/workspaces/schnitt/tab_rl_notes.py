"""Sub-Tab 'RL & Notes' im SCHNITT-Editor."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QSplitter, QTextEdit,
)

from services.project_notes_service import get_notes, update_notes


_AUTOSAVE_DEBOUNCE_MS = 1000


class SchnittTabRlNotes(QWidget):
    feedback_positive = Signal()
    feedback_negative = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(_AUTOSAVE_DEBOUNCE_MS)
        self._autosave_timer.timeout.connect(self._save_notes)
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_rl_column())
        splitter.addWidget(self._build_notes_column())
        splitter.setSizes([400, 600])
        outer.addWidget(splitter)

    def _build_rl_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(8)

        v.addWidget(QLabel("Wie beurteilst du den letzten Auto-Edit?"))
        btn_row = QHBoxLayout()
        self.btn_thumbs_up = QPushButton("\U0001F44D Gut")
        self.btn_thumbs_down = QPushButton("\U0001F44E Schlecht")
        self.btn_thumbs_up.setToolTip(
            "Letzten Auto-Edit als gut bewerten und als positives RL-Feedback speichern."
        )
        self.btn_thumbs_up.setAccessibleName("Auto-Edit positiv bewerten")
        self.btn_thumbs_down.setToolTip(
            "Letzten Auto-Edit als schlecht bewerten und als negatives RL-Feedback speichern."
        )
        self.btn_thumbs_down.setAccessibleName("Auto-Edit negativ bewerten")
        for b in (self.btn_thumbs_up, self.btn_thumbs_down):
            b.setFixedHeight(36)
            btn_row.addWidget(b)
        self.btn_thumbs_up.clicked.connect(self.feedback_positive)
        self.btn_thumbs_down.clicked.connect(self.feedback_negative)
        v.addLayout(btn_row)

        v.addWidget(QLabel("Letzte RL-Events"))
        self.rl_event_list = QListWidget()
        self.rl_event_list.setToolTip(
            "Letzte Reinforcement-Learning-Feedback-Ereignisse fuer dieses Projekt."
        )
        self.rl_event_list.setAccessibleName("Letzte RL-Feedback-Ereignisse")
        v.addWidget(self.rl_event_list, stretch=1)

        return col

    def _build_notes_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        v.addWidget(QLabel("Notes (Markdown, Auto-Save)"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setToolTip(
            "Projekt-Notizen fuer SCHNITT schreiben. Speichert automatisch nach kurzer Pause."
        )
        self.notes_edit.setAccessibleName("SCHNITT Projekt-Notizen")
        self.notes_edit.setAcceptRichText(False)
        self.notes_edit.setPlaceholderText("# Hier Notizen, Anmerkungen, To-dos…")
        self.notes_edit.textChanged.connect(self._on_text_changed)
        v.addWidget(self.notes_edit, stretch=1)

        self.saved_label = QLabel("Noch nicht gespeichert.")
        self.saved_label.setStyleSheet("color:#6b7280; font-size:10px;")
        v.addWidget(self.saved_label)
        return col

    def set_active_project(self, project_id: int | None) -> None:
        self._project_id = project_id
        self._autosave_timer.stop()
        if project_id is None:
            self.notes_edit.blockSignals(True)
            self.notes_edit.setPlainText("")
            self.notes_edit.blockSignals(False)
            self.saved_label.setText("Kein Projekt aktiv.")
            return
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(get_notes(project_id))
        self.notes_edit.blockSignals(False)
        self.saved_label.setText("Gespeicherten Stand geladen.")

    def _on_text_changed(self):
        if self._project_id is None:
            return
        self._autosave_timer.start()

    def _save_notes(self) -> None:
        if self._project_id is None:
            return
        # T4.2: Service liefert updated_at zurück → konsistente Zeit aus DB statt
        # neuem datetime.now() in der UI.
        ts = update_notes(self._project_id, self.notes_edit.toPlainText())
        self.saved_label.setText(
            f"Zuletzt gespeichert: {ts.strftime('%H:%M:%S')}"
        )
