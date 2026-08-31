"""Sub-Tab 'Notizen' im SCHNITT-Editor.

Hervorgegangen aus dem frueheren Tab "RL & Notes" (B-927, Userentscheidung
2026-08-31). Die linke Haelfte jenes Tabs — Daumen hoch/runter und die Liste
"Letzte RL-Events" — ist entfallen: die Liste hatte repo-weit keinen einzigen
Schreibzugriff und das Feedback beeinflusste den Schnitt nicht. Die
Projekt-Notizen funktionieren dagegen und sind hier unveraendert weitergefuehrt.
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit

from services.project_notes_service import get_notes, update_notes


_AUTOSAVE_DEBOUNCE_MS = 1000


class SchnittTabNotizen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(_AUTOSAVE_DEBOUNCE_MS)
        self._autosave_timer.timeout.connect(self._save_notes)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
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
        self.saved_label.setStyleSheet("color:#98a2b1; font-size:10px;")
        v.addWidget(self.saved_label)

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
