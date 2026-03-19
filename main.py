import sys
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QStatusBar, QDockWidget, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QFileDialog, QHeaderView,
    QProgressBar, QLabel, QLineEdit, QSlider, QGroupBox,
    QComboBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QDialog, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QBrush, QPen, QPixmap, QImage

APP_VERSION = "0.2.0"
STYLE_DIR = Path(__file__).parent / "styles"

from database import init_db, engine, AudioTrack, VideoClip, TimelineEntry
from sqlalchemy.orm import Session as DBSession
from services.ingest_service import (
    ingest_audio, ingest_video, get_all_media,
    AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
from services.audio_service import AudioAnalyzer
from services.video_service import VideoAnalyzer
from services.pacing_service import PacingSettings, calculate_cut_points, CutPoint
from services.export_service import export_timeline, get_timeline_summary


# ── Background Worker fuer Audio-Analyse ───────────────────────────────

class AnalysisWorker(QObject):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)

    def __init__(self, track_id: int, title: str):
        super().__init__()
        self.track_id = track_id
        self.title = title
        self.analyzer = AudioAnalyzer()

    def run(self):
        self.started.emit(self.track_id, self.title)
        try:
            result = self.analyzer.analyze_and_store(self.track_id)
            self.finished.emit(self.track_id, result)
        except Exception as e:
            self.error.emit(self.track_id, str(e))


# ── Background Worker fuer Video-Analyse ──────────────────────────────

class VideoAnalysisWorker(QObject):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)

    def __init__(self, clip_id: int, title: str):
        super().__init__()
        self.clip_id = clip_id
        self.title = title
        self.analyzer = VideoAnalyzer()

    def run(self):
        self.started.emit(self.clip_id, self.title)
        try:
            result = self.analyzer.analyze_and_store(self.clip_id)
            self.finished.emit(self.clip_id, result)
        except Exception as e:
            self.error.emit(self.clip_id, str(e))


# ── Export Worker ─────────────────────────────────────────────────────

class ExportWorker(QObject):
    finished = Signal(str)       # output_path
    error = Signal(str)          # error_msg
    progress = Signal(int, int, str)  # step, total, message

    def __init__(self, project_id: int, output_name: str):
        super().__init__()
        self.project_id = project_id
        self.output_name = output_name

    def run(self):
        try:
            path = export_timeline(
                project_id=self.project_id,
                output_name=self.output_name,
                progress_cb=lambda s, t, m: self.progress.emit(s, t, m),
            )
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


# ── Draggable Timeline Clip (QGraphicsRectItem) ─────────────────────

class TimelineClipItem(QGraphicsRectItem):
    """Ein verschiebbarer Clip auf der QGraphicsView-Timeline."""

    AUDIO_COLOR = QColor(70, 130, 220, 200)
    VIDEO_COLOR = QColor(230, 140, 50, 200)
    SELECTED_BORDER = QColor(255, 255, 100)

    def __init__(self, entry_id: int, media_id: int, track_type: str,
                 title: str, x: float, y: float, width: float, height: float,
                 on_moved=None):
        super().__init__(QRectF(0, 0, width, height))
        self.entry_id = entry_id
        self.media_id = media_id
        self.track_type = track_type
        self.on_moved = on_moved

        self.setPos(x, y)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        color = self.AUDIO_COLOR if track_type == "audio" else self.VIDEO_COLOR
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(150), 1))

        # Label
        label = QGraphicsTextItem(title[:30], self)
        label.setDefaultTextColor(QColor(255, 255, 255))
        label.setFont(QFont("Segoe UI", 8))
        label.setPos(4, 2)

        self._track_y = y  # Spur-Y fixieren

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            # Nur horizontal bewegen, Y fixiert auf Spur
            new_pos = QPointF(max(0, value.x()), self._track_y)
            return new_pos
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.on_moved:
                self.on_moved(self.entry_id, value.x())
        return super().itemChange(change, value)


# ── QGraphicsView Timeline ───────────────────────────────────────────

PIXELS_PER_SECOND = 20  # Zoom-Faktor
TRACK_HEIGHT = 50
AUDIO_TRACK_Y = 10
VIDEO_TRACK_Y = AUDIO_TRACK_Y + TRACK_HEIGHT + 10
CUT_MARKERS_Y = VIDEO_TRACK_Y + TRACK_HEIGHT + 10
RULER_Y = CUT_MARKERS_Y + 30


class InteractiveTimeline(QGraphicsView):
    """QGraphicsView-basierte Timeline mit 2 Spuren und Drag & Drop."""

    clip_moved = Signal(int, float)  # entry_id, new_start_time

    def __init__(self, console_log=None):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(200)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333;")
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.console_log = console_log
        self.clip_items: list[TimelineClipItem] = []
        self.cut_lines: list[QGraphicsLineItem] = []

        self._draw_track_backgrounds()
        self._draw_labels()

    def _draw_track_backgrounds(self):
        """Zeichnet die Spur-Hintergruende."""
        audio_bg = self._scene.addRect(
            QRectF(0, AUDIO_TRACK_Y, 2000, TRACK_HEIGHT),
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(40, 40, 55))
        )
        audio_bg.setZValue(-10)
        video_bg = self._scene.addRect(
            QRectF(0, VIDEO_TRACK_Y, 2000, TRACK_HEIGHT),
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(55, 40, 40))
        )
        video_bg.setZValue(-10)

    def _draw_labels(self):
        """Spur-Labels."""
        for label_text, y in [("Audio", AUDIO_TRACK_Y), ("Video", VIDEO_TRACK_Y)]:
            txt = self._scene.addText(label_text, QFont("Segoe UI", 9))
            txt.setDefaultTextColor(QColor(150, 150, 150))
            txt.setPos(-50, y + 15)
            txt.setZValue(10)

    def load_from_db(self, project_id: int = 1):
        """Laedt alle TimelineEntry-Eintraege und zeigt sie als Clips."""
        # Alte Clips entfernen
        for item in self.clip_items:
            self._scene.removeItem(item)
        self.clip_items.clear()

        with DBSession(engine) as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=project_id)
                .all()
            )
            for entry in entries:
                if entry.track == "audio":
                    track = session.get(AudioTrack, entry.media_id)
                    title = track.title if track else "?"
                    dur = track.duration if track and track.duration else 30.0
                    y = AUDIO_TRACK_Y
                elif entry.track == "video":
                    clip = session.get(VideoClip, entry.media_id)
                    title = Path(clip.file_path).stem if clip else "?"
                    dur = clip.duration if clip and clip.duration else 10.0
                    y = VIDEO_TRACK_Y
                else:
                    continue

                width = dur * PIXELS_PER_SECOND
                x = entry.start_time * PIXELS_PER_SECOND

                item = TimelineClipItem(
                    entry_id=entry.id,
                    media_id=entry.media_id,
                    track_type=entry.track,
                    title=title,
                    x=x, y=y,
                    width=width, height=TRACK_HEIGHT,
                    on_moved=self._on_clip_moved,
                )
                self._scene.addItem(item)
                self.clip_items.append(item)

        self._update_scene_rect()

    def add_clip(self, entry_id: int, media_id: int, track_type: str,
                 title: str, start_time: float, duration: float):
        """Fuegt einen einzelnen Clip hinzu."""
        y = AUDIO_TRACK_Y if track_type == "audio" else VIDEO_TRACK_Y
        width = duration * PIXELS_PER_SECOND
        x = start_time * PIXELS_PER_SECOND

        item = TimelineClipItem(
            entry_id=entry_id, media_id=media_id, track_type=track_type,
            title=title, x=x, y=y, width=width, height=TRACK_HEIGHT,
            on_moved=self._on_clip_moved,
        )
        self._scene.addItem(item)
        self.clip_items.append(item)
        self._update_scene_rect()

    def set_cut_points(self, cuts: list[CutPoint], total_duration: float):
        """Zeigt Cut-Marker als vertikale Linien."""
        for line in self.cut_lines:
            self._scene.removeItem(line)
        self.cut_lines.clear()

        color_map = {
            "beat": QColor(100, 200, 100, 180),
            "scene": QColor(255, 200, 60, 180),
            "energy": QColor(200, 100, 200, 180),
        }
        for cp in cuts:
            x = cp.time * PIXELS_PER_SECOND
            color = color_map.get(cp.source, QColor(180, 180, 180))
            pen = QPen(color, 1)
            line_h = int(20 * cp.strength)
            line = self._scene.addLine(x, CUT_MARKERS_Y, x, CUT_MARKERS_Y + line_h, pen)
            line.setZValue(5)
            self.cut_lines.append(line)

        self._draw_ruler(total_duration)
        self._update_scene_rect()

    def _draw_ruler(self, total_duration: float):
        """Zeitachse unten."""
        pen = QPen(QColor(120, 120, 120), 1)
        total_px = total_duration * PIXELS_PER_SECOND
        self._scene.addLine(0, RULER_Y, total_px, RULER_Y, pen)

        step = max(1.0, total_duration / 20)
        t = 0.0
        while t <= total_duration:
            x = t * PIXELS_PER_SECOND
            self._scene.addLine(x, RULER_Y - 3, x, RULER_Y + 3, pen)
            txt = self._scene.addText(f"{t:.0f}s", QFont("Segoe UI", 7))
            txt.setDefaultTextColor(QColor(120, 120, 120))
            txt.setPos(x - 10, RULER_Y + 5)
            t += step

    def _on_clip_moved(self, entry_id: int, new_x: float):
        """Clip wurde verschoben -> DB aktualisieren."""
        new_start = max(0, new_x / PIXELS_PER_SECOND)
        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if entry:
                old_start = entry.start_time
                entry.start_time = round(new_start, 3)
                # end_time mitverschieben
                if entry.end_time is not None:
                    delta = new_start - old_start
                    entry.end_time = round(entry.end_time + delta, 3)
                session.commit()
        self.clip_moved.emit(entry_id, new_start)

    def _update_scene_rect(self):
        """Scene-Rect erweitern damit Scrolling funktioniert."""
        r = self._scene.itemsBoundingRect()
        r.adjust(-60, -10, 200, 40)
        self._scene.setSceneRect(r)


# ── Video-Vorschau Widget ─────────────────────────────────────────────

class VideoPreviewWidget(QLabel):
    """Kleines Video-Vorschaufenster mit Frame-Extraction via FFmpeg."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("video_preview")
        self.setMinimumSize(320, 180)
        self.setMaximumHeight(220)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Keine Vorschau")
        self.setScaledContents(False)

        self._current_path: str | None = None
        self._current_time: float = 0.0
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(100)  # ~10 fps preview
        self._play_timer.timeout.connect(self._advance_frame)
        self._is_playing = False
        self._duration: float = 0.0

    def load_video(self, file_path: str, duration: float = 0.0):
        """Laedt ein Video und zeigt den ersten Frame."""
        self._current_path = file_path
        self._current_time = 0.0
        self._duration = duration
        self._extract_and_show_frame(0.0)

    def play_from(self, time_sec: float):
        """Startet kurze Vorschau ab einer bestimmten Zeit."""
        if not self._current_path:
            return
        self._current_time = time_sec
        self._is_playing = True
        self._play_timer.start()

    def stop(self):
        self._play_timer.stop()
        self._is_playing = False

    def toggle_play(self):
        if self._is_playing:
            self.stop()
        else:
            self.play_from(self._current_time)

    def _advance_frame(self):
        """Zeigt den naechsten Frame (alle 100ms -> +0.5s Sprung)."""
        self._current_time += 0.5
        if self._duration > 0 and self._current_time >= self._duration:
            self._current_time = 0.0
            self.stop()
            return
        self._extract_and_show_frame(self._current_time)

    def _extract_and_show_frame(self, time_sec: float):
        """Extrahiert einen Frame via FFmpeg und zeigt ihn an."""
        if not self._current_path or not Path(self._current_path).exists():
            self.setText("Datei nicht gefunden")
            return
        try:
            cmd = [
                "ffmpeg", "-ss", str(time_sec), "-i", self._current_path,
                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", "320x180", "-v", "quiet", "-y", "pipe:1"
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if result.returncode == 0 and len(result.stdout) == 320 * 180 * 3:
                img = QImage(result.stdout, 320, 180, 320 * 3, QImage.Format.Format_RGB888)
                self.setPixmap(QPixmap.fromImage(img))
            else:
                self.setText(f"Frame @ {time_sec:.1f}s")
        except Exception:
            self.setText("FFmpeg nicht verfuegbar")


# ── About Dialog ──────────────────────────────────────────────────────

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About PB_studio")
        self.setFixedSize(400, 280)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("PB_studio")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #00d4ff;")
        layout.addWidget(title)

        subtitle = QLabel("Director's Cockpit")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #7c3aed; font-weight: 600;")
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #2a2d35;")
        layout.addWidget(line)

        info = QLabel(
            f"Version {APP_VERSION}\n\n"
            "Beat-synchronisierte Video-Produktion\n"
            "mit KI-gestuetztem Pacing.\n\n"
            "Built with PySide6 + FFmpeg + librosa"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #808899; font-size: 12px; line-height: 1.5;")
        layout.addWidget(info)

        btn = QPushButton("Schliessen")
        btn.setObjectName("btn_accent")
        btn.setMaximumWidth(140)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)


# ── Hauptfenster ──────────────────────────────────────────────────────

class PBWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"PB_studio v{APP_VERSION} - Director's Cockpit")
        self.resize(1400, 800)
        self._active_threads: list[QThread] = []
        self._active_workers: list[QObject] = []

        # Zentrales Widget und Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top-Bar mit About-Button
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        btn_about = QPushButton("\u2139  About")
        btn_about.setMaximumWidth(100)
        btn_about.clicked.connect(self._show_about)
        top_bar.addWidget(btn_about)
        layout.addLayout(top_bar)

        # Tab-System
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_media_ingest_tab(), "\U0001F4C1  Media Ingest")
        self.tabs.addTab(self._build_directors_desk_tab(), "\U0001F3AC  Director's Desk")
        self.tabs.addTab(self._build_production_tab(), "\U0001F3A5  Production")

        # Statusleiste
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"PB_studio v{APP_VERSION} | System bereit")

        # System-Konsole
        self.setup_console()

        # Tabelle initial befuellen
        self._refresh_media_table()

    def _show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    # ── Media Ingest Tab ──────────────────────────────────────────────

    def _build_media_ingest_tab(self) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tab_layout.addWidget(splitter)

        # Linke Seite: Buttons
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        btn_video = QPushButton("\U0001F4F9  Video importieren")
        btn_video.setMinimumHeight(40)
        btn_video.clicked.connect(self._import_video)
        left_layout.addWidget(btn_video)

        btn_audio = QPushButton("\U0001F3B5  Audio importieren")
        btn_audio.setMinimumHeight(40)
        btn_audio.clicked.connect(self._import_audio)
        left_layout.addWidget(btn_audio)

        self.btn_analyze = QPushButton("\U0001F50D  Audio analysieren")
        self.btn_analyze.setMinimumHeight(40)
        self.btn_analyze.clicked.connect(self._analyze_selected_audio)
        left_layout.addWidget(self.btn_analyze)

        self.btn_analyze_video = QPushButton("\U0001F50E  Video analysieren")
        self.btn_analyze_video.setMinimumHeight(40)
        self.btn_analyze_video.clicked.connect(self._analyze_selected_video)
        left_layout.addWidget(self.btn_analyze_video)

        # Button: Zur Timeline hinzufuegen
        self.btn_add_to_timeline = QPushButton("\u2795  Zur Timeline hinzufuegen")
        self.btn_add_to_timeline.setMinimumHeight(40)
        self.btn_add_to_timeline.clicked.connect(self._add_selected_to_timeline)
        left_layout.addWidget(self.btn_add_to_timeline)

        # Fortschrittsanzeige
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Analyse laeuft...")
        left_layout.addWidget(self.progress_bar)

        splitter.addWidget(left_panel)

        # Rechte Seite: Media-Tabelle
        self.media_table = QTableWidget()
        self.media_table.setColumnCount(7)
        self.media_table.setHorizontalHeaderLabels(
            ["ID", "Typ", "Titel", "BPM", "Aufloesung", "FPS", "Dateipfad"]
        )
        self.media_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.media_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.media_table.setAlternatingRowColors(True)

        header = self.media_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        splitter.addWidget(self.media_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        return tab

    # ── Director's Desk Tab ──────────────────────────────────────────

    def _build_directors_desk_tab(self) -> QWidget:
        tab = QWidget()
        main_layout = QVBoxLayout(tab)

        # ── Top section: Controls (left) + Video Preview (right) ──
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Control-Panel (links) ──
        control_group = QGroupBox("\u2699  Pacing-Steuerung")
        control_layout = QVBoxLayout(control_group)

        # Vibe-Eingabe
        vibe_row = QHBoxLayout()
        vibe_row.addWidget(QLabel("\U0001F3AD  Stimmung / Vibe:"))
        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("z.B. energetisch, melancholisch, aggressiv...")
        vibe_row.addWidget(self.vibe_input)
        control_layout.addLayout(vibe_row)

        # Slider-Reihe
        sliders_layout = QHBoxLayout()

        # Audio/Video-Auswahl
        source_layout = QVBoxLayout()
        source_layout.addWidget(QLabel("\U0001F3B5  Audio-Track:"))
        self.audio_combo = QComboBox()
        source_layout.addWidget(self.audio_combo)
        source_layout.addWidget(QLabel("\U0001F4F9  Video-Clip:"))
        self.video_combo = QComboBox()
        self.video_combo.currentIndexChanged.connect(self._on_video_combo_changed)
        source_layout.addWidget(self.video_combo)
        sliders_layout.addLayout(source_layout)

        self.tempo_slider, tempo_box = self._create_slider("Tempo", 0, 100, 50)
        sliders_layout.addWidget(tempo_box)
        self.energy_slider, energy_box = self._create_slider("Energie", 0, 100, 50)
        sliders_layout.addWidget(energy_box)
        self.density_slider, density_box = self._create_slider("Schnitt-Dichte", 0, 100, 50)
        sliders_layout.addWidget(density_box)

        btn_layout = QVBoxLayout()
        btn_layout.addStretch()
        self.btn_generate = QPushButton("\u26A1  Timeline\ngenerieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setMinimumHeight(60)
        self.btn_generate.setMinimumWidth(120)
        self.btn_generate.clicked.connect(self._generate_timeline)
        btn_layout.addWidget(self.btn_generate)
        btn_layout.addStretch()
        sliders_layout.addLayout(btn_layout)

        control_layout.addLayout(sliders_layout)
        top_splitter.addWidget(control_group)

        # ── Video-Vorschau (rechts oben) ──
        preview_group = QGroupBox("\U0001F4FA  Vorschau")
        preview_layout = QVBoxLayout(preview_group)

        self.video_preview = VideoPreviewWidget()
        preview_layout.addWidget(self.video_preview)

        # Play/Stop Buttons
        preview_btn_row = QHBoxLayout()
        self.btn_preview_play = QPushButton("\u25B6  Play")
        self.btn_preview_play.clicked.connect(self._toggle_preview_play)
        preview_btn_row.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("\u23F9  Stop")
        self.btn_preview_stop.clicked.connect(self.video_preview.stop)
        preview_btn_row.addWidget(self.btn_preview_stop)
        preview_layout.addLayout(preview_btn_row)

        self.preview_time_label = QLabel("00:00 / 00:00")
        self.preview_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_time_label.setStyleSheet("color: #808899; font-size: 11px;")
        preview_layout.addWidget(self.preview_time_label)

        top_splitter.addWidget(preview_group)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(top_splitter)

        # ── Interaktive Timeline (QGraphicsView) ──
        timeline_group = QGroupBox("\U0001F3AC  Timeline (Drag & Drop)")
        timeline_layout = QVBoxLayout(timeline_group)

        self.timeline_view = InteractiveTimeline()
        self.timeline_view.clip_moved.connect(self._on_timeline_clip_moved)
        timeline_layout.addWidget(self.timeline_view)

        # Cut-Info
        self.cut_info_label = QLabel("Noch keine Timeline generiert.")
        self.cut_info_label.setStyleSheet("color: #808899; padding: 4px;")
        timeline_layout.addWidget(self.cut_info_label)

        main_layout.addWidget(timeline_group, stretch=1)

        # Combos initial befuellen
        self._refresh_director_combos()

        return tab

    def _on_video_combo_changed(self, index: int):
        """Laedt Vorschau wenn ein Video ausgewaehlt wird."""
        video_id = self.video_combo.currentData()
        if video_id is None:
            self.video_preview.setText("Keine Vorschau")
            return
        with DBSession(engine) as session:
            clip = session.get(VideoClip, video_id)
            if clip and clip.file_path:
                dur = clip.duration if clip.duration else 0.0
                self.video_preview.load_video(clip.file_path, dur)

    def _toggle_preview_play(self):
        self.video_preview.toggle_play()

    # ── Production Tab ────────────────────────────────────────────────

    def _build_production_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Info
        info_group = QGroupBox("Timeline-Status")
        info_layout = QVBoxLayout(info_group)
        self.production_info = QLabel("Timeline laden...")
        self.production_info.setStyleSheet("color: #ccc; font-size: 14px;")
        info_layout.addWidget(self.production_info)
        layout.addWidget(info_group)

        # Export-Einstellungen
        settings_group = QGroupBox("Export-Einstellungen")
        settings_layout = QHBoxLayout(settings_group)

        settings_layout.addWidget(QLabel("Dateiname:"))
        self.export_name_input = QLineEdit("output.mp4")
        settings_layout.addWidget(self.export_name_input)

        settings_layout.addWidget(QLabel("Aufloesung:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1920x1080", "1280x720", "854x480", "3840x2160"])
        settings_layout.addWidget(self.resolution_combo)

        settings_layout.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "24", "25", "60"])
        settings_layout.addWidget(self.fps_combo)

        layout.addWidget(settings_group)

        # Export-Button + Progress
        export_row = QHBoxLayout()
        self.btn_export = QPushButton("\U0001F680  Video exportieren")
        self.btn_export.setObjectName("btn_accent")
        self.btn_export.setMinimumHeight(50)
        self.btn_export.clicked.connect(self._start_export)
        export_row.addWidget(self.btn_export)

        self.btn_refresh_production = QPushButton("\U0001F504  Aktualisieren")
        self.btn_refresh_production.setMinimumHeight(50)
        self.btn_refresh_production.clicked.connect(self._refresh_production_info)
        export_row.addWidget(self.btn_refresh_production)
        layout.addLayout(export_row)

        # Export-Fortschritt
        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        self.export_progress.setTextVisible(True)
        layout.addWidget(self.export_progress)

        # Export-Log
        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setMaximumHeight(200)
        # Styled by dark_steel.qss
        layout.addWidget(self.export_log)

        layout.addStretch()

        return tab

    def _create_slider(self, label: str, min_val: int, max_val: int, default: int):
        box = QGroupBox(label)
        box_layout = QVBoxLayout(box)
        value_label = QLabel(str(default))
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        slider.setMinimumHeight(80)
        slider.valueChanged.connect(lambda v: value_label.setText(str(v)))
        box_layout.addWidget(value_label)
        box_layout.addWidget(slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        return slider, box

    def _refresh_director_combos(self):
        media = get_all_media()
        self.audio_combo.clear()
        self.video_combo.clear()
        self.audio_combo.addItem("-- kein Audio --", None)
        self.video_combo.addItem("-- kein Video --", None)
        for item in media:
            label = f"[{item['id']}] {item['title']}"
            if item["type"] == "Audio":
                bpm = item.get("bpm")
                if bpm:
                    label += f" ({bpm} BPM)"
                self.audio_combo.addItem(label, item["id"])
            elif item["type"] == "Video":
                self.video_combo.addItem(label, item["id"])

    def _generate_timeline(self):
        audio_id = self.audio_combo.currentData()
        video_id = self.video_combo.currentData()

        settings = PacingSettings(
            tempo=self.tempo_slider.value(),
            energy=self.energy_slider.value(),
            cut_density=self.density_slider.value(),
            vibe=self.vibe_input.text(),
        )

        audio_dur = 0.0
        video_dur = 0.0
        if audio_id is not None:
            with DBSession(engine) as s:
                track = s.get(AudioTrack, audio_id)
                if track and track.duration:
                    audio_dur = track.duration
        if video_id is not None:
            with DBSession(engine) as s:
                clip = s.get(VideoClip, video_id)
                if clip and clip.duration:
                    video_dur = clip.duration

        total_dur = max(audio_dur, video_dur, 30.0)

        cuts = calculate_cut_points(audio_id, video_id, settings, total_dur)

        # Timeline-View aktualisieren
        self.timeline_view.load_from_db()
        self.timeline_view.set_cut_points(cuts, total_dur)

        beat_cuts = sum(1 for c in cuts if c.source == "beat")
        scene_cuts = sum(1 for c in cuts if c.source == "scene")
        energy_cuts = sum(1 for c in cuts if c.source == "energy")
        self.cut_info_label.setText(
            f"{len(cuts)} Schnittpunkte | Beat: {beat_cuts} | Szene: {scene_cuts} | "
            f"Energie: {energy_cuts} | Dauer: {total_dur:.1f}s"
        )
        self.console_text.append(
            f"[Pacing] Timeline generiert: {len(cuts)} Cuts "
            f"(Tempo={settings.tempo}, Energie={settings.energy}, Dichte={settings.cut_density})"
        )

    def _on_timeline_clip_moved(self, entry_id: int, new_start: float):
        self.console_text.append(
            f"[Timeline] Clip {entry_id} verschoben -> Start: {new_start:.2f}s"
        )

    # ── Zur Timeline hinzufuegen ──────────────────────────────────────

    def _add_selected_to_timeline(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return

        media_type = self.media_table.item(row, 1).text()
        media_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        track_type = "audio" if media_type == "Audio" else "video"

        # Start-Zeit: ans Ende der bestehenden Clips der gleichen Spur
        with DBSession(engine) as session:
            existing = (
                session.query(TimelineEntry)
                .filter_by(project_id=1, track=track_type)
                .order_by(TimelineEntry.start_time.desc())
                .first()
            )
            start_time = 0.0
            if existing and existing.end_time:
                start_time = existing.end_time

            # Duration ermitteln
            if track_type == "audio":
                obj = session.get(AudioTrack, media_id)
                duration = obj.duration if obj and obj.duration else 30.0
            else:
                obj = session.get(VideoClip, media_id)
                duration = obj.duration if obj and obj.duration else 10.0

            entry = TimelineEntry(
                project_id=1,
                track=track_type,
                media_id=media_id,
                start_time=round(start_time, 3),
                end_time=round(start_time + duration, 3),
                lane=0,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

        # Clip auf Timeline anzeigen
        self.timeline_view.add_clip(
            entry_id=entry_id,
            media_id=media_id,
            track_type=track_type,
            title=title,
            start_time=start_time,
            duration=duration,
        )

        self.console_text.append(
            f"[Timeline] {media_type} '{title}' hinzugefuegt bei {start_time:.1f}s "
            f"(Dauer: {duration:.1f}s)"
        )

    # ── Import-Logik ──────────────────────────────────────────────────

    def _import_video(self):
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Videos importieren", "", ext_filter)
        self._process_imports(paths, "video")

    def _import_audio(self):
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Audio importieren", "", ext_filter)
        self._process_imports(paths, "audio")

    def _process_imports(self, paths: list[str], media_type: str):
        if not paths:
            return

        added = 0
        for p in paths:
            if media_type == "audio":
                result = ingest_audio(p)
            else:
                result = ingest_video(p)

            name = Path(p).name
            if result is None:
                self.console_text.append(f"[Warnung] Datei bereits importiert: {name}")
            else:
                self.console_text.append(f"[Ingest] {media_type.capitalize()} importiert: {name}")
                added += 1

        if added:
            self._refresh_media_table()
            self._refresh_director_combos()
            self.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

    # ── Audio-Analyse ─────────────────────────────────────────────────

    def _analyze_selected_audio(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return

        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen analysiert werden.")
            return

        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        thread = QThread()
        worker = AnalysisWorker(track_id, title)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self._on_analysis_started)
        worker.finished.connect(self._on_analysis_finished)
        worker.error.connect(self._on_analysis_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_worker(thread, worker))

        self._active_threads.append(thread)
        self._active_workers.append(worker)

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)
        thread.start()

    def _on_analysis_started(self, track_id: int, title: str):
        self.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict):
        bpm = result["bpm"]
        duration = result["duration"]
        beats = len(result.get("beat_positions", []))
        self.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Beats: {beats} | Energie-Punkte: {len(result['energy_curve'])}"
        )
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse abgeschlossen | System bereit")
        self._refresh_media_table()
        self._refresh_director_combos()

    def _on_analysis_error(self, track_id: int, error_msg: str):
        self.console_text.append(f"[Fehler] Audio-Analyse fehlgeschlagen (ID {track_id}): {error_msg}")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse-Fehler | System bereit")

    # ── Video-Analyse ──────────────────────────────────────────────────

    def _analyze_selected_video(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return

        media_type = self.media_table.item(row, 1).text()
        if media_type != "Video":
            self.console_text.append("[Warnung] Nur Video-Dateien koennen hier analysiert werden.")
            return

        clip_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        thread = QThread()
        worker = VideoAnalysisWorker(clip_id, title)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self._on_video_analysis_started)
        worker.finished.connect(self._on_video_analysis_finished)
        worker.error.connect(self._on_video_analysis_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_worker(thread, worker))

        self._active_threads.append(thread)
        self._active_workers.append(worker)
        self.btn_analyze_video.setEnabled(False)
        self.btn_analyze_video.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)
        thread.start()

    def _on_video_analysis_started(self, clip_id: int, title: str):
        self.console_text.append(f"[Video] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Video-Analyse: {title}")

    def _on_video_analysis_finished(self, clip_id: int, result: dict):
        self.console_text.append(
            f"[Video] Analyse fertig: {result['width']}x{result['height']} | "
            f"{result['fps']} FPS | Dauer: {result.get('duration', '?')}s | Codec: {result['codec']}"
        )
        if "proxy_path" in result:
            self.console_text.append(f"[Video] Proxy erstellt: {result['proxy_path']}")
        self.btn_analyze_video.setEnabled(True)
        self.btn_analyze_video.setText("Video analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Video-Analyse abgeschlossen | System bereit")
        self._refresh_media_table()
        self._refresh_director_combos()

    def _on_video_analysis_error(self, clip_id: int, error_msg: str):
        self.console_text.append(f"[Fehler] Video-Analyse fehlgeschlagen (ID {clip_id}): {error_msg}")
        self.btn_analyze_video.setEnabled(True)
        self.btn_analyze_video.setText("Video analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Video-Analyse-Fehler | System bereit")

    def _cleanup_worker(self, thread: QThread, worker: QObject):
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if thread in self._active_threads:
            self._active_threads.remove(thread)

    # ── Production / Export ────────────────────────────────────────────

    def _refresh_production_info(self):
        summary = get_timeline_summary()
        self.production_info.setText(
            f"Video-Clips: {summary['video_clips']} | "
            f"Audio-Tracks: {summary['audio_tracks']} | "
            f"Gesamt-Eintraege: {summary['total_entries']} | "
            f"Geschaetzte Dauer: {summary['estimated_duration']:.1f}s"
        )

    def _start_export(self):
        summary = get_timeline_summary()
        if summary["total_entries"] == 0:
            self.export_log.append("[Fehler] Keine Clips auf der Timeline!")
            return

        output_name = self.export_name_input.text().strip() or "output.mp4"
        if not output_name.endswith(".mp4"):
            output_name += ".mp4"

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Exportiere...")
        self.export_progress.setVisible(True)
        self.export_progress.setRange(0, 0)
        self.export_log.append(f"[Export] Starte Export: {output_name}")

        thread = QThread()
        worker = ExportWorker(project_id=1, output_name=output_name)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_export_progress)
        worker.finished.connect(self._on_export_finished)
        worker.error.connect(self._on_export_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_worker(thread, worker))

        self._active_threads.append(thread)
        self._active_workers.append(worker)
        thread.start()

    def _on_export_progress(self, step: int, total: int, message: str):
        self.export_progress.setRange(0, total)
        self.export_progress.setValue(step)
        self.export_log.append(f"[Export] {message} ({step}/{total})")

    def _on_export_finished(self, output_path: str):
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Video exportieren")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[Export] FERTIG: {output_path}")
        self.console_text.append(f"[Export] Video exportiert: {output_path}")
        self.status_bar.showMessage(f"Export fertig: {output_path}")

    def _on_export_error(self, error_msg: str):
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Video exportieren")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[FEHLER] Export fehlgeschlagen: {error_msg}")
        self.console_text.append(f"[Fehler] Export: {error_msg}")

    # ── Tabelle ───────────────────────────────────────────────────────

    def _refresh_media_table(self):
        media = get_all_media()
        self.media_table.setRowCount(len(media))
        for row, item in enumerate(media):
            self.media_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.media_table.setItem(row, 1, QTableWidgetItem(item["type"]))
            self.media_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.media_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            res = item.get("resolution", "-")
            self.media_table.setItem(row, 4, QTableWidgetItem(res or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.media_table.setItem(row, 5, QTableWidgetItem(fps_str))
            self.media_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

    # ── System-Konsole ────────────────────────────────────────────────

    def setup_console(self):
        dock = QDockWidget("System-Konsole", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.append("[System] PB_studio Core Engine erfolgreich gestartet.")

        dock.setWidget(self.console_text)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)


def main():
    init_db()
    app = QApplication(sys.argv)

    # Dark Steel Stylesheet laden
    qss_path = STYLE_DIR / "dark_steel.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = PBWindow()
    window.console_text.append("[System] SQLite Datenbank (pb_studio.db) erfolgreich initialisiert.")
    window.console_text.append(f"[System] Dark Steel Theme geladen.")
    window.timeline_view.load_from_db()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
