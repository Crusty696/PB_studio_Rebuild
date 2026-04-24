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
        """P9-Step2: TaskManager als TASKS-Tab im Right-Panel.

        TaskManagerDock erbt zwar von QDockWidget, aber wir nutzen nur den
        Inner-Container via .widget() und packen den ins QTabWidget. Das
        QDockWidget-Object selbst wird nicht in's MainWindow added — bleibt
        als Logik-Container fuer Signals (cancel_requested, _add_task, etc.).
        """
        self.window._task_mgr_dock = TaskManagerDock(self.window)
        self.window._task_mgr_dock.cancel_requested.connect(self.window.worker_dispatcher._cancel_worker_for_task)
        task_w = self.window._task_mgr_dock.widget()
        # Wichtig: re-parent zum Right-Panel, sonst stirbt das Widget mit dem Dock
        task_w.setParent(self.window.right_panel)
        self.window.right_panel.addTab(task_w, "TASKS")
        self.window._task_panel_widget = task_w
        self.window.task_dock = task_w
        # show_dock_requested → bringt TASKS-Tab nach vorn
        def _focus_tasks():
            for i in range(self.window.right_panel.count()):
                if self.window.right_panel.tabText(i) == "TASKS":
                    self.window.right_panel.setCurrentIndex(i)
                    return
        GlobalTaskManager.instance().show_dock_requested.connect(_focus_tasks)

    def setup_console(self):
        """P9-Step2: System-Konsole als LOG-Tab im Right-Panel."""
        console_panel = QWidget()
        console_panel.setObjectName("console_dock")
        cl = QVBoxLayout(console_panel)
        cl.setContentsMargins(4, 2, 4, 4)
        cl.setSpacing(0)

        self.window.console_text = QTextEdit()
        self.window.console_text.setReadOnly(True)
        self.window.console_text.document().setMaximumBlockCount(500)
        self.window.console_text.setToolTip(
            "System-Konsole: Zeigt alle Aktionen, Warnungen und Fehler der Anwendung in Echtzeit an"
        )
        self.window.console_text.append("[System] PB_studio Core Engine erfolgreich gestartet.")
        cl.addWidget(self.window.console_text)

        self.window.right_panel.addTab(console_panel, "LOG")
        self.window._console_panel_widget = console_panel
        self.window.console_dock = console_panel

        # F-022/F-034 Fix: Throttled Console Buffer with Thread-Safety
        import threading
        self._console_lock = threading.Lock()
        self._console_buffer = []
        self._console_timer = QTimer(self.window)
        self._console_timer.setInterval(250)
        self._console_timer.timeout.connect(self._flush_console_buffer)
        self._console_timer.start()

    def setup_chat_dock(self):
        """P9-Step2: ChatDock-Inhalt als CHAT-Tab im Right-Panel."""
        self.window.chat_dock = ChatDock(self.window)
        chat_w = self.window.chat_dock.widget()
        chat_w.setParent(self.window.right_panel)
        # CHAT zuerst → erster Tab (Chat = primaerer Sidebar-Use-Case)
        self.window.right_panel.insertTab(0, chat_w, "CHAT")
        self.window.right_panel.setCurrentIndex(0)

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

            # GPU-Status LAZY anzeigen via ModelManager direkt (nicht ueber Agent)
            def _show_gpu_info_deferred():
                try:
                    from services.model_manager import ModelManager
                    mm = ModelManager()
                    gpu_info = mm.gpu_info
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
        """Schreibt gepufferte Nachrichten gesammelt ins UI-Widget.

        Bug-C-Fix: Nur EIN UI-Update-Tick pro Flush, unabhaengig davon wie
        viele Zeilen gepuffert sind. Cursor-bewegen statt append() pro Zeile,
        damit jede Zeile auch ein eigener Block (eigene maxBlockCount-Zeile)
        wird ohne N synchrone Layout-Recompute-Zyklen auszuloesen.
        """
        with self._console_lock:
            if not self._console_buffer:
                return
            lines = self._console_buffer
            self._console_buffer = []

        widget = self.window.console_text
        # Einziger Append: insertPlainText am Ende, mit fuehrendem Newline
        # falls schon Inhalt existiert. Das laeuft als ein einziger
        # Layout-/Resize-Pass, nicht als N.
        from PySide6.QtGui import QTextCursor
        cursor = widget.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Wenn das Dokument nicht leer ist, beginnt der Block mit einem
        # Newline, damit jede Zeile ein eigener "Block" wird (wichtig fuer
        # maximumBlockCount-Trimming).
        if not widget.document().isEmpty():
            cursor.insertText("\n")
        cursor.insertText("\n".join(lines))
        # Auto-scroll ans Ende, wie es .append() auch macht
        widget.setTextCursor(cursor)
        widget.ensureCursorVisible()
