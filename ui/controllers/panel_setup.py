"""PanelSetupController — Refactored from PanelSetupMixin."""

import logging
from PySide6.QtWidgets import QVBoxLayout, QLabel, QTextEdit, QWidget
from PySide6.QtCore import Qt, QTimer
from services.task_manager import GlobalTaskManager
from ui.widgets.task_manager_dock import TaskManagerDock
from ui.chat_dock import ChatDock
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

class PanelSetupController(PBComponent):
    """Controller for TaskDock, Console, and ChatDock in PBWindow."""

    def setup_task_dock(self):
        """TaskManager als QWidget im unteren QSplitter-Panel."""
        self.window._task_mgr_dock = TaskManagerDock(self.window)
        self.window._task_mgr_dock.cancel_requested.connect(self.window.worker_dispatcher._cancel_worker_for_task)
        task_w = self.window._task_mgr_dock.widget()
        task_w.setMinimumWidth(180)
        self.window._inner_splitter.addWidget(task_w)
        self.window._task_panel_widget = task_w
        # Alias fuer Kompatibilitaet
        self.window.task_dock = task_w
        # TaskManager show_dock Signal verbinden
        GlobalTaskManager.instance().show_dock_requested.connect(
            lambda: self.window._task_panel_widget.setVisible(True)
        )

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

        self.window.console_text = QTextEdit()
        self.window.console_text.setReadOnly(True)
        self.window.console_text.document().setMaximumBlockCount(500)
        self.window.console_text.setToolTip(
            "System-Konsole: Zeigt alle Aktionen, Warnungen und Fehler der Anwendung in Echtzeit an"
        )
        self.window.console_text.append("[System] PB_studio Core Engine erfolgreich gestartet.")
        cl.addWidget(self.window.console_text)

        self.window._inner_splitter.addWidget(console_panel)
        self.window._console_panel_widget = console_panel
        # Alias fuer Kompatibilitaet
        self.window.console_dock = console_panel

        # F-022/F-034 Fix: Throttled Console Buffer with Thread-Safety
        import threading
        self._console_lock = threading.Lock()
        self._console_buffer = []
        self._console_timer = QTimer(self.window)
        self._console_timer.setInterval(250)  # 4 Updates pro Sekunde
        self._console_timer.timeout.connect(self._flush_console_buffer)
        self._console_timer.start()

    def setup_chat_dock(self):
        self.window.chat_dock = ChatDock(self.window)
        self.window.chat_dock.setMinimumWidth(200)
        self.window.chat_dock.setMaximumWidth(400)
        self.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.window.chat_dock)
        # Start collapsed — user can open via View menu or toggleViewAction
        self.window.chat_dock.setVisible(False)

        # MainWindow-Referenz fuer direkte Kommandos (analysiere, schneide, etc.)
        self.window.chat_dock.set_main_window(self.window)

        try:
            import services.register_actions  # noqa: F401
            from services.local_agent_service import LocalAgentService
            from services.ollama_service import OllamaService
            from ui.dialogs.settings_dialog import get_ollama_settings
            _ollama_cfg = get_ollama_settings()

            # Auto-Start: Ollama-Prozess im Hintergrund starten (wenn aktiviert)
            self.window._ollama_svc = OllamaService.get()
            if _ollama_cfg["enabled"]:
                self.window._ollama_svc.start()
                if self.window._ollama_svc.is_ready:
                    self.window.console_text.append("[LLM] Ollama-Engine aktiv.")
                else:
                    self.window.console_text.append("[LLM] Ollama wird im Hintergrund gestartet...")

            self.window._ai_agent = LocalAgentService(
                ollama_url=_ollama_cfg["url"],
                ollama_model=_ollama_cfg["model"] or None,
                use_ollama=_ollama_cfg["enabled"],
            )
            self.window.chat_dock.set_agent(self.window._ai_agent)

            # GPU-Status LAZY anzeigen — torch-Import erst beim ersten KI-Aufruf
            def _show_gpu_info_deferred():
                try:
                    gpu_info = self.window._ai_agent.model_manager.gpu_info
                    gpu_name = gpu_info.get("name", "unbekannt")
                    vram = gpu_info.get("vram_total_mb", 0)
                    if gpu_name != "CPU" and vram > 0:
                        self.window.console_text.append(f"[GPU] HARDWARE AKTIV: {gpu_name} ({vram:.0f} MB VRAM)")
                except (ImportError, AttributeError, OSError) as exc:
                    logger.warning("_show_gpu_info_deferred: failed to get GPU info: %s", exc)
            QTimer.singleShot(2000, _show_gpu_info_deferred)

            _backend = "Ollama" if _ollama_cfg["enabled"] else "HuggingFace (lokal)"
            self.window.chat_dock.append_system(
                f"Agent bereit. Backend: {_backend}\n"
                "Befehle: 'analysiere', 'schneide', 'gpu status'"
            )
            self.window.console_text.append("[KI] Chat-Assistent initialisiert (Modell wird bei erster Anfrage geladen).")
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.error("[B-014] register_actions / Agent-Init fehlgeschlagen: %s", e, exc_info=True)
            self.window.chat_dock.append_error(f"Agent konnte nicht initialisiert werden: {e}")
            self.window.console_text.append(f"[KI-Fehler] {e}")

    def _console_append(self, text: str) -> None:
        """Puffert Konsolen-Nachrichten thread-sicher (Fix F-034)."""
        with self._console_lock:
            self._console_buffer.append(text)

    def _flush_console_buffer(self):
        """Schreibt gepufferte Nachrichten gesammelt ins UI-Widget."""
        with self._console_lock:
            if not self._console_buffer:
                return
            full_text = "\n".join(self._console_buffer)
            self._console_buffer.clear()
        
        self.window.console_text.append(full_text)
