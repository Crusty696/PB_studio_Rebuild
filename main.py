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

# B-336: dGPU (GTX 1060 / Surface-Book-2-Base) muss VOR dem ersten torch.cuda-
# Call verbunden/wach sein. torch cached den CUDA-Init prozessweit: ist die GPU
# im Import-Moment kurz abwesend (ConfigManagerErrorCode=45 / PnP-Wake-Delay),
# bleibt torch.cuda.is_available() den ganzen Prozess False -> komplette Session
# auf CPU (alle Modelle + libx264). Die spaetere PnP-Recovery-Schleife in main()
# kann torch dann nicht mehr umstimmen. Darum hier ein OS-Level-PnP-Check (ohne
# torch) mit kurzem Retry, damit torchs erste Probe die wache GPU sieht.
if os.name == "nt":
    try:
        import time as _gpu_wait_time
        from services.startup_checks import check_nvidia_gpu_state
        for _gpu_attempt in range(4):
            _gpu_state, _gpu_detail = check_nvidia_gpu_state()
            if _gpu_state == "ok":
                break
            if _gpu_attempt == 0:
                print(
                    f"[GPU] dGPU noch nicht bereit ({_gpu_state}: {_gpu_detail}) "
                    f"- warte aufs Aufwachen vor CUDA-Init ...",
                    flush=True,
                )
            _gpu_wait_time.sleep(1.5)
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
    QHBoxLayout, QStatusBar, QPushButton,
    QLabel, QFrame,
    QStackedWidget,
    QSizePolicy,
    QDockWidget,
)
from PySide6.QtCore import Qt, QThread, QObject, QTimer, QTranslator, QLocale

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

import os
from services.timeline_service import TimelineService


# ======================================================================
# Task-Engine (extracted to services/task_manager.py)
# ======================================================================
import services.task_manager as _task_manager_module
from services.task_manager import GlobalTaskManager

# P3-FIX: TaskManagerProxy entfernt da überall GlobalTaskManager.instance() direkt
# verwendet wird. Der Proxy wurde nie wirklich genutzt.


# ======================================================================
# Background Workers (extracted to workers/ package)
# ======================================================================

# Command Pattern: Worker-Registry (side-effect import registriert alle Worker)
import workers.registry  # noqa: F401


# ======================================================================
# UI Widgets (extracted to ui/ submodules)
# ======================================================================
from ui.widgets.nav_bar import WorkspaceNavBar
from ui.widgets.workflow_components import ContextPanel
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
        # Workflow shell: resizable again. The old fixed 1513x936 layout made
        # empty areas and hidden affordances worse on real monitors.
        self.resize(1513, 936)
        self.setMinimumSize(1280, 800)
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

        # Phase-2 + Phase-3 App-Sync (Plan 06_PHASES.md):
        # EmbeddingScheduler wird async gestartet (QTimer 0 → nach Show
        # damit Boot nicht blockiert). Brain-Store-Health-Check ebenso.
        self._brain_v3_scheduler = None
        from PySide6.QtCore import QTimer as _QTBV3
        _QTBV3.singleShot(0, self._boot_brain_v3_services)

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

        # ── Workflow Navigation ──
        self.nav_bar = WorkspaceNavBar()
        self.nav_bar.workspace_changed.connect(self.workspace_setup._on_workspace_changed)
        main_layout.addWidget(self.nav_bar)

        # ── Workspace Stack ──
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.workspace_setup._create_workspaces()

        # Context panel starts collapsed. Tasks, log and chat stay alive and
        # can expand it when the user or a task needs context.
        self.right_panel = ContextPanel()

        # Hauptbereich: nur noch der Workspace-Stack im zentralen Layout.
        _content = QWidget()
        _content_h = QHBoxLayout(_content)
        _content_h.setContentsMargins(0, 0, 0, 0)
        _content_h.setSpacing(0)
        _content_h.addWidget(self.workspace_stack)
        main_layout.addWidget(_content, stretch=1)

        # UI-Ueberholung 2026-06-13 (User-Feedback "TASKS halb so gross + andockbar"):
        # Das Kontext-/TASKS-Panel ist jetzt ein QDockWidget statt fest in der
        # HBox -> abreissbar (float), verschiebbar (links/rechts), schliessbar,
        # und mit ~halber Breite (ContextPanel.DEFAULT_WIDTH 280 -> 180).
        self.right_dock = QDockWidget("Kontext", self)
        self.right_dock.setObjectName("context_dock")
        self.right_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.right_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.right_dock.setWidget(self.right_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)

        # Kompatibilitaets-Aliase (alter Code referenziert _main_splitter
        # / _inner_splitter — gibt's nicht mehr, aber wir setzen None damit
        # alte Aufrufe leise fehlschlagen statt AttributeError).
        self._main_splitter = None
        self._inner_splitter = None
        self._bottom_panel = None

        # ── Status Bar ── (P9-LAYOUT: kompakt, kein Size-Grip, fixed 18 px)
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setFixedHeight(18)
        self.status_bar.setStyleSheet("QStatusBar { font-size: 10px; padding: 0; }")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"PB_studio v{APP_VERSION} | System bereit")

        # ── LLM-Anzeige (aktuelles KI-Modell + Ladebalken) ──
        from ui.widgets.model_status_field import ModelStatusField
        self._model_status_field = ModelStatusField()
        self.statusBar().addPermanentWidget(self._model_status_field)

        # ── Resource Monitor (CPU / RAM / GPU) ──
        self._resource_monitor = ResourceMonitorWidget()
        self.statusBar().addPermanentWidget(self._resource_monitor)

        # ── Panel Widgets — alle in das Right-Panel-TabWidget ──
        self.panel_setup.setup_task_dock()
        self.panel_setup.setup_console()
        self.panel_setup.setup_chat_dock()
        for i in range(self.right_panel.count()):
            if self.right_panel.tabText(i).lower() == "tasks":
                self.right_panel.setCurrentIndex(i)
                break
        # B-253: globaler Listener auf analysis_status_service.mark_completed,
        # triggert UI-Refresh nach Pipeline-Done (egal ob UI-Button oder
        # ActionRegistry-Pfad). Loest insbesondere das stem_separation-
        # Refresh-Loch.
        self.panel_setup.setup_analysis_completion_bridge()

        # B-321: Brain-V3-Stats importiert Pydantic/Brain-Service schwer.
        # Tab erst beim Oeffnen laden, nicht im PBWindow-Konstruktor.
        self._brain_v3_stats_panel = None
        self._brain_v3_stats_placeholder = QWidget(parent=self.right_panel)
        _brain_lazy_layout = QVBoxLayout(self._brain_v3_stats_placeholder)
        _brain_lazy_layout.addWidget(QLabel("Brain V3 wird beim Öffnen geladen."))
        self._brain_v3_stats_tab_index = self.right_panel.addTab(
            self._brain_v3_stats_placeholder,
            "Brain V3",
        )
        self.right_panel.currentChanged.connect(self._on_context_panel_tab_changed)
        logger.info("PBWindow: BrainV3StatsPanel als Lazy-Tab eingehängt")

        # P9-Step2: Toggle-Buttons in Top-Bar wechseln den aktiven Tab im
        # Right-Panel statt Sichtbarkeit zu togglen. Right-Panel selbst
        # bleibt immer sichtbar (300 px Sidebar).
        def _to_tab(label_substring):
            self._set_context_panel_visible(True)
            for i in range(self.right_panel.count()):
                if label_substring.lower() in self.right_panel.tabText(i).lower():
                    self.right_panel.setCurrentIndex(i)
                    return
        self._btn_toggle_tasks.clicked.connect(lambda: _to_tab("tasks"))
        self._btn_toggle_console.clicked.connect(lambda: _to_tab("log"))
        self._btn_toggle_chat.clicked.connect(lambda: _to_tab("chat"))
        self._btn_context_panel.clicked.connect(self._set_context_panel_visible)

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

    def _on_context_panel_tab_changed(self, index: int) -> None:
        if index == getattr(self, "_brain_v3_stats_tab_index", -1):
            self._load_brain_v3_stats_panel()

    def _load_brain_v3_stats_panel(self) -> None:
        if self._brain_v3_stats_panel is not None:
            return
        try:
            from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
            panel = BrainV3StatsPanel(parent=self.right_panel)
            self._brain_v3_stats_panel = panel
            self.right_panel.removeTab(self._brain_v3_stats_tab_index)
            self._brain_v3_stats_tab_index = self.right_panel.insertTab(
                self._brain_v3_stats_tab_index,
                panel,
                "Brain V3",
            )
            self.right_panel.setCurrentIndex(self._brain_v3_stats_tab_index)
            logger.info("PBWindow: BrainV3StatsPanel lazy geladen")
        except Exception as exc:
            logger.warning("Brain-V3-Stats-Panel konnte nicht geladen werden: %s", exc)

    def _set_context_panel_visible(self, visible: bool) -> None:
        """Collapse/expand the contextual side panel without destroying widgets.

        UI-Ueberholung 2026-06-13: Das Panel sitzt jetzt in einem QDockWidget;
        Ein-/Ausblenden geschieht ueber die Dock-Sichtbarkeit. Die Panel-interne
        Breiten-Logik (set_context_visible) setzt zusaetzlich die ~halbe Breite,
        wenn sichtbar.
        """
        dock = getattr(self, "right_dock", None)
        if hasattr(self.right_panel, "set_context_visible"):
            self.right_panel.set_context_visible(visible)
        else:
            self.right_panel.setFixedWidth(self.right_panel.DEFAULT_WIDTH if visible else 0)
            self.right_panel.setVisible(visible)
        if dock is not None:
            dock.setVisible(visible)
        if hasattr(self, "_btn_context_panel"):
            self._btn_context_panel.setChecked(visible)

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
        gleichen Worker-Pfad wie der SCHNITT-Workspace-Auto-Edit-Knopf.

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
            from services.pacing_service import AdvancedPacingSettings

            edit_workspace = getattr(self, "edit_workspace", None)
            if edit_workspace is None or not hasattr(edit_workspace, "start_auto_edit_worker"):
                logger.warning(
                    "B-198 F-1: Brain-Run ignoriert — EditWorkspaceController fehlt."
                )
                return
            edit_workspace.start_auto_edit_worker(
                audio_id=int(audio_id),
                video_ids=video_ids,
                settings=AdvancedPacingSettings(),
                task_name="Auto-Edit (Studio Brain)",
                task_description="Studio-Brain SteerTab Run",
            )
            logger.info(
                "B-198 F-1: Brain-Run dispatched via EditWorkspaceController → audio=%s, %d clips, "
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

    def _boot_brain_v3_services(self) -> None:
        """Phase-2 + Phase-3 App-Sync (Plan 06_PHASES.md):
        - Brain-Store-Health-Check (3 V3-DBs lesbar, Disk-Space)
        - GpuSerializer Init (Singleton)
        - EmbeddingScheduler start (QThread + asyncio-Loop)
        Alle Aktionen sind best-effort; Fehler werden geloggt, App laeuft weiter.
        """
        # Health-Check
        try:
            from services.brain_v3.storage.brain_store import BrainStore
            store = BrainStore()
            health = store.health_check()
            health_msg = (
                f"[Brain V3] Hirn-Store-Health: "
                f"weights.db {'ok' if health.weights_ok else 'fail'}, "
                f"patterns.db {'ok' if health.patterns_ok else 'fail'}, "
                f"embedding_cache.db {'ok' if health.embedding_cache_ok else 'fail'}, "
                f"migrations v{health.migrations_version}, free {health.disk_space_mb} MB"
            )
            logger.info(health_msg)
            self.console_text.append(health_msg)
            for err in health.errors:
                err_msg = f"[Brain V3] Health-Warnung: {err}"
                logger.warning(err_msg)
                self.console_text.append(err_msg)
        except Exception as exc:
            logger.warning("_boot_brain_v3_services: health-check fehlgeschlagen: %s", exc)
            self.console_text.append(f"[Brain V3] Health-Check Fehler: {exc}")

        # GpuSerializer-Init (Lazy-Singleton)
        try:
            from services.brain_v3.gpu_serializer import get_default_serializer
            get_default_serializer()
            logger.info("_boot_brain_v3_services: GpuSerializer initialisiert")
        except Exception as exc:
            logger.warning("_boot_brain_v3_services: GpuSerializer-Init fehlgeschlagen: %s", exc)

        # EmbeddingScheduler start
        try:
            from services.brain_v3.embedding_scheduler import get_default_scheduler
            scheduler = get_default_scheduler()
            scheduler.start()
            self._brain_v3_scheduler = scheduler
            logger.info("[Brain V3] EmbeddingScheduler gestartet")
            self.console_text.append("[Brain V3] EmbeddingScheduler gestartet")
        except Exception as exc:
            logger.warning("_boot_brain_v3_services: EmbeddingScheduler-Start fehlgeschlagen: %s", exc)
            self.console_text.append(f"[Brain V3] EmbeddingScheduler Fehler: {exc}")

        self._start_brain_v3_backup_check()

    def _start_brain_v3_backup_check(self) -> None:
        """Phase 6: weekly Brain-V3 DB backup check, never on GUI thread."""
        try:
            import threading

            thread = threading.Thread(
                target=self._run_brain_v3_backup_check,
                name="brain-v3-weekly-backup",
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            logger.warning("Brain-V3 weekly backup thread start failed: %s", exc)

    def _run_brain_v3_backup_check(self) -> None:
        try:
            from services.brain_v3.storage.backup import run_weekly_backup_if_due

            result = run_weekly_backup_if_due()
        except Exception as exc:
            logger.warning("Brain-V3 weekly backup check failed: %s", exc)
            return
        if result.ran and result.backup is not None:
            logger.info(
                "[Brain V3] Weekly backup created: %s (%d files, %d pruned)",
                result.backup.backup_dir,
                len(result.backup.files_written),
                len(result.deleted),
            )
        elif result.reason != "not_due":
            logger.warning("[Brain V3] Weekly backup skipped: %s", result.reason)

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

        # ResourceMonitorWidget besitzt einen QThread. Ohne stop() beendet
        # Windows den Prozess nach QApplication-Exit mit STATUS_STACK_BUFFER_OVERRUN.
        try:
            resource_monitor = getattr(self, "_resource_monitor", None)
            if resource_monitor is not None and hasattr(resource_monitor, "stop"):
                resource_monitor.stop()
        except Exception as exc:
            logger.warning("closeEvent: ResourceMonitor-Stop fehlgeschlagen: %s", exc)

        # 7. Video & Audio Cleanup
        if hasattr(self, "video_preview"):
            try:
                self.video_preview.stop()
            except Exception as e:  # B-035 Fix: Log instead of silent pass
                logger.debug("Video preview stop failed: %s", e)

        if hasattr(self, "stem_player"):
            self.stem_player.cleanup()

        try:
            chat_dock = getattr(self, "chat_dock", None)
            if chat_dock is not None and hasattr(chat_dock, "shutdown"):
                chat_dock.shutdown()
        except Exception as exc:
            logger.warning("closeEvent: ChatDock-Shutdown fehlgeschlagen: %s", exc)

        # 8. Ollama stoppen (Gemma 4 Arbeitsplan)
        try:
            OllamaService.get().stop()
            logger.info("closeEvent: Ollama gestoppt.")
        except Exception as exc:
            logger.warning("closeEvent: Ollama-Stop fehlgeschlagen: %s", exc)

        # 8a. Convert-Controller DB-Pool stoppen. Der globale Executor haelt
        # sonst den nicht-daemon Thread `convert_db_0` nach App-Close am Leben.
        try:
            from ui.controllers.convert import shutdown_convert_db_pool
            if not shutdown_convert_db_pool(timeout=2.0):
                logger.warning("closeEvent: convert DB pool stop timed out")
        except Exception as exc:
            logger.warning("closeEvent: convert DB pool stop fehlgeschlagen: %s", exc)

        # 8b. Brain V3 EmbeddingScheduler graceful drain (Phase-3 App-Sync).
        try:
            scheduler = getattr(self, "_brain_v3_scheduler", None)
            if scheduler is not None and scheduler.is_running():
                scheduler.request_stop(timeout_ms=5000)
                logger.info("closeEvent: EmbeddingScheduler gestoppt")
        except Exception as exc:
            logger.warning("closeEvent: EmbeddingScheduler-Stop fehlgeschlagen: %s", exc)

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
                # Warte bis der asynchrone Download beendet ist
                if not done_event.wait(timeout=600):
                    print(f"\n[ERROR] Timeout beim Download von {m_id}")
                else:
                    if download_started:
                        print(f"\n[OK] {m_id} erfolgreich verarbeitet.")
                    else:
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
        from services.gpu_info import initialize_gpu_info_cache, detect_stuck_driver
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

    # SCHNITT-Redesign 2026-05-09 Phase 03 Task 3.1: WheelGuard verhindert
    # versehentliches Verstellen von Combos/Slidern/SpinBoxen beim
    # Maus-Drueberscrollen, solange das Widget keinen Fokus hat.
    # T4.4 (Tier 4 Hardening): Referenz wird ans QApplication-Objekt
    # gehaengt (statt nur Funktions-Local), damit der Filter garantiert
    # ueber die App-Lifetime gehalten wird und nicht durch Refactor des
    # main()-Scopes versehentlich GC'd werden kann.
    from ui.widgets.wheel_guard import WheelGuard
    app._wheel_guard = WheelGuard(app)
    app.installEventFilter(app._wheel_guard)

    # User-Anweisung 2026-06-03: Opt-in Click-Logger (PB_CLICK_LOG=1).
    # Application-globaler EventFilter (wie WheelGuard, QObject-basiert — B-330)
    # loggt JEDEN MouseButtonPress/-Release mit Widget-Klasse, objectName, Text
    # und Position ins normale Logging (=Session-Log). Die Auswirkungen eines
    # Klicks sind die unmittelbar folgenden Action-/Task-Logzeilen in derselben
    # Datei -> Klick->Wirkung direkt korrelierbar. Default AUS (env-gated),
    # damit normale Laeufe/Tests unbeeinflusst bleiben.
    # Lokaler Import noetig: main() enthaelt weiter unten ein lokales
    # `import os`, das `os` fuer die GESAMTE Funktion lokal macht ->
    # Zugriff hier oben waere sonst UnboundLocalError.
    import os as _os_clicklog
    if _os_clicklog.environ.get("PB_CLICK_LOG") == "1":
        from PySide6.QtCore import QObject as _QObject, QEvent as _QEvent

        class _ClickLogger(_QObject):
            def eventFilter(self, obj, event):
                et = event.type()
                if et in (_QEvent.Type.MouseButtonPress, _QEvent.Type.MouseButtonRelease):
                    try:
                        kind = "PRESS" if et == _QEvent.Type.MouseButtonPress else "RELEASE"
                        try:
                            btn = event.button().name
                        except Exception:
                            btn = "?"
                        cls = type(obj).__name__
                        try:
                            name = obj.objectName() or ""
                        except Exception:
                            name = ""
                        text = ""
                        try:
                            t = getattr(obj, "text", None)
                            if callable(t):
                                text = str(t())[:40]
                        except Exception:
                            text = ""
                        try:
                            p = event.globalPosition().toPoint()
                            pos = f"({p.x()},{p.y()})"
                        except Exception:
                            pos = ""
                        try:
                            en = "1" if obj.isEnabled() else "0"
                        except Exception:
                            en = "?"
                        logging.info(
                            "[CLICK] %s %s %s name='%s' text='%s' en=%s %s",
                            kind, btn, cls, name, text, en, pos,
                        )
                    except Exception:  # Logging darf NIE die App stoeren
                        pass
                return False  # nur beobachten, nie schlucken

        app._click_logger = _ClickLogger(app)
        app.installEventFilter(app._click_logger)
        logging.info("[CLICK] Click-Logger aktiv (PB_CLICK_LOG=1)")

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
                  PBT_APMPOWERSTATUSCHANGE = 0x000A  (B-433: AC<->Akku-Wechsel -> SB2 dGPU-Flap)
                  PBT_POWERSETTINGCHANGE  = 0x8013  (kann Display-Power-State liefern)
                """

                def __init__(self):
                    super().__init__()
                    # B-435: Die SB2-Firmware feuert bei instabiler Stromquelle
                    # rapide wiederholte 0x000A-Events (hunderte/min) -> Log-Flut
                    # + CUDA-Reprobe-Thrash. Debounce: max. 1 Reprobe+Log pro Fenster,
                    # unterdrueckte Events werden aggregiert gezaehlt.
                    self._last_status_change_ts = 0.0
                    self._status_change_suppressed = 0
                    self._STATUS_CHANGE_DEBOUNCE_SEC = 3.0

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
                            elif wparam == 0x000A:  # PBT_APMPOWERSTATUSCHANGE
                                # B-433: Auf dem Surface Book 2 wirft die Firmware
                                # die dGPU (GTX 1060 in der Base) bei einem
                                # Stromquellen-Wechsel ab (AC<->Akku unter Volllast,
                                # Netzteil-Overload). Der CUDA-Context kann dabei
                                # sterben OHNE Sleep/Resume — die bisherigen
                                # PBT_APMRESUME*-Pfade greifen also nicht. Wir
                                # erzwingen beim naechsten GPU-Op einen Health-Check.
                                # B-435: Die Firmware feuert dabei oft eine FLUT von
                                # 0x000A (hunderte/min). Debounce -> nur 1 Reprobe+Log
                                # pro Fenster; der Health-Check beim naechsten Modell-
                                # Load deckt den dGPU-Zustand ohnehin ab.
                                import time as _t
                                _now = _t.monotonic()
                                if _now - self._last_status_change_ts < self._STATUS_CHANGE_DEBOUNCE_SEC:
                                    self._status_change_suppressed += 1
                                else:
                                    _log = logging.getLogger(__name__)
                                    if self._status_change_suppressed:
                                        _log.info(
                                            "B-435: %d weitere 0x000A-Power-Events im "
                                            "Debounce-Fenster (%.0fs) unterdrueckt.",
                                            self._status_change_suppressed,
                                            self._STATUS_CHANGE_DEBOUNCE_SEC,
                                        )
                                        self._status_change_suppressed = 0
                                    self._last_status_change_ts = _now
                                    _log.info(
                                        "B-433: Power-Source-Change (wParam=0x000A) — "
                                        "CUDA-Context wird beim naechsten Modell-Load geprobed."
                                    )
                                    from services.model_manager import ModelManager
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

    # ── Startup ───────────────────────────────────────────────────────
    # FIX H-22: Create DB tables before PBWindow to prevent access errors.
    # Cycle 14: Alembic migrations must also run synchronously before PBWindow.
    from services.startup_checks import run_database_bootstrap
    run_database_bootstrap(splash=splash, process_events=QApplication.processEvents)

    # ── B-498: Automatisches taegliches DB-Backup ─────────────────────
    # Nach erfolgreichem DB-Bootstrap (init_db + Alembic sind durch), VOR
    # PBWindow-Konstruktion und allen Worker-Starts. Laeuft synchron im
    # Main-Thread: die sqlite3-backup()-API liegt fuer eine DB im
    # 100-MB-Bereich im Sekundenbereich, und max. 1x pro 24h (if_stale).
    # Fehler werden geloggt, blockieren den Start aber NICHT —
    # run_startup_backup() faengt intern alle Exceptions.
    splash.show_message("Pruefe Datenbank-Backup...")
    QApplication.processEvents()
    from services.backup_service import run_startup_backup
    from database import session as _db_session
    run_startup_backup(
        db_path=Path(_db_session.APP_ROOT) / "pb_studio.db",
        backup_dir=Path(_db_session.APP_ROOT) / "storage" / "backups",
        reason="daily",
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
                OllamaService.get().start_background()
                if OllamaService.get().ready_cached():
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
                _ai_status = '● AI ready' if OllamaService.get().ready_cached() else '● AI loading...'
                window.status_bar.showMessage(f"System bereit | {status.status_bar_text()} | {_ai_status}")
                window.console_text.append(f"[System] {status.status_bar_text()}")
                logger.info("Startup checks completed: %s", status.status_bar_text())
                # FIX H-4: Show startup check dialog if there are errors or warnings
                from ui.dialogs.startup_check_dialog import maybe_show_startup_dialog
                if not maybe_show_startup_dialog(status, window):
                    # User chose "Beenden" — exit the application
                    # F-10 (B-342): quit the worker thread on the exit path too,
                    # not only on success, so it does not leak.
                    window._startup_check_thread.quit()
                    app.quit()
                    return
                # 3. Timeline laden wenn alles bereit ist
                window.timeline_view.load_from_db()
                window._startup_check_thread.quit()

            window._startup_check_worker.finished.connect(on_done)
            window._startup_check_worker.progress.connect(lambda msg: window.status_bar.showMessage(msg))
            window._startup_check_thread.started.connect(window._startup_check_worker.run)
            # F-10 (B-342): delete worker + thread once the thread loop ends,
            # mirroring the deleteLater discipline used elsewhere (TaskManager,
            # worker_dispatcher). Without this the QThread object lived for the
            # whole app lifetime.
            window._startup_check_thread.finished.connect(
                window._startup_check_worker.deleteLater
            )
            window._startup_check_thread.finished.connect(
                window._startup_check_thread.deleteLater
            )
            window._startup_check_thread.start()
            
        except Exception as e:
            logger.error("Fehler bei finaler Initialisierung: %s", e, exc_info=True)

    # Startet 500ms nach dem das Fenster sichtbar ist
    QTimer.singleShot(500, final_init)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
