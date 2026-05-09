# Phase 04 — SchnittWorkspace Skeleton

**Ziel:** Drei-State-Skelett: `SchnittWorkspace` mit `QStackedWidget`, `SchnittEmptyView`, `SchnittLoadingView`, `SchnittEditorView` als Stub. State-Manager mit Empty-State-Detection. Echte Sub-Tab-Inhalte folgen ab Phase 05.

---

## Task 4.1: Empty/Loading-Views

**Files:**
- Create: `ui/workspaces/schnitt/__init__.py`
- Create: `ui/workspaces/schnitt/empty_view.py`
- Create: `ui/workspaces/schnitt/loading_view.py`
- Test: `tests/ui/test_schnitt_views_skeleton.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_schnitt_views_skeleton.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.empty_view import SchnittEmptyView
from ui.workspaces.schnitt.loading_view import SchnittLoadingView


def _qapp():
    return QApplication.instance() or QApplication([])


def test_empty_view_has_four_presets_and_custom():
    _qapp()
    v = SchnittEmptyView()
    keys = v.preset_keys()
    assert keys == ["Techno", "Cinematic", "House", "Festival"]
    assert v.btn_custom is not None
    assert v.btn_custom.text() == "Eigene Einstellungen…"


def test_empty_view_emits_preset_signal():
    _qapp()
    v = SchnittEmptyView()
    received = []
    v.preset_selected.connect(received.append)
    v._buttons["Techno"].click()
    assert received == ["Techno"]


def test_loading_view_initial_text_and_setter():
    _qapp()
    v = SchnittLoadingView()
    assert v.status_label.text() != ""
    v.set_stage("cut_calc", 0.42)
    assert "Schnitte" in v.status_label.text()
    assert v.progress_bar.value() == 42
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: `__init__.py`**

```python
# ui/workspaces/schnitt/__init__.py
"""SCHNITT-Workspace (Redesign 2026-05-09)."""
```

- [ ] **Step 4: `empty_view.py`**

```python
# ui/workspaces/schnitt/empty_view.py
"""Empty-State der SCHNITT-Workspace: Quick-Lane mit Preset-Buttons."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)


_PRESETS = [
    ("Techno",    "Schnell, druckvoll. 4 Beats, Reaktivität 70 %."),
    ("Cinematic", "Ruhig, langsam. 16 Beats, Reaktivität 30 %."),
    ("House",     "Mittel groovig. 8 Beats, Reaktivität 50 %."),
    ("Festival",  "Maximaler Druck. 1 Beat, Reaktivität 90 %."),
]


class SchnittEmptyView(QWidget):
    preset_selected = Signal(str)
    custom_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_empty")
        self._buttons: dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(16)
        layout.addStretch(1)

        title = QLabel("Noch keine Timeline vorhanden.")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #f9fafb;")
        layout.addWidget(title)

        subtitle = QLabel("Wähle einen Auto-Edit Stil, um zu starten.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #9ca3af; font-size: 13px;")
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        row = QHBoxLayout()
        row.setSpacing(12)
        for key, hint in _PRESETS:
            btn = self._make_preset_button(key, hint)
            self._buttons[key] = btn
            row.addWidget(btn)
        layout.addLayout(row)

        self.btn_custom = QPushButton("Eigene Einstellungen…")
        self.btn_custom.setFixedHeight(28)
        self.btn_custom.clicked.connect(self.custom_clicked)
        custom_row = QHBoxLayout()
        custom_row.addStretch(1)
        custom_row.addWidget(self.btn_custom)
        custom_row.addStretch(1)
        layout.addLayout(custom_row)

        layout.addStretch(2)

    def _make_preset_button(self, key: str, hint: str) -> QPushButton:
        btn = QPushButton(f"{key}\n\n{hint}")
        btn.setObjectName("preset_button")
        btn.setMinimumSize(180, 110)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setStyleSheet(
            "QPushButton#preset_button {"
            "  background:#0f1318; border:1px solid rgba(255,255,255,30);"
            "  border-radius:8px; color:#e8e6e3; font-size:13px; padding:12px;"
            "}"
            "QPushButton#preset_button:hover {"
            "  border:1px solid #d4a44a; background:#181f27;"
            "}"
        )
        btn.clicked.connect(lambda _checked, k=key: self.preset_selected.emit(k))
        return btn

    def preset_keys(self) -> list[str]:
        return [k for k, _ in _PRESETS]
```

- [ ] **Step 5: `loading_view.py`**

```python
# ui/workspaces/schnitt/loading_view.py
"""Loading-State der SCHNITT-Workspace mit rotierendem Status-Text + Progress."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout,
)


_STAGE_TEXT = {
    "audio_load": "Lade Audio…",
    "beat_grid": "Bestimme Beatgrid…",
    "structure": "Erkenne Songstruktur…",
    "cut_calc": "Setze Schnitte…",
    "clip_select": "Wähle Clips aus…",
    "anchor_sync": "Synchronisiere Anker…",
    "db_write": "Speichere Timeline…",
}


class SchnittLoadingView(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_loading")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 80, 40, 80)
        layout.setSpacing(16)
        layout.addStretch(1)

        title = QLabel("Auto-Edit läuft…")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #f9fafb;")
        layout.addWidget(title)

        self.status_label = QLabel("Vorbereiten…")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #d4a44a; font-size: 14px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setFixedHeight(26)
        self.btn_cancel.clicked.connect(self.cancel_requested)
        cancel_row.addWidget(self.btn_cancel)
        cancel_row.addStretch(1)
        layout.addLayout(cancel_row)

        layout.addStretch(2)

    def set_stage(self, stage_key: str, fraction: float) -> None:
        self.status_label.setText(_STAGE_TEXT.get(stage_key, "Vorbereiten…"))
        self.progress_bar.setValue(int(max(0.0, min(1.0, fraction)) * 100))

    def reset(self) -> None:
        self.status_label.setText("Vorbereiten…")
        self.progress_bar.setValue(0)
```

- [ ] **Step 6: Pass bestätigen.**

- [ ] **Step 7: Commit**

```bash
git add ui/workspaces/schnitt/__init__.py ui/workspaces/schnitt/empty_view.py ui/workspaces/schnitt/loading_view.py tests/ui/test_schnitt_views_skeleton.py
git commit -m "feat(schnitt): empty + loading view skeletons"
```

- [ ] **Step 8: Vault-Update.**

---

## Task 4.2: `SchnittEditorView` Stub

**Files:**
- Create: `ui/workspaces/schnitt/editor_view.py`
- Test: `tests/ui/test_schnitt_editor_view_skeleton.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_schnitt_editor_view_skeleton.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.editor_view import SchnittEditorView


def _qapp():
    return QApplication.instance() or QApplication([])


def test_editor_has_four_subtabs():
    _qapp()
    v = SchnittEditorView()
    titles = [v.sub_tabs.tabText(i) for i in range(v.sub_tabs.count())]
    assert titles == ["Schnitt", "Pacing & Anker", "Audio", "RL & Notes"]


def test_editor_has_persistent_inspector():
    _qapp()
    v = SchnittEditorView()
    assert v.inspector_panel is not None
    assert v.inspector_panel.parent() is v
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung (Stub-Tabs als `QWidget`-Platzhalter)**

```python
# ui/workspaces/schnitt/editor_view.py
"""SchnittEditorView — finale Editor-Stage mit 4 Sub-Tabs + persistentem Inspector.
Sub-Tab-Inhalte werden in Phasen 05–08 ausimplementiert."""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTabWidget, QVBoxLayout, QLabel,
)
from ui.clip_inspector import ClipInspectorPanel


class SchnittEditorView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_editor")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)
        self.sub_tabs.addTab(self._stub("Sub-Tab Schnitt — Phase 05"), "Schnitt")
        self.sub_tabs.addTab(self._stub("Sub-Tab Pacing & Anker — Phase 06"), "Pacing & Anker")
        self.sub_tabs.addTab(self._stub("Sub-Tab Audio — Phase 07"), "Audio")
        self.sub_tabs.addTab(self._stub("Sub-Tab RL & Notes — Phase 08"), "RL & Notes")
        layout.addWidget(self.sub_tabs, stretch=3)

        self.inspector_panel = ClipInspectorPanel(self)
        layout.addWidget(self.inspector_panel, stretch=1)

    @staticmethod
    def _stub(text: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
        v.addWidget(lbl, alignment=0x84)
        v.addStretch(1)
        return w
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/workspaces/schnitt/editor_view.py tests/ui/test_schnitt_editor_view_skeleton.py
git commit -m "feat(schnitt): editor view shell with 4 stub sub-tabs"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 4.3: `SchnittWorkspace` mit State-Manager

**Files:**
- Create: `ui/workspaces/schnitt_workspace.py`
- Test: `tests/ui/test_schnitt_workspace_states.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_schnitt_workspace_states.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from database import init_db, engine
from database.models import Project, TimelineEntry
from database.session import DBSession
from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY, STATE_LOADING, STATE_EDITOR


def _qapp():
    return QApplication.instance() or QApplication([])


def _project(with_clip: bool):
    init_db()
    with DBSession(engine) as s:
        p = Project(name="schnitt-state")
        s.add(p); s.flush()
        if with_clip:
            s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                                 start_time=0, end_time=2, lane=0))
        s.commit()
        return p.id


def test_initial_no_project_shows_empty():
    _qapp()
    ws = SchnittWorkspace()
    ws.set_active_project(None)
    assert ws.current_state() == STATE_EMPTY


def test_project_with_no_clips_shows_empty():
    _qapp()
    ws = SchnittWorkspace()
    pid = _project(with_clip=False)
    ws.set_active_project(pid)
    assert ws.current_state() == STATE_EMPTY


def test_project_with_clips_shows_editor():
    _qapp()
    ws = SchnittWorkspace()
    pid = _project(with_clip=True)
    ws.set_active_project(pid)
    assert ws.current_state() == STATE_EDITOR


def test_show_loading_then_editor():
    _qapp()
    ws = SchnittWorkspace()
    pid = _project(with_clip=False)
    ws.set_active_project(pid)
    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING
    # Simuliere Worker-Done
    pid2 = _project(with_clip=True)
    ws.set_active_project(pid2)
    ws.refresh_state_from_db()
    assert ws.current_state() == STATE_EDITOR
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Implementierung**

```python
# ui/workspaces/schnitt_workspace.py
"""SchnittWorkspace — Master-Tab für Auto-Schnitt + Review (Redesign 2026-05-09).
Drei States: Empty (Quick-Lane) / Loading (Worker laeuft) / Editor (Sub-Tabs)."""
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from database import engine
from database.session import DBSession
from database.models import TimelineEntry

from ui.workspaces.schnitt.empty_view import SchnittEmptyView
from ui.workspaces.schnitt.loading_view import SchnittLoadingView
from ui.workspaces.schnitt.editor_view import SchnittEditorView


STATE_EMPTY = 0
STATE_LOADING = 1
STATE_EDITOR = 2


class SchnittWorkspace(QWidget):
    preset_selected = Signal(str)
    custom_clicked = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_workspace")
        self._project_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        self.empty_view = SchnittEmptyView()
        self.loading_view = SchnittLoadingView()
        self.editor_view = SchnittEditorView()
        self._stack.addWidget(self.empty_view)     # 0
        self._stack.addWidget(self.loading_view)   # 1
        self._stack.addWidget(self.editor_view)    # 2
        layout.addWidget(self._stack)

        self.empty_view.preset_selected.connect(self.preset_selected)
        self.empty_view.custom_clicked.connect(self.custom_clicked)
        self.loading_view.cancel_requested.connect(self.cancel_requested)

    def set_active_project(self, project_id: int | None) -> None:
        self._project_id = project_id
        self.refresh_state_from_db()

    def refresh_state_from_db(self) -> None:
        if self._project_id is None:
            self._stack.setCurrentIndex(STATE_EMPTY)
            return
        with DBSession(engine) as s:
            n = (
                s.query(TimelineEntry)
                .filter_by(project_id=self._project_id, track="video")
                .count()
            )
        self._stack.setCurrentIndex(STATE_EDITOR if n > 0 else STATE_EMPTY)

    def enter_loading(self) -> None:
        self.loading_view.reset()
        self._stack.setCurrentIndex(STATE_LOADING)

    def show_progress(self, stage_key: str, fraction: float) -> None:
        self.loading_view.set_stage(stage_key, fraction)

    def current_state(self) -> int:
        return self._stack.currentIndex()
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/workspaces/schnitt_workspace.py tests/ui/test_schnitt_workspace_states.py
git commit -m "feat(schnitt): SchnittWorkspace state manager"
```

- [ ] **Step 6: Vault-Update.**

---

## Phasen-Abschluss

Phase 04 fertig. Skelett steht. Sub-Tabs werden ab Phase 05 ausgemalt.

Nächste Phase: [05_SUBTAB_SCHNITT.md](05_SUBTAB_SCHNITT.md).
