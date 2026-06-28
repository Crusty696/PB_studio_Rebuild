"""Brain V3 — Lern-Session-Dialog (Phase 5, 06_PHASES.md Z.418-420).

Listet n=15 Stichproben-Cuts (Top-N nach Bayes-Varianz) und laesst den
User pro Eintrag einen 4-Klick-Feedback abgeben. Wenn Sample-Pfade vorhanden
sind, zeigt der Dialog Audio-/Video-Preview und kann sie starten/stoppen.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.brain.brain_v3_service import BrainV3Service
from services.brain.context_resolver import CutContext
from services.brain.schemas.brain_v3_schemas import (
    LearningSampleCut,
)
from ui.widgets.brain_v3_feedback_popup import (
    BrainV3FeedbackPopup,
    confidence_color_hex,
)
from ui.widgets.video_preview import VideoPreviewWidget
from workers.base import BaseWorker, run_worker

logger = logging.getLogger(__name__)


class _LearningLoadWorker(BaseWorker):
    """Laedt die Stichproben-Cuts (DB + SQLAlchemy + Medien-Stat) off-thread."""

    def __init__(self, service, n: int):
        super().__init__()
        self._service = service
        self._n = int(n)

    def _do_work(self):
        resp = self._service.learning_session(n=self._n)
        return list(resp.samples)


class _AudioPreviewSpawnWorker(BaseWorker):
    """Spawnt ffplay off-thread (CreateProcess blockiert sonst ~1s GUI)."""

    def __init__(self, cmd: list[str]):
        super().__init__()
        self._cmd = cmd

    def _do_work(self):
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return subprocess.Popen(
            self._cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )


class BrainV3LearningSessionDialog(QDialog):
    """Iteriert n unsicherste Cuts. Pro Cut Feedback-Popup."""

    session_finished = Signal(int)  # n_processed

    def __init__(
        self,
        service: Optional[BrainV3Service] = None,
        n_samples: int = 15,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._service = service or BrainV3Service()
        self._n_requested = int(n_samples)
        self._samples: list[LearningSampleCut] = []
        self._processed = 0
        self._current_preview: LearningSampleCut | None = None
        self._audio_preview_source: Path | None = None
        self._audio_preview_start_s = 0.0
        self._audio_preview_duration_s = 4.0
        self._audio_preview_process: subprocess.Popen | None = None
        self._preview_stop_requested = False
        self.setWindowTitle("Brain V3 — Lern-Session")
        self.setModal(True)
        self.resize(760, 560)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        title = QLabel("Lern-Session — unsicherste Cuts bewerten")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        root.addWidget(title)

        self._lbl_status = QLabel("Lade Stichproben ...")
        self._lbl_status.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        root.addWidget(self._lbl_status)

        body = QHBoxLayout()
        body.setSpacing(10)

        self._list = QListWidget()
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        body.addWidget(self._list, 1)

        preview_box = QVBoxLayout()
        preview_box.setSpacing(6)
        self._lbl_preview = QLabel("Preview: keine Stichprobe")
        self._lbl_preview.setStyleSheet("font-weight: 600; font-size: 12px;")
        preview_box.addWidget(self._lbl_preview)

        self._video_preview = VideoPreviewWidget()
        self._video_preview.setFixedSize(320, 180)
        preview_box.addWidget(self._video_preview)

        preview_actions = QHBoxLayout()
        self._btn_preview_play = QPushButton("Preview starten")
        self._btn_preview_play.clicked.connect(self._toggle_preview)
        self._btn_preview_play.setEnabled(False)
        preview_actions.addWidget(self._btn_preview_play)
        self._btn_preview_stop = QPushButton("Stop")
        self._btn_preview_stop.clicked.connect(self._stop_preview)
        self._btn_preview_stop.setEnabled(False)
        preview_actions.addWidget(self._btn_preview_stop)
        preview_actions.addStretch(1)
        preview_box.addLayout(preview_actions)
        preview_box.addStretch(1)
        body.addLayout(preview_box)
        root.addLayout(body, 1)

        actions = QHBoxLayout()
        self._btn_open = QPushButton("Bewerten")
        self._btn_open.clicked.connect(self._on_open_clicked)
        actions.addWidget(self._btn_open)
        actions.addStretch(1)
        self._btn_close = QPushButton("Schliessen")
        self._btn_close.clicked.connect(self._on_close_clicked)
        actions.addWidget(self._btn_close)
        root.addLayout(actions)

    def _load(self) -> None:
        # B-336-Freeze: learning_session macht state.db-Query + SQLAlchemy +
        # Path.exists()-Stat pro Medienpfad + json.loads (~3s) — lief synchron
        # im __init__ vor exec() -> weisser Bildschirm beim Dialog-Open.
        worker = _LearningLoadWorker(self._service, self._n_requested)
        run_worker(
            self, worker,
            on_finish=self._on_samples_loaded,
            on_error=self._on_load_error,
        )

    def _on_samples_loaded(self, samples) -> None:
        try:
            self._samples = list(samples)
            self._lbl_status.setText(
                f"{len(self._samples)} Stichproben geladen "
                f"(angefragt: {self._n_requested})"
            )
            self._populate()
        except RuntimeError:
            pass  # Dialog waehrend Load geschlossen — C++ Objekt bereits weg

    def _on_load_error(self, msg: str) -> None:
        logger.warning("BrainV3LearningSessionDialog: load failed: %s", msg)
        try:
            self._lbl_status.setText(f"Fehler: {msg}")
        except RuntimeError:
            pass

    def _populate(self) -> None:
        self._list.clear()
        for s in self._samples:
            color = confidence_color_hex(1.0 - s.uncertainty)  # invert: hoch=unsicher
            item = QListWidgetItem(
                f"Cut #{s.cut_id}   uncertainty={s.uncertainty:.3f}"
            )
            item.setData(Qt.ItemDataRole.UserRole, s.cut_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, s)
            item.setForeground(Qt.GlobalColor.white)
            # Hintergrund leicht eingefaerbt nach Confidence
            item.setBackground(self._safe_brush(color))
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    @staticmethod
    def _safe_brush(color_hex: str):
        from PySide6.QtGui import QBrush, QColor
        c = QColor(color_hex)
        c.setAlpha(60)
        return QBrush(c)

    def _on_open_clicked(self) -> None:
        item = self._list.currentItem()
        if item is None and self._list.count() > 0:
            item = self._list.item(0)
        if item is None:
            return
        self._open_feedback_for(item)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        self._open_feedback_for(item)

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._clear_preview()
            return
        sample = current.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(sample, LearningSampleCut):
            self._load_preview(sample)

    def _load_preview(self, sample: LearningSampleCut) -> None:
        self._stop_preview()
        self._current_preview = sample
        self._lbl_preview.setText(f"Preview: Cut #{sample.cut_id}")

        audio_ok = self._load_audio_preview(sample)
        video_ok = self._load_video_preview(sample.video_preview_path)
        can_preview = audio_ok or video_ok
        self._btn_preview_play.setEnabled(can_preview)
        self._btn_preview_stop.setEnabled(can_preview)
        if not can_preview:
            self._lbl_preview.setText(f"Preview: Cut #{sample.cut_id} (keine Medienpfade)")

    def _load_audio_preview(self, sample: LearningSampleCut) -> bool:
        if not sample.audio_preview_path:
            self._audio_preview_source = None
            return False
        p = Path(sample.audio_preview_path)
        if not p.exists():
            self._audio_preview_source = None
            return False
        self._audio_preview_source = p
        self._audio_preview_start_s = max(0.0, float(sample.audio_position_s or 0.0))
        self._audio_preview_duration_s = max(0.5, min(float(sample.preview_duration_s or 4.0), 6.0))
        return True

    def _load_video_preview(self, path: str | None) -> bool:
        if not path:
            self._video_preview.setText("Keine Video-Preview")
            return False
        p = Path(path)
        if not p.exists():
            self._video_preview.setText("Video-Datei nicht gefunden")
            return False
        self._video_preview.load_video(str(p))
        return True

    def _clear_preview(self) -> None:
        self._stop_preview()
        self._current_preview = None
        self._lbl_preview.setText("Preview: keine Stichprobe")
        self._video_preview.setText("Keine Video-Preview")
        self._audio_preview_source = None
        self._audio_preview_start_s = 0.0
        self._audio_preview_duration_s = 4.0
        self._btn_preview_play.setEnabled(False)
        self._btn_preview_stop.setEnabled(False)

    def _toggle_preview(self) -> None:
        if self._audio_preview_process is not None and self._audio_preview_process.poll() is None:
            self._stop_preview()
            return
        if self._audio_preview_source is not None:
            self._start_audio_preview(
                self._audio_preview_source,
                self._audio_preview_start_s,
                self._audio_preview_duration_s,
            )
        self._btn_preview_play.setText("Pause")

    def _stop_preview(self) -> None:
        # Falls ein Spawn-Worker noch laeuft: dessen Ergebnis soll terminiert
        # werden (siehe _on_audio_spawned).
        self._preview_stop_requested = True
        self._video_preview.stop()
        proc = self._audio_preview_process
        self._audio_preview_process = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._btn_preview_play.setText("Preview starten")

    def _start_audio_preview(self, source: Path, start_s: float, duration_s: float) -> bool:
        ffplay = _find_ffplay()
        if not ffplay:
            logger.warning("BrainV3LearningSessionDialog: ffplay nicht gefunden")
            return False
        cmd = [
            ffplay,
            "-ss",
            f"{max(0.0, start_s):.3f}",
            "-t",
            f"{max(0.5, min(duration_s, 6.0)):.3f}",
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "error",
            str(source),
        ]
        # B-336-Freeze: subprocess.Popen/CreateProcess blockiert ~1s GUI-Thread.
        self._preview_stop_requested = False
        worker = _AudioPreviewSpawnWorker(cmd)
        run_worker(
            self, worker,
            on_finish=self._on_audio_spawned,
            on_error=lambda msg: logger.warning(
                "BrainV3LearningSessionDialog: ffplay start failed: %s", msg
            ),
        )
        return True

    def _on_audio_spawned(self, proc) -> None:
        if self._preview_stop_requested:
            try:
                if proc is not None and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            return
        self._audio_preview_process = proc

    def _shutdown_preview(self) -> None:
        self._stop_preview()
        thread = getattr(self._video_preview, "_frame_thread", None)
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(1500)

    def _open_feedback_for(self, item: QListWidgetItem) -> None:
        cut_id = int(item.data(Qt.ItemDataRole.UserRole))
        popup = BrainV3FeedbackPopup(
            cut_id=cut_id,
            service=self._service,
            context=CutContext(),  # Lern-Session: neutral Context (TODO Phase 5+)
            cut_label=f"Stichprobe Cut #{cut_id}",
            parent=self,
        )
        popup.feedback_submitted.connect(self._on_feedback_done)
        popup.exec()

    def _on_feedback_done(self, cut_id: int, rating: str, n_buckets: int) -> None:
        self._processed += 1
        # Item aus Liste entfernen
        for i in range(self._list.count()):
            it = self._list.item(i)
            if int(it.data(Qt.ItemDataRole.UserRole)) == cut_id:
                self._list.takeItem(i)
                break
        self._lbl_status.setText(
            f"Bewertet: {self._processed} | Verbleibend: {self._list.count()} "
            f"| Letztes Update: {n_buckets} Buckets"
        )
        if self._list.count() == 0:
            self._clear_preview()
            self.session_finished.emit(self._processed)

    def _on_close_clicked(self) -> None:
        self._shutdown_preview()
        self.session_finished.emit(self._processed)
        self.accept()

    def closeEvent(self, event) -> None:
        self._shutdown_preview()
        super().closeEvent(event)


def _find_ffplay() -> str | None:
    root_bin = Path(__file__).resolve().parents[2] / "bin" / "ffplay.exe"
    if root_bin.exists():
        return str(root_bin)
    return shutil.which("ffplay")
