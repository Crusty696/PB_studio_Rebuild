"""PB Studio — Project Dialogs (New / Open).

Uses the Gold-Accent theme tokens from ui.theme.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QMessageBox,
)

from ui.theme import ACCENT, ACCENT_DIM, BG1, BG2, BG3, T1, T2, T3


# ======================================================================
# New Project Dialog
# ======================================================================

class NewProjectDialog(QDialog):
    """Dialog for creating a new PB Studio project.

    Fields: name, path (with browse), resolution combo, fps spin.
    """

    _DIALOG_STYLE = f"""
        QDialog {{
            background-color: {BG1};
        }}
        QLabel {{
            color: {T2};
            font-size: 12px;
            background: transparent;
        }}
        QLineEdit {{
            background-color: {BG2};
            color: {T1};
            border: 1px solid rgba(255,255,255,15);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QLineEdit:focus {{
            border-color: {ACCENT};
        }}
        QComboBox {{
            background-color: {BG2};
            color: {T1};
            border: 1px solid rgba(255,255,255,15);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QDoubleSpinBox {{
            background-color: {BG2};
            color: {T1};
            border: 1px solid rgba(255,255,255,15);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QPushButton {{
            background-color: {BG3};
            color: {T2};
            border: 1px solid rgba(255,255,255,15);
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton:hover {{
            color: {T1};
            border-color: rgba(255,255,255,25);
        }}
        QPushButton#btn_ok {{
            background-color: {ACCENT_DIM};
            color: {BG1};
            border: none;
        }}
        QPushButton#btn_ok:hover {{
            background-color: {ACCENT};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neues Projekt erstellen")
        self.setMinimumWidth(480)
        self.setStyleSheet(self._DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Neues Projekt")
        title.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: 700; background: transparent;")
        layout.addWidget(title)

        # -- Name --
        layout.addWidget(QLabel("Projektname:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Mein Projekt")
        layout.addWidget(self.name_input)

        # -- Path --
        layout.addWidget(QLabel("Speicherort:"))
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Ordner waehlen...")
        path_row.addWidget(self.path_input, stretch=1)
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(36)
        btn_browse.clicked.connect(self._browse_path)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        # -- Resolution --
        layout.addWidget(QLabel("Aufloesung:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "1920x1080", "3840x2160", "1280x720", "2560x1440",
            "1080x1920", "1080x1080",
        ])
        layout.addWidget(self.resolution_combo)

        # -- FPS --
        layout.addWidget(QLabel("FPS:"))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 120.0)
        self.fps_spin.setValue(30.0)
        self.fps_spin.setDecimals(2)
        self.fps_spin.setSingleStep(0.01)
        layout.addWidget(self.fps_spin)

        # -- Buttons --
        layout.addSpacing(10)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_ok = QPushButton("Erstellen")
        btn_ok.setObjectName("btn_ok")
        btn_ok.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _browse_path(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Projektordner waehlen",
        )
        if folder:
            self.path_input.setText(folder)

    def _validate_and_accept(self):
        name = self.name_input.text().strip()
        path = self.path_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Bitte einen Projektnamen eingeben.")
            return
        if not path:
            QMessageBox.warning(self, "Fehler", "Bitte einen Speicherort waehlen.")
            return
        self.accept()

    def get_values(self) -> dict:
        """Return dialog values as a dict.

        Keys: ``name``, ``path`` (Path), ``resolution`` (str), ``fps`` (float).
        The actual project folder is ``path / name``.
        """
        base = Path(self.path_input.text().strip())
        name = self.name_input.text().strip()
        return {
            "name": name,
            "path": base / name,
            "resolution": self.resolution_combo.currentText(),
            "fps": self.fps_spin.value(),
        }


# ======================================================================
# Open Project Dialog
# ======================================================================

class OpenProjectDialog(QDialog):
    """Folder browser that validates ``pb_studio.db`` exists."""

    _DIALOG_STYLE = f"""
        QDialog {{
            background-color: {BG1};
        }}
        QLabel {{
            color: {T2};
            font-size: 12px;
            background: transparent;
        }}
        QLineEdit {{
            background-color: {BG2};
            color: {T1};
            border: 1px solid rgba(255,255,255,15);
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QLineEdit:focus {{
            border-color: {ACCENT};
        }}
        QPushButton {{
            background-color: {BG3};
            color: {T2};
            border: 1px solid rgba(255,255,255,15);
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: 600;
            font-size: 11px;
            min-height: 28px;
        }}
        QPushButton:hover {{
            color: {T1};
            border-color: rgba(255,255,255,25);
        }}
        QPushButton#btn_ok {{
            background-color: {ACCENT_DIM};
            color: {BG1};
            border: none;
        }}
        QPushButton#btn_ok:hover {{
            background-color: {ACCENT};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Projekt oeffnen")
        self.setMinimumWidth(480)
        self.setStyleSheet(self._DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Projekt oeffnen")
        title.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: 700; background: transparent;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Projektordner waehlen (muss pb_studio.db enthalten):"))

        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Projektordner waehlen...")
        path_row.addWidget(self.path_input, stretch=1)
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(36)
        btn_browse.clicked.connect(self._browse_path)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {T3}; font-size: 11px; background: transparent;")
        layout.addWidget(self.status_label)

        layout.addSpacing(10)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_ok = QPushButton("Oeffnen")
        btn_ok.setObjectName("btn_ok")
        btn_ok.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _browse_path(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Projektordner waehlen",
        )
        if folder:
            self.path_input.setText(folder)
            self._check_path(folder)

    def _check_path(self, folder: str):
        p = Path(folder) / "pb_studio.db"
        if p.exists():
            self.status_label.setText(f"pb_studio.db gefunden")
            self.status_label.setStyleSheet(f"color: #4ade80; font-size: 11px; background: transparent;")
        else:
            self.status_label.setText("pb_studio.db NICHT gefunden!")
            self.status_label.setStyleSheet(f"color: #f87171; font-size: 11px; background: transparent;")

    def _validate_and_accept(self):
        path = self.path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Fehler", "Bitte einen Projektordner waehlen.")
            return
        db_file = Path(path) / "pb_studio.db"
        if not db_file.exists():
            QMessageBox.warning(
                self, "Fehler",
                f"Im gewaehlten Ordner existiert keine pb_studio.db.\n{path}",
            )
            return
        self.accept()

    def get_path(self) -> Path:
        """Return the selected project folder as a Path."""
        return Path(self.path_input.text().strip())
