"""Brain V3 — Lern-Session-Dialog (Phase 5, 06_PHASES.md Z.418-420).

Listet n=15 Stichproben-Cuts (Top-N nach Bayes-Varianz) und laesst den
User pro Eintrag einen 4-Klick-Feedback abgeben. Wenn Sample-Pfade vorhanden
sind, zeigt der Dialog Audio-/Video-Preview und kann sie starten/stoppen.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
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

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3.context_resolver import CutContext
from services.brain_v3.schemas.brain_v3_schemas import (
    FeedbackRequest,
    LearningSampleCut,
)
from ui.widgets.brain_v3_feedback_popup import (
    BrainV3FeedbackPopup,
    confidence_color_hex,
)
from ui.widgets.video_preview import VideoPreviewWidget

logger = logging.getLogger(__name__)


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
        self._audio_output = QAudioOutput(self)
        self._audio_player = QMediaPlayer(self)
        self._audio_player.setAudioOutput(self._audio_output)
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
        try:
            resp = self._service.learning_session(n=self._n_requested)
        except Exception as exc:
            logger.warning("BrainV3LearningSessionDialog: load failed: %s", exc)
            self._lbl_status.setText(f"Fehler: {exc}")
            return
        self._samples = list(resp.samples)
        self._lbl_status.setText(
            f"{len(self._samples)} Stichproben geladen "
            f"(angefragt: {self._n_requested})"
        )
        self._populate()

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

        audio_ok = self._load_audio_preview(sample.audio_preview_path)
        video_ok = self._load_video_preview(sample.video_preview_path)
        can_preview = audio_ok or video_ok
        self._btn_preview_play.setEnabled(can_preview)
        self._btn_preview_stop.setEnabled(can_preview)
        if not can_preview:
            self._lbl_preview.setText(f"Preview: Cut #{sample.cut_id} (keine Medienpfade)")

    def _load_audio_preview(self, path: str | None) -> bool:
        if not path:
            self._audio_player.setSource(QUrl())
            return False
        p = Path(path)
        if not p.exists():
            self._audio_player.setSource(QUrl())
            return False
        self._audio_player.setSource(QUrl.fromLocalFile(str(p)))
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
        self._audio_player.setSource(QUrl())
        self._btn_preview_play.setEnabled(False)
        self._btn_preview_stop.setEnabled(False)

    def _toggle_preview(self) -> None:
        if self._audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._stop_preview()
            return
        if self._current_preview is not None:
            self._video_preview.play_from(float(self._current_preview.video_position_s))
        if not self._audio_player.source().isEmpty():
            self._audio_player.play()
        self._btn_preview_play.setText("Pause")

    def _stop_preview(self) -> None:
        self._video_preview.stop()
        self._audio_player.stop()
        self._btn_preview_play.setText("Preview starten")

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
