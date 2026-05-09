"""SchnittWorkspace — Master-Tab für Auto-Schnitt + Review (Redesign 2026-05-09).
Drei States: Empty (Quick-Lane) / Loading (Worker laeuft) / Editor (Sub-Tabs).

Plan-Abweichung: `database.session.DBSession` existiert im Repo nicht — wir
nutzen `sqlalchemy.orm.Session` (alias DBSession), konsistent mit Phase 02/03.
"""
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from sqlalchemy.orm import Session as DBSession

from database import engine
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
