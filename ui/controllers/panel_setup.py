"""PanelSetupController — Refactored from PanelSetupMixin."""

import logging
from PySide6.QtWidgets import QVBoxLayout, QTextEdit, QWidget
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from services.task_manager import GlobalTaskManager
from ui.widgets.task_manager_dock import TaskManagerDock
from ui.chat_dock import ChatDock
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)


class _AnalysisCompletionBridge(QObject):
    """B-253: Thread-safe Qt-Bridge fuer Analysis-Completion-Events.

    ``analysis_status_service.mark_completed`` ruft seine Listener im
    Caller-Thread (oft Worker-BG-Thread). UI-Code darf aber nur im
    Main-Thread laufen. Diese Bridge wandelt den Listener-Call in ein
    Qt-Signal mit ``Qt.QueuedConnection`` um — der Slot laeuft garantiert
    im Main-Thread.
    """
    completed = Signal(str, int, str, dict)


_VIDEO_MEDIA_TABLE_REFRESH_STEPS = {
    "metadata_extract",
    "scene_db_storage",
}


def _completion_should_refresh_media_table(media_type: str, step_key: str) -> bool:
    """Return whether a completion event changes media-table visible state."""
    if media_type == "audio":
        return True
    if media_type == "video":
        return step_key in _VIDEO_MEDIA_TABLE_REFRESH_STEPS
    return False


class PanelSetupController(PBComponent):
    """Controller for TaskDock, Console, and ChatDock in PBWindow."""

    def setup_task_dock(self):
        """P9-Step2: TaskManager als TASKS-Tab im Right-Panel.

        TaskManagerDock erbt zwar von QDockWidget, aber wir nutzen nur den
        Inner-Container via .widget() und packen den ins QTabWidget. Das
        QDockWidget-Object selbst wird nicht in's MainWindow added — bleibt
        als Logik-Container fuer Signals (cancel_requested, _add_task, etc.).

        B-252: Das DockWidget-Object selbst wird hide()'d, sonst rendert Qt
        es als minimiertes leeres Fenster im MainWindow-Eck (User-Report:
        "zwei minimierte fenster auf hoehe der video/audio-reiter").
        """
        self.window._task_mgr_dock = TaskManagerDock(self.window)
        self.window._task_mgr_dock.cancel_requested.connect(self.window.worker_dispatcher._cancel_worker_for_task)
        task_w = self.window._task_mgr_dock.widget()
        # Wichtig: re-parent zum Right-Panel, sonst stirbt das Widget mit dem Dock
        task_w.setParent(self.window.right_panel)
        self.window.right_panel.addTab(task_w, "TASKS")
        self.window._task_panel_widget = task_w
        self.window.task_dock = task_w
        # B-252: leeres DockWidget-Geistershell ausblenden
        self.window._task_mgr_dock.hide()
        # show_dock_requested → bringt TASKS-Tab nach vorn
        def _focus_tasks():
            if hasattr(self.window, "_set_context_panel_visible"):
                self.window._set_context_panel_visible(True)
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
        """P9-Step2: ChatDock-Inhalt als CHAT-Tab im Right-Panel.

        B-252: Wie bei setup_task_dock — das ChatDock-QDockWidget-Object
        selbst wird hide()'d, sonst rendert Qt es als zweites leeres
        minimiertes Fenster im MainWindow-Eck.
        """
        self.window.chat_dock = ChatDock(self.window)
        chat_w = self.window.chat_dock.widget()
        chat_w.setParent(self.window.right_panel)
        # CHAT zuerst → erster Tab (Chat = primaerer Sidebar-Use-Case)
        self.window.right_panel.insertTab(0, chat_w, "CHAT")
        self.window.right_panel.setCurrentIndex(0)
        # B-252: leeres DockWidget-Geistershell ausblenden
        self.window.chat_dock.hide()

        # MainWindow-Referenz fuer direkte Kommandos (analysiere, schneide, etc.)
        self.window.chat_dock.set_main_window(self.window)

        try:
            import services.register_actions  # noqa: F401
            from services.local_agent_service import LocalAgentService
            from services.ollama_service import OllamaService
            from ui.dialogs.settings_dialog import get_ollama_settings
            _ollama_cfg = get_ollama_settings()

            self.window._ollama_svc = OllamaService.get()
            _ollama_enabled = bool(_ollama_cfg["enabled"])
            _daemon_alive = False
            if _ollama_enabled:
                try:
                    self.window._ollama_svc.start_background()
                except Exception as _start_exc:
                    logger.warning("OllamaService.start_background failed: %s", _start_exc)
                _daemon_alive = bool(self.window._ollama_svc.ready_cached())
                if not _daemon_alive:
                    # zweite Chance: schneller Socket-Probe (DNS umgehen)
                    try:
                        import socket as _sock
                        _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                        _s.settimeout(1.5)
                        _s.connect(("127.0.0.1", 11434))
                        _s.close()
                        _daemon_alive = True
                    except OSError:
                        _daemon_alive = False
            _ollama_use = _ollama_enabled and _daemon_alive
            if _ollama_use:
                self.window.console_text.append("[LLM] Ollama-Engine aktiv.")
            elif _ollama_enabled:
                self.window.console_text.append("[LLM] Ollama wird im Hintergrund gestartet...")
            else:
                self.window.console_text.append("[LLM] Ollama deaktiviert — Fallback aktiv.")

            self.window._ai_agent = LocalAgentService(
                ollama_url=_ollama_cfg["url"],
                ollama_model=_ollama_cfg["model"] or None,
                # B-434: Boot-Race-Fix. _daemon_alive ist beim Boot oft noch
                # False (app-gestartetes Ollama braucht ~5s bis API-ready).
                # use_ollama=False wuerde den Agent fuer die GANZE Session
                # tot-cachen (kein Re-Probe). Bei aktiviertem Ollama -> None
                # uebergeben => Lazy-Auto-Detect beim ersten Chat-Call (Ollama
                # dann ready). Bei echtem User-Disable -> False (respektiert).
                use_ollama=(None if _ollama_enabled else False),
            )
            self.window.chat_dock.set_agent(self.window._ai_agent)

            # B-209: Bei Project-Switch System-Prompt-Cache invalidieren —
            # sonst zeigt der Agent bis zu 30s lang Medien aus dem ALTEN
            # Projekt im Prompt und gibt damit fachlich falsche Antworten.
            # Hook (invalidate_system_prompt_cache) existiert seit Batch-7
            # (B-082), war aber bisher nirgends verdrahtet.
            try:
                pm = getattr(self.window, "_project_manager", None)
                if pm is not None and hasattr(pm, "project_changed"):
                    agent_ref = self.window._ai_agent
                    pm.project_changed.connect(
                        lambda *_a, **_kw: agent_ref.invalidate_system_prompt_cache("media")
                    )
                else:
                    logger.warning(
                        "B-209: project_manager.project_changed nicht verfuegbar — "
                        "sysprompt-media-cache wird nicht bei Project-Switch invalidiert."
                    )
            except (AttributeError, RuntimeError) as _wire_exc:
                logger.warning(
                    "B-209: project_changed -> invalidate_system_prompt_cache wiring failed: %s",
                    _wire_exc,
                )

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

            # B-321: Kein synchroner Ollama-Health-Check im UI-Bootpfad.
            # Der Status-Dot prueft Verfuegbarkeit im Worker-Thread.
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

    def setup_analysis_completion_bridge(self):
        """B-253: Verdrahtet einen globalen Listener auf
        ``analysis_status_service.mark_completed`` und triggert UI-Refreshs.

        Loest das Refresh-Loch wenn die Pipeline ueber das ActionRegistry
        / agent_command_signal / auto_workflow laeuft (statt ueber den
        UI-Button-Pfad). Konkretes Beispiel: nach stem_separation hat
        die DB die stem_*_path-Felder gesetzt + die WAV-Files liegen auf
        Disk, aber der Stem-Workspace + die Audio-Pool-Tabelle wussten
        nichts davon weil ``StemsController._on_stem_finished`` nur am
        UI-Button-Pfad haengt.
        """
        from services import analysis_status_service

        self.window._completion_bridge = _AnalysisCompletionBridge(self.window)

        def _on_completed_main_thread(media_type: str, media_id: int, step_key: str, summary: dict):
            """Slot im Main-Thread (Qt.QueuedConnection garantiert das).

            Triggert je Step-Type den passenden UI-Refresh.
            """
            try:
                # B-321: Video-Pipeline hat viele Zwischenschritte. Nicht
                # jeder Step aendert die sichtbaren Tabellenfelder; sonst
                # stapeln sich Medien-DB-Reloads waehrend GPU/DB Last.
                should_refresh_media_table = _completion_should_refresh_media_table(media_type, step_key)
                logger.info(
                    "B-253 completion-bridge: %s/%d/%s -> %s",
                    media_type,
                    media_id,
                    step_key,
                    "UI-Refresh" if should_refresh_media_table else "no table refresh",
                )

                if should_refresh_media_table:
                    try:
                        self.window.media_table_controller._refresh_media_table_debounced()
                    except Exception as e:
                        logger.warning("B-253: media_table-Refresh fehlgeschlagen: %s", e)

                # Stem-Workspace nur bei stem_separation
                if media_type == "audio" and step_key == "stem_separation":
                    try:
                        self.window.stems._update_stem_workspace(media_id)
                    except Exception as e:
                        logger.warning("B-253: stem_workspace-Refresh fehlgeschlagen: %s", e)
            except Exception as e:
                logger.warning("B-253: completion-bridge slot fehlgeschlagen: %s", e)

        self.window._completion_bridge.completed.connect(
            _on_completed_main_thread, Qt.ConnectionType.QueuedConnection
        )

        def _bg_listener(media_type: str, media_id: int, step_key: str, summary: dict):
            """Listener-Funktion die im BG-Thread laeuft. Emit ist thread-safe,
            Qt.QueuedConnection serialisiert den Slot-Call auf den Main-Thread."""
            try:
                self.window._completion_bridge.completed.emit(
                    media_type, media_id, step_key, summary or {}
                )
            except Exception as e:
                logger.warning("B-253: bg-listener emit fehlgeschlagen: %s", e)

        analysis_status_service.register_completion_listener(_bg_listener)
        # F-11 (B-343): unregister on window teardown. Without this, a late
        # mark_completed from a still-running BG worker would fire the listener
        # into destroyed widgets. Keep a ref so it can be removed.
        self.window._completion_bridge_listener = _bg_listener

        def _unregister_bridge_listener(*_args):
            try:
                analysis_status_service.unregister_completion_listener(_bg_listener)
            except Exception as e:
                logger.warning("F-11: bridge-listener unregister fehlgeschlagen: %s", e)

        self.window.destroyed.connect(_unregister_bridge_listener)
        logger.info("B-253: Analysis-Completion-Bridge installiert.")

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
