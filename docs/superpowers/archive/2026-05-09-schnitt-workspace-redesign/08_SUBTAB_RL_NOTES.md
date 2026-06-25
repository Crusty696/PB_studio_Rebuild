# Phase 08 — Sub-Tab „RL & Notes"

**Ziel:** RL-Feedback (👍/👎 + Event-Liste) + Notes-Editor mit Auto-Save.

---

## Task 8.1: Layout + Auto-Save-Debounce

**Files:**
- Create: `ui/workspaces/schnitt/tab_rl_notes.py`
- Modify: `ui/workspaces/schnitt/editor_view.py`
- Test: `tests/ui/test_subtab_rl_notes.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_subtab_rl_notes.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from database import init_db, engine
from database.models import Project
from database.session import DBSession
from services.project_notes_service import get_notes
from ui.workspaces.schnitt.tab_rl_notes import SchnittTabRlNotes


def _qapp():
    return QApplication.instance() or QApplication([])


def _project():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="rl-notes-test")
        s.add(p); s.commit()
        return p.id


def test_widgets_present():
    _qapp()
    t = SchnittTabRlNotes()
    assert t.btn_thumbs_up is not None
    assert t.btn_thumbs_down is not None
    assert t.rl_event_list is not None
    assert t.notes_edit is not None


def test_typing_triggers_autosave_after_debounce(qtbot=None):
    app = _qapp()
    pid = _project()
    t = SchnittTabRlNotes()
    t.set_active_project(pid)
    t.notes_edit.setPlainText("# Mein Plan")
    # Debounce 1000 ms — verkürze für Test über das interne Timer-Objekt
    t._autosave_timer.setInterval(20)
    t._autosave_timer.start()
    # Event-Loop laufen lassen
    QTimer.singleShot(80, app.quit)
    app.exec()
    assert get_notes(pid) == "# Mein Plan"
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/workspaces/schnitt/tab_rl_notes.py
"""Sub-Tab 'RL & Notes' im SCHNITT-Editor."""
from datetime import datetime
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
        self.btn_thumbs_up = QPushButton("👍 Gut")
        self.btn_thumbs_down = QPushButton("👎 Schlecht")
        for b in (self.btn_thumbs_up, self.btn_thumbs_down):
            b.setFixedHeight(36)
            btn_row.addWidget(b)
        self.btn_thumbs_up.clicked.connect(self.feedback_positive)
        self.btn_thumbs_down.clicked.connect(self.feedback_negative)
        v.addLayout(btn_row)

        v.addWidget(QLabel("Letzte RL-Events"))
        self.rl_event_list = QListWidget()
        v.addWidget(self.rl_event_list, stretch=1)

        return col

    def _build_notes_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        v.addWidget(QLabel("Notes (Markdown, Auto-Save)"))
        self.notes_edit = QTextEdit()
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
        update_notes(self._project_id, self.notes_edit.toPlainText())
        self.saved_label.setText(
            f"Zuletzt gespeichert: {datetime.now().strftime('%H:%M:%S')}"
        )
```

- [ ] **Step 4: Editor-View einbinden** (Tab 3 Stub durch echtes Tab ersetzen).

- [ ] **Step 5: Pass bestätigen.**

- [ ] **Step 6: Commit**

```bash
git add ui/workspaces/schnitt/tab_rl_notes.py ui/workspaces/schnitt/editor_view.py tests/ui/test_subtab_rl_notes.py
git commit -m "feat(schnitt): subtab RL & Notes with autosave"
```

- [ ] **Step 7: Vault-Update.**

---

## Phasen-Abschluss

Phase 08 fertig. Alle 4 Sub-Tabs sind funktional eingebunden.

Nächste Phase: [09_WORKER_REFACTOR.md](09_WORKER_REFACTOR.md).
