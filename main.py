# main.py (In VS Code einfügen und speichern)
"""
PB_studio v0.4.0 — DaVinci Resolve Style UI Rebuild
=====================================================
4 Arbeitsbereiche: MEDIA | EDIT | CONVERT | DELIVER
Bottom-Navigationsleiste wie DaVinci Resolve.
Optimierte Timeline mit Caching.
"""

from dotenv import load_dotenv
load_dotenv()

import gc
import sys
import subprocess
import time
import logging
import traceback
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QStatusBar, QDockWidget, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QFileDialog, QHeaderView,
    QProgressBar, QLabel, QLineEdit, QSlider, QGroupBox,
    QComboBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QDialog, QFrame,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QStackedWidget,
    QSizePolicy, QSpacerItem, QMenu, QGraphicsPolygonItem, QSpinBox, QDoubleSpinBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QBrush, QPen, QPixmap, QImage, QPolygonF, QAction

# NEU: PB Studio Gold-Accent Theme (ersetzt qt_material)
from ui.theme import get_stylesheet

APP_VERSION = "0.5.0"

logger = logging.getLogger(__name__)

# Globale Thread-Registry: hält Referenzen auf aktive QThread/Worker-Paare,
# damit sie nicht vorzeitig garbage-collected werden.
_GLOBAL_ACTIVE_THREADS: list[tuple] = []
STYLE_DIR = Path(__file__).parent / "styles"
RESOURCE_DIR = Path(__file__).parent / "resources"

from database import init_db, engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, WaveformData, ClipAnchor
from sqlalchemy.orm import Session as DBSession
import json as _json
from services.ingest_service import (
    get_all_media, get_all_audio, get_all_video,
    delete_all_media, delete_selected_media, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
import os
from services.pacing_service import (
    PacingSettings, calculate_cut_points, CutPoint, auto_edit_to_beats,
    AdvancedPacingSettings, generate_keyframe_strings_for_project,
)
from services.export_service import get_timeline_summary
from services.timeline_service import TimelineService, PB_NS
from ui.chat_dock import ChatDock
from ui.waveform_item import WaveformGraphicsItem


# ======================================================================
# Task-Engine (extracted to services/task_manager.py)
# ======================================================================
import services.task_manager as _task_manager_module
from services.task_manager import TaskInfo, GlobalTaskManager

# Modul-Level task_manager — Proxy-Objekt das immer auf den Singleton delegiert.
# Verhindert AttributeError wenn vor main() zugegriffen wird.
class _TaskManagerProxy:
    """Proxy: Leitet alle Attribut-Zugriffe an GlobalTaskManager.instance() weiter."""
    def __getattr__(self, name):
        return getattr(GlobalTaskManager.instance(), name)
task_manager = _TaskManagerProxy()


# ======================================================================
# Background Workers (extracted to workers/ package)
# ======================================================================
from workers import (
    CancellableMixin,
    AnalysisWorker, WaveformAnalysisWorker,
    VideoAnalysisWorker, VideoBatchAnalysisWorker, VideoAnalysisPipelineWorker, FrameExtractWorker,
    StemSeparationWorker, AutoDuckingWorker,
    ExportWorker, FolderImportWorker, BatchConvertWorker, ProxyCreationWorker,
    AutoEditWorker, SemanticSearchWorker,
    DummyProgressWorker,
)


# Command Pattern: Worker-Registry (side-effect import registriert alle Worker)
import workers.registry  # noqa: F401


# ======================================================================
# UI Widgets (extracted to ui/ submodules)
# ======================================================================
from ui.timeline import (
    AnchorMarkerItem, TimelineClipItem, InteractiveTimeline,
    PIXELS_PER_SECOND, TRACK_HEIGHT, AUDIO_TRACK_Y, VIDEO_TRACK_Y,
    CUT_MARKERS_Y, RULER_Y,
)
from ui.widgets.pacing_curve import PacingCurveWidget
from ui.widgets.video_preview import VideoPreviewWidget
from ui.widgets.task_manager_dock import TaskManagerDock
from ui.widgets.nav_bar import WorkspaceNavBar
from ui.dialogs.about import AboutDialog
from ui.dialogs.project_dialog import NewProjectDialog, OpenProjectDialog
from services.project_manager import ProjectManager
from ui.widgets.resource_monitor import ResourceMonitorWidget
from ui.mixins import (
    AudioAnalysisMixin, VideoAnalysisMixin, EditWorkspaceMixin,
    ImportMediaMixin, ConvertMixin, ExportMixin, StemsMixin, SearchMixin,
)



# Hauptfenster — DaVinci Resolve Style
# ======================================================================

class PBWindow(QMainWindow, AudioAnalysisMixin, VideoAnalysisMixin,
               EditWorkspaceMixin, ImportMediaMixin, ConvertMixin,
               ExportMixin, StemsMixin, SearchMixin):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"PB_studio v{APP_VERSION} — Director's Cockpit")
        self.resize(1500, 900)
        self._active_threads: list[QThread] = []
        self._active_workers: list[QObject] = []
        self._otio_timeline_service: TimelineService | None = None
        self._refresh_pending = False  # debounce flag for _refresh_media_table
        self._project_manager = ProjectManager(self)
        self._project_manager.project_changed.connect(self._on_project_changed)

        # Zentrales Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Bar (minimal) ──
        top_bar = QWidget()
        top_bar.setObjectName("top_bar")
        top_bar.setFixedHeight(36)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)

        app_title = QLabel(f"PB_studio v{APP_VERSION}")
        app_title.setStyleSheet("color: #e8e6e3; font-weight: 700; font-size: 13px; background: transparent;")
        top_layout.addWidget(app_title)

        # ── Project buttons ──
        proj_btn_style = (
            "QPushButton { color: #9ca3af; font-size: 10px; font-weight: 600; "
            "border: 1px solid rgba(255,255,255,12); border-radius: 3px; padding: 2px 10px; "
            "background: #161c26; min-height: 22px; }"
            "QPushButton:hover { color: #e8e6e3; border-color: #d4a44a; background: #1e2632; }"
        )
        btn_new_project = QPushButton("+ Neu")
        btn_new_project.setFixedHeight(24)
        btn_new_project.setStyleSheet(proj_btn_style)
        btn_new_project.setToolTip("Neues Projekt erstellen")
        btn_new_project.clicked.connect(self._new_project)
        top_layout.addWidget(btn_new_project)

        btn_open_project = QPushButton("Oeffnen")
        btn_open_project.setFixedHeight(24)
        btn_open_project.setStyleSheet(proj_btn_style)
        btn_open_project.setToolTip("Bestehendes Projekt oeffnen")
        btn_open_project.clicked.connect(self._open_project)
        top_layout.addWidget(btn_open_project)

        btn_save_as = QPushButton("Speichern unter")
        btn_save_as.setFixedHeight(24)
        btn_save_as.setStyleSheet(proj_btn_style)
        btn_save_as.setToolTip("Projekt unter neuem Namen speichern")
        btn_save_as.clicked.connect(self._save_project_as)
        top_layout.addWidget(btn_save_as)

        self._project_name_label = QLabel("")
        self._project_name_label.setStyleSheet(
            "color: #d4a44a; font-size: 11px; font-weight: 600; background: transparent; padding: 0 8px;"
        )
        top_layout.addWidget(self._project_name_label)

        top_layout.addStretch()

        # ── Panel toggle buttons (DaVinci-style) ──
        toggle_style = (
            "QPushButton { color: #6b7280; font-size: 9px; font-weight: 600; "
            "border: 1px solid rgba(255,255,255,15); border-radius: 3px; padding: 2px 8px; "
            "background: #0f1318; min-height: 24px; }"
            "QPushButton:checked { color: #e8e6e3; border-color: #d4a44a; background: #1e2632; }"
            "QPushButton:hover { border-color: rgba(255,255,255,25); color: #9ca3af; }"
        )
        self._btn_toggle_tasks = QPushButton("Tasks")
        self._btn_toggle_tasks.setCheckable(True)
        self._btn_toggle_tasks.setChecked(True)
        self._btn_toggle_tasks.setFixedHeight(24)
        self._btn_toggle_tasks.setStyleSheet(toggle_style)
        self._btn_toggle_tasks.setToolTip("Hintergrund-Tasks ein/ausblenden")
        top_layout.addWidget(self._btn_toggle_tasks)

        self._btn_toggle_console = QPushButton("Konsole")
        self._btn_toggle_console.setCheckable(True)
        self._btn_toggle_console.setChecked(True)
        self._btn_toggle_console.setFixedHeight(24)
        self._btn_toggle_console.setStyleSheet(toggle_style)
        self._btn_toggle_console.setToolTip("System-Konsole ein/ausblenden")
        top_layout.addWidget(self._btn_toggle_console)

        self._btn_toggle_chat = QPushButton("KI Chat")
        self._btn_toggle_chat.setCheckable(True)
        self._btn_toggle_chat.setChecked(False)
        self._btn_toggle_chat.setFixedHeight(24)
        self._btn_toggle_chat.setStyleSheet(toggle_style)
        self._btn_toggle_chat.setToolTip("KI-Chat Panel ein/ausblenden")
        top_layout.addWidget(self._btn_toggle_chat)

        btn_about = QPushButton("About")
        btn_about.setMaximumWidth(80)
        btn_about.setFixedHeight(28)
        btn_about.setToolTip("Informationen ueber PB_studio anzeigen (Version, Technologie, Credits)")
        btn_about.clicked.connect(self._show_about)
        top_layout.addWidget(btn_about)

        main_layout.addWidget(top_bar)

        # ── Trennlinie ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,6);")
        main_layout.addWidget(sep)

        # ── Workspace (volle Flaeche — dominiert das Fenster) ──
        self.workspace_stack = QStackedWidget()
        self._create_workspaces()

        # ── Vertikaler QSplitter: Workspace oben | System-Panel unten ──
        # Der Benutzer kann den Splitter fast ganz nach unten schieben.
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.setChildrenCollapsible(True)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.addWidget(self.workspace_stack)

        # Unteres Panel: horizontaler QSplitter (Tasks | Konsole)
        self._bottom_panel = QWidget()
        self._bottom_panel.setObjectName("bottom_panel")
        self._bottom_panel.setMinimumHeight(24)
        _bp_layout = QHBoxLayout(self._bottom_panel)
        _bp_layout.setContentsMargins(0, 0, 0, 0)
        _bp_layout.setSpacing(0)
        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        _bp_layout.addWidget(self._inner_splitter)
        self._main_splitter.addWidget(self._bottom_panel)

        main_layout.addWidget(self._main_splitter, stretch=1)

        # ── Bottom Navigation Bar (DaVinci Style) ──
        self.nav_bar = WorkspaceNavBar()
        self.nav_bar.workspace_changed.connect(self.workspace_stack.setCurrentIndex)
        main_layout.addWidget(self.nav_bar)

        # ── Status Bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"PB_studio v{APP_VERSION} | System bereit")

        # ── Resource Monitor (CPU / RAM / GPU) ──
        resource_monitor = ResourceMonitorWidget()
        self.statusBar().addPermanentWidget(resource_monitor)

        # ── Panel Widgets (Tasks + Konsole als QSplitter, Chat als Dock) ──
        self.setup_task_dock()
        self.setup_console()
        self.setup_chat_dock()

        # Splitter-Groessen: Workspace dominiert, Console minimal
        # User kann Splitter fast ganz nach unten schieben
        self._main_splitter.setSizes([850, 60])
        self._inner_splitter.setSizes([400, 600])

        # Wire toggle buttons to panel visibility
        self._btn_toggle_tasks.toggled.connect(self._task_panel_widget.setVisible)
        self._btn_toggle_console.toggled.connect(self._console_panel_widget.setVisible)
        self._btn_toggle_chat.toggled.connect(self.chat_dock.setVisible)
        # Sync chat dock close (X) back to toggle button
        self.chat_dock.visibilityChanged.connect(self._btn_toggle_chat.setChecked)

        self._refresh_media_table()

    # ── Thread-safe UI helpers ────────────────────────────────────────

    def _console_append(self, text: str) -> None:
        """Thread-safe console append via QTimer."""
        QTimer.singleShot(0, lambda: self.console_text.append(text))

    def _refresh_media_table_debounced(self) -> None:
        """Debounced media table refresh — coalesces rapid calls."""
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(200, self._do_refresh_media_table)

    def _do_refresh_media_table(self) -> None:
        """Fuehrt die verzögerte Aktualisierung der Media-Tabelle aus."""
        self._refresh_pending = False
        self._refresh_media_table()

    def closeEvent(self, event):
        # 0. Check for running tasks and ask user
        try:
            tm = GlobalTaskManager.instance()
            running = [t for t in tm.get_all_tasks() if t.status == "running"]
            if running:
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, "Laufende Tasks",
                    f"{len(running)} Task(s) laufen noch. Trotzdem beenden?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    event.ignore()
                    return
        except Exception:
            pass

        # 1. Stop background timers
        if hasattr(self, '_task_mgr_dock') and hasattr(self._task_mgr_dock, '_timer'):
            self._task_mgr_dock._timer.stop()

        # 2. Alle Tasks im GlobalTaskManager abbrechen
        try:
            tm = GlobalTaskManager.instance()
            for task in tm.get_all_tasks():
                if task.status == "running":
                    tm.cancel_task(task.task_id)
        except Exception:
            pass

        # 2. Legacy: direkt verwaltete Threads stoppen
        for thread in list(self._active_threads):
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(1000)
        self._active_threads.clear()
        self._active_workers.clear()
        # Globale Liste beim Schliessen ebenfalls leeren
        _GLOBAL_ACTIVE_THREADS.clear()

        # 3. Video Preview stoppen (verhindert Thread-Leak + DB-Error)
        if hasattr(self, "video_preview"):
            try:
                self.video_preview.stop()
            except Exception:
                pass

        # 4. Stem Player aufraeumen
        if hasattr(self, "stem_player"):
            self.stem_player.cleanup()

        # 4. GPU-VRAM freigeben
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
        except Exception:
            pass

        # 5. Close DB connection pool
        try:
            from database import engine
            engine.dispose()
        except Exception:
            pass

        super().closeEvent(event)


    # ==================================================================
    # Project management
    # ==================================================================

    def _new_project(self):
        """Show NewProjectDialog and create a new project."""
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        try:
            self._project_manager.create_project(
                path=vals["path"],
                name=vals["name"],
                resolution=vals["resolution"],
                fps=vals["fps"],
            )
            self._console_append(f"[Projekt] Neues Projekt erstellt: {vals['name']}")
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", str(exc))
            self._console_append(f"[Projekt-Fehler] {exc}")

    def _open_project(self):
        """Show OpenProjectDialog and open an existing project."""
        dlg = OpenProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        path = dlg.get_path()
        try:
            meta = self._project_manager.open_project(path)
            self._console_append(f"[Projekt] Geoeffnet: {meta.get('name', path.name)}")
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", str(exc))
            self._console_append(f"[Projekt-Fehler] {exc}")

    def _save_project_as(self):
        """Save the current project to a new location."""
        from PySide6.QtWidgets import QInputDialog
        folder = QFileDialog.getExistingDirectory(
            self, "Zielordner waehlen",
        )
        if not folder:
            return
        name, ok = QInputDialog.getText(
            self, "Projektname", "Name fuer das neue Projekt:",
        )
        if not ok or not name.strip():
            return
        target = Path(folder) / name.strip()
        try:
            self._project_manager.save_project_as(target)
            self._console_append(f"[Projekt] Gespeichert unter: {target}")
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", str(exc))
            self._console_append(f"[Projekt-Fehler] {exc}")

    def _on_project_changed(self, path):
        """Refresh all UI after a project switch."""
        path = Path(path)
        project_name = path.name
        self._project_name_label.setText(project_name)
        self.setWindowTitle(f"PB_studio v{APP_VERSION} — {project_name}")
        self._refresh_media_table()
        self._refresh_director_combos()
        # Reload timeline from new DB
        try:
            self.timeline_view.load_from_db()
        except Exception:
            pass
        self.status_bar.showMessage(f"Projekt: {project_name}  |  {path}")

    def _show_about(self):
        dialog = AboutDialog(version=APP_VERSION, parent=self)
        dialog.exec()


    # ==================================================================
    # Workspace creation (UI in ui/workspaces/, signals wired here)
    # ==================================================================

    def _create_workspaces(self):
        """Creates all 5 workspaces, promotes widgets, wires signals."""
        from ui.workspaces import (
            MediaWorkspace, EditWorkspace, StemsWorkspace,
            ConvertWorkspace, DeliverWorkspace,
        )

        # --- MEDIA workspace ---
        self._media_ws = MediaWorkspace()
        self.workspace_stack.addWidget(self._media_ws)

        # Promote widgets for backward compat
        self.btn_analyze = self._media_ws.btn_analyze
        self.btn_analyze_video = self._media_ws.btn_analyze_video
        self.btn_video_pipeline = self._media_ws.btn_video_pipeline
        self.btn_waveform = self._media_ws.btn_waveform
        self.btn_stem_separate = self._media_ws.btn_stem_separate
        self.btn_auto_duck = self._media_ws.btn_auto_duck
        self.btn_add_to_timeline = self._media_ws.btn_add_to_timeline
        self.progress_bar = self._media_ws.progress_bar
        self.search_input = self._media_ws.search_input
        self.btn_search = self._media_ws.btn_search
        self.btn_search_clear = self._media_ws.btn_search_clear
        self.btn_select_all_video = self._media_ws.btn_select_all_video
        self.video_pool_table = self._media_ws.video_pool_table
        self.btn_delete_selected_video = self._media_ws.btn_delete_selected_video
        self.btn_select_all_audio = self._media_ws.btn_select_all_audio
        self.audio_pool_table = self._media_ws.audio_pool_table
        self.btn_delete_selected_audio = self._media_ws.btn_delete_selected_audio
        self.stem_player = self._media_ws.stem_player
        self.media_table = self._media_ws.media_table

        # Wire MEDIA signals
        self._media_ws.btn_import_video.clicked.connect(self._import_video)
        self._media_ws.btn_import_audio.clicked.connect(self._import_audio)
        self._media_ws.btn_import_folder.clicked.connect(self._import_folder)
        self._media_ws.btn_clear_all.clicked.connect(self._clear_all_media)
        self.btn_analyze.clicked.connect(self._analyze_selected_audio)
        self.btn_analyze_video.clicked.connect(self._analyze_selected_video)
        self.btn_video_pipeline.clicked.connect(self._start_video_pipeline)
        self.btn_waveform.clicked.connect(self._analyze_waveform)
        self.btn_stem_separate.clicked.connect(self._start_stem_separation)
        self.btn_auto_duck.clicked.connect(self._start_auto_ducking)
        self.btn_add_to_timeline.clicked.connect(self._add_selected_to_timeline)
        self.search_input.returnPressed.connect(self._run_semantic_search)
        self.btn_search.clicked.connect(self._run_semantic_search)
        self.btn_search_clear.clicked.connect(self._clear_search)
        self.btn_select_all_video.clicked.connect(
            lambda: self._toggle_all_checkboxes(self.video_pool_table)
        )
        self.btn_select_all_audio.clicked.connect(
            lambda: self._toggle_all_checkboxes(self.audio_pool_table)
        )
        self.btn_delete_selected_video.clicked.connect(
            lambda: self._delete_selected_media("video")
        )
        self.btn_delete_selected_audio.clicked.connect(
            lambda: self._delete_selected_media("audio")
        )
        self.video_pool_table.currentCellChanged.connect(self._on_video_pool_selected)
        self.audio_pool_table.currentCellChanged.connect(self._on_audio_pool_selected)
        self.stem_player.playback_finished.connect(self._on_stem_playback_finished)

        # Phase 4: Neue Media-Buttons (Stubs — Backend noch nicht implementiert)
        if hasattr(self._media_ws, 'btn_key_detect'):
            self._media_ws.btn_key_detect.clicked.connect(self._detect_key)
        if hasattr(self._media_ws, 'btn_lufs_analyze'):
            self._media_ws.btn_lufs_analyze.clicked.connect(self._analyze_lufs)
        if hasattr(self._media_ws, 'btn_structure_detect'):
            self._media_ws.btn_structure_detect.clicked.connect(self._detect_structure)
        if hasattr(self._media_ws, 'btn_motion_analysis'):
            self._media_ws.btn_motion_analysis.clicked.connect(self._analyze_selected_video)
        if hasattr(self._media_ws, 'btn_siglip_embeddings'):
            self._media_ws.btn_siglip_embeddings.clicked.connect(self._start_video_pipeline)

        # --- EDIT workspace ---
        self._edit_ws = EditWorkspace()
        self.workspace_stack.addWidget(self._edit_ws)

        # Promote widgets
        self.video_preview = self._edit_ws.video_preview
        self.btn_preview_play = self._edit_ws.btn_preview_play
        self.btn_preview_stop = self._edit_ws.btn_preview_stop
        self.preview_time_label = self._edit_ws.preview_time_label
        self.btn_toggle_inspector = self._edit_ws.btn_toggle_inspector
        self.inspector_panel = self._edit_ws.inspector_panel
        self.audio_combo = self._edit_ws.audio_combo
        self.video_combo = self._edit_ws.video_combo
        self.vibe_input = self._edit_ws.vibe_input
        self.cut_rate_combo = self._edit_ws.cut_rate_combo
        self.energy_reactivity_slider = self._edit_ws.energy_reactivity_slider
        self.energy_reactivity_spin = self._edit_ws.energy_reactivity_spin
        self.breakdown_combo = self._edit_ws.breakdown_combo
        self.tempo_slider = self._edit_ws.tempo_slider
        self.energy_slider = self._edit_ws.energy_slider
        self.density_slider = self._edit_ws.density_slider
        self.btn_generate = self._edit_ws.btn_generate
        self.btn_auto_edit = self._edit_ws.btn_auto_edit
        self.anchor_list = self._edit_ws.anchor_list
        self.btn_add_anchor = self._edit_ws.btn_add_anchor
        self.btn_remove_anchor = self._edit_ws.btn_remove_anchor
        self.btn_sync_anchors = self._edit_ws.btn_sync_anchors
        self.btn_learn_ai = self._edit_ws.btn_learn_ai
        self.btn_keyframe_string = self._edit_ws.btn_keyframe_string
        self.keyframe_text = self._edit_ws.keyframe_text
        self.pacing_curve = self._edit_ws.pacing_curve
        self.timeline_view = self._edit_ws.timeline_view
        self.cut_info_label = self._edit_ws.cut_info_label

        # Wire EDIT signals
        self.btn_preview_play.clicked.connect(self._toggle_preview_play)
        self.btn_preview_stop.clicked.connect(self.video_preview.stop)
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        self.video_combo.currentIndexChanged.connect(self._on_video_combo_changed)
        self.audio_combo.currentIndexChanged.connect(self._on_audio_combo_changed)
        self.btn_generate.clicked.connect(self._generate_timeline)
        self.btn_auto_edit.clicked.connect(self._auto_edit_to_beat)
        self.btn_add_anchor.clicked.connect(self._add_anchor_dialog)
        self.btn_remove_anchor.clicked.connect(self._remove_selected_anchor)
        self.btn_sync_anchors.clicked.connect(self._sync_anchors)
        self.btn_learn_ai.clicked.connect(self._learn_anchor_as_ai_rule)
        self.btn_keyframe_string.clicked.connect(self._show_keyframe_strings)
        # Phase 4: RL Feedback + Style Preset
        if hasattr(self._edit_ws, 'btn_thumbs_up'):
            self._edit_ws.btn_thumbs_up.clicked.connect(self._rl_feedback_positive)
        if hasattr(self._edit_ws, 'btn_thumbs_down'):
            self._edit_ws.btn_thumbs_down.clicked.connect(self._rl_feedback_negative)
        if hasattr(self._edit_ws, 'style_preset_combo'):
            self._edit_ws.style_preset_combo.currentIndexChanged.connect(self._apply_style_preset)
        self.timeline_view.clip_moved.connect(self._on_timeline_clip_moved)
        # VideoPreview: position label + play-button icon state
        self.video_preview.position_changed.connect(self._on_preview_position_changed)
        self.video_preview.playback_state_changed.connect(self._on_preview_state_changed)
        self._refresh_director_combos()

        # --- STEMS workspace ---
        self._stems_ws = StemsWorkspace()
        self.workspace_stack.addWidget(self._stems_ws)
        self.stem_workspace = self._stems_ws.stem_widget

        # Wire STEMS signals
        self.stem_workspace.stem_volume_changed.connect(self.stem_player.set_volume)
        self.stem_workspace.stem_mute_toggled.connect(self.stem_player.set_mute)
        self.stem_workspace.play_requested.connect(self.stem_player.play)
        self.stem_workspace.pause_requested.connect(self.stem_player.pause)
        self.stem_workspace.stop_requested.connect(self.stem_player.stop)
        self.stem_workspace.seek_requested.connect(self.stem_player.seek)
        self.stem_player.position_changed.connect(self.stem_workspace.update_position)
        self.stem_player.state_changed.connect(self.stem_workspace.update_playback_state)

        # --- CONVERT workspace ---
        self._convert_ws = ConvertWorkspace()
        self.workspace_stack.addWidget(self._convert_ws)

        # Promote widgets
        self.convert_resolution = self._convert_ws.convert_resolution
        self.convert_fps = self._convert_ws.convert_fps
        self.convert_format = self._convert_ws.convert_format
        self.btn_standardize_all = self._convert_ws.btn_standardize_all
        self.convert_progress = self._convert_ws.convert_progress
        self.convert_log = self._convert_ws.convert_log
        self.effects_clip_combo = self._convert_ws.effects_clip_combo
        self.brightness_slider = self._convert_ws.brightness_slider
        self.brightness_label = self._convert_ws.brightness_label
        self.contrast_slider = self._convert_ws.contrast_slider
        self.contrast_label = self._convert_ws.contrast_label
        self.crossfade_slider = self._convert_ws.crossfade_slider
        self.crossfade_label = self._convert_ws.crossfade_label
        self.effects_preview = self._convert_ws.effects_preview

        # Wire CONVERT signals
        self.btn_standardize_all.clicked.connect(self._standardize_all_videos)

        # --- DELIVER workspace ---
        self._deliver_ws = DeliverWorkspace()
        self.workspace_stack.addWidget(self._deliver_ws)

        # Promote widgets
        self.production_info = self._deliver_ws.production_info
        self.export_name_input = self._deliver_ws.export_name_input
        self.resolution_combo = self._deliver_ws.resolution_combo
        self.fps_combo = self._deliver_ws.fps_combo
        self.btn_export = self._deliver_ws.btn_export
        self.btn_refresh_production = self._deliver_ws.btn_refresh_production
        self.export_progress = self._deliver_ws.export_progress
        self.export_log = self._deliver_ws.export_log

        # Wire DELIVER signals
        self.btn_export.clicked.connect(self._start_export)
        self.btn_refresh_production.clicked.connect(self._refresh_production_info)

    # Helper: Slider erstellen
    # ==================================================================

    def _create_compact_slider(self, label: str, min_val: int, max_val: int,
                               default: int):
        """Compact horizontal slider row: [Label] [=====o=====] [Value]"""
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label)
        lbl.setFixedWidth(46)
        lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        slider.setFixedHeight(16)
        row.addWidget(slider, stretch=1)
        val_lbl = QLabel(str(default))
        val_lbl.setFixedWidth(26)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        val_lbl.setStyleSheet("color: #9ca3af; font-size: 10px;")
        slider.valueChanged.connect(lambda v: val_lbl.setText(str(v)))
        row.addWidget(val_lbl)
        return slider, row

    def _toggle_inspector(self):
        """Toggle inspector panel visibility."""
        if self.inspector_panel.isVisible():
            self.inspector_panel.hide()
            self.btn_toggle_inspector.setText("\u25C0")
        else:
            self.inspector_panel.show()
            self.btn_toggle_inspector.setText("\u25B6")

    @staticmethod
    def _add_separator(layout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,6);")
        layout.addWidget(sep)

    # ==================================================================
    # Helper: Thread starten
    # ==================================================================

    def _start_worker_thread(self, worker: QObject, on_finish=None, on_error=None):
        """Legacy-Bridge: Leitet an GlobalTaskManager.start_task() weiter.

        Alle Threads werden jetzt vom TaskManager gehalten (GC-Schutz).
        Existierende Aufrufe bleiben kompatibel.

        Bug-3 Fix: Nutzt GlobalTaskManager.instance() statt globalem task_manager,
        damit Buttons auch ohne Chat-Dock-Initialisierung funktionieren.
        """
        # Worker-Name fuer Task-Anzeige aus Klasse ableiten
        worker_name = type(worker).__name__.replace("Worker", "")

        # Singleton direkt – unabhaengig vom globalen task_manager
        tm = GlobalTaskManager.instance()

        # Falls der Worker schon eine task_id hat (von manueller create_task()),
        # registrieren wir Thread+Worker im bestehenden Task.
        existing_task_id = getattr(worker, 'task_id', None)

        if existing_task_id and existing_task_id in tm._tasks:
            # Thread im bestehenden Task registrieren
            task = tm._tasks[existing_task_id]
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            if on_finish:
                def _guarded_finish(*args, _w=worker, _cb=on_finish):
                    if not getattr(_w, '_errored', False):
                        _cb(*args)
                worker.finished.connect(_guarded_finish)
            # Error-Signal: Fallback-Logger immer verbinden (stille Fehler verhindern).
            # finish_task() wird nur aufgerufen wenn WEDER ein on_error-Callback uebergeben
            # wurde NOR der error-Slot bereits manuell verbunden wurde (receiver_count > 0).
            # Dies verhindert den Doppel-Aufruf von finish_task() wenn der Caller bereits
            # eigene error-Handler (die finish_task aufrufen) vor _start_worker_thread
            # verbindet.
            _has_prior_error_cb = on_error is not None
            def _default_error_handler(*args, _tid=existing_task_id, _name=worker_name,
                                       _tm=tm, _has_cb=_has_prior_error_cb):
                err_msg = str(args[-1]) if args else "Unbekannter Fehler"
                logging.error(
                    "[TaskEngine] Worker-Fehler '%s' (task_id=%s): %s",
                    _name, _tid, err_msg,
                )
                if not _has_cb:
                    _tm.finish_task(_tid, status="error", message=err_msg)
            worker.error.connect(_default_error_handler)
            if on_error:
                worker.error.connect(on_error)

            # Progress-Signal auto-verbinden wenn vorhanden
            if hasattr(worker, "progress"):
                worker.progress.connect(
                    lambda pct, msg, _tid=existing_task_id: tm.update_task(
                        _tid, pct, message=msg
                    )
                )

            worker.finished.connect(thread.quit)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(
                lambda _tid=existing_task_id: tm._on_thread_done(_tid)
            )

            task.thread = thread
            task.worker = worker
            self._active_threads.append(thread)
            self._active_workers.append(worker)
            thread.finished.connect(
                lambda _t=thread, _w=worker: self._cleanup_worker(_t, _w)
            )
            thread.start()
            return thread
        else:
            # Neuer Task ueber die Engine
            task = tm.start_task(
                name=worker_name,
                worker=worker,
                on_finish=on_finish,
                on_error=on_error,
            )
            # Defensive: start_task() gibt str zurueck bei Cross-Thread-Routing
            if isinstance(task, str):
                self._active_workers.append(worker)
                return None
            if task.thread:
                self._active_threads.append(task.thread)
                task.thread.finished.connect(
                    lambda _t=task.thread, _w=worker: self._cleanup_worker(_t, _w)
                )
            self._active_workers.append(worker)
            return task.thread

    def _cancel_worker_for_task(self, task_id: str):
        """Cancel via TaskEngine (Singleton, nie None)."""
        GlobalTaskManager.instance().cancel_task(task_id)
        self.console_text.append(f"[System] Task abgebrochen: {task_id}")

    # ==================================================================
    # Combos aktualisieren
    # ==================================================================

    def _refresh_director_combos(self):
        media = get_all_media()
        self.audio_combo.clear()
        self.video_combo.clear()
        self.audio_combo.addItem("-- kein Audio --", None)
        self.video_combo.addItem("-- kein Video --", None)
        for item in media:
            label = f"[{item['id']}] {item['title']}"
            if item["type"] == "Audio":
                bpm = item.get("bpm")
                if bpm:
                    label += f" ({bpm} BPM)"
                self.audio_combo.addItem(label, item["id"])
            elif item["type"] == "Video":
                self.video_combo.addItem(label, item["id"])

    def _cleanup_worker(self, thread: QThread, worker: QObject):
        """Entfernt Worker/Thread aus lokalen Listen.
        GC-Schutz liegt jetzt beim GlobalTaskManager (TaskInfo haelt Referenzen).
        """
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        # Legacy-Liste auch aufräumen (falls noch Eintraege)
        pair = (thread, worker)
        if pair in _GLOBAL_ACTIVE_THREADS:
            _GLOBAL_ACTIVE_THREADS.remove(pair)

    # ==================================================================
    # Media-Tabelle
    # ==================================================================

    def _toggle_all_checkboxes(self, table: QTableWidget):
        """Alle Checkboxen in Spalte 0 toggeln (Alle an / Alle aus)."""
        # Pruefen ob bereits alle angehakt sind
        all_checked = True
        for row in range(table.rowCount()):
            chk = table.item(row, 0)
            if chk and chk.checkState() != Qt.CheckState.Checked:
                all_checked = False
                break

        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for row in range(table.rowCount()):
            chk = table.item(row, 0)
            if chk:
                chk.setCheckState(new_state)

    def _refresh_media_table(self, _also_combos: bool = True):
        # Einmal laden, ueberall verwenden (statt 4-6 DB-Sessions)
        videos = get_all_video()
        audios = get_all_audio()

        # Video Pool
        self.video_pool_table.setRowCount(len(videos))
        for row, item in enumerate(videos):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.video_pool_table.setItem(row, 0, chk)
            self.video_pool_table.setItem(row, 1, QTableWidgetItem(str(item["id"])))
            self.video_pool_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            self.video_pool_table.setItem(row, 3, QTableWidgetItem(item.get("resolution") or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.video_pool_table.setItem(row, 4, QTableWidgetItem(fps_str))
            self.video_pool_table.setItem(row, 5, QTableWidgetItem("-"))
            self.video_pool_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

        # Audio Pool
        self.audio_pool_table.setRowCount(len(audios))
        for row, item in enumerate(audios):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.audio_pool_table.setItem(row, 0, chk)
            self.audio_pool_table.setItem(row, 1, QTableWidgetItem(str(item["id"])))
            self.audio_pool_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.audio_pool_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            self.audio_pool_table.setItem(row, 4, QTableWidgetItem("-"))
            self.audio_pool_table.setItem(row, 5, QTableWidgetItem(item.get("stems", "-")))
            self.audio_pool_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

        # Hidden proxy table — aus bereits geladenen Daten zusammenbauen
        media = [dict(m, type="Audio") for m in audios] + [dict(m, type="Video") for m in videos]
        self.media_table.setRowCount(len(media))
        for row, item in enumerate(media):
            self.media_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.media_table.setItem(row, 1, QTableWidgetItem(item["type"]))
            self.media_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.media_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            res = item.get("resolution", "-")
            self.media_table.setItem(row, 4, QTableWidgetItem(res or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.media_table.setItem(row, 5, QTableWidgetItem(fps_str))
            stems = item.get("stems", "-")
            self.media_table.setItem(row, 6, QTableWidgetItem(stems))
            self.media_table.setItem(row, 7, QTableWidgetItem(item["file_path"]))

        # Director-Combos gleich mit aktualisieren (spart redundante DB-Abfrage)
        if _also_combos:
            self.audio_combo.clear()
            self.video_combo.clear()
            self.audio_combo.addItem("-- kein Audio --", None)
            self.video_combo.addItem("-- kein Video --", None)
            for item in media:
                label = f"[{item['id']}] {item['title']}"
                if item["type"] == "Audio":
                    bpm = item.get("bpm")
                    if bpm:
                        label += f" ({bpm} BPM)"
                    self.audio_combo.addItem(label, item["id"])
                elif item["type"] == "Video":
                    self.video_combo.addItem(label, item["id"])

    # ==================================================================
    # System-Konsole & Chat Dock
    # ==================================================================

    def setup_task_dock(self):
        """TaskManager als QWidget im unteren QSplitter-Panel."""
        self._task_mgr_dock = TaskManagerDock(self)
        self._task_mgr_dock.cancel_requested.connect(self._cancel_worker_for_task)
        task_w = self._task_mgr_dock.widget()
        task_w.setMinimumWidth(180)
        self._inner_splitter.addWidget(task_w)
        self._task_panel_widget = task_w
        # Alias fuer Kompatibilitaet
        self.task_dock = task_w

    def setup_console(self):
        """System-Konsole als QWidget im unteren QSplitter-Panel."""
        console_panel = QWidget()
        console_panel.setObjectName("console_dock")
        console_panel.setMinimumWidth(120)
        cl = QVBoxLayout(console_panel)
        cl.setContentsMargins(4, 2, 4, 4)
        cl.setSpacing(0)

        hdr = QLabel("KONSOLE")
        hdr.setStyleSheet(
            "color: #6b7280; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; background: transparent; padding: 2px 0;"
        )
        cl.addWidget(hdr)

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.document().setMaximumBlockCount(500)  # Max 500 Zeilen
        self.console_text.setToolTip(
            "System-Konsole: Zeigt alle Aktionen, Warnungen und Fehler der Anwendung in Echtzeit an"
        )
        self.console_text.append("[System] PB_studio Core Engine erfolgreich gestartet.")
        cl.addWidget(self.console_text)

        self._inner_splitter.addWidget(console_panel)
        self._console_panel_widget = console_panel
        # Alias fuer Kompatibilitaet
        self.console_dock = console_panel

    def setup_chat_dock(self):
        self.chat_dock = ChatDock(self)
        self.chat_dock.setMinimumWidth(200)
        self.chat_dock.setMaximumWidth(400)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        # Start collapsed — user can open via View menu or toggleViewAction
        self.chat_dock.setVisible(False)

        # MainWindow-Referenz für direkte Kommandos (analysiere, schneide, etc.)
        self.chat_dock.set_main_window(self)

        try:
            import services.register_actions  # noqa: F401
            from services.local_agent_service import LocalAgentService
            self._ai_agent = LocalAgentService()
            self.chat_dock.set_agent(self._ai_agent)

            # GPU-Status LAZY anzeigen — torch-Import erst beim ersten KI-Aufruf
            # (vermeidet ~11s Startup-Blockade durch sofortigen model_manager-Zugriff)
            def _show_gpu_info_deferred():
                try:
                    gpu_info = self._ai_agent.model_manager.gpu_info
                    gpu_name = gpu_info.get("name", "unbekannt")
                    vram = gpu_info.get("vram_total_mb", 0)
                    if gpu_name != "CPU" and vram > 0:
                        hw_msg = f"HARDWARE AKTIV: {gpu_name} ({vram:.0f} MB VRAM)"
                        self.console_text.append(f"[GPU] {hw_msg}")
                except Exception:
                    pass
            # Verzögert nach UI-Aufbau — blockiert nicht den Start
            QTimer.singleShot(2000, _show_gpu_info_deferred)
            self.chat_dock.append_system(
                "Agent bereit.\n"
                "Befehle: 'analysiere', 'schneide', 'gpu status'"
            )

            self.console_text.append("[KI] Chat-Assistent initialisiert (Modell wird bei erster Anfrage geladen).")
        except Exception as e:
            self.chat_dock.append_error(f"Agent konnte nicht initialisiert werden: {e}")
            self.console_text.append(f"[KI-Fehler] {e}")


def setup_logging():
    """Konfiguriert das Logging-System: Console + RotatingFileHandler fuer logs/pb_studio.log."""
    from logging.handlers import RotatingFileHandler

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "pb_studio.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler (DEBUG+)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File Handler (DEBUG+, 5 MB x 3 Dateien)
    fh = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.info("Logging initialisiert → %s", log_file)


def _global_exception_hook(exc_type, exc_value, exc_tb):
    """Faengt unhandled Exceptions ab, loggt sie und verhindert lautloses Sterben."""
    import traceback as _tb
    msg = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("UNHANDLED EXCEPTION:\n%s", msg)
    print(f"\n{'='*60}\n  CRASH — Unhandled Exception\n{'='*60}\n{msg}", flush=True)
    # Nicht sys.exit() — Qt soll Chance zum Cleanup haben


def main():
    setup_logging()

    # Globaler Exception-Hook: Crashes nie verschlucken
    sys.excepthook = _global_exception_hook

    # Auch fuer Worker-Threads: unhandled exceptions loggen
    import threading
    _orig_excepthook = threading.excepthook
    def _thread_exception_hook(args):
        logging.critical(
            "THREAD CRASH [%s]: %s",
            args.thread.name if args.thread else "?",
            args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        print(f"\n[THREAD CRASH] {args.thread}: {args.exc_value}", flush=True)
        if _orig_excepthook:
            _orig_excepthook(args)
    threading.excepthook = _thread_exception_hook

    try:
        init_db()
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.critical("Datenbank-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        print(f"[FATAL] DB-Init fehlgeschlagen: {exc}")
        sys.exit(1)

    app = QApplication(sys.argv)

    # TaskManager als erstes erstellen und an QApplication verankern
    _tm = GlobalTaskManager.instance()
    _task_manager_module.task_manager = _tm  # Modul-Level fuer andere Imports
    app.task_manager = _tm

    # NEU: PB Studio v0.5 Gold-Accent Dark Theme
    app.setStyleSheet(get_stylesheet())

    # Startup Dependency Check (laeuft VOR PBWindow, parallel, <2s)
    from services.startup_checks import check_system
    from ui.dialogs.startup_check_dialog import maybe_show_startup_dialog
    _sys_status = check_system()
    app.system_status = _sys_status
    maybe_show_startup_dialog(_sys_status)

    try:
        window = PBWindow()
    except Exception as exc:
        logging.critical("Fenster-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        print(f"[FATAL] Fenster konnte nicht erstellt werden: {exc}")
        traceback.print_exc()
        sys.exit(1)

    window.console_text.append("[System] SQLite Datenbank (pb_studio.db) erfolgreich initialisiert.")
    window.console_text.append("[System] PB Studio Gold-Accent Theme aktiv — v0.5 Design.")
    window.console_text.append(f"[System] Version {APP_VERSION} — Workspace UI + KI-Pacing + Beat-Snap.")
    window.console_text.append(f"[System] {_sys_status.status_bar_text()}")
    window.status_bar.showMessage(f"PB_studio v{APP_VERSION}  |  {_sys_status.status_bar_text()}")
    window.showMaximized()
    # Timeline-Daten NACH dem Fenster laden (non-blocking Startup)
    QTimer.singleShot(0, window.timeline_view.load_from_db)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()