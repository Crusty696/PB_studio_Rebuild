"""PanelSetupMixin — extrahiert aus main.py (AUD-44).

Kapselt:
  - setup_task_dock()               — TaskManager-Panel im unteren Splitter
  - setup_console()                 — System-Konsole im unteren Splitter
  - setup_chat_dock()               — KI-Chat Dock (rechts, eingeblendet)
  - _console_append()               — Thread-safe Konsolen-Ausgabe
  - _refresh_media_table_debounced() — Debounced media-table refresh
  - _do_refresh_media_table()       — Verzögerte Aktualisierung
"""

import logging

from PySide6.QtWidgets import QVBoxLayout, QLabel, QTextEdit, QWidget
from PySide6.QtCore import Qt, QTimer

from services.task_manager import GlobalTaskManager
from ui.widgets.task_manager_dock import TaskManagerDock
from ui.chat_dock import ChatDock

logger = logging.getLogger(__name__)


class PanelSetupMixin:
    """Mixin fuer MainWindow: TaskDock, Konsole, ChatDock."""

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
        # TaskManager show_dock Signal verbinden
        GlobalTaskManager.instance().show_dock_requested.connect(
            lambda: self._task_panel_widget.setVisible(True)
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

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.document().setMaximumBlockCount(500)
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

        # MainWindow-Referenz fuer direkte Kommandos (analysiere, schneide, etc.)
        self.chat_dock.set_main_window(self)

        try:
            import services.register_actions  # noqa: F401
            from services.local_agent_service import LocalAgentService
            from ui.dialogs.settings_dialog import get_ollama_settings
            _ollama_cfg = get_ollama_settings()
            self._ai_agent = LocalAgentService(
                ollama_url=_ollama_cfg["url"],
                ollama_model=_ollama_cfg["model"] or None,
                use_ollama=_ollama_cfg["enabled"],
            )
            self.chat_dock.set_agent(self._ai_agent)

            # GPU-Status LAZY anzeigen — torch-Import erst beim ersten KI-Aufruf
            def _show_gpu_info_deferred():
                try:
                    gpu_info = self._ai_agent.model_manager.gpu_info
                    gpu_name = gpu_info.get("name", "unbekannt")
                    vram = gpu_info.get("vram_total_mb", 0)
                    if gpu_name != "CPU" and vram > 0:
                        self.console_text.append(f"[GPU] HARDWARE AKTIV: {gpu_name} ({vram:.0f} MB VRAM)")
                except Exception as exc:
                    logger.warning("_show_gpu_info_deferred: failed to get GPU info: %s", exc)
            QTimer.singleShot(2000, _show_gpu_info_deferred)

            _backend = "Ollama" if _ollama_cfg["enabled"] else "HuggingFace (lokal)"
            self.chat_dock.append_system(
                f"Agent bereit. Backend: {_backend}\n"
                "Befehle: 'analysiere', 'schneide', 'gpu status'"
            )
            self.console_text.append("[KI] Chat-Assistent initialisiert (Modell wird bei erster Anfrage geladen).")
        except Exception as e:
            logger.error("[B-014] register_actions / Agent-Init fehlgeschlagen: %s", e, exc_info=True)
            self.chat_dock.append_error(f"Agent konnte nicht initialisiert werden: {e}")
            self.console_text.append(f"[KI-Fehler] {e}")

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
        """Fuehrt die verzoegerte Aktualisierung der Media-Tabelle aus."""
        self._refresh_pending = False
        self._refresh_media_table()
