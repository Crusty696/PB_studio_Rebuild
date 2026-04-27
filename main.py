# main.py
"""
PB_studio v0.5.0 — DaVinci Resolve Style UI Rebuild
=====================================================
4 Arbeitsbereiche: MEDIA | EDIT | CONVERT | DELIVER
Bottom-Navigationsleiste wie DaVinci Resolve.
Optimierte Timeline mit Caching.
"""

from dotenv import load_dotenv
load_dotenv()

# --- ABSOLUTE EARLY INIT (BEFORE QT) ---
import os
import sys
from pathlib import Path

# B-215: OpenMP/MKL Doppel-Init-Schutz. Conda's intel-openmp (libiomp5md.dll)
# kollidiert mit Windows' vcomp140.dll wenn beide initialisiert werden →
# /GS-Stack-Guard schlaegt zu (STATUS_STACK_BUFFER_OVERRUN, exit -1073740791).
# KMP_DUPLICATE_LIB_OK=TRUE ist der offizielle Intel-OpenMP-Workaround;
# OMP_NUM_THREADS limitiert die Thread-Spawns auf einen sinnvollen Wert,
# damit nicht 16+ OpenMP-Threads + Qt-Eventloop-Threads gleichzeitig
# Native-Locks anfechten. MUSS vor dem ersten torch/numpy-Import gesetzt
# werden — daher hier ganz oben.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

# Diagnostik: faulthandler aktivieren — bei nativen Crashes (SIGSEGV) und
# bei kontrolliertem Stack-Dump auf SIGBREAK (Ctrl+Pause auf Windows)
# wird ein Python-Stacktrace nach stderr geschrieben. Hilft bei der
# Diagnose von UI-Hangs (Brain-Open et al.) — User triggert per
# Ctrl+Pause einen Stack-Dump aller Threads.
import faulthandler as _faulthandler
_faulthandler.enable()
try:
    import signal as _signal
    if hasattr(_signal, "SIGBREAK"):
        _faulthandler.register(_signal.SIGBREAK, all_threads=True)
except Exception:  # broad: best-effort, kein App-Killer
    pass

# P1-FIX: Lokales bin-Verzeichnis zum PATH hinzufügen (ffmpeg/ffprobe Support)
_APP_ROOT = Path(__file__).parent.absolute()
_BIN_DIR = str(_APP_ROOT / "bin")
if _BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ["PATH"]

# CUDA-FIX: NVIDIA Treiber und VENV DLLs injizieren
# Dynamisch den NVIDIA-Treiber-Ordner im DriverStore finden (aendert sich bei Updates).
def _find_nv_driver_dir() -> str | None:
    driver_store = Path(r"C:\Windows\System32\DriverStore\FileRepository")
    if not driver_store.exists():
        return None
    # NVIDIA Display-Treiber-Ordner: nv*.inf_amd64_*
    # Mehrere koennen existieren — nehme den neuesten (hoechstes Aenderungsdatum).
    candidates = sorted(
        (d for d in driver_store.iterdir()
         if d.is_dir() and d.name.startswith("nv") and "amd64" in d.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for d in candidates:
        # Pruefe ob CUDA-relevante DLLs vorhanden sind (OpenCL, NvFBC, nvcuda)
        if any((d / n).exists() for n in ("nvcuda64.dll", "nvcuda.dll", "OpenCL64.dll", "NvFBC64.dll")):
            return str(d)
    # Fallback: erster nv*-Ordner
    return str(candidates[0]) if candidates else None

_NV_DRIVER = _find_nv_driver_dir()

# B-215: Torch-DLL-Pfad MUSS aus dem aktuell laufenden Python-Interpreter
# kommen — NICHT hardcoded auf .venv310. Wenn der User via Conda-Env startet
# (Migration 2026-04-27, siehe wiki/synthesis/cycle-21-conda-migration), aber
# main.py legacy `.venv310/Lib/site-packages/torch/lib` an PATH klebt,
# laden Windows' DLL-Loader unterschiedliche torch-DLLs als die, die der
# Python-Interpreter aus seinem site-packages importiert — Resultat:
# Heap-Korruption beim ersten echten Workload (RAFT/SigLIP), STATUS_STACK_
# BUFFER_OVERRUN (exit -1073740791).
def _detect_torch_dll_dir() -> str | None:
    """Findet das torch/lib-Verzeichnis des AKTUELLEN Interpreters."""
    try:
        # sys.prefix ist die env-Root (conda env oder venv).
        cand = Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib"
        if cand.exists():
            return str(cand)
        # POSIX-Fallback (sollte unter Windows nicht greifen)
        cand_unix = Path(sys.prefix) / "lib" / "python3.10" / "site-packages" / "torch" / "lib"
        if cand_unix.exists():
            return str(cand_unix)
    except Exception:
        pass
    return None

_VENV_DLLS = _detect_torch_dll_dir()

_DLL_DIRS: list[str] = []
if _VENV_DLLS:
    _DLL_DIRS.append(_VENV_DLLS)
if _NV_DRIVER:
    _DLL_DIRS.insert(0, _NV_DRIVER)

for _p in _DLL_DIRS:
    if _p not in os.environ["PATH"]:
        os.environ["PATH"] = _p + os.pathsep + os.environ["PATH"]
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_p)
        except Exception:
            pass

# FORCE CUDA INIT BEFORE QT LOADS
try:
    import torch
    if torch.cuda.is_available():
        # Trigger actual context creation
        torch.cuda.get_device_name(0)
except Exception:
    pass
# ---------------------------------------

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
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer, QTranslator, QLocale, QSettings
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QBrush, QPen, QPixmap, QImage, QPolygonF, QAction

# NEU: PB Studio Gold-Accent Theme (ersetzt qt_material)
from ui.theme import get_stylesheet
from services.ollama_service import OllamaService

APP_VERSION = "0.5.0"
ENABLE_VERSION_CHECK = False  # Deaktiviert bis Update-Server konfiguriert

import logging
logger = logging.getLogger(__name__)

# P-017: Legacy Thread-Registry — importiert aus WorkerDispatcher-Controller.
from ui.controllers.worker_dispatcher import _GLOBAL_ACTIVE_THREADS
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

# P3-FIX: TaskManagerProxy entfernt da überall GlobalTaskManager.instance() direkt
# verwendet wird. Der Proxy wurde nie wirklich genutzt.


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
from ui.dialogs.shortcut_help_dialog import ShortcutHelpDialog
from ui.dialogs.project_dialog import NewProjectDialog, OpenProjectDialog
from services.project_manager import ProjectManager
from ui.widgets.resource_monitor import ResourceMonitorWidget
from ui.controllers import (
    WorkerDispatcherController, AudioAnalysisController, VideoAnalysisController,
    EditWorkspaceController, ImportMediaController, ConvertController,
    ExportController, StemsController, SearchController,
    WorkspaceSetupController, PanelSetupController,
    ProjectManagementController, MediaTableController,
)


# ======================================================================
# Hauptfenster — DaVinci Resolve Style
# ======================================================================

class PBWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.logger = logger
        self._app_version = APP_VERSION
        self.setWindowTitle(f"PB_studio v{APP_VERSION} — Director's Cockpit")
        # P9-LAYOUT: Festes Fenster 1513×936. Kein Resize, keine Splitter.
        # Begruendung: Vorgabe aus docs/ui_audit/LAYOUT_PLAN.md — Inhalt soll
        # IMMER vollstaendig sichtbar sein, ohne Scrollen oder Verschieben.
        # Maximize-Button via WindowFlags abschalten.
        self.setFixedSize(1513, 936)
        from PySide6.QtCore import Qt as _Qt
        self.setWindowFlag(_Qt.WindowType.WindowMaximizeButtonHint, False)
        self._active_threads: list[QThread] = []
        self._active_workers: list[QObject] = []
        self._otio_timeline_service: TimelineService | None = None
        self._refresh_pending = False
        self._dirty = False  # AUD-108: unsaved changes tracking

        # P8-FREEZE-PROBE: Heartbeat fuer den Watchdog-Thread (siehe main()).
        # Der QTimer tickt alle 200ms → setzt den Zeitstempel. Watchdog
        # vergleicht: wenn Zeitstempel >1.5s alt → Stack-Dump (Main-Thread hing).
        import os as _os_hb
        if _os_hb.environ.get("PB_STUDIO_FREEZE_PROBE") == "1":
            import time as _time_hb
            from PySide6.QtCore import QTimer as _QTHb
            self._fh_timer = _QTHb(self)
            self._fh_timer.setInterval(200)
            def _tick():
                import sys as _s
                _mod = _s.modules.get("__main__")
                if _mod is not None:
                    _mod.__dict__["_fh_heartbeat"] = _time_hb.monotonic()
            self._fh_timer.timeout.connect(_tick)
            self._fh_timer.start()

        # P8-CUDA-FIX: Wenn der Boot CUDA als stuck erkannt hat (siehe main()),
        # bieten wir dem User sofort den Recovery-Dialog an. Der kann ihn auch
        # ablehnen → App laeuft dann mit CPU-Fallback weiter.
        import os as _os_stuck
        if _os_stuck.environ.get("PB_STUDIO_CUDA_STUCK") == "1":
            # Dialog nachladen via QTimer, damit der ctor zuerst durchlaeuft
            from PySide6.QtCore import QTimer as _QTStuck
            _QTStuck.singleShot(500, self._offer_cuda_recovery)

        # Controllers (Composition instead of Mixins)
        self.worker_dispatcher = WorkerDispatcherController(self)
        self.audio_analysis = AudioAnalysisController(self)
        self.video_analysis = VideoAnalysisController(self)
        self.edit_workspace = EditWorkspaceController(self)
        self.import_media = ImportMediaController(self)
        self.convert = ConvertController(self)
        self.export = ExportController(self)
        self.stems = StemsController(self)
        self.search = SearchController(self)
        self.workspace_setup = WorkspaceSetupController(self)
        self.panel_setup = PanelSetupController(self)
        self.project_management = ProjectManagementController(self)
        self.media_table_controller = MediaTableController(self)

        self._project_manager = ProjectManager(self)
        self._project_manager.project_changed.connect(self.project_management._on_project_changed)

        # Zentrales Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Bar ──
        self.workspace_setup._build_top_bar(main_layout, APP_VERSION)

        # ── Update-Notification Banner (hidden until a new version is found) ──
        self._update_banner = self._build_update_banner()
        main_layout.addWidget(self._update_banner)

        # ── Trennlinie ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,6);")
        main_layout.addWidget(sep)

        # ── Workspace Stack ── (P9-Step2: feste Breite, kein Splitter mehr)
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setFixedWidth(1213)
        self.workspace_setup._create_workspaces()

        # ── P9-Step2: Right-Panel als QTabWidget (300×836). Ersetzt den
        # Vertikal/Horizontal-Splitter + 3 QDockWidgets. Tabs werden in
        # panel_setup.setup_*() befuellt.
        from PySide6.QtWidgets import QTabWidget as _QTab
        self.right_panel = _QTab()
        self.right_panel.setFixedWidth(300)
        self.right_panel.setObjectName("right_panel")
        self.right_panel.setDocumentMode(True)
        self.right_panel.setTabPosition(_QTab.TabPosition.North)

        # Hauptbereich: Workspace links + Right-Panel rechts (HBox)
        _content = QWidget()
        _content_h = QHBoxLayout(_content)
        _content_h.setContentsMargins(0, 0, 0, 0)
        _content_h.setSpacing(0)
        _content_h.addWidget(self.workspace_stack)
        _content_h.addWidget(self.right_panel)
        main_layout.addWidget(_content, stretch=1)

        # Kompatibilitaets-Aliase (alter Code referenziert _main_splitter
        # / _inner_splitter — gibt's nicht mehr, aber wir setzen None damit
        # alte Aufrufe leise fehlschlagen statt AttributeError).
        self._main_splitter = None
        self._inner_splitter = None
        self._bottom_panel = None

        # ── Bottom Navigation Bar (DaVinci Style) ──
        self.nav_bar = WorkspaceNavBar()
        self.nav_bar.workspace_changed.connect(self.workspace_setup._on_workspace_changed)
        main_layout.addWidget(self.nav_bar)

        # ── Status Bar ── (P9-LAYOUT: kompakt, kein Size-Grip, fixed 18 px)
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setFixedHeight(18)
        self.status_bar.setStyleSheet("QStatusBar { font-size: 10px; padding: 0; }")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"PB_studio v{APP_VERSION} | System bereit")

        # ── Resource Monitor (CPU / RAM / GPU) ──
        resource_monitor = ResourceMonitorWidget()
        self.statusBar().addPermanentWidget(resource_monitor)

        # ── Panel Widgets — alle in das Right-Panel-TabWidget ──
        self.panel_setup.setup_task_dock()
        self.panel_setup.setup_console()
        self.panel_setup.setup_chat_dock()

        # P9-Step2: Toggle-Buttons in Top-Bar wechseln den aktiven Tab im
        # Right-Panel statt Sichtbarkeit zu togglen. Right-Panel selbst
        # bleibt immer sichtbar (300 px Sidebar).
        def _to_tab(label_substring):
            for i in range(self.right_panel.count()):
                if label_substring.lower() in self.right_panel.tabText(i).lower():
                    self.right_panel.setCurrentIndex(i)
                    return
        self._btn_toggle_tasks.clicked.connect(lambda: _to_tab("tasks"))
        self._btn_toggle_console.clicked.connect(lambda: _to_tab("log"))
        self._btn_toggle_chat.clicked.connect(lambda: _to_tab("chat"))

        # AUD-107: Restore window state after event loop starts (docks need a shown window)
        QTimer.singleShot(0, self.workspace_setup._restore_window_state)

        # P-016: Media-Tabelle NACH dem Window-Show laden (nicht im __init__)
        QTimer.singleShot(0, self.media_table_controller._refresh_media_table)

        # AUD-103: Version check — P1-FIX: gesteuert durch Feature-Flag
        if ENABLE_VERSION_CHECK:
            QTimer.singleShot(3000, self._start_version_check)

        # AUD-105: Keyboard shortcut help overlay (F1 + Ctrl+?)
        from PySide6.QtGui import QShortcut, QKeySequence as _QKS
        QShortcut(_QKS(Qt.Key.Key_F1), self, self.project_management._show_shortcut_help)
        QShortcut(_QKS("Ctrl+?"), self, self.project_management._show_shortcut_help)
        # P16: Studio Brain window — Ctrl+B shortcut. Singleton window,
        # brought to front on every call. Top-bar button is wired
        # separately in workspace_setup._build_top_bar.
        QShortcut(_QKS("Ctrl+B"), self, self._open_studio_brain)

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

    def _console_append(self, text: str) -> None:
        """Bug-C-Fix: Routet alle Konsolen-Writes durch den gepufferten Flush
        des PanelSetupControllers (250 ms Sammel-Tick). Vermeidet, dass jeder
        Worker-Progress-Tick einen synchronen QTextEdit.append() ausloest und
        damit Resize/MetaCall-SLOW-Events auf dem UI-Thread erzeugt.

        Falls der Puffer noch nicht initialisiert ist (sehr fruehe Phase vor
        setup_console()), faellt die Methode auf den direkten Append zurueck.
        """
        ps = getattr(self, 'panel_setup', None)
        if ps is not None and hasattr(ps, '_console_buffer'):
            ps._console_append(text)
            return
        if hasattr(self, 'console_text') and self.console_text is not None:
            self.console_text.append(text)

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
            # FIX H-1: Disconnect previous connections to prevent accumulation
            try:
                self._update_banner_link.clicked.disconnect()
            except RuntimeError:
                pass  # No connections yet
            self._update_banner_link.clicked.connect(
                lambda: __import__("webbrowser").open(download_url)
            )
        self._update_banner.setVisible(True)
        logger.info("Update banner shown: v%s available", latest_version)

    # ── End AUD-103 ───────────────────────────────────────────────────────

    # ── P16: Studio Brain entry-point ─────────────────────────────────────

    def _open_studio_brain(self) -> None:
        """Open (or bring to front) the Studio Brain window.

        Singleton via ``StudioBrainWindow.instance()`` — repeated calls
        reuse the same window and simply raise it. Defaults wire BrainService,
        SteerOverrideQueue, and BackupService against the app's main DB, so
        no explicit injection is needed at the call site.

        B-197 F-2: Wir verbinden ``timelineNavigationRequested(float)``
        einmalig mit Timeline + Video-Preview, damit Story-Map-Thumbnail-
        Clicks im Audit-Tab den Playhead in der Edit-Workspace springen
        lassen. Vorher war das Signal ein Dead-End.
        """
        try:
            from ui.studio_brain_window import StudioBrainWindow
            win = StudioBrainWindow.instance()
            # B-197 F-2: idempotent connect (Qt dedupliziert nicht von selbst,
            # daher disconnect-then-connect im Try um Doppel-Verbindungen bei
            # mehrfachen Brain-Opens zu verhindern).
            try:
                win.timelineNavigationRequested.disconnect(self._on_brain_timeline_nav)
            except (RuntimeError, TypeError):
                pass  # noch nie verbunden — first call
            win.timelineNavigationRequested.connect(self._on_brain_timeline_nav)
            # B-198 F-1: SteerTab Run-Button ist jetzt verkabelt. Vorher feuerte
            # ``runRequested(snapshot)`` ins Leere — der User sah nur Toast,
            # nichts passierte. Jetzt loest das Signal einen echten
            # ``auto_edit``-Task ueber den TaskManager aus.
            steer = getattr(win, "_steer_tab", None)
            if steer is not None and hasattr(steer, "runRequested"):
                try:
                    steer.runRequested.disconnect(self._on_brain_run_requested)
                except (RuntimeError, TypeError):
                    pass
                steer.runRequested.connect(self._on_brain_run_requested)
            win.show()
            win.raise_()
            win.activateWindow()
            logger.info("Studio Brain window opened")
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            logger.exception("Studio Brain open failed")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Studio Brain",
                f"Failed to open Studio Brain:\n\n{exc}",
            )

    def _on_brain_run_requested(self, snapshot: dict) -> None:
        """B-198 F-1: Slot fuer ``SteerTab.runRequested(dict)``.

        Brueckt den im Brain abgesetzten Pacing-Run-Wunsch auf den
        ``auto_edit``-Task im ``GlobalTaskManager``-Worker-Registry
        (siehe ``workers/registry.py``). Damit landet der Run im
        gleichen Worker-Pfad wie der EditWorkspace-Auto-Edit-Knopf.

        Snapshot-Felder die heute schon greifen:
        - ``audio_track_id`` → verpflichtend
        - ``video_ids`` werden hier aus der DB nachgezogen (alle
          non-deleted VideoClips im aktiven Project)

        Snapshot-Felder die heute IGNORIERT werden (Folge-Story):
        - ``weights_profile``, ``pins``, ``boosts``, ``excludes``.
          Der OverrideQueue-Inhalt fliesst aktuell nicht in die
          ``auto_edit_phase3``-Pipeline. ``SteerTab`` zeigt sie an,
          aber das Pacing kennt sie nicht. Vor F-1-v2 muss
          ``services/pacing_service.py`` so erweitert werden, dass
          die Queue-Items als Vorzugsfilter / Boost-Multiplikator
          eingehen.
        """
        try:
            audio_id = snapshot.get("audio_track_id")
            if audio_id is None:
                logger.warning(
                    "B-198 F-1: Brain-Run ignoriert — kein audio_track_id im Snapshot."
                )
                return
            from services.ingest_service import get_all_video

            video_ids = [v["id"] for v in get_all_video()]
            if not video_ids:
                logger.warning(
                    "B-198 F-1: Brain-Run ignoriert — keine Video-Clips im aktiven Project."
                )
                return
            from services.task_manager import GlobalTaskManager

            tm = GlobalTaskManager.instance()
            tm.agent_command_signal.emit(
                "auto_edit",
                {
                    "audio_track_id": int(audio_id),
                    "video_ids": video_ids,
                },
            )
            logger.info(
                "B-198 F-1: Brain-Run dispatched → audio=%s, %d clips, "
                "weights_profile=%s, queue_items=%d/%d/%d (pins/boosts/excludes)",
                audio_id, len(video_ids),
                snapshot.get("weights_profile") or "<default>",
                len(snapshot.get("pins") or []),
                len(snapshot.get("boosts") or []),
                len(snapshot.get("excludes") or []),
            )
        except Exception as exc:  # broad: UI-Slot darf nicht crashen
            logger.exception("B-198 F-1: Brain-Run-Dispatch failed: %s", exc)

    def _on_brain_timeline_nav(self, time_sec: float) -> None:
        """B-197 F-2: Slot fuer ``StudioBrainWindow.timelineNavigationRequested``.

        Setzt den Playhead in der InteractiveTimeline und lasst die
        Video-Preview an die gleiche Stelle springen. Beide APIs sind
        bestehend (`set_playhead_time` / `seek_to`); der Slot verkabelt
        sie nur defensiv (jeder Aufruf in eigenem try, damit ein
        fehlendes Sub-Widget nicht den anderen blockiert).
        """
        try:
            timeline = getattr(self, "timeline_view", None)
            if timeline is not None and hasattr(timeline, "set_playhead_time"):
                timeline.set_playhead_time(float(time_sec))
        except Exception as exc:  # broad: UI-Slot darf nicht crashen
            logger.warning("B-197 F-2: timeline.set_playhead_time failed: %s", exc)
        try:
            preview = getattr(self, "video_preview", None)
            if preview is not None and hasattr(preview, "seek_to"):
                preview.seek_to(float(time_sec))
        except Exception as exc:
            logger.warning("B-197 F-2: video_preview.seek_to failed: %s", exc)

    def _save_window_state(self):
        self.workspace_setup._save_window_state()

    def _mark_dirty(self):
        self.project_management._mark_dirty()

    def _offer_cuda_recovery(self):
        """P8-CUDA-FIX: Dialog bei stuck CUDA-Driver, bietet Recovery an.

        Recovery-Script braucht Admin-Rechte (UAC-Prompt). Wenn der User
        akzeptiert, wird die GPU disabled + enabled und die App-Session
        weiterlaufen mit CPU-Fallback. Beim naechsten App-Start ist CUDA
        wieder aktiv.
        """
        try:
            from PySide6.QtWidgets import QMessageBox
            import os as _os
            err = _os.environ.get("PB_STUDIO_CUDA_ERR", "CUDA unknown error")
            reply = QMessageBox.warning(
                self,
                "CUDA-Treiber blockiert",
                "Der NVIDIA-Treiber meldet einen stuck state:\n\n"
                f"  {err}\n\n"
                "Das passiert nach einem harten Prozess-Kill waehrend "
                "aktivem CUDA-Workload. Fuer diese Session laeuft die App "
                "mit CPU-Fallback.\n\n"
                "Jetzt automatisch reparieren?\n"
                "(Es wird ein UAC-Dialog folgen; Klick dort auf 'Ja'.\n"
                " Die GPU wird kurz deaktiviert und wieder aktiviert —\n"
                " kein Neustart noetig.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                from services.gpu_info import run_recovery_script
                if run_recovery_script():
                    QMessageBox.information(
                        self, "CUDA-Recovery gestartet",
                        "Das Recovery-Script laeuft jetzt in einem separaten Fenster.\n"
                        "Nach Abschluss: App bitte neu starten, damit CUDA erkannt wird.",
                    )
                else:
                    QMessageBox.critical(
                        self, "Recovery fehlgeschlagen",
                        "Das Recovery-Script konnte nicht gestartet werden.\n"
                        "Bitte manuell ausfuehren:\n"
                        "  scripts\\cuda_recovery.ps1\n"
                        "Oder Computer neu starten.",
                    )
            # Flag zuruecksetzen, damit der Dialog nicht wiederholt erscheint
            _os.environ.pop("PB_STUDIO_CUDA_STUCK", None)
        except Exception as exc:
            logger.warning("_offer_cuda_recovery failed: %s", exc)

    def closeEvent(self, event):
        """Behandelt das Schliessen der Anwendung (Fix F-003: Asynchroner Shutdown).

        MEDIUM-7 AUDIT: PBWindow ist eine God-Class mit 12 Controllers.
        Die Shutdown-Logik (10 Schritte) bleibt hier weil sie Zugriff auf
        alle Controller braucht. Refactor in ShutdownManager wuerde nur
        verschieben, nicht vereinfachen.
        """
        # 1. Fenster-Zustand sofort sichern
        try:
            self._save_window_state()
        except Exception as exc:
            logger.warning("closeEvent: failed to save window state: %s", exc)

        # 2. Prüfung auf ungespeicherte Änderungen
        if self._dirty:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Ungespeicherte Änderungen",
                "Es gibt ungespeicherte Änderungen. Trotzdem beenden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        # 3. Laufende Tasks prüfen
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
        except Exception as exc:
            logger.warning("closeEvent: failed to check running tasks: %s", exc)

        # ── AB HIER STARTET DER ASYNCHRONE SHUTDOWN ──
        # Fenster sofort verstecken für gefühlt "sofortiges" Beenden
        self.hide()
        QApplication.processEvents()
        logger.info("Shutdown eingeleitet: Fenster versteckt, beginne Cleanup...")

        # 4. Timer und Flag setzen
        if hasattr(self, '_task_mgr_dock') and hasattr(self._task_mgr_dock, '_timer'):
            self._task_mgr_dock._timer.stop()
        
        try:
            GlobalTaskManager.instance()._shutting_down = True
        except Exception as e:  # B-035 Fix: Log instead of silent pass
            logger.debug("Failed to set shutdown flag: %s", e)

        # 5. Alle Hintergrund-Tasks abbrechen UND warten (P7-FIX).
        # Vorher wurde cancel_task() gefeuert, aber auf die QThreads nicht
        # gewartet → bei ffmpeg-Export u.ä. loesst Qt beim nachfolgenden
        # event.accept() den FATAL "QThread: Destroyed while thread is still
        # running" aus, mit Risiko von DB-Korruption bei offenen Sessions.
        try:
            import time as _time
            tm = GlobalTaskManager.instance()
            running_tasks = [t for t in tm.get_all_tasks() if t.status == "running"]
            for task in running_tasks:
                tm.cancel_task(task.task_id)
            # Gebe jeder Task zusammen max. 10s, pro Task max 3s
            deadline = _time.monotonic() + 10.0
            for task in running_tasks:
                thread = getattr(task, "thread", None)
                if thread is None:
                    continue
                try:
                    if not thread.isRunning():
                        continue
                except RuntimeError:
                    continue  # C++-Teil bereits weg
                remaining = max(0.1, deadline - _time.monotonic())
                per_task_ms = int(min(3.0, remaining) * 1000)
                try:
                    thread.quit()
                    if not thread.wait(per_task_ms):
                        logger.warning(
                            "closeEvent: Task %s beendet sich nicht in %dms, force terminate.",
                            task.task_id, per_task_ms,
                        )
                        thread.terminate()
                        thread.wait(500)
                except RuntimeError as exc:
                    logger.debug("closeEvent: thread cleanup raced with auto-delete (%s): %s",
                                 task.task_id, exc)
        except Exception as e:  # B-035 Fix: Log instead of silent pass
            logger.warning("Failed to cancel/wait tasks on shutdown: %s", e)

        # 6. Legacy-Threads stoppen (minimales Warten)
        for thread in list(self._active_threads):
            thread.quit()
            if not thread.wait(500):
                logger.warning("Thread %s reagiert nicht, wird verwaist.", thread)

        self._active_threads.clear()
        self._active_workers.clear()
        _GLOBAL_ACTIVE_THREADS.clear()

        # M-9 Fix: Stop version check thread with timeout guard
        if hasattr(self, '_version_checker') and self._version_checker is not None:
            if self._version_checker.isRunning():
                self._version_checker.quit()
                if not self._version_checker.wait(2000):  # 2 second timeout
                    logger.warning("Version check thread did not stop gracefully")

        # 7. Video & Audio Cleanup
        if hasattr(self, "video_preview"):
            try:
                self.video_preview.stop()
            except Exception as e:  # B-035 Fix: Log instead of silent pass
                logger.debug("Video preview stop failed: %s", e)

        if hasattr(self, "stem_player"):
            self.stem_player.cleanup()

        # 8. Ollama stoppen (Gemma 4 Arbeitsplan)
        try:
            OllamaService.get().stop()
            logger.info("closeEvent: Ollama gestoppt.")
        except Exception as exc:
            logger.warning("closeEvent: Ollama-Stop fehlgeschlagen: %s", exc)

        # 9. VRAM final freigeben — **SYNCHRON**. P8-CUDA-FIX: Vorher
        # `unload_in_background()` → startet Worker-Thread, dann sofort
        # event.accept() → Prozess stirbt mit aktivem CUDA-Context.
        # Der NVIDIA-Treiber behaelt dann den Context gesperrt (Windows
        # WDDM-Eigenheit), `torch.cuda.is_available()` liefert beim naechsten
        # App-Start "CUDA unknown error" und die GPU ist fuer ALLE Prozesse
        # geblockt bis zum Device-Reset. Deshalb jetzt:
        #   - synchron entladen
        #   - torch.cuda.synchronize() + empty_cache() (schon in unload)
        #   - auch Worker-Pools (Demucs-Modell, SigLIP, beat_this) einzeln entladen
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
            logger.info("closeEvent: ModelManager.unload() synchron abgeschlossen")
        except Exception as exc:
            logger.warning("closeEvent: ModelManager.unload() fehlgeschlagen: %s", exc)

        # Finaler CUDA-Cleanup — auch falls der ModelManager schon leer war,
        # koennen Worker-lokale Tensor-Referenzen noch VRAM halten.
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.info("closeEvent: CUDA synchronize + empty_cache")
        except Exception as exc:
            logger.debug("closeEvent: final CUDA cleanup: %s", exc)

        # 10. Close DB connection pool (FIX C-2: BEFORE event.accept())
        try:
            from database import engine
            engine.dispose()
        except (ImportError, RuntimeError, OSError) as exc:
            logger.warning("closeEvent: failed to dispose DB connection pool: %s", exc)

        logger.info("Cleanup-Tasks gestartet. App-Fenster wird geschlossen.")
        event.accept()

        super().closeEvent(event)


# ======================================================================
# Logging + Entry Point
# ======================================================================

_log_listener = None  # Modul-global, damit atexit/shutdown ihn erreichen


def setup_logging():
    """Konfiguriert das Logging-System mit QueueHandler+QueueListener.

    Design (Fix fuer die in docs/BUG_logging_second_cause.md beschriebene Log-
    Stille nach Qt moveToThread-Warnings in Worker-Threads):

    * Loggende Threads (inkl. Qt-Worker) haengen nur `QueueHandler` am Root,
      der legt LogRecords in eine thread-safe `queue.Queue` — kein File-I/O,
      kein exclusive-Handle, kein Logging-Lock-Stau zwischen Workern.
    * Ein einziger `QueueListener`-Thread entleert die Queue in die echten
      Handler (StreamHandler + RotatingFileHandler). Damit gibt es genau
      einen Owner pro File-Handle.
    * Bei App-Shutdown: `_log_listener.stop()` via atexit, damit die Queue
      vor dem Prozessende geleert wird (sonst verliert man die letzten
      ~10 Records beim Crash).

    Console + RotatingFileHandler (5 MB, 3 Backups) fuer logs/pb_studio.log.
    Optionaler JSON-Format-Modus fuer Produktions-Builds:
      PB_STUDIO_JSON_LOGS=1  →  strukturiertes JSON (eine Zeile pro Record)
    """
    import atexit
    import json as _json
    import os
    import queue
    from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

    global _log_listener

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "pb_studio.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    use_json = os.environ.get("PB_STUDIO_JSON_LOGS", "").strip() == "1"

    if use_json:
        class _JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
                payload = {
                    "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc"] = self.formatException(record.exc_info)
                return _json.dumps(payload, ensure_ascii=False)

        fmt: logging.Formatter = _JsonFormatter()
    else:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Echte Sinks — bekommen Formatter + Level, laufen aber NUR im Listener-Thread
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    fh = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # Falls setup_logging mehrfach aufgerufen werden sollte: alten Listener stoppen
    if _log_listener is not None:
        try:
            _log_listener.stop()
        except Exception:  # pragma: no cover
            pass
    # Alte Handler am Root entfernen, um Doppel-Logs zu vermeiden
    for _h in list(root.handlers):
        root.removeHandler(_h)

    log_queue: queue.Queue = queue.Queue(-1)  # unbegrenzt — wir trauen dem Listener
    qh = QueueHandler(log_queue)
    root.addHandler(qh)

    _log_listener = QueueListener(log_queue, ch, fh, respect_handler_level=True)
    _log_listener.start()
    atexit.register(_log_listener.stop)

    logging.info(
        "Logging initialisiert → %s (json=%s, rotation=5MB×3, queue=async)",
        log_file, use_json,
    )


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
    # CLI-Argumente prüfen (HEADLESS MODE für Installer/Pre-Caching)
    if "--pre-cache" in sys.argv:
        import threading
        print("\n" + "=" * 60)
        print("  PB Studio — Model Pre-Caching Mode (Headless)")
        print("=" * 60)
        
        from services.model_lifecycle_service import get_model_lifecycle_service, RECOMMENDED_HF_MODELS
        import time
        
        service = get_model_lifecycle_service()
        models_to_download = [m["id"] for m in RECOMMENDED_HF_MODELS]
        
        # Zusätzliche Modelle aus pre_cache_models.py (falls nicht in RECOMMENDED_HF_MODELS)
        additional = ["facebook/htdemucs", "CPJKU/beat_this"]
        for m_id in additional:
            if m_id not in models_to_download:
                models_to_download.append(m_id)
        
        print(f"\nStarte Download von {len(models_to_download)} Modellen...")
        
        for m_id in models_to_download:
            print(f"\n[{m_id}] Prüfe/Lade...")

            # Download starten (blockierend für CLI)
            done_event = threading.Event()
            download_started = False

            def _prog(p):
                nonlocal download_started
                if p.finished:
                    done_event.set()
                elif p.status == "downloading":
                    download_started = True
                    print(f"  Progress: {p.progress*100:.1f}% | Speed: {p.speed_mbps:.1f} MB/s | ETA: {p.eta_sec}s", end="\r")

            success = service.download_hf_model(m_id, progress_cb=_prog)
            if success:
                # FIX H-19: Only wait if download actually started; reduce timeout to 5 min
                if download_started:
                    if not done_event.wait(timeout=300):
                        print(f"\n[ERROR] Timeout beim Download von {m_id}")
                    else:
                        print(f"\n[OK] {m_id} erfolgreich verarbeitet.")
                else:
                    # Model already cached, no download needed
                    print(f"\n[OK] {m_id} bereits vorhanden.")
            else:
                print(f"[SKIP/ERROR] Download konnte nicht gestartet werden für {m_id}")
        
        print("\n" + "=" * 60)
        print("  Pre-Caching abgeschlossen.")
        print("=" * 60 + "\n")
        sys.exit(0)

    setup_logging()

    # P8-FAULTHANDLER: Heartbeat-Watchdog — dumpt NUR wenn der Qt-Main-Thread
    # den Event-Loop >1.5s nicht mehr bedient. Aktiv wenn PB_STUDIO_FREEZE_PROBE=1.
    #
    # Mechanik:
    #   - QTimer im Main-Thread tickt alle 200ms → aktualisiert _heartbeat_ts.
    #   - Watchdog-Thread prueft alle 500ms: wenn _heartbeat_ts > 1.5s alt,
    #     dumpt faulthandler.dump_traceback(all_threads=True).
    #   - Kein periodischer Dump bei idle. Nur bei echten Main-Thread-Hangs.
    import os as _os_fh
    if _os_fh.environ.get("PB_STUDIO_FREEZE_PROBE") == "1":
        import faulthandler as _fh
        import threading as _threading_fh
        import time as _time_fh
        from pathlib import Path as _P
        _freeze_log = _P(__file__).parent / "logs" / "freeze_stacks.log"
        _freeze_log.parent.mkdir(exist_ok=True)
        _freeze_fp = open(_freeze_log, "a", buffering=1, encoding="utf-8")
        _fh.enable(file=_freeze_fp)
        # Modul-globaler Heartbeat — wird vom QTimer im Main-Thread aktualisiert
        globals()["_fh_heartbeat"] = _time_fh.monotonic()
        globals()["_fh_fp"] = _freeze_fp
        def _watchdog():
            last_dump = 0.0
            while True:
                _time_fh.sleep(0.5)
                delta = _time_fh.monotonic() - globals().get("_fh_heartbeat", 0)
                if delta > 1.5 and (_time_fh.monotonic() - last_dump) > 2.0:
                    _freeze_fp.write(f"\n=== WATCHDOG: Main-Thread blockiert seit {delta:.1f}s ===\n")
                    _freeze_fp.flush()
                    _fh.dump_traceback(file=_freeze_fp, all_threads=True)
                    last_dump = _time_fh.monotonic()
        _wd = _threading_fh.Thread(target=_watchdog, daemon=True, name="freeze-watchdog")
        _wd.start()
        logging.info("[FREEZE-PROBE] Heartbeat-Watchdog aktiv → %s (dumpt nur bei echten Main-Thread-Hangs >1.5s)", _freeze_log)

    # P8-FIX: GPU-Info einmal beim Boot cachen. Vermeidet torch.cuda.*
    # Aufrufe im Main-Thread (z.B. About-Dialog, Chat-Status), die bei
    # stuck CUDA-Treiber minutenlang blockieren koennen.
    try:
        from services.gpu_info import initialize_gpu_info_cache, detect_stuck_driver, run_recovery_script
        _gpu = initialize_gpu_info_cache()
        logging.info("GPU-Info Cache: %s", _gpu.summary())

        # P8-CUDA-RECOVERY: Wenn CUDA kompiliert aber nicht verfuegbar → Stuck?
        if not _gpu.available and _gpu.compiled_cuda:
            is_stuck, err = detect_stuck_driver()
            if is_stuck:
                logging.error("CUDA-Treiber im Stuck-State erkannt: %s", err)
                # UAC-Recovery-Prompt anbieten — Qt-Dialog erst nach App-Start
                # Wir merken uns das und zeigen's im PBWindow ctor.
                import os
                os.environ["PB_STUDIO_CUDA_STUCK"] = "1"
                os.environ["PB_STUDIO_CUDA_ERR"] = err[:200]
    except Exception as _exc:  # pragma: no cover
        logging.warning("GPU-Info Cache-Init fehlgeschlagen: %s", _exc)

    # P8-CUDA-FIX: atexit-Safety-Net. Wird bei jeder regulaeren
    # Prozess-Beendigung aufgerufen (auch sys.exit, nicht aber taskkill /F).
    # Falls closeEvent aus irgend einem Grund nicht lief, entladen wir hier
    # noch einmal defensiv. Verhindert Stuck-Driver bei unerwarteten Exits.
    def _cuda_atexit_cleanup():
        # B-112 / BUG-14-b: dropped torch.cuda.synchronize() — it can
        # block forever on a stuck kernel during interpreter shutdown
        # (e.g. after a Code-47 dGPU). closeEvent already does sync;
        # this atexit safety-net only needs to release VRAM.
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    import atexit as _atexit_cuda
    _atexit_cuda.register(_cuda_atexit_cleanup)

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

    # B-196: ``Qt.AA_ShareOpenGLContexts`` MUSS vor ``QApplication(...)`` gesetzt
    # werden — Voraussetzung fuer QtWebEngine. Ohne dieses Attribut kann der
    # spaetere Lazy-Import von ``PySide6.QtWebEngineWidgets`` (wenn der User
    # das Studio Brain oeffnet) im laufenden UI-Thread deadlocken. Im
    # isolierten Test passiert das nicht, weil dort QApplication frisch ist —
    # genau dieser Unterschied versteckt den Bug bis zum echten Brain-Open.
    from PySide6.QtCore import Qt as _Qt
    QApplication.setAttribute(_Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    # B-196: WebEngineWidgets EARLY pre-importieren — registriert Chromium
    # waehrend des App-Starts statt mitten in einem UI-Klick. Idempotent;
    # bei fehlender Library bleibt es bei einem Logger-Eintrag und der
    # GraphCockpit-Tab faellt automatisch in seinen TextEdit-Fallback.
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView  # noqa: F401
    except Exception as _qweb_exc:  # broad: WebEngine darf App-Start nicht killen
        logging.getLogger(__name__).warning(
            "B-196: QtWebEngineWidgets early-import fehlgeschlagen: %s. "
            "Studio Brain wird ohne Graph-Cockpit starten.", _qweb_exc,
        )

    app = QApplication(sys.argv)

    # B-218: Native Power-Event-Listener fuer Windows. Bei Laptop-Andocken/
    # -Sleep verliert die GTX 1060 Mobile den CUDA-Power-State -> der
    # gehaltene CUDA-Context wird stale. Beim naechsten cuda-Call (Modell-
    # Load oder Inferenz) crasht torch nativ mit STATUS_STACK_BUFFER_OVERRUN
    # (exit -1073740791). Wir signalisieren ModelManager bei Resume, dass
    # der Context probed werden soll — bei Fail wird auf CPU zurueckgefallen.
    if sys.platform == "win32":
        try:
            from PySide6.QtCore import QAbstractNativeEventFilter

            class _PowerEventFilter(QAbstractNativeEventFilter):
                """Hoert auf WM_POWERBROADCAST.

                Wichtige WMs (winuser.h):
                  WM_POWERBROADCAST = 0x0218
                  PBT_APMSUSPEND          = 0x0004
                  PBT_APMRESUMESUSPEND    = 0x0007
                  PBT_APMRESUMEAUTOMATIC  = 0x0012
                  PBT_POWERSETTINGCHANGE  = 0x8013  (kann Display-Power-State liefern)
                """

                def nativeEventFilter(self, event_type, message):
                    if event_type != b"windows_generic_MSG" and event_type != "windows_generic_MSG":
                        return False, 0
                    try:
                        import ctypes
                        from ctypes import wintypes

                        class _MSG(ctypes.Structure):
                            _fields_ = [
                                ("hWnd", wintypes.HWND),
                                ("message", wintypes.UINT),
                                ("wParam", wintypes.WPARAM),
                                ("lParam", wintypes.LPARAM),
                                ("time", wintypes.DWORD),
                                ("pt_x", wintypes.LONG),
                                ("pt_y", wintypes.LONG),
                            ]

                        addr = int(message)
                        msg = _MSG.from_address(addr)
                        if msg.message == 0x0218:  # WM_POWERBROADCAST
                            wparam = int(msg.wParam) & 0xFFFFFFFF
                            if wparam in (0x0007, 0x0012):  # RESUMESUSPEND / RESUMEAUTOMATIC
                                from services.model_manager import ModelManager
                                logging.getLogger(__name__).info(
                                    "B-218: Power-Resume detected (wParam=0x%04x) — "
                                    "informiere ModelManager.", wparam,
                                )
                                ModelManager().notify_power_resume()
                            elif wparam == 0x0004:  # APMSUSPEND
                                logging.getLogger(__name__).info(
                                    "B-218: System geht in Suspend — CUDA-Context "
                                    "wird voraussichtlich invalidiert."
                                )
                                from services.model_manager import ModelManager
                                ModelManager().notify_power_resume()
                    except Exception:
                        # Filter darf NIE den Eventloop killen.
                        pass
                    return False, 0

            _power_filter = _PowerEventFilter()
            app.installNativeEventFilter(_power_filter)
            # Reference halten, sonst GC sweeped den Filter.
            app._power_filter_ref = _power_filter  # type: ignore[attr-defined]
        except Exception as _pwr_exc:
            logging.getLogger(__name__).warning(
                "B-218: Power-Event-Listener konnte nicht installiert werden — "
                "CUDA-Health-Check greift nur lazy beim naechsten Modell-Load: %s",
                _pwr_exc,
            )

    # Sticky-Tooltips: haelt Tooltips sichtbar, solange der Cursor auf
    # dem Widget steht (Qt-Default blendet nach 10 s aus). Lokaler Import
    # um Qt-Init-Reihenfolge nicht zu stoeren.
    from ui.tooltip_utils import install_sticky_tooltips
    install_sticky_tooltips(app)

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
    # FIX H-18: Initialize system_status before use in final_init
    app.system_status = None

    app.setStyleSheet(get_stylesheet())

    # ── App Icon ──────────────────────────────────────────────────────
    from ui.app_icon import get_app_icon
    _app_icon = get_app_icon()
    app.setWindowIcon(_app_icon)

    # ── Splash Screen ─────────────────────────────────────────────────
    from ui.splash import PBSplashScreen
    splash = PBSplashScreen(APP_VERSION)
    splash.show()
    QApplication.processEvents()
    splash.show_message("Initialisiere Datenbank...")
    QApplication.processEvents()

    # ── Startup ───────────────────────────────────────────────────────
    # FIX H-22: Create DB tables before PBWindow to prevent access errors
    from database import Base, engine
    Base.metadata.create_all(engine)

    # Cycle 14 Hotfix: Alembic-Migrations SYNCHRON vor PBWindow ausführen.
    # Vorher lief das nur im StartupCheckWorker async — wenn PBWindow
    # einen Worker startete der ORM-Queries macht (z.B. media_table
    # "Medien-DB laden"), konnte dieser schneller sein als die Migration
    # und mit "no such column" crashen, sobald ein Schema-Change frisch
    # geadded wurde (z.B. b2c3d4e5f6a7 sub_genre/spectral_hash/
    # harmonic_tension).
    try:
        splash.show_message("Datenbank-Migrationen prüfen...")
        QApplication.processEvents()
        from database import init_db as _init_db_sync
        _init_db_sync()
    except Exception as _mig_exc:  # broad: Migration darf App-Start nicht killen
        logger.error(
            "Alembic-Migrationen beim Start fehlgeschlagen: %s. "
            "App startet trotzdem; ORM-Queries können crashen.",
            _mig_exc,
        )

    # P1-FIX: Fenster sofort zeigen, damit der User Feedback hat.
    # Schwere Operationen werden verzögert ausgeführt.
    splash.show_message("Lade Benutzeroberfläche...")
    QApplication.processEvents()

    # P16: Surface Book 2 GPU stuck-state detection. If the dGPU is in
    # CM_PROB_HELD_FOR_EJECT (Code 47), show a friendly dialog before
    # constructing PBWindow — otherwise the user faces silent CPU-fallback
    # with no explanation.
    try:
        from services.startup_checks import check_nvidia_gpu_state
        from ui.dialogs.gpu_recovery_dialog import GpuRecoveryDialog
        # B-220: Recovery-Dialog mit Re-Check-Loop. User kann
        # Detach+Reattach machen und "GPU erneut pruefen" klicken — Dialog
        # schliesst, App re-queryt PnP-Status. Wenn ok: App startet
        # normal. Wenn weiter stuck: Dialog wird neu gezeigt, User kann
        # erneut versuchen, Reboot oder CPU waehlen.
        # Maximum 5 Re-Checks um Endlos-Schleife zu verhindern (User-
        # Bedienfehler). Danach wird der Recheck-Pfad nicht mehr
        # angeboten — Dialog zeigt nur noch Reboot/CPU/Cancel.
        _max_rechecks = 5
        _recheck_count = 0
        while True:
            _gpu_state, _gpu_msg = check_nvidia_gpu_state()
            if _gpu_state == "ok":
                # GPU jetzt verfuegbar — kein Dialog noetig.
                if _recheck_count > 0:
                    logger.info(
                        "B-220: GPU nach %d Re-Check(s) wieder verfuegbar — App startet normal.",
                        _recheck_count,
                    )
                break
            if _gpu_state in ("held_for_eject", "failed_post_start"):
                logger.warning(
                    "GPU-Stuck-State erkannt (%s): %s", _gpu_state, _gpu_msg,
                )
                splash.hide()
                _dlg = GpuRecoveryDialog(problem_kind=_gpu_state)
                _dlg.exec()
                _choice = _dlg.choice()
                if _choice == "cancel":
                    sys.exit(0)
                if _choice == "restart":
                    # PB Studio beendet sich. User startet den Computer manuell
                    # neu (Start → Power → Neu starten). Wir triggern KEINEN
                    # automatischen Reboot, weil das ungesicherte Arbeit in
                    # anderen Programmen zerstoeren wuerde.
                    sys.exit(0)
                if _choice == "recheck" and _recheck_count < _max_rechecks:
                    _recheck_count += 1
                    logger.info(
                        "B-220: User triggered GPU re-check (%d/%d).",
                        _recheck_count, _max_rechecks,
                    )
                    splash.show()
                    QApplication.processEvents()
                    continue  # zurueck zur check_nvidia_gpu_state-Schleife
                # "cpu_fallback" oder recheck-Limit erreicht: weiter mit CPU.
                splash.show()
                QApplication.processEvents()
                break
            # other_error oder absent: log, kein Dialog.
            logger.warning(
                "GPU-Status %s: %s — App startet im CPU-Fallback.",
                _gpu_state, _gpu_msg,
            )
            break
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - diagnostic path
        logger.warning("GPU state check failed: %s", exc)

    try:
        window = PBWindow()
    except (ImportError, RuntimeError, OSError) as exc:
        splash.close()
        logging.critical("Fenster-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        sys.exit(1)

    window.setWindowIcon(_app_icon)
    window.showMaximized()
    splash.finish(window)

    # Performance-Watchdog: Misst jedes Event im Main-Thread.
    # Loggt alles >50ms in logs/pb_studio.log als [SLOW EVENT].
    from services.perf_watchdog import install_watchdog
    install_watchdog(app, threshold_ms=50)

    # ── Verzögerte Initialisierung (Fix F-035) ────────────────────────
    def final_init():
        try:
            # FIX H-21: Removed duplicate init_db() call - StartupCheckWorker handles it
            # 1. KI-Engine (Gemma 4 Arbeitsplan)
            try:
                OllamaService.get().start()
                if OllamaService.get().is_ready:
                    window.console_text.append("[KI] AI-Engine aktiv. Modell: Gemma 4 E4B (lokal).")
                else:
                    window.console_text.append("[KI] AI-Engine wird im Hintergrund gestartet...")
            except Exception as exc:
                logger.warning("Ollama-Start fehlgeschlagen: %s", exc)

            # 3. System Check (async via Worker um UI flüssig zu halten)
            # FIX C-4: Store worker refs on window to prevent GC while thread runs
            from workers.startup import StartupCheckWorker
            window._startup_check_worker = StartupCheckWorker()
            window._startup_check_thread = QThread(window)
            window._startup_check_worker.moveToThread(window._startup_check_thread)

            def on_done(status):
                app.system_status = status
                _ai_status = '● AI ready' if OllamaService.get().is_ready else '● AI loading...'
                window.status_bar.showMessage(f"System bereit | {status.status_bar_text()} | {_ai_status}")
                window.console_text.append(f"[System] {status.status_bar_text()}")
                # FIX H-4: Show startup check dialog if there are errors or warnings
                from ui.dialogs.startup_check_dialog import maybe_show_startup_dialog
                if not maybe_show_startup_dialog(status, window):
                    # User chose "Beenden" — exit the application
                    app.quit()
                    return
                # 3. Timeline laden wenn alles bereit ist
                window.timeline_view.load_from_db()
                window._startup_check_thread.quit()

            window._startup_check_worker.finished.connect(on_done)
            window._startup_check_worker.progress.connect(lambda msg: window.status_bar.showMessage(msg))
            window._startup_check_thread.started.connect(window._startup_check_worker.run)
            window._startup_check_thread.start()
            
        except Exception as e:
            logger.error("Fehler bei finaler Initialisierung: %s", e, exc_info=True)

    # Startet 500ms nach dem das Fenster sichtbar ist
    QTimer.singleShot(500, final_init)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
