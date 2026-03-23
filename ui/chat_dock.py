"""
KI-Assistent Chat-Widget (QDockWidget).

Bietet eine Chat-Oberfläche zum lokalen KI-Agenten.
Der Agent läuft in einem QThread, damit die UI nicht blockiert.
Unterstützt Multi-Action-Anzeige.

Direktes Kommando-Routing: Bekannte Befehle (analysiere, schneide, auto-edit)
werden OHNE LLM direkt an MainWindow-Methoden weitergeleitet.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor

# Globaler GC-Schutz: Threads und Worker hier halten, damit der
# Garbage Collector sie NIEMALS löscht, solange sie laufen.
_GLOBAL_ACTIVE_THREADS: list[tuple] = []

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMainWindow

logger = logging.getLogger(__name__)


class _TrackedRegistry:
    """Thread-sicherer Wrapper um eine ActionRegistry.

    Zählt execute()-Aufrufe und bricht bei Überschreitung ab,
    OHNE die originale Registry per Monkey-Patch zu verändern.
    """

    def __init__(self, original_registry, max_calls: int, status_signal):
        self._registry = original_registry
        self._count = 0
        self._max = max_calls
        self._status = status_signal

    def execute(self, name, params=None):
        self._count += 1
        self._status.emit(f"Führt [{name}] aus...")
        if self._count > self._max:
            self._status.emit("Loop erkannt - Abgebrochen")
            raise _LoopBreakError(
                f"Agent-Loop erkannt: {self._count} Tool-Calls "
                f"ohne User-Antwort (Max: {self._max})"
            )
        return self._registry.execute(name, params)

    # Delegiere alle anderen Attribute an die originale Registry
    def __getattr__(self, name):
        return getattr(self._registry, name)


class AIAgentWorker(QObject):
    """Führt agent.process(text) in einem separaten Thread aus.

    Meldet Agent-Status live und bricht bei Loop-Erkennung ab.
    """
    finished = Signal(dict)        # Ergebnis von process()
    error = Signal(str)            # Fehlermeldung
    status_changed = Signal(str)   # Live-Status des Agenten

    # Loop-Schutz: max aufeinanderfolgende Tool-Calls ohne User-Antwort
    MAX_CONSECUTIVE_CALLS = 3

    def __init__(self, agent, user_text: str):
        super().__init__()
        self.agent = agent
        self.user_text = user_text

    def run(self):
        _ok = False
        try:
            self.status_changed.emit("Denkt nach...")

            # Thread-sichere Tracking-Registry statt Monkey-Patching
            original_registry = getattr(self.agent, 'registry', None)
            if original_registry is not None:
                tracked = _TrackedRegistry(
                    original_registry,
                    self.MAX_CONSECUTIVE_CALLS,
                    self.status_changed,
                )
                self.agent.registry = tracked

            try:
                result = self.agent.process(self.user_text)
                self.status_changed.emit("Bereit")
                self.finished.emit(result)
                _ok = True
            except _LoopBreakError as le:
                logger.warning("Agent-Loop abgebrochen: %s", le)
                self.finished.emit({
                    "action": "none",
                    "error": str(le),
                    "message": None,
                    "result": None,
                })
                _ok = True
            finally:
                # Original-Registry wiederherstellen
                if original_registry is not None:
                    self.agent.registry = original_registry

        except Exception as e:
            logger.error("AIAgentWorker crashed: %s", e, exc_info=True)
            self.status_changed.emit("Fehler")
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit({})


class _LoopBreakError(Exception):
    """Wird geworfen wenn der Agent zu viele Tool-Calls ohne Antwort macht."""
    pass


class ChatDock(QDockWidget):
    """Dock-Widget mit Chat-Verlauf, Eingabefeld und Senden-Button.

    Unterstützt Multi-Action-Ergebnisse: Wenn die KI mehrere Aktionen
    gleichzeitig ausführt, werden alle Ergebnisse einzeln angezeigt.
    """

    def __init__(self, parent=None):
        super().__init__("KI Assistent", parent)
        self.setObjectName("chat_dock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setMinimumWidth(240)

        self._agent = None
        self._main_window: QMainWindow | None = None
        self._thread: QThread | None = None
        self._worker: AIAgentWorker | None = None

        # --- UI aufbauen ---
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Chat-Verlauf
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setFont(QFont("Cascadia Code", 10))
        self.chat_log.setToolTip("Chat-Verlauf: Hier siehst du alle Nachrichten zwischen dir und dem KI-Assistenten sowie ausgefuehrte Aktionen")
        layout.addWidget(self.chat_log)

        # Agent-Status-Label (über dem Eingabefeld)
        self.status_label = QLabel("Agent Status: Bereit")
        self.status_label.setFont(QFont("Cascadia Code", 9))
        self.status_label.setStyleSheet(
            "QLabel {"
            "  color: #00E676;"
            "  background-color: #1A1A2E;"
            "  border: 1px solid #333;"
            "  border-radius: 4px;"
            "  padding: 4px 8px;"
            "}"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.status_label)

        # Eingabezeile + Button
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Nachricht an KI-Assistent...")
        self.input_field.setFont(QFont("Segoe UI", 10))
        self.input_field.setMinimumHeight(34)
        self.input_field.setToolTip("Gib hier deine Nachricht oder deinen Befehl an den KI-Assistenten ein. Druecke Enter oder klicke Senden")
        self.input_field.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_field)

        self.btn_send = QPushButton("Senden")
        self.btn_send.setMinimumHeight(34)
        self.btn_send.setMinimumWidth(80)
        self.btn_send.setToolTip("Sendet deine Nachricht an den lokalen KI-Assistenten. Der Agent verarbeitet die Anfrage im Hintergrund")
        self.btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self.btn_send)

        layout.addLayout(input_row)
        self.setWidget(container)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_agent(self, agent) -> None:
        """Setzt die LocalAgentService-Instanz."""
        self._agent = agent

    def set_main_window(self, main_window) -> None:
        """Verbindet den Chat mit dem Hauptfenster für direkte Aktionen."""
        self._main_window = main_window

    def append_system(self, text: str) -> None:
        """Zeigt eine System-Nachricht im Chat an."""
        self._append_colored(text, "#707070")

    def append_user(self, text: str) -> None:
        """Zeigt eine Benutzer-Nachricht im Chat an."""
        self._append_colored(f"▸ Du: {text}", "#00F0FF")

    def append_ai(self, text: str) -> None:
        """Zeigt eine KI-Antwort im Chat an."""
        self._append_colored(f"◂ KI: {text}", "#00E676")

    def append_action(self, action_name: str, result: str | None = None) -> None:
        """Zeigt eine ausgeführte Aktion im Chat an."""
        self._append_colored(f"  ⚡ {action_name}", "#00F0FF")
        if result is not None:
            self._append_colored(f"    → {result}", "#B0B0B0")

    def append_error(self, text: str) -> None:
        """Zeigt eine Fehlermeldung im Chat an."""
        self._append_colored(f"✖ {text}", "#FF5252")

    def append_divider(self) -> None:
        """Fügt eine visuelle Trennlinie ein."""
        self._append_colored("─" * 40, "#333333")

    # ------------------------------------------------------------------
    # Interne Logik
    # ------------------------------------------------------------------

    def _append_colored(self, text: str, hex_color: str) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(hex_color))
        cursor = self.chat_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)
        self.chat_log.setTextCursor(cursor)
        self.chat_log.ensureCursorVisible()

    def _on_send(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return

        self.append_user(text)
        self.input_field.clear()

        # Quick-Command-Detection: Bekannte Befehle direkt ausführen (ohne LLM)
        if self._try_quick_command(text):
            return

        if self._agent is None:
            self.append_error("Kein Agent konfiguriert.")
            return

        # UI sperren + Status-Marker setzen (wird nach Antwort entfernt)
        self.input_field.setEnabled(False)
        self.btn_send.setEnabled(False)
        self._status_cursor_pos = self.chat_log.textCursor().position()
        self._append_colored("Agent arbeitet...", "#555555")

        # Worker ueber zentrale Task-Engine starten
        worker = AIAgentWorker(self._agent, text)
        worker.finished.connect(self._on_agent_finished)
        worker.error.connect(self._on_agent_error)
        worker.status_changed.connect(self._on_agent_status)

        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None or not hasattr(app, 'task_manager'):
                raise AttributeError("TaskManager nicht verfügbar")
            tm = app.task_manager
            result = tm.start_task(
                name="KI-Agent",
                worker=worker,
                description=text[:50],
            )
            # start_task gibt TaskInfo (Main-Thread) oder task_id str (BG-Thread) zurueck
            self._thread = result.thread if hasattr(result, 'thread') else None
            self._worker = worker
        except (ImportError, AttributeError):
            # Fallback: direkter Thread-Start
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(self._cleanup_thread)
            self._thread = thread
            self._worker = worker
            _GLOBAL_ACTIVE_THREADS.append((thread, worker))
            thread.start()

    def _cleanup_thread(self) -> None:
        """Nullt Thread/Worker-Referenzen nach Fertigstellung."""
        # Globalen GC-Schutz aufheben
        if self._thread is not None and self._worker is not None:
            pair = (self._thread, self._worker)
            if pair in _GLOBAL_ACTIVE_THREADS:
                _GLOBAL_ACTIVE_THREADS.remove(pair)
        self._thread = None
        self._worker = None

    def _remove_status_line(self) -> None:
        """Entfernt die 'Agent arbeitet...' Zeile aus dem Chat-Log."""
        pos = getattr(self, '_status_cursor_pos', None)
        if pos is None:
            return
        cursor = self.chat_log.textCursor()
        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        text = cursor.selectedText()
        # Nur entfernen wenn es die Status-Zeile ist
        if "Agent arbeitet..." in text:
            cursor.removeSelectedText()
            # Trailing newline entfernen
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            if not cursor.selectedText().strip():
                cursor.removeSelectedText()
                cursor.deletePreviousChar()  # Newline davor
        self._status_cursor_pos = None

    # ------------------------------------------------------------------
    # Quick-Commands: Direkte MainWindow-Anbindung ohne LLM
    # ------------------------------------------------------------------

    def _try_quick_command(self, text: str) -> bool:
        """Prüft ob der Text ein bekanntes Quick-Command ist.

        Gibt True zurück wenn ein Kommando erkannt und ausgeführt wurde.
        """
        if self._main_window is None:
            return False

        text_lower = text.lower().strip()

        # --- ANALYSIERE: Alle Videos markieren + Pipeline starten ---
        if self._match_analyze_command(text_lower):
            self._exec_analyze_all()
            return True

        # --- SCHNEIDE / AUTO-EDIT: Auto-Edit-Prozess starten ---
        if self._match_auto_edit_command(text_lower):
            self._exec_auto_edit()
            return True

        # --- GPU-STATUS: Hardware-Info anzeigen ---
        if self._match_gpu_status_command(text_lower):
            self._exec_gpu_status()
            return True

        return False

    @staticmethod
    def _match_analyze_command(text: str) -> bool:
        patterns = [
            "analysiere", "analyse starten", "analyze",
            "videos analysieren", "alle analysieren",
            "pipeline starten", "starte analyse",
            "starte die analyse",
        ]
        return any(p in text for p in patterns)

    @staticmethod
    def _match_auto_edit_command(text: str) -> bool:
        patterns = [
            "schneide", "auto-edit", "autoedit", "auto edit",
            "schnitt starten", "automatisch schneiden",
            "beat edit", "pacing",
        ]
        return any(p in text for p in patterns)

    @staticmethod
    def _match_gpu_status_command(text: str) -> bool:
        patterns = ["gpu status", "gpu info", "hardware", "vram", "cuda"]
        return any(p in text for p in patterns)

    def _exec_analyze_all(self) -> None:
        """Markiert alle Videos im Pool und startet die Pipeline."""
        mw = self._main_window
        try:
            table = mw.video_pool_table
            row_count = table.rowCount()

            if row_count == 0:
                self.append_ai("Keine Videos im Pool vorhanden. Importiere zuerst Videos.")
                return

            # Alle Zeilen im Video Pool selektieren
            table.selectAll()

            self.append_ai(
                f"Ich habe alle {row_count} Videos markiert und starte "
                f"die Analyse auf der GPU!"
            )

            # Pipeline starten (auf dem Main-Thread via QTimer)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, mw._start_video_pipeline)

            self.append_divider()

        except Exception as e:
            logger.exception("Fehler bei _exec_analyze_all")
            self.append_error(f"Analyse konnte nicht gestartet werden: {e}")

    def _exec_auto_edit(self) -> None:
        """Startet den Auto-Edit-Prozess."""
        mw = self._main_window
        try:
            # Prüfe ob Audio-Track vorhanden
            if not hasattr(mw, 'audio_combo') or mw.audio_combo.currentData() is None:
                self.append_ai(
                    "Kein Audio-Track ausgewaehlt. Waehle zuerst einen "
                    "Audio-Track im Director-Workspace aus."
                )
                return

            self.append_ai(
                "Auto-Edit wird gestartet! Schneide Videos zum Beat "
                "mit den aktuellen DJ-Pacing-Einstellungen."
            )

            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, mw._auto_edit_to_beat)

            self.append_divider()

        except Exception as e:
            logger.exception("Fehler bei _exec_auto_edit")
            self.append_error(f"Auto-Edit konnte nicht gestartet werden: {e}")

    def _exec_gpu_status(self) -> None:
        """Zeigt GPU-Hardware-Status im Chat an."""
        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                used = torch.cuda.memory_allocated() / 1024 / 1024
                total = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
                self.append_ai(
                    f"HARDWARE AKTIV: {name}\n"
                    f"  VRAM: {used:.0f} MB / {total:.0f} MB belegt\n"
                    f"  CUDA: {torch.version.cuda or 'N/A'}\n"
                    f"  GPU-Zwang: AKTIV"
                )
            else:
                self.append_ai("Keine CUDA-GPU erkannt. Alle Modelle laufen auf CPU.")
        except Exception as e:
            self.append_error(f"GPU-Status nicht abrufbar: {e}")

    def _on_agent_status(self, status: str) -> None:
        """Aktualisiert das Agent-Status-Label live."""
        self.status_label.setText(f"Agent Status: {status}")

        # Farbe je nach Status
        if "Loop erkannt" in status or "Fehler" in status or "Abgebrochen" in status:
            color = "#FF5252"  # Rot
        elif "Bereit" in status or "Wartet" in status:
            color = "#00E676"  # Grün
        elif "Führt" in status:
            color = "#00B0FF"  # Blau — Tool wird ausgeführt
        else:
            color = "#FFC107"  # Gelb — Denkt nach

        self.status_label.setStyleSheet(
            f"QLabel {{"
            f"  color: {color};"
            f"  background-color: #1A1A2E;"
            f"  border: 1px solid #333;"
            f"  border-radius: 4px;"
            f"  padding: 4px 8px;"
            f"}}"
        )

    def _on_agent_finished(self, result: dict) -> None:
        self._remove_status_line()
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.input_field.setFocus()

        action = result.get("action", "none")
        message = result.get("message")
        error = result.get("error")
        action_result = result.get("result")
        actions = result.get("actions")

        if error and action != "multi":
            self.append_error(error)
            return

        if action == "multi" and actions:
            # Multi-Action Ergebnisse anzeigen
            self.append_ai(f"Multi-Aktion ({len(actions)} Befehle):")
            for i, act in enumerate(actions, 1):
                act_name = act.get("action", "none")
                act_result = act.get("result")
                act_error = act.get("error")
                act_message = act.get("message")

                if act_error:
                    self.append_error(f"  [{i}] {act_name}: {act_error}")
                elif act_name != "none":
                    result_str = str(act_result) if act_result is not None else None
                    self.append_action(f"[{i}] {act_name}", result_str)
                elif act_message:
                    self._append_colored(f"  [{i}] {act_message}", "#B0B0B0")

            # Gesamtfehler anzeigen
            if error:
                self.append_error(error)

        elif action != "none":
            # Single Action
            self.append_action(action, str(action_result) if action_result is not None else None)

        elif message:
            self.append_ai(message)
        else:
            self.append_ai("(Keine Antwort)")

        self.append_divider()

    def _on_agent_error(self, error_msg: str) -> None:
        self._remove_status_line()
        self._on_agent_status("Fehler")
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.input_field.setFocus()
        self.append_error(error_msg)
