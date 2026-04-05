"""
First-Run Setup Wizard — AUD-62.

Shown once on first launch when required models are missing.
4 pages:
  1. Welcome + Hardware Check
  2. Model Selection
  3. Download Progress
  4. Finish / Launch

State persisted via QSettings("PBStudio", "PBStudio"):
  setup/setup_complete = true  →  wizard skipped on next launch
"""

from __future__ import annotations

import json
import logging
import urllib.request

from services.timeout_constants import HTTP_HEALTH_CHECK_TIMEOUT_SEC, MODEL_DOWNLOAD_TIMEOUT_SEC

from PySide6.QtCore import (
    Qt, QThread, Signal, QObject, QSettings, QTimer,
)
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame,
    QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.theme import (
    ACCENT, ACCENT_BRIGHT, BG0, BG1, BG2, BG3,
    ERR, OK, T1, T2, T3, WARN,
)

logger = logging.getLogger(__name__)

APP_VERSION = "0.5.0"

# ── Constants ─────────────────────────────────────────────────────────────────

_SETTINGS_ORG = "PBStudio"
_SETTINGS_APP = "PBStudio"
_SETUP_KEY    = "setup/setup_complete"

# Models offered in wizard
_OLLAMA_MODELS = [
    {
        "id": "qwen2.5:1.5b-instruct",
        "display": "Qwen 2.5 1.5B",
        "size_gb": 1.0,
        "description": "Minimal LLM — sehr schnell, wenig VRAM",
        "required": True,
        "default": True,
        "tags": ["ollama", "llm"],
    },
    {
        "id": "phi3:mini",
        "display": "Phi-3 Mini 3.8B",
        "size_gb": 2.3,
        "description": "Empfohlen für Action-Parsing und KI-Chat",
        "required": False,
        "default": False,
        "tags": ["ollama", "llm"],
    },
    {
        "id": "qwen2.5:7b-instruct-q4_K_M",
        "display": "Qwen 2.5 7B (Q4)",
        "size_gb": 4.5,
        "description": "Beste Qualität für GTX 1060 6GB",
        "required": False,
        "default": False,
        "tags": ["ollama", "llm"],
    },
]

_HF_MODELS = [
    {
        "id": "Systran/faster-whisper-base",
        "display": "Whisper Base",
        "size_gb": 0.3,
        "description": "Audio-Transkription (erforderlich für Beat-Analyse)",
        "required": True,
        "default": True,
        "tags": ["hf", "audio"],
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_setup_complete() -> bool:
    """Returns True if the wizard has been completed before."""
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return s.value(_SETUP_KEY, False, type=bool)


def mark_setup_complete() -> None:
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    s.setValue(_SETUP_KEY, True)
    s.sync()


def _ollama_running(url: str = "http://localhost:11434") -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=HTTP_HEALTH_CHECK_TIMEOUT_SEC) as r:
            return r.status == 200
    except OSError:
        return False


def _hf_cache_has(repo_id: str) -> bool:
    """Returns True if the HuggingFace cache contains this repo."""
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        return any(r.repo_id == repo_id for r in cache.repos)
    except (ImportError, OSError):
        return False


def _ollama_has_model(model_id: str, url: str = "http://localhost:11434") -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=HTTP_HEALTH_CHECK_TIMEOUT_SEC) as r:
            data = json.loads(r.read())
        return any(m.get("name", "").startswith(model_id.split(":")[0])
                   for m in data.get("models", []))
    except (OSError, ValueError):
        return False


# ── Background worker ─────────────────────────────────────────────────────────

class _DownloadWorker(QObject):
    """Downloads models one by one; emits progress per model + overall."""

    step_progress = Signal(str, float, str)   # model_id, pct 0-1, status_text
    step_done     = Signal(str, bool, str)     # model_id, success, message
    all_done      = Signal(bool, str)          # all_ok, summary

    def __init__(
        self,
        ollama_models: list[str],
        hf_models: list[str],
        ollama_url: str = "http://localhost:11434",
    ):
        super().__init__()
        self._ollama = ollama_models
        self._hf = hf_models
        self._ollama_url = ollama_url
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        errors: list[str] = []

        for mid in self._ollama:
            if self._cancelled:
                break
            self.step_progress.emit(mid, 0.0, "Starte Download…")
            ok, msg = self._pull_ollama(mid)
            self.step_done.emit(mid, ok, msg)
            if not ok:
                errors.append(f"{mid}: {msg}")

        for repo in self._hf:
            if self._cancelled:
                break
            self.step_progress.emit(repo, 0.0, "Starte Download…")
            ok, msg = self._download_hf(repo)
            self.step_done.emit(repo, ok, msg)
            if not ok:
                errors.append(f"{repo}: {msg}")

        if self._cancelled:
            self.all_done.emit(False, "Abgebrochen.")
        elif errors:
            self.all_done.emit(False, "Einige Downloads fehlgeschlagen:\n" + "\n".join(errors))
        else:
            self.all_done.emit(True, "Alle Modelle erfolgreich heruntergeladen.")

    # ── internals ──

    def _pull_ollama(self, model_name: str) -> tuple[bool, str]:
        try:
            payload = json.dumps({"name": model_name, "stream": True}).encode()
            req = urllib.request.Request(
                f"{self._ollama_url}/api/pull",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=MODEL_DOWNLOAD_TIMEOUT_SEC) as resp:
                for line in resp:
                    if self._cancelled:
                        return False, "Abgebrochen"
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status_msg = chunk.get("status", "")
                    total = chunk.get("total", 0)
                    completed = chunk.get("completed", 0)
                    pct = (completed / total) if total > 0 else 0.0
                    self.step_progress.emit(model_name, pct, status_msg)
            return True, "OK"
        except (OSError, ValueError) as e:
            return False, str(e)

    def _download_hf(self, repo_id: str) -> tuple[bool, str]:
        try:
            from huggingface_hub import snapshot_download
            self.step_progress.emit(repo_id, 0.1, "Verbinde zu HuggingFace…")
            snapshot_download(repo_id=repo_id, local_files_only=False)
            self.step_progress.emit(repo_id, 1.0, "Fertig")
            return True, "OK"
        except (ImportError, OSError, RuntimeError) as e:
            return False, str(e)


# ── UI helpers ────────────────────────────────────────────────────────────────

def _card(content: QWidget, parent: QWidget | None = None) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("wiz_card")
    frame.setStyleSheet(
        f"QFrame#wiz_card {{ background: {BG2}; border: 1px solid rgba(255,255,255,0.06); "
        "border-radius: 12px; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    layout.addWidget(content)
    return frame


def _heading(text: str, size: int = 14) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {T1}; font-size: {size}px; font-weight: 700; background: transparent;"
    )
    return lbl


def _sub(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {T2}; font-size: 11px; background: transparent;")
    return lbl


def _status_chip(text: str, ok: bool) -> QLabel:
    lbl = QLabel(text)
    color = OK if ok else ERR
    bg = "rgba(74,222,128,0.12)" if ok else "rgba(248,113,113,0.12)"
    lbl.setStyleSheet(
        f"background: {bg}; color: {color}; border-radius: 6px; "
        "font-size: 10px; font-weight: 700; padding: 3px 8px;"
    )
    lbl.setFixedHeight(22)
    return lbl


def _btn(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: {BG0}; border-radius: 8px; "
            "font-size: 12px; font-weight: 700; padding: 8px 22px; border: none; }}"
            f"QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}"
            f"QPushButton:disabled {{ background: rgba(212,164,74,0.3); color: rgba(0,0,0,0.4); }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background: {BG3}; color: {T2}; border-radius: 8px; "
            "font-size: 12px; padding: 8px 18px; border: 1px solid rgba(255,255,255,0.08); }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.08); color: {T1}; }}"
        )
    return b


# ── Page 1: Hardware Check ────────────────────────────────────────────────────

class _PageHardware(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(16)

        # Header
        layout.addWidget(_heading("Willkommen bei PB Studio", 18))
        layout.addWidget(_sub(
            f"Version {APP_VERSION}  ·  AI-gestützter DJ Audio/Video Editor\n"
            "Dieser Assistent prüft dein System und richtet die KI-Modelle ein."
        ))

        layout.addSpacing(8)
        layout.addWidget(_heading("System-Check", 12))

        self._check_widget = QWidget()
        self._check_layout = QVBoxLayout(self._check_widget)
        self._check_layout.setContentsMargins(0, 0, 0, 0)
        self._check_layout.setSpacing(6)
        layout.addWidget(self._check_widget)

        self._loading_lbl = QLabel("Prüfe System…")
        self._loading_lbl.setStyleSheet(f"color: {T3}; font-size: 11px;")
        self._check_layout.addWidget(self._loading_lbl)

        layout.addStretch()
        QTimer.singleShot(100, self._run_check)

    def _run_check(self) -> None:
        from services.startup_checks import run_startup_checks
        try:
            status = run_startup_checks()
        except (ImportError, OSError, RuntimeError) as e:
            logger.warning("Startup check failed: %s", e)
            self._loading_lbl.setText(f"System-Check fehlgeschlagen: {e}")
            return

        # Clear loading label
        self._loading_lbl.setParent(None)

        rows = [
            ("GPU / CUDA", status.cuda_ok,
             f"{status.gpu_name}  {status.gpu_vram_mb // 1024} GB" if status.cuda_ok else "Nicht gefunden — CPU-Modus"),
            ("FFmpeg", status.ffmpeg_ok,
             status.ffmpeg_version if status.ffmpeg_ok else "Nicht gefunden"),
            ("Ollama", status.ollama_ok,
             "Läuft" if status.ollama_ok else "Nicht gestartet — wird im Hintergrund gestartet"),
            ("Festplatte", status.disk_ok,
             f"{status.disk_free_gb:.1f} GB frei"),
        ]

        for label, ok, detail in rows:
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 2, 0, 2)
            hl.setSpacing(10)
            hl.addWidget(_status_chip("OK" if ok else "!", ok))
            lbl = QLabel(f"<b>{label}</b>  <span style='color:{T3}'>{detail}</span>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setStyleSheet(f"color: {T1}; font-size: 11px; background: transparent;")
            hl.addWidget(lbl)
            hl.addStretch()
            self._check_layout.addWidget(row)

        if status.disk_free_gb < 15:
            warn = QLabel(
                f"⚠  Weniger als 15 GB frei ({status.disk_free_gb:.1f} GB). "
                "KI-Modelle benötigen ca. 12 GB."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"color: {WARN}; font-size: 11px; background: rgba(251,191,36,0.08); "
                "border-radius: 6px; padding: 8px 10px;"
            )
            self._check_layout.addWidget(warn)


# ── Page 2: Model Selection ───────────────────────────────────────────────────

class _PageModels(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(16)

        layout.addWidget(_heading("KI-Modelle auswählen", 16))
        layout.addWidget(_sub(
            "Wähle die Modelle die jetzt heruntergeladen werden sollen. "
            "Du kannst dies auch später über Einstellungen → Modell-Manager nachholen."
        ))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")
        inner = QWidget()
        scroll.setWidget(inner)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(8)
        layout.addWidget(scroll, 1)

        self._checkboxes: dict[str, QCheckBox] = {}

        inner_layout.addWidget(_heading("Ollama Sprachmodelle", 11))
        for m in _OLLAMA_MODELS:
            cb = self._model_row(inner_layout, m)
            self._checkboxes[m["id"]] = cb

        inner_layout.addSpacing(8)
        inner_layout.addWidget(_heading("HuggingFace Modelle", 11))
        for m in _HF_MODELS:
            already = _hf_cache_has(m["id"])
            cb = self._model_row(inner_layout, m, already=already)
            self._checkboxes[m["id"]] = cb

        inner_layout.addStretch()

        # Total size
        self._size_lbl = QLabel()
        self._size_lbl.setStyleSheet(f"color: {T2}; font-size: 11px;")
        layout.addWidget(self._size_lbl)
        self._update_size()

    def _model_row(self, layout: QVBoxLayout, m: dict, already: bool = False) -> QCheckBox:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {BG2}; border: 1px solid rgba(255,255,255,0.06); "
            "border-radius: 8px; }}"
        )
        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(12)

        cb = QCheckBox()
        cb.setChecked(m["default"] and not already)
        cb.setEnabled(not already)
        cb.stateChanged.connect(self._update_size)
        hl.addWidget(cb)

        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(m["display"])
        name_lbl.setStyleSheet(
            f"color: {T1}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        name_row.addWidget(name_lbl)
        if m.get("required"):
            req_chip = QLabel("Erforderlich")
            req_chip.setStyleSheet(
                f"background: rgba(212,164,74,0.15); color: {ACCENT}; "
                "border-radius: 4px; font-size: 9px; font-weight: 700; padding: 2px 6px;"
            )
            name_row.addWidget(req_chip)
        if already:
            done_chip = QLabel("Bereits installiert")
            done_chip.setStyleSheet(
                f"background: rgba(74,222,128,0.12); color: {OK}; "
                "border-radius: 4px; font-size: 9px; font-weight: 700; padding: 2px 6px;"
            )
            name_row.addWidget(done_chip)
        name_row.addStretch()
        info_layout.addLayout(name_row)

        desc_lbl = QLabel(m["description"])
        desc_lbl.setStyleSheet(f"color: {T3}; font-size: 10px; background: transparent;")
        info_layout.addWidget(desc_lbl)
        hl.addWidget(info, 1)

        size_lbl = QLabel(f"{m['size_gb']:.1f} GB")
        size_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        size_lbl.setStyleSheet(
            f"color: {T2}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        hl.addWidget(size_lbl)

        layout.addWidget(row)
        return cb

    def _update_size(self) -> None:
        total_gb = 0.0
        all_models = _OLLAMA_MODELS + _HF_MODELS
        for m in all_models:
            cb = self._checkboxes.get(m["id"])
            if cb and cb.isChecked():
                total_gb += m["size_gb"]
        self._size_lbl.setText(
            f"Geschätzter Download: <b>{total_gb:.1f} GB</b>  ·  "
            "Downloads können unterbrochen und fortgesetzt werden."
        )
        self._size_lbl.setTextFormat(Qt.TextFormat.RichText)

    def selected_ollama(self) -> list[str]:
        return [m["id"] for m in _OLLAMA_MODELS if self._checkboxes.get(m["id"], None) and self._checkboxes[m["id"]].isChecked()]

    def selected_hf(self) -> list[str]:
        return [m["id"] for m in _HF_MODELS if self._checkboxes.get(m["id"], None) and self._checkboxes[m["id"]].isChecked()]


# ── Page 3: Download Progress ─────────────────────────────────────────────────

class _PageDownload(QWidget):

    downloads_finished = Signal(bool)  # emitted when all downloads complete

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(16)

        layout.addWidget(_heading("Download läuft…", 16))
        self._status_lbl = _sub("Bereite Download vor…")
        layout.addWidget(self._status_lbl)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(True)
        self._overall_bar.setStyleSheet(
            f"QProgressBar {{ background: {BG3}; border-radius: 6px; height: 10px; "
            "text-align: center; color: transparent; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}"
        )
        layout.addWidget(self._overall_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_widget)
        layout.addWidget(scroll, 1)

        self._cancel_btn = _btn("Abbrechen")
        self._cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self._cancel_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._model_rows: dict[str, tuple[QLabel, QProgressBar]] = {}
        self._completed = 0
        self._total = 0

    def start(self, ollama_models: list[str], hf_models: list[str]) -> None:
        self._total = len(ollama_models) + len(hf_models)
        self._completed = 0

        if self._total == 0:
            self._status_lbl.setText("Nichts zu tun — alle Modelle bereits vorhanden.")
            self.downloads_finished.emit(True)
            return

        # Build progress rows
        for mid in ollama_models + hf_models:
            self._add_row(mid)

        self._worker = _DownloadWorker(ollama_models, hf_models)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.step_progress.connect(self._on_progress)
        self._worker.step_done.connect(self._on_step_done)
        self._worker.all_done.connect(self._on_all_done)
        self._thread.start()

    def _add_row(self, model_id: str) -> None:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {BG2}; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; }}"
        )
        vl = QVBoxLayout(frame)
        vl.setContentsMargins(12, 10, 12, 10)
        vl.setSpacing(4)

        lbl = QLabel(model_id)
        lbl.setStyleSheet(f"color: {T1}; font-size: 11px; font-weight: 600; background: transparent;")
        vl.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {BG3}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}"
        )
        vl.addWidget(bar)

        # Insert before stretch
        count = self._rows_layout.count()
        self._rows_layout.insertWidget(count - 1, frame)
        self._model_rows[model_id] = (lbl, bar)

    def _on_progress(self, model_id: str, pct: float, status_text: str) -> None:
        self._status_lbl.setText(f"{model_id}: {status_text}")
        if model_id in self._model_rows:
            lbl, bar = self._model_rows[model_id]
            bar.setValue(int(pct * 100))
            lbl.setText(f"{model_id}  <span style='color:{T3}; font-size:10px'>{status_text}</span>")
            lbl.setTextFormat(Qt.TextFormat.RichText)

    def _on_step_done(self, model_id: str, ok: bool, msg: str) -> None:
        self._completed += 1
        self._overall_bar.setValue(int(self._completed / self._total * 100))
        if model_id in self._model_rows:
            lbl, bar = self._model_rows[model_id]
            bar.setValue(100)
            color = OK if ok else ERR
            status = "✓ Fertig" if ok else f"✗ Fehler: {msg}"
            bar.setStyleSheet(
                f"QProgressBar {{ background: {BG3}; border-radius: 3px; }}"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
            )
            lbl.setText(
                f"{model_id}  <span style='color:{color}; font-size:10px'>{status}</span>"
            )
            lbl.setTextFormat(Qt.TextFormat.RichText)

    def _on_all_done(self, ok: bool, msg: str) -> None:
        self._cancel_btn.setEnabled(False)
        self._status_lbl.setText(msg)
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self.downloads_finished.emit(ok)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._cancel_btn.setEnabled(False)
        self._status_lbl.setText("Breche ab…")


# ── Page 4: Finish ────────────────────────────────────────────────────────────

class _PageFinish(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 24)
        layout.setSpacing(20)
        layout.addStretch()

        icon = QLabel("✓")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {OK}; font-size: 48px; font-weight: 900; background: transparent;"
        )
        layout.addWidget(icon)

        heading = QLabel("PB Studio ist bereit!")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"color: {T1}; font-size: 20px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(heading)

        self._detail_lbl = _sub(
            "Setup abgeschlossen. Klicke 'App starten' um PB Studio zu öffnen."
        )
        self._detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._detail_lbl)

        layout.addStretch()

    def set_message(self, msg: str) -> None:
        self._detail_lbl.setText(msg)


# ── Main Wizard Dialog ────────────────────────────────────────────────────────

class SetupWizard(QDialog):
    """
    First-Run Setup Wizard.

    Usage:
        if not is_setup_complete():
            wizard = SetupWizard()
            wizard.exec()
    """

    PAGE_HARDWARE = 0
    PAGE_MODELS   = 1
    PAGE_DOWNLOAD = 2
    PAGE_FINISH   = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PB Studio — Ersteinrichtung")
        self.setMinimumSize(580, 520)
        self.resize(620, 560)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self._apply_styles()
        self._build_ui()
        self._go_to(self.PAGE_HARDWARE)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"QDialog {{ background: {BG1}; color: {T1}; }}"
            f"QLabel {{ background: transparent; }}"
            f"QCheckBox {{ color: {T1}; font-size: 12px; spacing: 8px; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; "
            f"border: 1px solid {BG3}; background: {BG2}; }}"
            f"QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}"
            f"QScrollBar:vertical {{ background: {BG2}; width: 8px; margin: 0px; }}"
            f"QScrollBar::handle:vertical {{ background: {BG3}; border-radius: 4px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Step indicator ──
        self._step_bar = QWidget()
        self._step_bar.setFixedHeight(48)
        self._step_bar.setStyleSheet(f"background: {BG2}; border-bottom: 1px solid {BG3};")
        step_layout = QHBoxLayout(self._step_bar)
        step_layout.setContentsMargins(24, 8, 24, 8)
        step_layout.setSpacing(4)

        self._step_labels: list[QLabel] = []
        steps = ["Hardware", "Modelle", "Download", "Fertig"]
        for i, name in enumerate(steps):
            lbl = QLabel(f"  {i+1}  {name}  ")
            lbl.setStyleSheet(
                f"color: {T3}; font-size: 11px; font-weight: 500; "
                "border-radius: 6px; padding: 3px 6px;"
            )
            step_layout.addWidget(lbl)
            self._step_labels.append(lbl)
            if i < len(steps) - 1:
                sep = QLabel("›")
                sep.setStyleSheet(f"color: {BG3}; font-size: 14px;")
                step_layout.addWidget(sep)
        step_layout.addStretch()
        outer.addWidget(self._step_bar)

        # ── Pages ──
        self._stack = QStackedWidget()
        self._page_hw    = _PageHardware()
        self._page_mods  = _PageModels()
        self._page_dl    = _PageDownload()
        self._page_fin   = _PageFinish()
        self._stack.addWidget(self._page_hw)
        self._stack.addWidget(self._page_mods)
        self._stack.addWidget(self._page_dl)
        self._stack.addWidget(self._page_fin)
        outer.addWidget(self._stack, 1)

        # ── Bottom bar ──
        bottom = QWidget()
        bottom.setFixedHeight(64)
        bottom.setStyleSheet(f"background: {BG2}; border-top: 1px solid {BG3};")
        btn_layout = QHBoxLayout(bottom)
        btn_layout.setContentsMargins(24, 12, 24, 12)
        btn_layout.setSpacing(10)

        self._skip_btn = _btn("Überspringen")
        self._skip_btn.clicked.connect(self._skip)
        btn_layout.addWidget(self._skip_btn)
        btn_layout.addStretch()

        self._back_btn = _btn("Zurück")
        self._back_btn.clicked.connect(self._back)
        btn_layout.addWidget(self._back_btn)

        self._next_btn = _btn("Weiter →", primary=True)
        self._next_btn.clicked.connect(self._next)
        btn_layout.addWidget(self._next_btn)

        outer.addWidget(bottom)

        # Connect download page signal
        self._page_dl.downloads_finished.connect(self._on_downloads_finished)

    def _go_to(self, page: int) -> None:
        self._stack.setCurrentIndex(page)
        for i, lbl in enumerate(self._step_labels):
            if i == page:
                lbl.setStyleSheet(
                    f"color: {ACCENT}; font-size: 11px; font-weight: 700; "
                    f"background: rgba(212,164,74,0.12); border-radius: 6px; padding: 3px 6px;"
                )
            elif i < page:
                lbl.setStyleSheet(
                    f"color: {OK}; font-size: 11px; font-weight: 600; "
                    "border-radius: 6px; padding: 3px 6px;"
                )
            else:
                lbl.setStyleSheet(
                    f"color: {T3}; font-size: 11px; font-weight: 500; "
                    "border-radius: 6px; padding: 3px 6px;"
                )

        # Button visibility
        self._back_btn.setVisible(page not in (self.PAGE_HARDWARE, self.PAGE_DOWNLOAD, self.PAGE_FINISH))
        self._skip_btn.setVisible(page in (self.PAGE_HARDWARE, self.PAGE_MODELS))
        self._next_btn.setVisible(page != self.PAGE_FINISH)

        if page == self.PAGE_FINISH:
            # Replace next with "App starten"
            self._next_btn.setVisible(False)
            launch_btn = _btn("App starten  →", primary=True)
            launch_btn.clicked.connect(self._launch)
            # Find bottom layout and add
            bottom = self.layout().itemAt(2).widget()
            bottom.layout().addWidget(launch_btn)

    def _next(self) -> None:
        current = self._stack.currentIndex()
        if current == self.PAGE_MODELS:
            # Start downloads
            self._go_to(self.PAGE_DOWNLOAD)
            ollama = self._page_mods.selected_ollama()
            hf = self._page_mods.selected_hf()
            if not ollama and not hf:
                # Nothing to download — skip to finish
                self._go_to(self.PAGE_FINISH)
                self._page_fin.set_message("Keine Modelle zum Download ausgewählt. Du kannst sie später über den Modell-Manager installieren.")
                mark_setup_complete()
            else:
                self._next_btn.setEnabled(False)
                self._page_dl.start(ollama, hf)
        elif current < self.PAGE_FINISH:
            self._go_to(current + 1)

    def _back(self) -> None:
        current = self._stack.currentIndex()
        if current > 0:
            self._go_to(current - 1)

    def _skip(self) -> None:
        mark_setup_complete()
        self.accept()

    def _launch(self) -> None:
        mark_setup_complete()
        self.accept()

    def _on_downloads_finished(self, ok: bool) -> None:
        self._next_btn.setEnabled(True)
        self._go_to(self.PAGE_FINISH)
        if ok:
            self._page_fin.set_message(
                "Alle ausgewählten Modelle wurden heruntergeladen. PB Studio ist bereit."
            )
        else:
            self._page_fin.set_message(
                "Einige Downloads sind fehlgeschlagen. Du kannst fehlende Modelle "
                "später über Einstellungen → Modell-Manager nachholen."
            )
        mark_setup_complete()
