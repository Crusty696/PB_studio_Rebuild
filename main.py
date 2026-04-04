# main.py
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
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer, QTranslator, QLocale
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QBrush, QPen, QPixmap, QImage, QPolygonF, QAction

# NEU: PB Studio Gold-Accent Theme (ersetzt qt_material)
from ui.theme import get_stylesheet

APP_VERSION = "0.5.0"

logger = logging.getLogger(__name__)

# P-017: Legacy Thread-Registry — importiert aus WorkerDispatcherMixin-Modul.
from ui.mixins.worker_dispatcher import _GLOBAL_ACTIVE_THREADS
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
from services.task_manager import TaskInfo, GlobalTaskManager, TaskManagerProxy

# FIX B-010: TaskManagerProxy ist lazy und verbietet Zugriff vor QApplication
task_manager = TaskManagerProxy()


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
    WorkerDispatcherMixin,
    AudioAnalysisMixin, VideoAnalysisMixin, EditWorkspaceMixin,
    ImportMediaMixin, ConvertMixin, ExportMixin, StemsMixin, SearchMixin,
    WorkspaceSetupMixin, PanelSetupMixin, ProjectManagementMixin, MediaTableMixin,
)


# ======================================================================
# Hauptfenster — DaVinci Resolve Style
# ======================================================================

class PBWindow(QMainWindow,
               WorkerDispatcherMixin, AudioAnalysisMixin, VideoAnalysisMixin,
               EditWorkspaceMixin, ImportMediaMixin, ConvertMixin,
               ExportMixin, StemsMixin, SearchMixin,
               WorkspaceSetupMixin, PanelSetupMixin,
               ProjectManagementMixin, MediaTableMixin):
    def __init__(self):
        super().__init__()

        self._app_version = APP_VERSION
        self.setWindowTitle(f"PB_studio v{APP_VERSION} — Director's Cockpit")
        self.resize(1500, 900)
        self._active_threads: list[QThread] = []
        self._active_workers: list[QObject] = []
        self._otio_timeline_service: TimelineService | None = None
        self._refresh_pending = False
        self._project_manager = ProjectManager(self)
        self._project_manager.project_changed.connect(self._on_project_changed)

        # Zentrales Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Bar ──
        self._build_top_bar(main_layout, APP_VERSION)

        # ── Update-Notification Banner (hidden until a new version is found) ──
        self._update_banner = self._build_update_banner()
        main_layout.addWidget(self._update_banner)

        # ── Trennlinie ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,6);")
        main_layout.addWidget(sep)

        # ── Workspace Stack ──
        self.workspace_stack = QStackedWidget()
        self._create_workspaces()

        # ── Vertikaler QSplitter: Workspace oben | System-Panel unten ──
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.setChildrenCollapsible(True)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.addWidget(self.workspace_stack)

        # Unteres Panel: horizontaler QSplitter (Tasks | Konsole)
        self._bottom_panel = QWidget()
        self._bottom_panel.setObjectName("bottom_panel")
        self._bottom_panel.setMinimumHeight(80)
        _bp_layout = QHBoxLayout(self._bottom_panel)
        _bp_layout.setContentsMargins(0, 0, 0, 0)
        _bp_layout.setSpacing(0)
        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        _bp_layout.addWidget(self._inner_splitter)
        self._main_splitter.addWidget(self._bottom_panel)

        main_layout.addWidget(self._main_splitter, stretch=1)

        # ── Bottom Navigation Bar (DaVinci Style) ──
        self.nav_bar = WorkspaceNavBar()
        self.nav_bar.workspace_changed.connect(self._on_workspace_changed)
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

        # Splitter-Groessen: Workspace dominiert, unteres Panel sichtbar
        self._main_splitter.setSizes([700, 150])
        self._inner_splitter.setSizes([500, 500])

        # Wire toggle buttons to panel visibility
        self._btn_toggle_tasks.toggled.connect(self._task_panel_widget.setVisible)
        self._btn_toggle_console.toggled.connect(self._console_panel_widget.setVisible)
        self._btn_toggle_chat.toggled.connect(self.chat_dock.setVisible)
        self.chat_dock.visibilityChanged.connect(self._btn_toggle_chat.setChecked)

        # P-016: Media-Tabelle NACH dem Window-Show laden (nicht im __init__)
        QTimer.singleShot(0, self._refresh_media_table)

        # AUD-103: Version check — non-blocking, after window is visible
        QTimer.singleShot(3000, self._start_version_check)

    # ── AUD-103: Update notification ──────────────────────────────────────

    def _build_update_banner(self) -> QFrame:
        """Create the dismissible update-notification banner (hidden by default)."""
        banner = QFrame()
        banner.setObjectName("update_banner")
        banner.setStyleSheet(
            "#update_banner {"
            "  background-color: #1a3a1a;"
            "  border-bottom: 1px solid #2d6a2d;"
            "}"
        )
        banner.setVisible(False)
        banner.setFixedHeight(36)

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        self._update_banner_label = QLabel()
        self._update_banner_label.setStyleSheet("color: #7fff7f; font-size: 12px;")
        layout.addWidget(self._update_banner_label, stretch=1)

        self._update_banner_link = QPushButton("Download")
        self._update_banner_link.setFlat(True)
        self._update_banner_link.setStyleSheet(
            "QPushButton { color: #aaffaa; text-decoration: underline; font-size: 12px; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        self._update_banner_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_banner_link.setVisible(False)
        layout.addWidget(self._update_banner_link)

        btn_close = QPushButton("✕")
        btn_close.setFlat(True)
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("QPushButton { color: #7fff7f; font-size: 11px; } QPushButton:hover { color: #ffffff; }")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(banner.hide)
        layout.addWidget(btn_close)

        return banner

    def _start_version_check(self) -> None:
        """Launch the background version check thread."""
        from services.version_check_service import VersionCheckWorker
        self._version_checker = VersionCheckWorker(current_version=APP_VERSION)
        self._version_checker.update_available.connect(self._on_update_available)
        self._version_checker.finished.connect(self._version_checker.deleteLater)
        self._version_checker.start()
        logger.debug("Version check started (current=%s)", APP_VERSION)

    def _on_update_available(self, latest_version: str, download_url: str) -> None:
        """Show the update banner when a newer release is detected."""
        self._update_banner_label.setText(
            f"Update verfügbar: PB Studio v{latest_version}"
        )
        if download_url:
            self._update_banner_link.setVisible(True)
            self._update_banner_link.clicked.connect(
                lambda: __import__("webbrowser").open(download_url)
            )
        self._update_banner.setVisible(True)
        logger.info("Update banner shown: v%s available", latest_version)

    # ── End AUD-103 ───────────────────────────────────────────────────────

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
        except (ImportError, AttributeError, RuntimeError) as exc:
            logger.warning("closeEvent: failed to check running tasks: %s", exc)

        # 1. Stop background timers
        if hasattr(self, '_task_mgr_dock') and hasattr(self._task_mgr_dock, '_timer'):
            self._task_mgr_dock._timer.stop()

        # FIX B-002: Shutdown-Flag setzen VOR Task-Abbruch
        try:
            GlobalTaskManager.instance()._shutting_down = True
        except (AttributeError, RuntimeError) as exc:
            logger.warning("closeEvent: failed to set shutdown flag: %s", exc)

        # 2. Alle Tasks im GlobalTaskManager abbrechen
        try:
            tm = GlobalTaskManager.instance()
            for task in tm.get_all_tasks():
                if task.status == "running":
                    tm.cancel_task(task.task_id)
        except (AttributeError, RuntimeError) as exc:
            logger.warning("closeEvent: failed to cancel running tasks: %s", exc)

        # 2. Legacy: direkt verwaltete Threads stoppen
        for thread in list(self._active_threads):
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(1000)
        self._active_threads.clear()
        self._active_workers.clear()
        _GLOBAL_ACTIVE_THREADS.clear()

        # 3. Video Preview stoppen
        if hasattr(self, "video_preview"):
            try:
                self.video_preview.stop()
            except (RuntimeError, AttributeError) as exc:
                logger.warning("closeEvent: failed to stop video preview: %s", exc)

        # 4. Stem Player + Workspace aufraeumen
        if hasattr(self, "stem_player"):
            self.stem_player.cleanup()
        if hasattr(self, "stem_workspace"):
            self.stem_workspace._cleanup_peak_threads()
            for t in list(self.stem_workspace._peak_threads):
                try:
                    t.quit()
                    t.wait(1000)
                except RuntimeError as exc:
                    logger.warning("closeEvent: failed to stop stem peak thread: %s", exc)

        # 4. GPU-VRAM freigeben
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
        except (ImportError, RuntimeError, AttributeError) as exc:
            logger.warning("closeEvent: failed to unload GPU models: %s", exc)

        # 5. Close DB connection pool
        try:
            from database import engine
            engine.dispose()
        except (ImportError, RuntimeError, OSError) as exc:
            logger.warning("closeEvent: failed to dispose DB connection pool: %s", exc)

        super().closeEvent(event)


# ======================================================================
# Logging + Entry Point
# ======================================================================

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

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.info("Logging initialisiert → %s", log_file)


def _global_exception_hook(exc_type, exc_value, exc_tb):
    """Faengt unhandled Exceptions ab, loggt sie und zeigt einen Crash-Dialog."""
    import traceback as _tb
    msg = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("UNHANDLED EXCEPTION:\n%s", msg)
    print(f"\n{'='*60}\n  CRASH — Unhandled Exception\n{'='*60}\n{msg}", flush=True)

    # Show visual crash dialog if QApplication is running
    try:
        from PySide6.QtWidgets import QApplication as _QApp
        if _QApp.instance() is not None:
            from ui.dialogs.crash_dialog import CrashDialog
            dlg = CrashDialog(exc_type, exc_value, exc_tb)
            dlg.exec()
    except (ImportError, RuntimeError, AttributeError) as exc:
        logger.error("_global_exception_hook: crash dialog failed: %s", exc)
        print(f"[CRASH DIALOG FAILED] {exc}", flush=True)


# Bekannte harmlose Qt-Warnings die das Log zuspammen
_QT_WARNINGS_SUPPRESS = {
    "QBasicTimer::start: Timers cannot be started from another thread",
}
_qt_suppressed_counts: dict[str, int] = {}


def _qt_message_handler(mode, context, message):
    """Faengt Qt/C++ Warnungen und Fehler ab und loggt sie in die Log-Datei."""
    from PySide6.QtCore import QtMsgType
    if mode == QtMsgType.QtWarningMsg:
        for pattern in _QT_WARNINGS_SUPPRESS:
            if pattern in message:
                _qt_suppressed_counts[pattern] = _qt_suppressed_counts.get(pattern, 0) + 1
                if _qt_suppressed_counts[pattern] % 100 == 1:
                    logging.debug(
                        "[Qt C++] Unterdrueckt (harmlos, %dx bisher): %s",
                        _qt_suppressed_counts[pattern], pattern,
                    )
                return
        logging.warning("[Qt C++] %s (file: %s, line: %s)",
                        message, context.file or "?", context.line)
    elif mode == QtMsgType.QtCriticalMsg:
        logging.error("[Qt C++] CRITICAL: %s (file: %s, line: %s)",
                      message, context.file or "?", context.line)
    elif mode == QtMsgType.QtFatalMsg:
        logging.critical("[Qt C++] FATAL: %s (file: %s, line: %s)",
                         message, context.file or "?", context.line)


def main():
    setup_logging()

    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_message_handler)

    sys.excepthook = _global_exception_hook

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
    except (OSError, RuntimeError, ImportError) as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.critical("Datenbank-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        print(f"[FATAL] DB-Init fehlgeschlagen: {exc}")
        sys.exit(1)

    app = QApplication(sys.argv)

    # ── i18n / Translations ───────────────────────────────────────────
    # Load .qm file for the system locale (default: German).
    # Compile .ts → .qm with: pyside6-lrelease translations/pb_studio_de.ts
    _translator = QTranslator(app)
    _trans_dir = Path(__file__).parent / "translations"
    _locale_name = QLocale.system().name()  # e.g. "de_DE"
    for _lang in (_locale_name, _locale_name.split("_")[0], "de"):
        if _translator.load(f"pb_studio_{_lang}", str(_trans_dir)):
            app.installTranslator(_translator)
            break

    _tm = GlobalTaskManager.instance()
    _task_manager_module.task_manager = _tm
    app.task_manager = _tm

    app.setStyleSheet(get_stylesheet())

    # ── App Icon ──────────────────────────────────────────────────────
    from ui.app_icon import get_app_icon
    _app_icon = get_app_icon()
    app.setWindowIcon(_app_icon)

    # ── Splash Screen ─────────────────────────────────────────────────
    from ui.splash import PBSplashScreen
    splash = PBSplashScreen(APP_VERSION)
    splash.show()
    splash.show_message("Initialisiere Datenbank...")

    from services.startup_checks import check_system
    from ui.dialogs.startup_check_dialog import maybe_show_startup_dialog
    _sys_status = check_system()
    app.system_status = _sys_status

    # ── First-Run Setup Wizard (AUD-62) ──────────────────────────────
    from ui.dialogs.setup_wizard import is_setup_complete, SetupWizard
    if not is_setup_complete():
        splash.close()
        wizard = SetupWizard()
        wizard.exec()
        splash = PBSplashScreen(APP_VERSION)
        splash.show()

    splash.show_message("Prüfe System-Abhängigkeiten...")
    if not maybe_show_startup_dialog(_sys_status):
        splash.close()
        sys.exit(0)

    splash.show_message("Lade Benutzeroberfläche...")
    try:
        window = PBWindow()
    except (ImportError, RuntimeError, OSError) as exc:
        splash.close()
        logging.critical("Fenster-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        print(f"[FATAL] Fenster konnte nicht erstellt werden: {exc}")
        traceback.print_exc()
        sys.exit(1)

    # Set window icon explicitly (taskbar + title bar)
    window.setWindowIcon(_app_icon)

    splash.show_message("Bereit.")
    window.console_text.append("[System] SQLite Datenbank (pb_studio.db) erfolgreich initialisiert.")
    window.console_text.append("[System] PB Studio Gold-Accent Theme aktiv — v0.5 Design.")
    window.console_text.append(f"[System] Version {APP_VERSION} — Workspace UI + KI-Pacing + Beat-Snap.")
    window.console_text.append(f"[System] {_sys_status.status_bar_text()}")
    window.status_bar.showMessage(f"PB_studio v{APP_VERSION}  |  {_sys_status.status_bar_text()}")
    window.showMaximized()
    splash.finish(window)  # Closes splash when main window is ready
    QTimer.singleShot(0, window.timeline_view.load_from_db)
    sys.exit(app.exec())
