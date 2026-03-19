"""
KI-Assistent Chat-Widget (QDockWidget).

Bietet eine Chat-Oberfläche zum lokalen KI-Agenten.
Der Agent läuft in einem QThread, damit die UI nicht blockiert.
"""

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor


class AIAgentWorker(QObject):
    """Führt agent.process(text) in einem separaten Thread aus."""
    finished = Signal(dict)   # Ergebnis von process()
    error = Signal(str)       # Fehlermeldung

    def __init__(self, agent, user_text: str):
        super().__init__()
        self.agent = agent
        self.user_text = user_text

    def run(self):
        try:
            result = self.agent.process(self.user_text)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ChatDock(QDockWidget):
    """Dock-Widget mit Chat-Verlauf, Eingabefeld und Senden-Button."""

    def __init__(self, parent=None):
        super().__init__("KI Assistent", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setMinimumWidth(320)

        self._agent = None
        self._thread: QThread | None = None
        self._worker: AIAgentWorker | None = None

        # --- UI aufbauen ---
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Chat-Verlauf
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setFont(QFont("Segoe UI", 10))
        self.chat_log.setStyleSheet(
            "QTextEdit { background-color: #1b1d23; color: #ccc; "
            "border: 1px solid #333; padding: 6px; }"
        )
        layout.addWidget(self.chat_log)

        # Eingabezeile + Button
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Nachricht an KI-Assistent...")
        self.input_field.setFont(QFont("Segoe UI", 10))
        self.input_field.setMinimumHeight(32)
        self.input_field.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_field)

        self.btn_send = QPushButton("Senden")
        self.btn_send.setMinimumHeight(32)
        self.btn_send.setMinimumWidth(70)
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

    def append_system(self, text: str) -> None:
        """Zeigt eine System-Nachricht im Chat an."""
        self._append_colored(text, "#808899")

    def append_user(self, text: str) -> None:
        """Zeigt eine Benutzer-Nachricht im Chat an."""
        self._append_colored(f"Du: {text}", "#00d4ff")

    def append_ai(self, text: str) -> None:
        """Zeigt eine KI-Antwort im Chat an."""
        self._append_colored(f"KI: {text}", "#a0e060")

    def append_error(self, text: str) -> None:
        """Zeigt eine Fehlermeldung im Chat an."""
        self._append_colored(f"[Fehler] {text}", "#ff6666")

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

        if self._agent is None:
            self.append_error("Kein Agent konfiguriert.")
            return

        self.append_user(text)
        self.input_field.clear()

        # UI sperren
        self.input_field.setEnabled(False)
        self.btn_send.setEnabled(False)
        self._append_colored("KI denkt nach...", "#808899")

        # Worker starten
        worker = AIAgentWorker(self._agent, text)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_agent_finished)
        worker.error.connect(self._on_agent_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_agent_finished(self, result: dict) -> None:
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.input_field.setFocus()

        action = result.get("action", "none")
        message = result.get("message")
        error = result.get("error")
        action_result = result.get("result")

        if error:
            self.append_error(error)
            return

        if action != "none":
            self.append_ai(f"Aktion: {action}")
            if action_result is not None:
                self.append_ai(f"Ergebnis: {action_result}")
        elif message:
            self.append_ai(message)
        else:
            self.append_ai("(Keine Antwort)")

    def _on_agent_error(self, error_msg: str) -> None:
        self.input_field.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.input_field.setFocus()
        self.append_error(error_msg)
