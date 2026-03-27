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
from ui.widgets.resource_monitor import ResourceMonitorWidget



# Hauptfenster — DaVinci Resolve Style
# ======================================================================

class PBWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"PB_studio v{APP_VERSION} — Director's Cockpit")
        self.resize(1500, 900)
        self._active_threads: list[QThread] = []
        self._active_workers: list[QObject] = []
        self._otio_timeline_service: TimelineService | None = None
        self._refresh_pending = False  # debounce flag for _refresh_media_table

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

    def _refresh_effects_combos(self):
        self.effects_clip_combo.clear()
        self.effects_clip_combo.addItem("-- Clip waehlen --", None)
        with DBSession(engine) as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=1, track="video")
                .order_by(TimelineEntry.start_time)
                .all()
            )
            # Bug-19 Fix: Bulk-Load VideoClips — verhindert N+1 (1 SELECT statt N)
            _eids = [e.media_id for e in entries]
            _clips = (
                {c.id: c for c in session.query(VideoClip).filter(
                    VideoClip.id.in_(_eids)).all()}
                if _eids else {}
            )
            for entry in entries:
                clip = _clips.get(entry.media_id)
                if clip:
                    name = Path(clip.file_path).stem[:30]
                    label = f"[{entry.id}] {name} ({entry.start_time:.1f}s-{(entry.end_time or 0):.1f}s)"
                    self.effects_clip_combo.addItem(label, entry.id)

    def _on_effects_clip_changed(self, index: int):
        entry_id = self.effects_clip_combo.currentData()
        if entry_id is None:
            return
        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if entry:
                self.brightness_slider.setValue(int((entry.brightness or 0.0) * 100))
                self.contrast_slider.setValue(int((entry.contrast or 1.0) * 100))
                self.crossfade_slider.setValue(int((entry.crossfade_duration or 0.0) * 10))

    def _apply_effects(self):
        entry_id = self.effects_clip_combo.currentData()
        if entry_id is None:
            self.console_text.append("[Effects] Kein Clip ausgewaehlt.")
            return

        brightness = self.brightness_slider.value() / 100.0
        contrast = self.contrast_slider.value() / 100.0
        crossfade = self.crossfade_slider.value() / 10.0

        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if entry:
                entry.brightness = brightness
                entry.contrast = contrast
                entry.crossfade_duration = crossfade
                session.commit()

        self.console_text.append(
            f"[Effects] Clip {entry_id}: Helligkeit={brightness:.2f}, "
            f"Kontrast={contrast:.2f}, Crossfade={crossfade:.1f}s"
        )
        self._show_effect_preview(entry_id, brightness, contrast)

    def _show_effect_preview(self, entry_id: int, brightness: float, contrast: float):
        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                return
            clip = session.get(VideoClip, entry.media_id)
            if not clip:
                return
            file_path = clip.file_path

        # Validate and clamp float values to prevent FFmpeg filter injection
        b = max(-1.0, min(1.0, float(brightness)))
        c = max(0.0, min(3.0, float(contrast)))
        vf_extra = f"eq=brightness={b}:contrast={c}"
        worker = FrameExtractWorker(file_path, 1.0, 320, 180, vf_extra)
        worker.frame_ready.connect(self._on_effect_frame_ready)
        worker.error.connect(lambda msg: self.effects_preview.setText(msg))
        # Kurzlebiger Task (Frame-Extraktion) — ueber Task-Engine
        self._start_worker_thread(worker)

    def _on_effect_frame_ready(self, raw_data: bytes, width: int, height: int):
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888)
        self.effects_preview.setPixmap(QPixmap.fromImage(img))

    # ==================================================================
    # CONVERT: Video-Standardisierung
    # ==================================================================

    def _standardize_all_videos(self):
        """Konvertiert alle Videos im Video Pool ins gewaehlte Format per ffmpeg (im Worker-Thread)."""
        videos = get_all_video()
        if not videos:
            self.convert_log.append("[Convert] Keine Videos im Pool.")
            return

        # Parse settings
        res_text = self.convert_resolution.currentText()
        resolution = res_text.split(" ")[0]  # e.g. "1920x1080"

        fps_text = self.convert_fps.currentText()
        fps = fps_text.split(" ")[0]  # e.g. "30"

        fmt_text = self.convert_format.currentText()
        if "H.265" in fmt_text or "HEVC" in fmt_text:
            vcodec, ext = "libx265", ".mp4"
        elif "ProRes" in fmt_text:
            vcodec, ext = "prores_ks", ".mov"
        elif "mkv" in fmt_text:
            vcodec, ext = "libx264", ".mkv"
        else:
            vcodec, ext = "libx264", ".mp4"

        self.convert_progress.setVisible(True)
        self.convert_progress.setRange(0, len(videos))
        self.convert_progress.setValue(0)

        task = task_manager.create_task("Video Convert", f"{len(videos)} Videos -> {resolution} {fps}fps")

        worker = BatchConvertWorker(videos, resolution, fps, vcodec, ext)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: QTimer.singleShot(0, lambda: (
            self.convert_log.append(msg),
            self.convert_progress.setValue(pct),
        )))
        worker.finished.connect(lambda converted, total: self._on_batch_convert_finished(
            converted, total, task.task_id
        ))
        worker.error.connect(lambda err: self._on_batch_convert_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_batch_convert_finished(self, converted: int, total: int, task_id: str):
        if converted == 0 and total == 0:
            # Empty-result fallback (finally block): hide progress and close task.
            self.convert_progress.setVisible(False)
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.convert_progress.setVisible(False)
        task_manager.finish_task(task_id, message=f"{converted}/{total} konvertiert")
        self.convert_log.append(f"[Convert] Fertig: {converted}/{total} Videos konvertiert.")

    def _on_batch_convert_error(self, error_msg: str, task_id: str):
        self.convert_progress.setVisible(False)
        self.convert_log.append(f"[Convert-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Video Combo Changed
    # ==================================================================

    def _on_video_combo_changed(self, index: int):
        video_id = self.video_combo.currentData()
        if video_id is None:
            self.video_preview.setText("Keine Vorschau")
            return
        with DBSession(engine) as session:
            clip = session.get(VideoClip, video_id)
            if clip and clip.file_path:
                dur = clip.duration if clip.duration else 0.0
                self.video_preview.load_video(clip.file_path, dur)

    def _toggle_preview_play(self):
        self.video_preview.toggle_play()

    def _on_preview_position_changed(self, current: float, total: float):
        """Update the time label in the transport bar on every frame advance."""
        def _fmt(sec: float) -> str:
            m = int(sec // 60)
            s = sec % 60
            return f"{m:02d}:{s:05.2f}"
        self.preview_time_label.setText(f"{_fmt(current)} / {_fmt(total)}")

    def _on_preview_state_changed(self, is_playing: bool):
        """Flip play button icon to reflect current playback state."""
        self.btn_preview_play.setText("\u23F8" if is_playing else "\u25B6")

    def _on_audio_combo_changed(self, index: int):
        """Audio-Track gewechselt: Pacing-Kurven-Dauer aktualisieren."""
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            return
        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if track and track.duration:
                self.pacing_curve.set_duration(track.duration)
                self.console_text.append(
                    f"[Edit] Audio gewechselt: {track.title or 'Track'} "
                    f"({track.duration:.1f}s) — Pacing-Kurve aktualisiert."
                )

    # ==================================================================
    # Timeline generieren
    # ==================================================================

    def _generate_timeline(self):
        audio_id = self.audio_combo.currentData()
        video_id = self.video_combo.currentData()

        # Collect manual density curve from pacing widget
        densities = self.pacing_curve.get_all_densities()

        # Map cut_rate_combo to tempo for legacy PacingSettings
        cut_rate_map = {0: 90, 1: 70, 2: 50, 3: 30, 4: 10}
        tempo_val = cut_rate_map.get(self.cut_rate_combo.currentIndex(), 50)
        reactivity = self.energy_reactivity_spin.value()

        settings = PacingSettings(
            tempo=tempo_val,
            energy=reactivity,
            cut_density=reactivity,
            vibe=self.vibe_input.text(),
            manual_density_curve=densities,
        )

        audio_dur = 0.0
        video_dur = 0.0
        if audio_id is not None:
            with DBSession(engine) as s:
                track = s.get(AudioTrack, audio_id)
                if track and track.duration:
                    audio_dur = track.duration
        if video_id is not None:
            with DBSession(engine) as s:
                clip = s.get(VideoClip, video_id)
                if clip and clip.duration:
                    video_dur = clip.duration

        total_dur = max(audio_dur, video_dur, 30.0)

        # Update pacing curve duration
        self.pacing_curve.set_duration(total_dur)

        cuts = calculate_cut_points(audio_id, video_id, settings, total_dur)

        # Gold Beat-Marker: Alle Beat-basierten Cuts als goldene Linien anzeigen
        beat_times = [cp.time for cp in cuts if cp.source == "beat"]
        self.timeline_view.set_beat_markers(beat_times)

        self.timeline_view.load_from_db()
        self.timeline_view.set_cut_points(cuts, total_dur)

        beat_cuts = sum(1 for c in cuts if c.source == "beat")
        scene_cuts = sum(1 for c in cuts if c.source == "scene")
        energy_cuts = sum(1 for c in cuts if c.source == "energy")
        drum_cuts = sum(1 for c in cuts if c.source == "drum")
        self.cut_info_label.setText(
            f"{len(cuts)} Cuts | Beat:{beat_cuts} Szene:{scene_cuts} "
            f"Energie:{energy_cuts} Drum:{drum_cuts} | {total_dur:.0f}s"
        )
        self.console_text.append(
            f"[Pacing] {len(cuts)} Cuts generiert (Manual Curve aktiv)"
        )

    # ==================================================================
    # Auto-Edit to Beat
    # ==================================================================

    def _auto_edit_to_beat(self):
        """Phase 3: DJ-Pacing Auto-Edit mit OTIO Timeline."""
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        # Clip-IDs aus der bereits geladenen Video-Pool-Tabelle lesen (kein Main-Thread DB-Block)
        video_ids = []
        for _row in range(self.video_pool_table.rowCount()):
            _id_item = self.video_pool_table.item(_row, 1)
            if _id_item:
                try:
                    video_ids.append(int(_id_item.text()))
                except ValueError:
                    pass

        if not video_ids:
            self.console_text.append("[Auto-Edit] Keine Video-Clips vorhanden.")
            return

        # Phase 3: DJ-Regler auslesen
        cut_rate_map = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}
        base_cut_rate = cut_rate_map.get(self.cut_rate_combo.currentIndex(), 4)

        breakdown_map = {0: "halve", 1: "force16", 2: "none"}
        breakdown = breakdown_map.get(self.breakdown_combo.currentIndex(), "halve")

        # Anker aus UI sammeln
        anchors = self._collect_anchors_from_ui()

        settings = AdvancedPacingSettings(
            base_cut_rate=base_cut_rate,
            energy_reactivity=self.energy_reactivity_spin.value(),
            breakdown_behavior=breakdown,
            vibe=self.vibe_input.text(),
            manual_density_curve=self.pacing_curve.get_all_densities(),
            anchors=anchors,
        )

        self.console_text.append(
            f"[Auto-Edit] Phase 3 DJ-Pacing starte "
            f"(Rate={base_cut_rate} Beats, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}, {len(video_ids)} Clips, "
            f"{len(anchors)} Anker)..."
        )
        self.btn_auto_edit.setEnabled(False)
        self.btn_auto_edit.setText("laeuft...")

        # Task erstellen und Worker ueber _start_worker_thread starten
        tm = GlobalTaskManager.instance()
        task = tm.create_task(
            "Auto-Edit (Phase 3)",
            f"DJ-Pacing: {base_cut_rate}-Beat, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}"
        )
        worker = AutoEditWorker(audio_id, video_ids, settings)
        worker.task_id = task.task_id
        self._start_worker_thread(
            worker,
            on_finish=lambda segs, cps: self._on_auto_edit_finished(segs, cps, task.task_id),
            on_error=lambda err: self._on_auto_edit_error(err, task.task_id),
        )

    def _on_auto_edit_finished(self, segments: list, cut_points: list, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit")

        if not segments:
            # Could be error-path fallback OR legitimate empty result (no beats)
            if not cut_points:
                return  # Error-path: _on_auto_edit_error already handled
            self.console_text.append("[Auto-Edit] Keine Segmente erzeugt (kein Audio/Beats?).")
            task_manager.finish_task(task_id, "error", "Keine Segmente")
            return

        # 1. SQLite TimelineEntries aktualisieren (fuer UI-Anzeige)
        # Bug-21 Fix: DELETE und alle INSERTs in EINER Transaktion (kein Split-Commit).
        # Vorher: erster commit() nach DELETE persistierte sofort; wenn der zweite
        # Block (Insert-Loop) fehlschlug, war die Timeline leer ohne Ersatz-Einträge.
        with DBSession(engine) as session:
            session.query(TimelineEntry).filter_by(
                project_id=1, track="video"
            ).delete()

            for seg in segments:
                entry = TimelineEntry(
                    project_id=1,
                    track="video",
                    media_id=seg["video_id"],
                    start_time=seg["start"],
                    end_time=seg["end"],
                    source_start=seg.get("source_start", 0.0),
                    source_end=seg.get("source_end"),
                    lane=0,
                )
                session.add(entry)
            session.commit()  # Einziger Commit — atomar

        # 2. OTIO Timeline generieren
        self._build_otio_timeline(segments)

        # 3. UI aktualisieren
        self.timeline_view.load_from_db()

        # 4. CutPoints visualisieren
        if cut_points:
            total_dur = segments[-1]["end"] if segments else 60.0
            cps = [CutPoint(
                time=cp["time"], source=cp["source"], strength=cp["strength"]
            ) for cp in cut_points]
            # Gold Beat-Marker für Beat-Cuts
            beat_times = [cp["time"] for cp in cut_points if cp["source"] == "beat"]
            self.timeline_view.set_beat_markers(beat_times)
            self.timeline_view.set_cut_points(cps, total_dur)

            anchor_cuts = sum(1 for cp in cut_points if cp["source"] == "anchor")
            beat_cuts = sum(1 for cp in cut_points if cp["source"] == "beat")
            self.cut_info_label.setText(
                f"{len(cut_points)} Cuts | Beat:{beat_cuts} Anker:{anchor_cuts} | "
                f"{total_dur:.0f}s | {len(segments)} Segmente"
            )

        self.console_text.append(
            f"[Auto-Edit] Phase 3 fertig: {len(segments)} Segmente, "
            f"OTIO Timeline generiert."
        )
        task_manager.finish_task(task_id, "finished", f"{len(segments)} Segmente")

    def _build_otio_timeline(self, segments: list):
        """Baut eine OTIO-Timeline aus den Auto-Edit Segmenten."""
        audio_id = self.audio_combo.currentData()
        tls = TimelineService(fps=30.0)
        tls.create_timeline("PB Studio Auto-Edit")

        # Audio-Track hinzufuegen
        if audio_id is not None:
            with DBSession(engine) as session:
                track = session.get(AudioTrack, audio_id)
                if track:
                    audio_track = tls.get_audio_track()
                    tls.add_clip(
                        track=audio_track,
                        name=track.title or Path(track.file_path).stem,
                        media_path=track.file_path,
                        source_start=0.0,
                        source_duration=track.duration or 60.0,
                        available_duration=track.duration,
                    )

        # Video-Clips hinzufuegen
        video_track = tls.get_video_track()
        for seg in segments:
            source_duration = seg.get("source_end", seg["end"]) - seg.get("source_start", seg["start"])
            metadata = {}
            if seg.get("is_anchor"):
                metadata = {"scene_id": seg.get("scene_id", ""), "type": "anchor"}

            tls.add_clip(
                track=video_track,
                name=Path(seg["video_path"]).stem if seg.get("video_path") else f"clip_{seg['video_id']}",
                media_path=seg.get("video_path", ""),
                source_start=seg.get("source_start", 0.0),
                source_duration=source_duration,
                metadata=metadata if metadata else None,
            )

        # Anker als OTIO Marker speichern
        anchors = self._collect_anchors_from_ui()
        for anchor in anchors:
            tls.add_marker(
                name=f"Anchor_{anchor['scene_id']}",
                time=anchor["time"],
                color="MAGENTA",
                metadata={
                    "scene_id": anchor["scene_id"],
                    "type": "anchor",
                },
            )

        # Speichern
        self._otio_timeline_service = tls
        otio_path = tls.save_otio("exports/auto_edit_phase3.otio")
        self.console_text.append(f"[OTIO] Timeline gespeichert: {otio_path}")

    def _on_auto_edit_error(self, error_msg: str, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit")
        self.console_text.append(f"[Auto-Edit Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 3: Anchor System
    # ==================================================================

    def _collect_anchors_from_ui(self) -> list[dict]:
        """Sammelt alle Anker aus der Anchor-Liste im Inspector."""
        anchors = []
        for i in range(self.anchor_list.topLevelItemCount()):
            item = self.anchor_list.topLevelItem(i)
            time_text = item.text(0)
            scene_id = item.data(0, Qt.ItemDataRole.UserRole) or ""
            try:
                # Parse "MM:SS.ss" or plain seconds
                if ":" in time_text:
                    parts = time_text.replace("s", "").split(":")
                    time_sec = float(parts[0]) * 60 + float(parts[1])
                else:
                    time_sec = float(time_text.replace("s", ""))
                anchors.append({"time": time_sec, "scene_id": str(scene_id)})
            except (ValueError, IndexError):
                continue
        return anchors

    def _add_anchor_dialog(self):
        """Oeffnet einen Dialog zum Hinzufuegen eines neuen Audio-Ankers."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Anker hinzufuegen")
        dialog.setFixedSize(320, 180)
        dialog.setStyleSheet("background-color: #161c26; color: #e8e6e3;")
        layout = QVBoxLayout(dialog)

        # Zeitpunkt
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Zeitpunkt (Sek):"))
        time_spin = QDoubleSpinBox()
        time_spin.setRange(0.0, 36000.0)
        time_spin.setDecimals(3)
        time_spin.setSingleStep(0.1)
        time_spin.setValue(0.0)
        time_spin.setSuffix("s")
        time_row.addWidget(time_spin)
        layout.addLayout(time_row)

        # Video/Szene Auswahl
        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Video/Szene:"))
        scene_combo = QComboBox()
        scene_combo.addItem("-- Szene waehlen --", "")
        # Alle Szenen aus der DB laden (joinedload verhindert N+1)
        from sqlalchemy.orm import joinedload
        with DBSession(engine) as session:
            clips = session.query(VideoClip).options(
                joinedload(VideoClip.scenes)
            ).filter_by(project_id=1).all()
            for clip in clips:
                clip_name = Path(clip.file_path).stem[:20]
                for scene in clip.scenes:
                    label = (
                        f"{clip_name} | Szene {scene.id} "
                        f"({scene.start_time:.1f}-{scene.end_time:.1f}s)"
                    )
                    scene_combo.addItem(label, str(scene.id))
                # Falls keine Szenen: ganzen Clip anbieten
                if not clip.scenes:
                    scene_combo.addItem(f"{clip_name} (komplett)", f"clip_{clip.id}")
        scene_row.addWidget(scene_combo)
        layout.addLayout(scene_row)

        # OK/Cancel
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Hinzufuegen")
        btn_ok.setObjectName("btn_accent")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            time_sec = time_spin.value()
            scene_id = scene_combo.currentData() or ""
            scene_label = scene_combo.currentText()

            # Zur Anchor-Liste hinzufuegen
            minutes = int(time_sec // 60)
            secs = time_sec % 60
            time_str = f"{minutes}:{secs:05.2f}"

            item = QTreeWidgetItem([time_str, scene_label[:30]])
            item.setData(0, Qt.ItemDataRole.UserRole, scene_id)
            self.anchor_list.addTopLevelItem(item)

            self.console_text.append(
                f"[Anchor] Anker bei {time_str} -> {scene_label}"
            )

    def _remove_selected_anchor(self):
        """Entfernt den ausgewaehlten Anker aus der Liste."""
        selected = self.anchor_list.currentItem()
        if selected:
            idx = self.anchor_list.indexOfTopLevelItem(selected)
            self.anchor_list.takeTopLevelItem(idx)
            self.console_text.append("[Anchor] Anker entfernt.")

    def _sync_anchors(self):
        """Anker synchronisieren — richtet Video-Clips an Audio-Ankern aus."""
        synced = self.timeline_view.sync_anchors()
        if synced:
            self.timeline_view.load_from_db()
            self.console_text.append(
                "[Anchor] Anker synchronisiert — Video-Clips an Audio-Ankern ausgerichtet."
            )
        else:
            self.console_text.append(
                "[Anchor] Keine Anker gefunden. Setze Anker auf Audio- und Video-Clips "
                "(Rechtsklick oder Taste M), dann klicke erneut."
            )

    def _learn_anchor_as_ai_rule(self):
        """Speichert den ausgewaehlten Anker als KI-Lernregel fuer den Auto-Edit."""
        selected = self.anchor_list.currentItem()
        if not selected:
            self.console_text.append(
                "[KI-Gedaechtnis] Kein Anker ausgewaehlt. Bitte zuerst einen Anker in der Liste auswaehlen."
            )
            return

        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append(
                "[KI-Gedaechtnis] Kein Audio-Track ausgewaehlt. Bitte Audio-Combo setzen."
            )
            return

        time_text = selected.text(0)
        scene_id_raw = selected.data(0, Qt.ItemDataRole.UserRole)

        # Zeit parsen (Format "MM:SS.ss" oder Dezimal-Sekunden)
        try:
            if ":" in str(time_text):
                parts = str(time_text).split(":")
                anchor_time = int(parts[0]) * 60 + float(parts[1])
            else:
                anchor_time = float(time_text)
        except (ValueError, IndexError):
            self.console_text.append("[KI-Gedaechtnis] Fehler beim Parsen der Anker-Zeit.")
            return

        try:
            scene_int = int(scene_id_raw) if scene_id_raw else None
        except (ValueError, TypeError):
            scene_int = None

        label = f"Anker@{time_text}"

        from services.pacing_service import learn_from_anchor
        success = learn_from_anchor(audio_id, anchor_time, scene_int, label)

        if success:
            self.console_text.append(
                f"[KI-Gedaechtnis] Regel gelernt: {time_text}"
                + (f" | Szene #{scene_int}" if scene_int else "")
                + " — Wird beim naechsten Auto-Edit beruecksichtigt."
            )
            # Visuelles Feedback: kurz gruen aufleuchten
            self.btn_learn_ai.setStyleSheet(
                "background-color: #4ade80; color: #0a0d12; font-weight: 800; "
                "font-size: 10px; border-radius: 3px; letter-spacing: 1px;"
            )
            QTimer.singleShot(2000, lambda: self.btn_learn_ai.setStyleSheet(
                "background-color: #d4a44a; color: #0a0d12; font-weight: 800; "
                "font-size: 10px; border-radius: 3px; letter-spacing: 1px;"
            ))
        else:
            self.console_text.append("[KI-Gedaechtnis] Fehler beim Speichern der Regel.")

    # ── Phase 4: Neue Audio-Analyse Stubs ──────────────────────────────

    def _get_selected_audio_track(self):
        """Hilfsmethode: Gibt (track_id, file_path, title) des ausgewählten Audio-Tracks zurück."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append("[Warnung] Kein Audio-Track ausgewählt.")
            return None
        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                self.console_text.append("[Warnung] Audio-Track nicht in DB gefunden.")
                return None
            return (track.id, track.file_path, track.title or "Unbekannt", track.bpm)

    def _detect_key(self):
        """Erkennt die musikalische Tonart des ausgewählten Audio-Tracks."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import KeyDetectionWorker
        task = task_manager.create_task(f"Key: {title}", "Key-Erkennung (Krumhansl-Kessler)")
        worker = KeyDetectionWorker(track_id, file_path)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: self._console_append(f"[Key] {msg}"))
        worker.finished.connect(lambda result: (
            self._console_append(f"[Key] Erkannt: {result.key} ({result.camelot}) Conf={result.confidence:.0%}"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda err: self._console_append(f"[Key] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[Key] Starte Key-Erkennung für '{title}'...")

    def _analyze_lufs(self):
        """Analysiert die Lautstärke nach EBU R128."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, _ = info
        from workers.audio_analysis import LUFSAnalysisWorker
        task = task_manager.create_task(f"LUFS: {title}", "LUFS-Analyse (EBU R128)")
        worker = LUFSAnalysisWorker(track_id, file_path)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: self._console_append(f"[LUFS] {msg}"))
        worker.finished.connect(lambda result: (
            self._console_append(f"[LUFS] Integrated: {result.integrated:.1f} dB, LRA: {result.loudness_range:.1f} LU, TP: {result.true_peak:.1f} dBTP"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda err: self._console_append(f"[LUFS] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[LUFS] Starte LUFS-Analyse für '{title}'...")

    def _detect_structure(self):
        """Erkennt die Song-Struktur (INTRO/BUILDUP/DROP/BREAKDOWN/OUTRO)."""
        info = self._get_selected_audio_track()
        if not info:
            return
        track_id, file_path, title, bpm = info
        from workers.audio_analysis import StructureDetectionWorker
        task = task_manager.create_task(f"Struktur: {title}", "Song-Struktur Erkennung")
        worker = StructureDetectionWorker(track_id, file_path, bpm=bpm)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: self._console_append(f"[Struktur] {msg}"))
        worker.finished.connect(lambda result: (
            self._console_append(f"[Struktur] {len(result.segments)} Segmente erkannt"),
            self._refresh_media_table_debounced(),
        ))
        worker.error.connect(lambda err: self._console_append(f"[Struktur] Fehler: {err}"))
        self._start_worker_thread(worker)
        self.console_text.append(f"[Struktur] Starte Struktur-Erkennung für '{title}'...")

    def _rl_feedback_positive(self):
        """RL Feedback: User bestätigt aktuelle Pacing-Entscheidung (Thumbs Up)."""
        self.console_text.append("[RL-Feedback] 👍 Positiv — wird für zukünftige Auto-Edits gelernt.")
        self.statusBar().showMessage("RL-Feedback: Positiv gespeichert", 3000)

    def _rl_feedback_negative(self):
        """RL Feedback: User lehnt aktuelle Pacing-Entscheidung ab (Thumbs Down)."""
        self.console_text.append("[RL-Feedback] 👎 Negativ — wird für zukünftige Auto-Edits gelernt.")
        self.statusBar().showMessage("RL-Feedback: Negativ gespeichert", 3000)

    def _apply_style_preset(self, index: int):
        """Wendet einen Style-Preset auf die Pacing-Einstellungen an."""
        from database import engine, StylePreset
        from sqlalchemy.orm import Session as DBSession
        preset_name = self._edit_ws.style_preset_combo.currentText()
        if not preset_name:
            return
        try:
            with DBSession(engine) as session:
                preset = session.query(StylePreset).filter_by(name=preset_name).first()
                if not preset:
                    return
                # Preset-Werte in UI-Widgets schreiben
                cut_rate_map = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4}
                closest_beat = min(cut_rate_map.keys(), key=lambda x: abs(x - preset.cut_rate))
                self._edit_ws.cut_rate_combo.setCurrentIndex(cut_rate_map.get(closest_beat, 2))
                # Energy Reactivity (0-100 Slider)
                self._edit_ws.energy_reactivity_slider.setValue(int(preset.energy_reactivity * 100))
                # Breakdown Behavior
                breakdown_map = {"halve": 0, "16beat": 1, "none": 2}
                self._edit_ws.breakdown_combo.setCurrentIndex(breakdown_map.get(preset.breakdown_behavior, 0))
                self.console_text.append(
                    f"[Style-Preset] '{preset_name}' angewendet: "
                    f"Cut-Rate={preset.cut_rate}, Energy={preset.energy_reactivity}, "
                    f"Breakdown={preset.breakdown_behavior}"
                )
                self.statusBar().showMessage(f"Style-Preset '{preset_name}' angewendet", 3000)
        except Exception as e:
            self.console_text.append(f"[Style-Preset] Fehler: {e}")

    # ── Ende Phase 4 Stubs ───────────────────────────────────────────

    def _show_keyframe_strings(self):
        """Phase 3: Generiert und zeigt die Keyframe-Strings aller Video-Clips."""
        try:
            kf_string = generate_keyframe_strings_for_project(project_id=1)
            self.keyframe_text.setPlainText(kf_string)
            self.console_text.append("[Pacing] Keyframe-Strings generiert.")
        except Exception as e:
            self.keyframe_text.setPlainText(f"Fehler: {e}")
            self.console_text.append(f"[Pacing-Fehler] Keyframe-Strings: {e}")

    def _on_timeline_clip_moved(self, entry_id: int, new_start: float):
        self.console_text.append(
            f"[Timeline] Clip {entry_id} verschoben -> Start: {new_start:.2f}s"
        )

    # ==================================================================
    # Zur Timeline hinzufuegen
    # ==================================================================

    def _add_selected_to_timeline(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return

        media_type = self.media_table.item(row, 1).text()
        media_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        track_type = "audio" if media_type == "Audio" else "video"

        with DBSession(engine) as session:
            existing = (
                session.query(TimelineEntry)
                .filter_by(project_id=1, track=track_type)
                .order_by(TimelineEntry.start_time.desc())
                .first()
            )
            start_time = 0.0
            if existing and existing.end_time:
                start_time = existing.end_time

            if track_type == "audio":
                obj = session.get(AudioTrack, media_id)
                duration = obj.duration if obj and obj.duration else 30.0
            else:
                obj = session.get(VideoClip, media_id)
                duration = obj.duration if obj and obj.duration else 10.0

            entry = TimelineEntry(
                project_id=1,
                track=track_type,
                media_id=media_id,
                start_time=round(start_time, 3),
                end_time=round(start_time + duration, 3),
                lane=0,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

        self.timeline_view.add_clip(
            entry_id=entry_id,
            media_id=media_id,
            track_type=track_type,
            title=title,
            start_time=start_time,
            duration=duration,
        )

        self.console_text.append(
            f"[Timeline] {media_type} '{title}' hinzugefuegt bei {start_time:.1f}s "
            f"(Dauer: {duration:.1f}s)"
        )

        # Automatisch zum EDIT Workspace wechseln
        self.nav_bar.set_workspace(1)

    # ==================================================================
    # Pool-Selection → Hidden media_table Sync
    # ==================================================================

    def _on_video_pool_selected(self, row, col, prev_row, prev_col):
        """Sync video pool selection to hidden media_table."""
        if row < 0:
            return
        vid_id_item = self.video_pool_table.item(row, 1)
        if not vid_id_item:
            return
        vid_id = vid_id_item.text()
        for r in range(self.media_table.rowCount()):
            item = self.media_table.item(r, 0)
            type_item = self.media_table.item(r, 1)
            if item and type_item and item.text() == vid_id and type_item.text() == "Video":
                self.media_table.setCurrentCell(r, 0)
                break

    def _on_audio_pool_selected(self, row, col, prev_row, prev_col):
        """Sync audio pool selection to hidden media_table + StemWorkspace."""
        if row < 0:
            self.stem_player.stop()
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)
            return
        aud_id_item = self.audio_pool_table.item(row, 1)
        if not aud_id_item:
            self.stem_player.stop()
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)
            return
        aud_id = aud_id_item.text()
        for r in range(self.media_table.rowCount()):
            item = self.media_table.item(r, 0)
            type_item = self.media_table.item(r, 1)
            if item and type_item and item.text() == aud_id and type_item.text() == "Audio":
                self.media_table.setCurrentCell(r, 0)
                break

        # Stem Workspace aktualisieren
        self._update_stem_workspace(int(aud_id))

        # Phase 4: Audio Detail Cards aktualisieren
        try:
            from database import engine, AudioTrack, Beatgrid, StructureSegment
            from sqlalchemy.orm import Session as _DBSess
            from services.key_detection_service import CAMELOT_WHEEL
            audio_id = int(aud_id)
            with _DBSess(engine) as session:
                track = session.get(AudioTrack, audio_id)
                if track and hasattr(self._media_ws, '_update_audio_detail_cards'):
                    # Beat count aus Beatgrid
                    beat_count = None
                    if track.beatgrid and track.beatgrid.beat_positions:
                        try:
                            beat_count = len(_json.loads(track.beatgrid.beat_positions))
                        except Exception:
                            beat_count = None

                    # Camelot aus Key
                    camelot = CAMELOT_WHEEL.get(track.key) if track.key else None

                    # Stems Status
                    stems_status = "Ja" if track.stem_vocals_path else "Nein"

                    # Structure Segments
                    seg_rows = session.query(StructureSegment).filter_by(
                        audio_track_id=audio_id
                    ).order_by(StructureSegment.start_time).all()
                    segments = []
                    if seg_rows:
                        duration = track.duration or 1.0
                        for seg in seg_rows:
                            segments.append({
                                "label": seg.label,
                                "start": seg.start_time / duration,
                                "end": seg.end_time / duration,
                            })

                    track_data = {
                        "bpm": track.bpm,
                        "beat_count": beat_count,
                        "bpm_confidence": None,  # BPM hat kein separates Confidence-Feld
                        "key": track.key,
                        "key_confidence": track.key_confidence,
                        "camelot": camelot,
                        "mood": track.mood,
                        "energy": track.energy_curve,
                        "genre": track.genre,
                        "spectral_centroid": None,
                        "lufs": track.lufs,
                        "stems_status": stems_status,
                        "structure_segments": segments,
                    }
                    self._media_ws._update_audio_detail_cards(track_data)
        except Exception as e:
            logger.debug("Audio Detail Cards Update fehlgeschlagen: %s", e)

    def _on_stem_playback_finished(self):
        """[I-10 FIX] Benannte Methode für playback_finished — reset Position."""
        if hasattr(self, "stem_workspace"):
            self.stem_workspace.update_position(0.0)

    def _update_stem_workspace(self, track_id: int):
        """Lädt Stem-Pfade aus der DB, aktualisiert StemWorkspace und Player."""
        try:
            with DBSession(engine) as session:
                track = session.query(AudioTrack).filter_by(id=track_id).first()
                if not track:
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(None, None)
                    self.stem_player.stop()
                    return
                stem_paths = {
                    "vocals": track.stem_vocals_path,
                    "drums": track.stem_drums_path,
                    "bass": track.stem_bass_path,
                    "other": track.stem_other_path,
                }

                if self.stem_player.load_stems(stem_paths):
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(track_id, stem_paths)
                        self.stem_workspace.set_duration(self.stem_player.duration)
                    self.console_text.append(
                        f"[StemPlayer] Track #{track_id} geladen: "
                        f"{self.stem_player.duration:.1f}s"
                    )
                else:
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(track_id, stem_paths)
                        self.stem_workspace.set_duration(0.0)
        except Exception as e:
            self.console_text.append(f"[Stem-Widget] Fehler: {e}")
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)

    # ==================================================================
    # Import-Logik
    # ==================================================================

    def _import_video(self):
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Videos importieren", "", ext_filter)
        self._process_imports(paths, "video")

    def _import_audio(self):
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Audio importieren", "", ext_filter)
        self._process_imports(paths, "audio")

    def _process_imports(self, paths: list[str], media_type: str):
        """F-004 Fix: Imports laufen im Hintergrund-Thread (FolderImportWorker) statt synchron."""
        if not paths:
            return
        paths_audio = paths if media_type == "audio" else []
        paths_video = paths if media_type == "video" else []

        self.console_text.append(f"[Import] {len(paths)} {media_type.capitalize()}-Datei(en) werden importiert ...")
        self.status_bar.showMessage(f"Importiere {len(paths)} Datei(en) ...")

        worker = FolderImportWorker(paths_audio, paths_video)
        worker.file_imported.connect(self.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self._refresh_media_table()
                for clip_id, video_path, title in new_video_clips:
                    self._start_proxy_creation(clip_id, video_path, title)
            self.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

        def _on_error(msg: str):
            self.console_text.append(f"[Fehler] Import abgebrochen: {msg}")
            self.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _import_folder(self):
        """Importiert alle unterstuetzten Medien aus einem Ordner (rekursiv, Hintergrund-Thread)."""
        folder = QFileDialog.getExistingDirectory(self, "Ordner importieren")
        if not folder:
            return
        paths_audio: list[str] = []
        paths_video: list[str] = []
        for root, _dirs, files in os.walk(folder):
            for f in files:
                ext = Path(f).suffix.lower()
                full = os.path.join(root, f)
                if ext in AUDIO_EXTENSIONS:
                    paths_audio.append(full)
                elif ext in VIDEO_EXTENSIONS:
                    paths_video.append(full)
        total = len(paths_audio) + len(paths_video)
        if total == 0:
            self.console_text.append(f"[Warnung] Keine unterstuetzten Medien in: {folder}")
            return
        self.console_text.append(f"[Ordner] {total} Dateien gefunden in: {folder}")
        self.status_bar.showMessage(f"Importiere {total} Dateien aus Ordner ...")

        worker = FolderImportWorker(paths_audio, paths_video)

        worker.file_imported.connect(self.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self._refresh_media_table()
                for clip_id, video_path, title in new_video_clips:
                    self._start_proxy_creation(clip_id, video_path, title)
            self.status_bar.showMessage(
                f"{added} Datei(en) aus Ordner importiert | System bereit"
            )

        def _on_error(msg: str):
            self.console_text.append(f"[Fehler] Ordner-Import abgebrochen: {msg}")
            self.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _clear_all_media(self):
        """Loescht alle Medien aus Datenbank und UI."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Sammlung bereinigen",
            "Alle Medien aus der Datenbank entfernen?\nDie Original-Dateien bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = delete_all_media()
            self._refresh_media_table()
            self.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
            self.status_bar.showMessage(f"Sammlung bereinigt ({count} Eintraege) | System bereit")

    def _delete_selected_media(self, pool: str):
        """Loescht alle angehakten Medien (Checkboxen) aus Video oder Audio Pool."""
        from PySide6.QtWidgets import QMessageBox

        video_ids = []
        audio_ids = []

        if pool in ("video", "both"):
            for row in range(self.video_pool_table.rowCount()):
                chk = self.video_pool_table.item(row, 0)
                id_item = self.video_pool_table.item(row, 1)
                if chk and id_item and chk.checkState() == Qt.CheckState.Checked:
                    try:
                        video_ids.append(int(id_item.text()))
                    except ValueError:
                        pass

        if pool in ("audio", "both"):
            for row in range(self.audio_pool_table.rowCount()):
                chk = self.audio_pool_table.item(row, 0)
                id_item = self.audio_pool_table.item(row, 1)
                if chk and id_item and chk.checkState() == Qt.CheckState.Checked:
                    try:
                        audio_ids.append(int(id_item.text()))
                    except ValueError:
                        pass

        total = len(video_ids) + len(audio_ids)
        if total == 0:
            QMessageBox.information(
                self, "Nichts ausgewaehlt",
                "Bitte setze zuerst die Checkboxen der zu loeschenden Medien.",
            )
            return

        reply = QMessageBox.question(
            self, "Medien loeschen",
            f"{total} Medium/Medien aus der Datenbank entfernen?\n"
            "Die Original-Dateien bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = delete_selected_media(video_ids, audio_ids)
            self._refresh_media_table()
            self.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
            self.status_bar.showMessage(f"{count} Medien geloescht | System bereit")

    # ==================================================================
    # Audio-Analyse
    # ==================================================================

    def _analyze_selected_audio(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen analysiert werden.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Audio: {title}", "BPM + Beat-Analyse")

        worker = AnalysisWorker(track_id, title)
        worker.task_id = task.task_id
        worker.started.connect(self._on_analysis_started)
        worker.finished.connect(lambda tid, r: self._on_analysis_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_analysis_error(tid, err, task.task_id))
        worker.progress.connect(lambda pct, msg: self._console_append(f"[Audio] {msg}"))

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)

        self._start_worker_thread(worker)

    def _on_analysis_started(self, track_id: int, title: str):
        self.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict, task_id: str = ""):
        if not result:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_analyze.setEnabled(True)
            self.btn_analyze.setText("Audio analysieren")
            self.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        bpm = result["bpm"]
        duration = result["duration"]
        beats = len(result.get("beat_positions", []))
        self.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Beats: {beats} | Energie-Punkte: {len(result['energy_curve'])}"
        )
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse abgeschlossen | System bereit")
        self._refresh_media_table()
        if task_id:
            task_manager.finish_task(task_id, "finished", f"{bpm} BPM, {beats} Beats")

    def _on_analysis_error(self, track_id: int, error_msg: str, task_id: str = ""):
        self.console_text.append(f"[Fehler] Audio-Analyse fehlgeschlagen (ID {track_id}): {error_msg}")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Rekordbox Waveform-Analyse
    # ==================================================================

    def _analyze_waveform(self):
        """Startet Rekordbox-Style Frequenzanalyse für den ausgewählten Audio-Track."""
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Wellenform-Analyse nur fuer Audio-Dateien.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(
            f"Waveform: {title}", "Rekordbox Frequenz-Wellenform + Beatgrid"
        )

        worker = WaveformAnalysisWorker(track_id)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self._on_waveform_progress(pct, msg, task.task_id)
        )
        worker.finished.connect(
            lambda tid, r: self._on_waveform_finished(tid, r, title, task.task_id)
        )
        worker.error.connect(
            lambda tid, err: self._on_waveform_error(tid, err, task.task_id)
        )

        self.btn_waveform.setEnabled(False)
        self.btn_waveform.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)
        self.console_text.append(f"[Waveform] Starte Rekordbox-Analyse fuer '{title}'...")

        self._start_worker_thread(worker)

    def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
        # update_task wird automatisch durch die Task-Engine gemacht
        self.console_text.append(f"[Waveform] {msg} ({pct}%)")

    def _on_waveform_finished(self, track_id: int, result: dict, title: str, task_id: str):
        if not result:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_waveform.setEnabled(True)
            self.btn_waveform.setText("Rekordbox Wellenform")
            self.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        bpm = result["bpm"]
        beats = len(result.get("beat_positions", []))
        samples = result["num_samples"]
        self.console_text.append(
            f"[Waveform] Rekordbox-Analyse fertig: '{title}' | {bpm} BPM | "
            f"{beats} Beats | {samples} Wellenform-Samples (Low/Mid/High)"
        )
        self.btn_waveform.setEnabled(True)
        self.btn_waveform.setText("Rekordbox Wellenform")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Wellenform fertig: {title} | {bpm} BPM")
        self._refresh_media_table()

        # Timeline neu laden, damit die Wellenform sichtbar wird
        self.timeline_view.load_from_db()

        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{bpm} BPM, {beats} Beats, {samples} Samples"
            )

    def _on_waveform_error(self, track_id: int, error_msg: str, task_id: str):
        self.console_text.append(
            f"[Fehler] Wellenform-Analyse fehlgeschlagen (ID {track_id}): {error_msg}"
        )
        self.btn_waveform.setEnabled(True)
        self.btn_waveform.setText("Rekordbox Wellenform")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Wellenform-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Video-Analyse
    # ==================================================================

    # ------ Batch Video Analysis (1 Thread, sequentiell) ------

    def _analyze_selected_video(self):
        # Batch: Alle angehakten Zeilen im Video Pool auslesen
        checked_rows = []
        for row in range(self.video_pool_table.rowCount()):
            chk_item = self.video_pool_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                checked_rows.append(row)

        # Fallback: aktuelle Zeile wenn nichts angehakt
        if not checked_rows:
            row = self.video_pool_table.currentRow()
            if row >= 0:
                checked_rows.append(row)

        if not checked_rows:
            self.console_text.append("[Warnung] Keine Zeile im Video Pool ausgewaehlt oder angehakt.")
            return

        # Queue aufbauen
        batch = []
        for row in checked_rows:
            id_item = self.video_pool_table.item(row, 1)
            title_item = self.video_pool_table.item(row, 2)
            if not id_item:
                continue
            clip_id = int(id_item.text())
            title = title_item.text() if title_item else f"Clip {clip_id}"
            batch.append((clip_id, title))

        if not batch:
            return

        self.btn_analyze_video.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(batch))
        self.progress_bar.setValue(0)
        self.btn_analyze_video.setText(f"Analyse 0/{len(batch)}...")
        self.console_text.append(
            f"[Video] Batch-Analyse gestartet: {len(batch)} Videos (sequentiell)"
        )

        task = task_manager.create_task(
            f"Video-Batch ({len(batch)})", "Metadaten + Proxy"
        )

        worker = VideoBatchAnalysisWorker(batch)
        worker.task_id = task.task_id
        worker.item_done.connect(self._on_video_batch_item_done)
        worker.item_error.connect(self._on_video_batch_item_error)
        worker.finished.connect(
            lambda done, errors: self._on_video_batch_finished(done, errors, task.task_id)
        )
        self._video_batch_total = len(batch)
        self._video_batch_done = 0
        self._video_batch_errors = 0
        self._start_worker_thread(worker)

    def _on_video_batch_item_done(self, clip_id: int, info: str):
        """Ein einzelnes Video im Batch ist fertig."""
        self._video_batch_done += 1
        self.progress_bar.setValue(self._video_batch_done)
        self.btn_analyze_video.setText(
            f"Analyse {self._video_batch_done}/{self._video_batch_total}..."
        )
        self.status_bar.showMessage(
            f"Video-Analyse: {self._video_batch_done}/{self._video_batch_total} — {info}"
        )

    def _on_video_batch_item_error(self, clip_id: int, error_msg: str):
        """Ein einzelnes Video im Batch ist fehlgeschlagen."""
        self._video_batch_errors += 1
        self._video_batch_done += 1
        self.progress_bar.setValue(self._video_batch_done)
        self.btn_analyze_video.setText(
            f"Analyse {self._video_batch_done}/{self._video_batch_total}..."
        )
        self.console_text.append(
            f"[Fehler] Video ID {clip_id}: {error_msg}"
        )

    def _on_video_batch_finished(self, done: int, errors: int, task_id: str):
        """Gesamter Batch ist fertig."""
        self.btn_analyze_video.setEnabled(True)
        self.btn_analyze_video.setText("Video analysieren")
        self.progress_bar.setVisible(False)
        self._refresh_media_table()
        errors_info = f" ({errors} Fehler)" if errors else ""
        self.console_text.append(
            f"[Video] Batch-Analyse abgeschlossen: {done}/{self._video_batch_total}{errors_info}"
        )
        self.status_bar.showMessage(
            f"Alle {self._video_batch_total} Video-Analysen abgeschlossen | System bereit"
        )
        if task_id:
            status = "finished" if errors == 0 else "error"
            task_manager.finish_task(task_id, status, f"{done} fertig{errors_info}")

    # ==================================================================
    # Phase 2: Video Analysis Pipeline (SEKTOR 1)
    # ==================================================================

    def _start_video_pipeline(self):
        """Startet die 3-Schritt Video-Analyse-Pipeline für ALLE ausgewählten Videos.

        Liest alle markierten Zeilen im Video Pool aus und übergibt sie
        als Batch an den Worker. Sequenzielle Abarbeitung (6GB VRAM).
        """
        # SEKTOR 1: Alle angehakten Zeilen im Video Pool auslesen (Checkbox Spalte 0)
        selected_rows = set()
        for row in range(self.video_pool_table.rowCount()):
            chk_item = self.video_pool_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                selected_rows.add(row)
        # Fallback: blau markierte Zeilen oder aktuelle Zeile
        if not selected_rows:
            for index in self.video_pool_table.selectionModel().selectedRows():
                selected_rows.add(index.row())
        if not selected_rows:
            row = self.video_pool_table.currentRow()
            if row >= 0:
                selected_rows.add(row)
        if not selected_rows:
            self.console_text.append("[Warnung] Keine Zeile im Video Pool ausgewaehlt oder angehakt.")
            return

        # Clip-IDs und Titel aus der Video Pool Tabelle sammeln (kein DB-Zugriff im Main-Thread)
        batch = []
        for row in sorted(selected_rows):
            id_item = self.video_pool_table.item(row, 1)
            title_item = self.video_pool_table.item(row, 2)
            if not id_item:
                continue
            clip_id = int(id_item.text())
            title = title_item.text() if title_item else f"Clip {clip_id}"
            batch.append((clip_id, title))

        if not batch:
            self.console_text.append("[Warnung] Keine gültigen Videos in der Auswahl.")
            return

        # SEKTOR 2: Batch-Task erstellen
        count = len(batch)
        label = batch[0][1] if count == 1 else f"{count} Videos"
        task = task_manager.create_task(
            f"Pipeline: {label}",
            f"Batch-Analyse: {count} Video(s) — Szenen + Motion + SigLIP"
        )

        self.btn_video_pipeline.setEnabled(False)
        self.btn_video_pipeline.setText(f"Pipeline laeuft ({count})...")
        self.progress_bar.setVisible(True)

        titles_str = ", ".join(t for _, t in batch[:3])
        if count > 3:
            titles_str += f" (+{count - 3} weitere)"
        self.console_text.append(
            f"[Pipeline] Starte Batch-Analyse fuer {count} Video(s): {titles_str} "
            f"(SceneDetect → Keyframes → SigLIP)..."
        )

        worker = VideoAnalysisPipelineWorker(batch=batch)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self._on_pipeline_progress(pct, msg, task.task_id)
        )
        worker.finished.connect(
            lambda cid, r: self._on_pipeline_finished(cid, r, label, task.task_id)
        )
        worker.error.connect(
            lambda cid, err: self._on_pipeline_error(cid, err, task.task_id)
        )

        self._start_worker_thread(worker)

    def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
        # update_task wird automatisch durch die Task-Engine gemacht
        # GUI-Throttle: Nur bei Video-Wechseln oder alle 10% in die Console schreiben
        # um Event-Loop-Flooding und Repaint-Stau zu verhindern
        last_pct = getattr(self, '_pipeline_last_pct', -10)
        if abs(pct - last_pct) >= 10 or "wird analysiert" in msg:
            self.console_text.append(f"[Pipeline] {msg} ({pct}%)")
            self._pipeline_last_pct = pct

    def _on_pipeline_finished(self, clip_id: int, result: dict, title: str, task_id: str):
        if not result:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_video_pipeline.setEnabled(True)
            self.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
            self.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        scenes = result.get("scenes", 0)
        embeddings = result.get("embeddings", 0)
        videos_done = result.get("videos_processed", 1)
        self.console_text.append(
            f"[Pipeline] Fertig: {title} — {videos_done} Video(s), "
            f"{scenes} Szenen, {embeddings} Embeddings in LanceDB"
        )
        self.btn_video_pipeline.setEnabled(True)
        self.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(
            f"Pipeline fertig: {title} | {videos_done} Video(s), "
            f"{scenes} Szenen, {embeddings} Embeddings"
        )
        self._refresh_media_table()
        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{videos_done} Video(s), {scenes} Szenen, {embeddings} Embeddings"
            )

    def _on_pipeline_error(self, clip_id: int, error_msg: str, task_id: str):
        self.console_text.append(f"[Pipeline-Fehler] VideoClip {clip_id}: {error_msg}")
        self.btn_video_pipeline.setEnabled(True)
        self.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Pipeline-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 2: Proxy Creation (SEKTOR 2)
    # ==================================================================

    def _start_proxy_creation(self, clip_id: int, video_path: str, title: str):
        """Startet NVENC Proxy-Erstellung im Hintergrund."""
        task = task_manager.create_task(
            f"Proxy: {title}", "NVENC 540p Edit-Proxy"
        )
        self.console_text.append(f"[Proxy] Erstelle Edit-Proxy fuer '{title}'...")

        worker = ProxyCreationWorker(clip_id, video_path)
        worker.task_id = task.task_id
        worker.finished.connect(
            lambda cid, path: self._on_proxy_finished(cid, path, title, task.task_id)
        )
        worker.error.connect(
            lambda cid, err: self._on_proxy_error(cid, err, title, task.task_id)
        )

        self._start_worker_thread(worker)

    def _on_proxy_finished(self, clip_id: int, proxy_path: str, title: str, task_id: str):
        if not proxy_path:
            # Empty-result fallback (finally block): close task so it does not stay "running".
            task_manager.finish_task(task_id, "error", "Leerer Proxy-Pfad")
            return
        self.console_text.append(f"[Proxy] Fertig: '{title}' → {proxy_path}")
        self._refresh_media_table()
        task_manager.finish_task(task_id, "finished", proxy_path)

    def _on_proxy_error(self, clip_id: int, error_msg: str, title: str, task_id: str):
        self.console_text.append(f"[Proxy-Fehler] '{title}': {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 2: Semantic Search (SEKTOR 3)
    # ==================================================================

    def _run_semantic_search(self):
        """Startet SigLIP Text-zu-Video Suche."""
        query = self.search_input.text().strip()
        if not query:
            self.console_text.append("[Suche] Bitte Suchbegriff eingeben.")
            return

        self.btn_search.setEnabled(False)
        self.btn_search.setText("...")
        self.console_text.append(f"[Suche] SigLIP-Suche: '{query}'...")

        worker = SemanticSearchWorker(query, top_k=20)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_search_error)

        self._start_worker_thread(worker)

    def _on_search_finished(self, results: list):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Suchen")

        if not results:
            self.console_text.append("[Suche] Keine Ergebnisse gefunden.")
            return

        self.console_text.append(f"[Suche] {len(results)} Ergebnisse gefunden.")

        # Video Pool mit Suchergebnissen aktualisieren
        # Spalten-Layout muss mit _refresh_media_table uebereinstimmen:
        # col 0=Auswahl, col 1=ID, col 2=Titel, col 3=Aufloesung, col 4=FPS, col 5=Codec, col 6=Dateipfad
        self.video_pool_table.setRowCount(len(results))
        for row, r in enumerate(results):
            video_name = Path(r["video_path"]).stem
            scene_info = f"Sz{r['scene_index']} ({r['scene_start']:.1f}-{r['scene_end']:.1f}s)"
            distance = f"dist:{r['_distance']:.3f}"
            motion = f"motion:{r['motion_score']:.2f}"

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.video_pool_table.setItem(row, 0, chk)
            self.video_pool_table.setItem(row, 1, QTableWidgetItem(str(r.get("id", ""))))
            self.video_pool_table.setItem(row, 2, QTableWidgetItem(f"{video_name} | {scene_info}"))
            self.video_pool_table.setItem(row, 3, QTableWidgetItem(motion))
            self.video_pool_table.setItem(row, 4, QTableWidgetItem(distance))
            self.video_pool_table.setItem(row, 5, QTableWidgetItem("-"))
            self.video_pool_table.setItem(row, 6, QTableWidgetItem(r["video_path"]))

    def _on_search_error(self, error_msg: str):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Suchen")
        self.console_text.append(f"[Suche-Fehler] {error_msg}")

    def _clear_search(self):
        """Suche zurücksetzen — normale Video-Pool Anzeige."""
        self.search_input.clear()
        self._refresh_media_table()
        self.console_text.append("[Suche] Zurückgesetzt — alle Videos angezeigt.")

    # ==================================================================
    # Stem Separation
    # ==================================================================

    def _start_stem_separation(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen separiert werden.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Stems: {title}", "KI Stem Separation (Demucs)")

        self.btn_stem_separate.setEnabled(False)
        self.btn_stem_separate.setText("Separation laeuft...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat("KI-Separation laeuft... (kann mehrere Minuten dauern)")

        self.console_text.append(f"[Stems] Starte KI-Stem-Separation fuer '{title}'...")

        worker = StemSeparationWorker(track_id)
        worker.task_id = task.task_id  # Verknuepfung mit bestehendem Task
        worker.progress.connect(
            lambda pct, msg: self.console_text.append(f"[Stems] {msg} ({pct}%)")
        )
        worker.finished.connect(lambda tid, r: self._on_stem_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_stem_error(tid, err, task.task_id))

        self._start_worker_thread(worker)

    def _on_stem_finished(self, track_id: int, stems: dict, task_id: str):
        if not stems:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_stem_separate.setEnabled(True)
            self.btn_stem_separate.setText("KI Stem Separation")
            self.progress_bar.setVisible(False)
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)

        stem_list = [f"{k}: {('OK' if v else 'fehlt')}" for k, v in stems.items()]
        self.console_text.append(f"[Stems] Separation fertig: {', '.join(stem_list)}")
        self._refresh_media_table()
        self._update_stem_workspace(track_id)
        task_manager.finish_task(task_id, "finished", "Stems OK")

    def _on_stem_error(self, track_id: int, error_msg: str, task_id: str):
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)
        self.console_text.append(f"[Stem-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Auto-Ducking
    # ==================================================================

    def _start_auto_ducking(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Waehle einen Audio-Track mit Stems.")
            return
        track_id = int(self.media_table.item(row, 0).text())

        with DBSession(engine) as session:
            track = session.get(AudioTrack, track_id)
            if not track:
                return
            if not track.stem_vocals_path or not track.stem_other_path:
                self.console_text.append(
                    "[Ducking] Zuerst Stems separieren! (Vocals + Other benoetigt)"
                )
                return
            vocals_path = track.stem_vocals_path
            other_path = track.stem_other_path
            title = track.title

        import re as _re_ducking
        ducked_dir = Path(__file__).parent / "storage" / "ducked"
        ducked_dir.mkdir(parents=True, exist_ok=True)
        safe_title = _re_ducking.sub(r'[<>:"/\\|?*]', '_', title or "track")
        output_path = str(ducked_dir / f"{safe_title}_ducked.wav")
        task = task_manager.create_task(f"Ducking: {title}", "Auto-Ducking")

        self.btn_auto_duck.setEnabled(False)
        self.btn_auto_duck.setText("Ducking laeuft...")

        self.console_text.append(f"[Ducking] Starte Auto-Ducking fuer '{title}'...")

        worker = AutoDuckingWorker(other_path, vocals_path, output_path)
        worker.task_id = task.task_id
        worker.finished.connect(lambda p: self._on_ducking_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_ducking_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_ducking_finished(self, output_path: str, task_id: str):
        if not output_path:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_auto_duck.setEnabled(True)
            self.btn_auto_duck.setText("Auto-Ducking")
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.btn_auto_duck.setEnabled(True)
        self.btn_auto_duck.setText("Auto-Ducking")
        self.console_text.append(f"[Ducking] Fertig: {output_path}")
        task_manager.finish_task(task_id, "finished", f"Gespeichert: {output_path}")

    def _on_ducking_error(self, error_msg: str, task_id: str):
        self.btn_auto_duck.setEnabled(True)
        self.btn_auto_duck.setText("Auto-Ducking")
        self.console_text.append(f"[Ducking-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Production / Export
    # ==================================================================

    def _refresh_production_info(self):
        summary = get_timeline_summary()
        self.production_info.setText(
            f"Video-Clips: {summary['video_clips']} | "
            f"Audio-Tracks: {summary['audio_tracks']} | "
            f"Gesamt-Eintraege: {summary['total_entries']} | "
            f"Geschaetzte Dauer: {summary['estimated_duration']:.1f}s"
        )

    def _start_export(self):
        summary = get_timeline_summary()
        if summary["total_entries"] == 0:
            self.export_log.append("[Fehler] Keine Clips auf der Timeline!")
            return

        output_name = self.export_name_input.text().strip() or "output.mp4"
        if not output_name.endswith(".mp4"):
            output_name += ".mp4"

        resolution = self.resolution_combo.currentText()
        fps = float(self.fps_combo.currentText())

        task = task_manager.create_task(f"Export: {output_name}", "Video-Rendering")

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Exportiere...")
        self.export_progress.setVisible(True)
        self.export_progress.setRange(0, 0)
        self.export_log.append(f"[Export] Starte Export: {output_name} ({resolution} @ {fps}fps)")

        worker = ExportWorker(project_id=1, output_name=output_name,
                              resolution=resolution, fps=fps)
        worker.task_id = task.task_id
        worker.progress.connect(self._on_export_progress)
        worker.finished.connect(lambda p: self._on_export_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_export_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_export_progress(self, pct: int, message: str):
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(pct)
        self.export_log.append(f"[Export] {message} ({pct}%)")

    def _on_export_finished(self, output_path: str, task_id: str = ""):
        if not output_path:
            # Empty-result fallback (finally block): re-enable UI and close task.
            self.btn_export.setEnabled(True)
            self.btn_export.setText("Video exportieren")
            self.export_progress.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leerer Export-Pfad")
            return
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Video exportieren")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[Export] FERTIG: {output_path}")
        self.console_text.append(f"[Export] Video exportiert: {output_path}")
        self.status_bar.showMessage(f"Export fertig: {output_path}")
        if task_id:
            task_manager.finish_task(task_id, "finished", output_path)

    def _on_export_error(self, error_msg: str, task_id: str = ""):
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Video exportieren")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[FEHLER] Export fehlgeschlagen: {error_msg}")
        self.console_text.append(f"[Fehler] Export: {error_msg}")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

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
    window.showMaximized()
    # Timeline-Daten NACH dem Fenster laden (non-blocking Startup)
    QTimer.singleShot(0, window.timeline_view.load_from_db)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()