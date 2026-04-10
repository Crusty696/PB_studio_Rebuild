"""MEDIA Workspace: Import, analyze, manage audio and video files.

Flip-switch design — VIDEO MODUS and AUDIO MODUS as two exclusive pages.
"""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QProgressBar, QTableView, QHeaderView,
    QSplitter, QStackedWidget, QFrame, QSizePolicy, QTableWidget,
)
from PySide6.QtCore import Qt, QRect, QMimeData, QItemSelectionModel
from PySide6.QtGui import QPainter, QColor, QDrag

from services.stem_player import StemPlayer
from ui.widgets.media_grid import MediaPoolGrid
from ui.widgets.analysis_status_panel import AnalysisStatusPanel
from ui.models.media_table_model import MediaTableModel

# MIME type for internal clip drag & drop
CLIP_MIME_TYPE = "application/x-pb-studio-clip"


class DraggablePoolView(QTableView):
    """QTableView that supports drag-start for Timeline Drag & Drop (Fix F-006)."""

    def __init__(self, track_type: str, parent=None):
        super().__init__(parent)
        self._track_type = track_type  # "audio" or "video"
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTableView.DragDropMode.DragOnly)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)

    def startDrag(self, supportedActions):
        indexes = self.selectionModel().selectedRows()
        if not indexes:
            return
        
        # Wir nehmen das erste selektierte Item für das Drag-Objekt
        index = indexes[0]
        model = self.model()
        
        # ID ist in Spalte 1, Titel in Spalte 2 (laut MediaTableModel)
        id_val = model.index(index.row(), 1).data()
        title_val = model.index(index.row(), 2).data()

        if id_val is None:
            return

        payload = {
            "track_type": self._track_type,
            "media_id": int(id_val),
            "title": str(title_val),
        }

        mime = QMimeData()
        mime.setData(CLIP_MIME_TYPE, json.dumps(payload).encode("utf-8"))
        mime.setText(payload["title"])

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

_MODE_BTN_STYLE = """
    QPushButton {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 8px 24px;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        background: #1e2632;
        color: #9ca3af;
    }
    QPushButton:checked {
        border: 1px solid #d4a44a;
        color: #f0c866;
        background: rgba(212, 164, 74, 0.12);
    }
    QPushButton:hover:!checked {
        background: #283040;
        color: #f9fafb;
    }
"""


_VIEW_TOGGLE_STYLE = """
    QPushButton {
        font-size: 13px;
        background: #1a2030;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 4px;
        color: #6b7280;
    }
    QPushButton:checked {
        background: rgba(212,164,74,0.15);
        border: 1px solid #d4a44a;
        color: #f0c866;
    }
    QPushButton:hover:!checked {
        background: #222d40;
        color: #e5e7eb;
    }
"""

_CARD_STYLE = """
    QFrame {
        background: #161c26;
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
        padding: 10px;
    }
"""

_CARD_TITLE_STYLE = (
    "color: #d4a44a; font-weight: 700; font-size: 10px; "
    "letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px;"
)
_CARD_VALUE_STYLE = (
    "color: #f9fafb; font-size: 20px; font-weight: 800;"
)
_CARD_LABEL_STYLE = (
    "color: #6b7280; font-size: 10px; font-weight: 500;"
)
_CARD_TAG_BASE = (
    "font-size: 9px; font-weight: 600; padding: 2px 6px; "
    "border-radius: 3px;"
)

_SEGMENT_COLORS = {
    "INTRO": "#4ade80",
    "BUILDUP": "#d4a44a",
    "DROP": "#ef4444",
    "BREAKDOWN": "#00e5ff",
    "OUTRO": "#bf40ff",
    "VERSE": "#60a5fa",
    "CHORUS": "#f97316",
    "BRIDGE": "#a78bfa",
}


class StructureBarWidget(QWidget):
    """Horizontal bar that paints colored segments for audio structure."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = []  # list of (label, start_pct, end_pct)
        self.setFixedHeight(32)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: #0a0d12; border-radius: 4px;")

    def set_segments(self, segments):
        """Set segments as list of (label, start_pct, end_pct) with 0..1 range."""
        self._segments = segments or []
        self.update()

    def paintEvent(self, event):
        if not self._segments:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        for label, start, end in self._segments:
            color = QColor(_SEGMENT_COLORS.get(label.upper(), "#555555"))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            x0 = int(start * w)
            x1 = int(end * w)
            p.drawRoundedRect(QRect(x0, 2, max(x1 - x0, 2), h - 4), 3, 3)
            # Draw label text
            p.setPen(QColor("#000000"))
            text_rect = QRect(x0 + 2, 0, x1 - x0 - 4, h)
            if x1 - x0 > 40:
                p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
        p.end()


class MediaWorkspace(QWidget):
    """Media workspace — import, pool tables, analysis, search.

    All buttons/widgets are stored as attributes for PBWindow signal wiring.
    StemPlayer is created here because it must exist before the STEMS workspace.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_ui()

    # ── public helpers ────────────────────────────────────────
    def switch_to_video(self):
        self.btn_mode_video.setChecked(True)

    def switch_to_audio(self):
        self.btn_mode_audio.setChecked(True)

    # ── UI construction ───────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)

        # ── Mode Toggle Bar ──────────────────────────────────
        mode_bar = QHBoxLayout()
        mode_bar.setContentsMargins(0, 0, 0, 4)
        mode_bar.setSpacing(8)

        self.btn_mode_video = QPushButton("\U0001f3ac  VIDEO MODUS")
        self.btn_mode_video.setCheckable(True)
        self.btn_mode_video.setAutoExclusive(True)
        self.btn_mode_video.setChecked(True)
        self.btn_mode_video.setFixedHeight(42)
        self.btn_mode_video.setStyleSheet(_MODE_BTN_STYLE)
        self.btn_mode_video.setAccessibleName("Video Modus")
        self.btn_mode_video.setStatusTip("Wechselt in den Video-Modus: Video-Pool und Analyse-Pipeline")

        self.btn_mode_audio = QPushButton("\U0001f3b5  AUDIO MODUS")
        self.btn_mode_audio.setCheckable(True)
        self.btn_mode_audio.setAutoExclusive(True)
        self.btn_mode_audio.setFixedHeight(42)
        self.btn_mode_audio.setStyleSheet(_MODE_BTN_STYLE)
        self.btn_mode_audio.setAccessibleName("Audio Modus")
        self.btn_mode_audio.setStatusTip("Wechselt in den Audio-Modus: Audio-Pool und Stem-Analyse")

        mode_bar.addWidget(self.btn_mode_video, stretch=1)
        mode_bar.addWidget(self.btn_mode_audio, stretch=1)
        layout.addLayout(mode_bar)

        # ── Stacked Widget ───────────────────────────────────
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_video_page())   # index 0
        self.mode_stack.addWidget(self._build_audio_page())   # index 1
        layout.addWidget(self.mode_stack, stretch=1)

        # ── Shared Bottom Bar (always visible) ───────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)
        bottom_bar.setSpacing(8)

        self.btn_add_to_timeline = QPushButton("Zur Timeline hinzufuegen")
        self.btn_add_to_timeline.setObjectName("btn_accent")
        self.btn_add_to_timeline.setFixedHeight(35)
        self.btn_add_to_timeline.setMaximumWidth(300)
        self.btn_add_to_timeline.setToolTip("Markierte Datei auf Timeline legen")
        self.btn_add_to_timeline.setAccessibleName("Zur Timeline hinzufuegen")
        self.btn_add_to_timeline.setStatusTip("Markierte Datei auf die Edit-Timeline legen")
        bottom_bar.addWidget(self.btn_add_to_timeline)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Analyse laeuft...")
        self.progress_bar.setToolTip(
            "Zeigt den Fortschritt der aktuellen Hintergrund-Analyse an"
        )
        bottom_bar.addWidget(self.progress_bar, stretch=1)

        layout.addLayout(bottom_bar)

        # ── Non-visual widgets ───────────────────────────────
        self.stem_player = StemPlayer(self)

        # Legacy media_table (hidden proxy for selection-based functions)
        self.media_table = QTableWidget()
        self.media_table.setColumnCount(8)
        self.media_table.setHorizontalHeaderLabels(
            ["ID", "Typ", "Titel", "BPM", "Aufloesung", "FPS", "Stems", "Dateipfad"]
        )
        self.media_table.setVisible(False)

        # ── Connect mode toggle ──────────────────────────────
        self.btn_mode_video.toggled.connect(self._on_mode_toggled)
        self.btn_mode_audio.toggled.connect(lambda checked: self.mode_stack.setCurrentIndex(1 if checked else 0))

    # ── VIDEO PAGE ────────────────────────────────────────────
    def _build_video_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel — video actions
        left = QWidget()
        left.setMaximumWidth(260)
        left.setMinimumWidth(180)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.setSpacing(4)

        # Import
        grp = QGroupBox("Import")
        gl = QVBoxLayout(grp)

        self.btn_import_video = QPushButton("Video importieren")
        self.btn_import_video.setObjectName("btn_action")
        self.btn_import_video.setFixedHeight(35)
        self.btn_import_video.setMaximumWidth(300)
        self.btn_import_video.setToolTip(
            "Video-Dateien (MP4, MOV, AVI, MKV) importieren"
        )
        self.btn_import_video.setAccessibleName("Video importieren")
        self.btn_import_video.setStatusTip("Video-Dateien (MP4, MOV, AVI, MKV) in den Video-Pool importieren")
        gl.addWidget(self.btn_import_video)

        self.btn_import_folder = QPushButton("Ordner importieren")
        self.btn_import_folder.setObjectName("btn_action")
        self.btn_import_folder.setFixedHeight(35)
        self.btn_import_folder.setMaximumWidth(300)
        self.btn_import_folder.setToolTip(
            "Alle Audio- und Video-Dateien aus einem Ordner importieren"
        )
        self.btn_import_folder.setAccessibleName("Ordner importieren")
        self.btn_import_folder.setStatusTip("Alle Audio- und Video-Dateien aus einem Ordner importieren")
        gl.addWidget(self.btn_import_folder)
        gl.addStretch()
        ll.addWidget(grp)

        # Analyse-Pipeline
        grp = QGroupBox("Analyse-Pipeline")
        gl = QVBoxLayout(grp)

        self.btn_analyze_video = QPushButton("Szenen-Erkennung")
        self.btn_analyze_video.setObjectName("btn_action")
        self.btn_analyze_video.setFixedHeight(32)
        self.btn_analyze_video.setMaximumWidth(300)
        self.btn_analyze_video.setToolTip(
            "Szenen-Schnitte und Shot-Boundaries erkennen"
        )
        self.btn_analyze_video.setAccessibleName("Szenen-Erkennung starten")
        self.btn_analyze_video.setStatusTip("Erkennt Szenen-Schnitte und Shot-Boundaries im ausgewaehlten Video")
        gl.addWidget(self.btn_analyze_video)

        self.btn_motion_analysis = QPushButton("Video analysieren")
        self.btn_motion_analysis.setObjectName("btn_action")
        self.btn_motion_analysis.setFixedHeight(32)
        self.btn_motion_analysis.setMaximumWidth(300)
        self.btn_motion_analysis.setToolTip(
            "Startet die Video-Analyse (Metadaten + Proxy)"
        )
        self.btn_motion_analysis.setAccessibleName("Video analysieren")
        self.btn_motion_analysis.setStatusTip("Startet die Video-Analyse: Metadaten extrahieren und Proxy erstellen")
        gl.addWidget(self.btn_motion_analysis)

        self.btn_siglip_embeddings = QPushButton("Voll-Pipeline")
        self.btn_siglip_embeddings.setObjectName("btn_ai")
        self.btn_siglip_embeddings.setFixedHeight(32)
        self.btn_siglip_embeddings.setMaximumWidth(300)
        self.btn_siglip_embeddings.setToolTip(
            "Startet die komplette Pipeline (Szenen + Motion + Embeddings)"
        )
        self.btn_siglip_embeddings.setAccessibleName("KI-Vollanalyse starten")
        self.btn_siglip_embeddings.setStatusTip("Startet die komplette KI-Pipeline: Szenen, Motion und SigLIP-Embeddings")
        gl.addWidget(self.btn_siglip_embeddings)

        self.btn_video_pipeline = QPushButton("Voll-Pipeline (Szenen + KI)")
        self.btn_video_pipeline.setToolTip(
            "Vollstaendige 3-Schritt Pipeline:\n"
            "1. Szenen-Erkennung + Motion-Analyse\n"
            "2. Keyframe-Extraktion\n"
            "3. SigLIP Embeddings -> VectorDB"
        )
        self.btn_video_pipeline.setObjectName("btn_ai")
        self.btn_video_pipeline.setFixedHeight(32)
        self.btn_video_pipeline.setMaximumWidth(300)
        self.btn_video_pipeline.setStyleSheet(
            "QPushButton { border: 1px solid #d4a44a; }"
        )
        self.btn_video_pipeline.setAccessibleName("Vollstaendige Video-Pipeline starten")
        self.btn_video_pipeline.setStatusTip("Vollstaendige 3-Schritt Pipeline: Szenen, Keyframes und SigLIP-Embeddings")
        gl.addWidget(self.btn_video_pipeline)
        gl.addStretch()
        ll.addWidget(grp)

        # Verwaltung
        grp = QGroupBox("Verwaltung")
        gl = QVBoxLayout(grp)

        self.btn_clear_all = QPushButton("Sammlung bereinigen")
        self.btn_clear_all.setToolTip(
            "Alle Medien aus Datenbank und Ansicht entfernen"
        )
        self.btn_clear_all.setObjectName("btn_danger")
        self.btn_clear_all.setFixedHeight(35)
        self.btn_clear_all.setMaximumWidth(300)
        self.btn_clear_all.setAccessibleName("Mediensammlung loeschen")
        self.btn_clear_all.setStatusTip("Alle Medien aus der Datenbank und Ansicht entfernen")
        gl.addWidget(self.btn_clear_all)
        gl.addStretch()
        ll.addWidget(grp)

        ll.addStretch()
        splitter.addWidget(left)

        # Right panel — SigLIP search + video pool table
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        # Semantic search bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(4)

        lbl = QLabel("SigLIP")
        lbl.setStyleSheet(
            "color: #9ca3af; font-weight: 700; font-size: 9px; padding: 2px 6px; "
            "background: #0f1318; border: 1px solid rgba(255,255,255,15); border-radius: 3px;"
        )
        lbl.setFixedWidth(46)
        search_row.addWidget(lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Semantische Suche: z.B. 'person dancing on stage'..."
        )
        self.search_input.setToolTip("SigLIP Text-zu-Video Suche")
        self.search_input.setAccessibleName("Semantische Suche Eingabe")
        self.search_input.setStatusTip("Texteingabe fuer SigLIP-basierte semantische Video-Suche")
        search_row.addWidget(self.search_input, stretch=1)

        self.btn_search = QPushButton("Suchen")
        self.btn_search.setFixedWidth(80)
        self.btn_search.setToolTip("Semantische Suche starten (SigLIP + VectorDB)")
        self.btn_search.setAccessibleName("Semantische Suche starten")
        self.btn_search.setStatusTip("Startet die semantische Video-Suche per SigLIP-Embeddings")
        search_row.addWidget(self.btn_search)

        self.btn_search_clear = QPushButton("X")
        self.btn_search_clear.setFixedSize(35, 35)
        self.btn_search_clear.setObjectName("btn_danger")
        self.btn_search_clear.setToolTip("Suche zuruecksetzen")
        self.btn_search_clear.setAccessibleName("Suche zuruecksetzen")
        self.btn_search_clear.setStatusTip("Sucheingabe und Ergebnisse zuruecksetzen")
        search_row.addWidget(self.btn_search_clear)
        rl.addLayout(search_row)

        # Video pool header
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(4)
        hdr = QLabel("VIDEO POOL")
        hdr.setStyleSheet(
            "color: #d4a44a; font-weight: 700; font-size: 11px; "
            "padding: 2px 4px; background: #0a0d12;"
        )
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        self.btn_select_all_video = QPushButton("Alle")
        self.btn_select_all_video.setObjectName("btn_select_toggle")
        self.btn_select_all_video.setFixedSize(50, 22)
        self.btn_select_all_video.setToolTip("Alle Video-Checkboxen an-/abwaehlen")
        self.btn_select_all_video.setAccessibleName("Alle Videos auswaehlen")
        hdr_row.addWidget(self.btn_select_all_video)
        # List / Grid view toggle
        self.btn_video_list_view = QPushButton("☰")
        self.btn_video_list_view.setCheckable(True)
        self.btn_video_list_view.setChecked(True)
        self.btn_video_list_view.setFixedSize(26, 22)
        self.btn_video_list_view.setToolTip("Listen-Ansicht")
        self.btn_video_list_view.setAccessibleName("Listen-Ansicht")
        self.btn_video_list_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        hdr_row.addWidget(self.btn_video_list_view)
        self.btn_video_grid_view = QPushButton("⊞")
        self.btn_video_grid_view.setCheckable(True)
        self.btn_video_grid_view.setFixedSize(26, 22)
        self.btn_video_grid_view.setToolTip("Kachel-Ansicht mit Thumbnails")
        self.btn_video_grid_view.setAccessibleName("Kachel-Ansicht")
        self.btn_video_grid_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        hdr_row.addWidget(self.btn_video_grid_view)
        rl.addLayout(hdr_row)

        # Video pool table (Fix F-006: Model/View)
        self.video_pool_model = MediaTableModel(media_type="Video")
        self.video_pool_table = DraggablePoolView(track_type="video")
        self.video_pool_table.setModel(self.video_pool_model)
        
        vh = self.video_pool_table.horizontalHeader()
        vh.setStretchLastSection(True)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        vh.resizeSection(0, 45)   # Auswahl
        vh.resizeSection(1, 35)   # ID
        vh.resizeSection(2, 200)  # Titel
        vh.resizeSection(3, 80)   # Aufloesung
        vh.resizeSection(4, 50)   # FPS
        vh.resizeSection(5, 60)   # Codec
        # Spalte 6 (Dateipfad) stretcht automatisch

        # Grid view for video pool
        self.video_grid = MediaPoolGrid(media_type="video")

        # Stack: index 0 = list, index 1 = grid
        self._video_pool_stack = QStackedWidget()
        self._video_pool_stack.addWidget(self.video_pool_table)
        self._video_pool_stack.addWidget(self.video_grid)

        # Create vertical splitter for pool + analysis status
        pool_analysis_splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: Pool table/grid
        pool_container = QWidget()
        pool_layout = QVBoxLayout(pool_container)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        pool_layout.setSpacing(4)
        pool_layout.addWidget(self._video_pool_stack)

        # Delete row
        del_row = QHBoxLayout()
        del_row.setContentsMargins(0, 4, 0, 0)
        self.btn_delete_selected_video = QPushButton(
            "Ausgewaehlte Videos loeschen"
        )
        self.btn_delete_selected_video.setObjectName("btn_danger")
        self.btn_delete_selected_video.setFixedHeight(35)
        self.btn_delete_selected_video.setMaximumWidth(300)
        self.btn_delete_selected_video.setToolTip(
            "Alle angehakten Videos aus der Datenbank entfernen"
        )
        self.btn_delete_selected_video.setAccessibleName("Ausgewaehlte Videos loeschen")
        self.btn_delete_selected_video.setStatusTip("Alle per Checkbox markierten Videos aus der Datenbank loeschen")
        del_row.addWidget(self.btn_delete_selected_video)
        del_row.addStretch()
        pool_layout.addLayout(del_row)

        pool_analysis_splitter.addWidget(pool_container)

        # Bottom: Analysis Status Panel
        self.video_analysis_panel = AnalysisStatusPanel()
        pool_analysis_splitter.addWidget(self.video_analysis_panel)

        # Set initial splitter sizes (70% pool, 30% analysis)
        pool_analysis_splitter.setStretchFactor(0, 7)
        pool_analysis_splitter.setStretchFactor(1, 3)
        pool_analysis_splitter.setSizes([600, 300])
        pool_analysis_splitter.setCollapsible(0, False)
        pool_analysis_splitter.setCollapsible(1, True)

        rl.addWidget(pool_analysis_splitter)

        # Wire toggle buttons (exclusive, manual)
        self.btn_video_list_view.clicked.connect(
            lambda: self._toggle_video_view(0)
        )
        self.btn_video_grid_view.clicked.connect(
            lambda: self._toggle_video_view(1)
        )

        # Wire selection changes to update analysis panel
        self.video_pool_table.selectionModel().selectionChanged.connect(
            self._on_video_selection_changed
        )

        # Wire analysis_requested signal to dispatch workers
        self.video_analysis_panel.analysis_requested.connect(
            self._on_analysis_requested
        )

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 6)
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)
        splitter.setSizes([220, 1200])

        page_layout.addWidget(splitter)
        return page

    # ── AUDIO PAGE ────────────────────────────────────────────
    def _build_audio_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel — audio actions
        left = QWidget()
        left.setMaximumWidth(260)
        left.setMinimumWidth(180)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.setSpacing(4)

        # Import
        grp = QGroupBox("Import")
        gl = QVBoxLayout(grp)

        self.btn_import_audio = QPushButton("Audio importieren")
        self.btn_import_audio.setObjectName("btn_action")
        self.btn_import_audio.setFixedHeight(35)
        self.btn_import_audio.setMaximumWidth(300)
        self.btn_import_audio.setToolTip(
            "Audio-Dateien (WAV, MP3, FLAC, OGG) importieren"
        )
        self.btn_import_audio.setAccessibleName("Audio importieren")
        self.btn_import_audio.setStatusTip("Audio-Dateien (WAV, MP3, FLAC, OGG) in den Audio-Pool importieren")
        gl.addWidget(self.btn_import_audio)

        # Folder import on audio page — forwards to the primary btn_import_folder
        self._btn_import_folder_audio = QPushButton("Ordner importieren")
        self._btn_import_folder_audio.setObjectName("btn_action")
        self._btn_import_folder_audio.setFixedHeight(35)
        self._btn_import_folder_audio.setMaximumWidth(300)
        self._btn_import_folder_audio.setToolTip(
            "Alle Audio- und Video-Dateien aus einem Ordner importieren"
        )
        self._btn_import_folder_audio.clicked.connect(
            lambda: self.btn_import_folder.click()
        )
        gl.addWidget(self._btn_import_folder_audio)
        gl.addStretch()
        ll.addWidget(grp)

        # Analyse
        grp = QGroupBox("Analyse")
        gl = QVBoxLayout(grp)

        self.btn_analyze = QPushButton("Audio analysieren")
        self.btn_analyze.setObjectName("btn_action")
        self.btn_analyze.setFixedHeight(32)
        self.btn_analyze.setMaximumWidth(300)
        self.btn_analyze.setToolTip("BPM, Beats und Energie-Verlauf erkennen")
        self.btn_analyze.setAccessibleName("Audio analysieren")
        self.btn_analyze.setStatusTip("BPM, Beats und Energie-Verlauf des Audio-Tracks erkennen")
        gl.addWidget(self.btn_analyze)

        self.btn_waveform = QPushButton("Wellenform")
        self.btn_waveform.setToolTip(
            "Frequenz-Wellenform (Low/Mid/High) + Beatgrid berechnen"
        )
        self.btn_waveform.setObjectName("btn_action")
        self.btn_waveform.setFixedHeight(32)
        self.btn_waveform.setMaximumWidth(300)
        self.btn_waveform.setAccessibleName("Wellenform berechnen")
        self.btn_waveform.setStatusTip("Frequenz-Wellenform (Low/Mid/High) und Beatgrid berechnen")
        gl.addWidget(self.btn_waveform)

        self.btn_key_detect = QPushButton("Key erkennen")
        self.btn_key_detect.setObjectName("btn_action")
        self.btn_key_detect.setFixedHeight(32)
        self.btn_key_detect.setMaximumWidth(300)
        self.btn_key_detect.setToolTip(
            "Tonart und Camelot-Wert erkennen"
        )
        self.btn_key_detect.setAccessibleName("Tonart erkennen")
        self.btn_key_detect.setStatusTip("Musikalische Tonart und Camelot-Wert erkennen")
        gl.addWidget(self.btn_key_detect)

        self.btn_lufs_analyze = QPushButton("LUFS / Loudness")
        self.btn_lufs_analyze.setObjectName("btn_action")
        self.btn_lufs_analyze.setFixedHeight(32)
        self.btn_lufs_analyze.setMaximumWidth(300)
        self.btn_lufs_analyze.setToolTip(
            "Integrierte Lautheit (LUFS), True Peak und Dynamik messen"
        )
        self.btn_lufs_analyze.setAccessibleName("LUFS Loudness messen")
        self.btn_lufs_analyze.setStatusTip("Integrierte Lautheit (LUFS), True Peak und Dynamikbereich messen")
        gl.addWidget(self.btn_lufs_analyze)

        self.btn_structure_detect = QPushButton("Struktur erkennen")
        self.btn_structure_detect.setObjectName("btn_action")
        self.btn_structure_detect.setFixedHeight(32)
        self.btn_structure_detect.setMaximumWidth(300)
        self.btn_structure_detect.setToolTip(
            "Song-Struktur erkennen (Intro, Buildup, Drop, Breakdown, Outro)"
        )
        self.btn_structure_detect.setAccessibleName("Song-Struktur erkennen")
        self.btn_structure_detect.setStatusTip("Song-Struktur-Segmente erkennen: Intro, Buildup, Drop, Breakdown, Outro")
        gl.addWidget(self.btn_structure_detect)
        gl.addStretch()
        ll.addWidget(grp)

        # KI-Werkzeuge
        grp = QGroupBox("KI-Werkzeuge")
        gl = QVBoxLayout(grp)

        self.btn_stem_separate = QPushButton("Stems trennen")
        self.btn_stem_separate.setObjectName("btn_ai")
        self.btn_stem_separate.setFixedHeight(32)
        self.btn_stem_separate.setMaximumWidth(300)
        self.btn_stem_separate.setToolTip(
            "Demucs: Vocals, Drums, Bass, Other trennen"
        )
        self.btn_stem_separate.setAccessibleName("Stems trennen")
        self.btn_stem_separate.setStatusTip("Audio-Stems per Demucs-KI trennen: Vocals, Drums, Bass, Other")
        gl.addWidget(self.btn_stem_separate)

        self.btn_auto_duck = QPushButton("Auto-Ducking")
        self.btn_auto_duck.setObjectName("btn_ai")
        self.btn_auto_duck.setFixedHeight(32)
        self.btn_auto_duck.setMaximumWidth(300)
        self.btn_auto_duck.setToolTip(
            "Musik bei Sprache automatisch absenken"
        )
        self.btn_auto_duck.setAccessibleName("Auto-Ducking aktivieren")
        self.btn_auto_duck.setStatusTip("Musik bei erkannter Sprache automatisch per Sidechain-Ducking absenken")
        gl.addWidget(self.btn_auto_duck)

        # Komplett-Analyse: Alle Schritte sequentiell
        self.btn_analyze_all = QPushButton("KOMPLETT-ANALYSE")
        self.btn_analyze_all.setObjectName("btn_accent")
        self.btn_analyze_all.setFixedHeight(35)
        self.btn_analyze_all.setMaximumWidth(300)
        self.btn_analyze_all.setToolTip(
            "Startet alle Analysen nacheinander:\n"
            "BPM/Beats -> Wellenform -> Key -> LUFS -> Struktur -> Stems"
        )
        self.btn_analyze_all.setAccessibleName("Komplett-Analyse starten")
        self.btn_analyze_all.setStatusTip("Alle Audio-Analysen nacheinander starten: BPM, Wellenform, Key, LUFS, Struktur, Stems")
        gl.addWidget(self.btn_analyze_all)
        gl.addStretch()
        ll.addWidget(grp)

        ll.addStretch()
        splitter.addWidget(left)

        # Right panel — audio pool table
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        # Audio pool header
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(4)
        hdr = QLabel("AUDIO POOL")
        hdr.setStyleSheet(
            "color: #d4a44a; font-weight: 700; font-size: 11px; "
            "padding: 2px 4px; background: #0a0d12;"
        )
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        self.btn_select_all_audio = QPushButton("Alle")
        self.btn_select_all_audio.setObjectName("btn_select_toggle")
        self.btn_select_all_audio.setFixedSize(50, 22)
        self.btn_select_all_audio.setToolTip("Alle Audio-Checkboxen an-/abwaehlen")
        hdr_row.addWidget(self.btn_select_all_audio)
        # List / Grid view toggle
        self.btn_audio_list_view = QPushButton("☰")
        self.btn_audio_list_view.setCheckable(True)
        self.btn_audio_list_view.setChecked(True)
        self.btn_audio_list_view.setFixedSize(26, 22)
        self.btn_audio_list_view.setToolTip("Listen-Ansicht")
        self.btn_audio_list_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        hdr_row.addWidget(self.btn_audio_list_view)
        self.btn_audio_grid_view = QPushButton("⊞")
        self.btn_audio_grid_view.setCheckable(True)
        self.btn_audio_grid_view.setFixedSize(26, 22)
        self.btn_audio_grid_view.setToolTip("Kachel-Ansicht mit Wellenform")
        self.btn_audio_grid_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        hdr_row.addWidget(self.btn_audio_grid_view)
        rl.addLayout(hdr_row)

        # Audio pool table (Fix F-006: Model/View)
        self.audio_pool_model = MediaTableModel(media_type="Audio")
        self.audio_pool_table = DraggablePoolView(track_type="audio")
        self.audio_pool_table.setModel(self.audio_pool_model)
        
        ah = self.audio_pool_table.horizontalHeader()
        ah.setStretchLastSection(True)
        ah.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        ah.resizeSection(0, 45)   # Auswahl
        ah.resizeSection(1, 35)   # ID
        ah.resizeSection(2, 200)  # Titel
        ah.resizeSection(3, 55)   # BPM
        ah.resizeSection(4, 45)   # Key
        ah.resizeSection(5, 55)   # Stems
        # Spalte 6 (Dateipfad) stretcht automatisch

        # Grid view for audio pool
        self.audio_grid = MediaPoolGrid(media_type="audio")

        # Stack: index 0 = list, index 1 = grid
        self._audio_pool_stack = QStackedWidget()
        self._audio_pool_stack.addWidget(self.audio_pool_table)
        self._audio_pool_stack.addWidget(self.audio_grid)

        # Create vertical splitter for pool + analysis status
        pool_analysis_splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: Pool table/grid
        pool_container = QWidget()
        pool_layout = QVBoxLayout(pool_container)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        pool_layout.setSpacing(4)
        pool_layout.addWidget(self._audio_pool_stack, stretch=3)

        # Wire toggle buttons
        self.btn_audio_list_view.clicked.connect(
            lambda: self._toggle_audio_view(0)
        )
        self.btn_audio_grid_view.clicked.connect(
            lambda: self._toggle_audio_view(1)
        )

        # ── Audio Detail Cards ─────────────────────────────────
        self.audio_detail_container = QWidget()
        self.audio_detail_container.setVisible(False)
        detail_layout = QVBoxLayout(self.audio_detail_container)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        detail_layout.setSpacing(6)

        # Detail header
        detail_hdr = QLabel("TRACK DETAILS")
        detail_hdr.setStyleSheet(
            "color: #d4a44a; font-weight: 700; font-size: 10px; "
            "letter-spacing: 1px; padding: 2px 4px; background: #0a0d12;"
        )
        detail_layout.addWidget(detail_hdr)

        # Three info cards in a row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)

        # --- BPM Card ---
        self._card_bpm = QFrame()
        self._card_bpm.setStyleSheet(_CARD_STYLE)
        self._card_bpm.setMinimumHeight(90)
        bpm_vl = QVBoxLayout(self._card_bpm)
        bpm_vl.setContentsMargins(8, 6, 8, 6)
        bpm_vl.setSpacing(2)
        lbl = QLabel("BPM / KEY")
        lbl.setStyleSheet(_CARD_TITLE_STYLE)
        bpm_vl.addWidget(lbl)
        self._lbl_bpm_value = QLabel("--")
        self._lbl_bpm_value.setStyleSheet(_CARD_VALUE_STYLE)
        bpm_vl.addWidget(self._lbl_bpm_value)
        bpm_detail = QHBoxLayout()
        bpm_detail.setSpacing(6)
        self._lbl_beat_count = QLabel("Beats: --")
        self._lbl_beat_count.setStyleSheet(_CARD_LABEL_STYLE)
        bpm_detail.addWidget(self._lbl_beat_count)
        self._lbl_confidence = QLabel("Conf: --")
        self._lbl_confidence.setStyleSheet(_CARD_LABEL_STYLE)
        bpm_detail.addWidget(self._lbl_confidence)
        bpm_detail.addStretch()
        bpm_vl.addLayout(bpm_detail)
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self._lbl_key = QLabel("Key: --")
        self._lbl_key.setStyleSheet(
            "color: #00e5ff; font-size: 11px; font-weight: 600;"
        )
        key_row.addWidget(self._lbl_key)
        self._lbl_camelot = QLabel("")
        self._lbl_camelot.setStyleSheet(
            "color: #bf40ff; font-size: 10px; font-weight: 600; "
            "padding: 1px 4px; background: #161c26; border-radius: 3px;"
        )
        key_row.addWidget(self._lbl_camelot)
        key_row.addStretch()
        bpm_vl.addLayout(key_row)
        bpm_vl.addStretch()
        cards_row.addWidget(self._card_bpm)

        # --- Classify Card ---
        self._card_classify = QFrame()
        self._card_classify.setStyleSheet(_CARD_STYLE)
        self._card_classify.setMinimumHeight(90)
        cls_vl = QVBoxLayout(self._card_classify)
        cls_vl.setContentsMargins(8, 6, 8, 6)
        cls_vl.setSpacing(2)
        lbl = QLabel("CLASSIFY")
        lbl.setStyleSheet(_CARD_TITLE_STYLE)
        cls_vl.addWidget(lbl)
        self._lbl_mood = QLabel("Mood: --")
        self._lbl_mood.setStyleSheet(
            "color: #4ade80; font-size: 11px; font-weight: 600;"
        )
        cls_vl.addWidget(self._lbl_mood)
        self._lbl_energy = QLabel("Energy: --")
        self._lbl_energy.setStyleSheet(
            "color: #d4a44a; font-size: 11px; font-weight: 600;"
        )
        cls_vl.addWidget(self._lbl_energy)
        self._lbl_genre = QLabel("Genre: --")
        self._lbl_genre.setStyleSheet(
            "color: #00e5ff; font-size: 11px; font-weight: 600;"
        )
        cls_vl.addWidget(self._lbl_genre)
        cls_vl.addStretch()
        cards_row.addWidget(self._card_classify)

        # --- Status Card ---
        self._card_status = QFrame()
        self._card_status.setStyleSheet(_CARD_STYLE)
        self._card_status.setMinimumHeight(90)
        st_vl = QVBoxLayout(self._card_status)
        st_vl.setContentsMargins(8, 6, 8, 6)
        st_vl.setSpacing(2)
        lbl = QLabel("STATUS")
        lbl.setStyleSheet(_CARD_TITLE_STYLE)
        st_vl.addWidget(lbl)
        self._lbl_spectral = QLabel("Spectral: --")
        self._lbl_spectral.setStyleSheet(_CARD_LABEL_STYLE)
        st_vl.addWidget(self._lbl_spectral)
        self._lbl_lufs = QLabel("LUFS: --")
        self._lbl_lufs.setStyleSheet(_CARD_LABEL_STYLE)
        st_vl.addWidget(self._lbl_lufs)
        self._lbl_stems_status = QLabel("Stems: --")
        self._lbl_stems_status.setStyleSheet(_CARD_LABEL_STYLE)
        st_vl.addWidget(self._lbl_stems_status)
        self._lbl_structure_count = QLabel("Segments: --")
        self._lbl_structure_count.setStyleSheet(_CARD_LABEL_STYLE)
        st_vl.addWidget(self._lbl_structure_count)
        st_vl.addStretch()
        cards_row.addWidget(self._card_status)

        detail_layout.addLayout(cards_row)

        # ── Structure Bar ──────────────────────────────────────
        struct_hdr = QLabel("STRUCTURE")
        struct_hdr.setStyleSheet(
            "color: #6b7280; font-weight: 700; font-size: 9px; "
            "letter-spacing: 1px; padding: 2px 4px;"
        )
        detail_layout.addWidget(struct_hdr)

        self.structure_bar = StructureBarWidget()
        detail_layout.addWidget(self.structure_bar)

        pool_layout.addWidget(self.audio_detail_container)

        # Delete row
        del_row = QHBoxLayout()
        del_row.setContentsMargins(0, 4, 0, 0)
        self.btn_delete_selected_audio = QPushButton(
            "Ausgewaehlte Audios loeschen"
        )
        self.btn_delete_selected_audio.setObjectName("btn_danger")
        self.btn_delete_selected_audio.setFixedHeight(35)
        self.btn_delete_selected_audio.setMaximumWidth(300)
        self.btn_delete_selected_audio.setToolTip(
            "Alle angehakten Audio-Dateien aus der Datenbank entfernen"
        )
        del_row.addWidget(self.btn_delete_selected_audio)
        del_row.addStretch()
        pool_layout.addLayout(del_row)

        pool_analysis_splitter.addWidget(pool_container)

        # Bottom: Analysis Status Panel
        self.audio_analysis_panel = AnalysisStatusPanel()
        pool_analysis_splitter.addWidget(self.audio_analysis_panel)

        # Set initial splitter sizes (70% pool, 30% analysis)
        pool_analysis_splitter.setStretchFactor(0, 7)
        pool_analysis_splitter.setStretchFactor(1, 3)
        pool_analysis_splitter.setSizes([600, 300])
        pool_analysis_splitter.setCollapsible(0, False)
        pool_analysis_splitter.setCollapsible(1, True)

        rl.addWidget(pool_analysis_splitter)

        # Wire selection changes to update analysis panel
        self.audio_pool_table.selectionModel().selectionChanged.connect(
            self._on_audio_selection_changed
        )

        # Wire analysis_requested signal to dispatch workers
        self.audio_analysis_panel.analysis_requested.connect(
            self._on_analysis_requested
        )

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 6)
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)
        splitter.setSizes([220, 1200])

        page_layout.addWidget(splitter)
        return page

    # ── Slots ─────────────────────────────────────────────────
    def _on_mode_toggled(self, checked: bool):
        self.mode_stack.setCurrentIndex(0 if checked else 1)

    def _toggle_video_view(self, idx: int):
        """Switch video pool between list (0) and grid (1) view."""
        self._video_pool_stack.setCurrentIndex(idx)
        self.btn_video_list_view.setChecked(idx == 0)
        self.btn_video_grid_view.setChecked(idx == 1)

    def _toggle_audio_view(self, idx: int):
        """Switch audio pool between list (0) and grid (1) view."""
        self._audio_pool_stack.setCurrentIndex(idx)
        self.btn_audio_list_view.setChecked(idx == 0)
        self.btn_audio_grid_view.setChecked(idx == 1)

    def _on_video_selection_changed(self):
        """Update video analysis panel when selection changes."""
        indexes = self.video_pool_table.selectionModel().selectedRows()
        if not indexes:
            return

        # Get first selected row
        row = indexes[0].row()
        model = self.video_pool_model

        # Get video_id from column 1
        video_id_idx = model.index(row, 1)
        video_id = video_id_idx.data()

        # Get title from column 2
        title_idx = model.index(row, 2)
        title = title_idx.data()

        if video_id is not None:
            self.video_analysis_panel.set_media("video", int(video_id), str(title or ""))

    def _on_audio_selection_changed(self):
        """Update audio analysis panel when selection changes."""
        indexes = self.audio_pool_table.selectionModel().selectedRows()
        if not indexes:
            return

        # Get first selected row
        row = indexes[0].row()
        model = self.audio_pool_model

        # Get audio_id from column 1
        audio_id_idx = model.index(row, 1)
        audio_id = audio_id_idx.data()

        # Get title from column 2
        title_idx = model.index(row, 2)
        title = title_idx.data()

        if audio_id is not None:
            self.audio_analysis_panel.set_media("audio", int(audio_id), str(title or ""))

    def _on_analysis_requested(self, step_key: str):
        """Handle analysis_requested signal from AnalysisStatusPanel.

        Dispatches the appropriate worker based on step_key and current media type.
        """
        # Determine which panel sent the signal and get media info
        sender_panel = self.sender()

        if sender_panel == self.video_analysis_panel:
            media_type = "video"
            media_id = self.video_analysis_panel._media_id
            title = self.video_analysis_panel.file_info_label.text()
        elif sender_panel == self.audio_analysis_panel:
            media_type = "audio"
            media_id = self.audio_analysis_panel._media_id
            title = self.audio_analysis_panel.file_info_label.text()
        else:
            return

        if media_id is None:
            return

        # Delegate to PBWindow controllers
        # Access parent window through the workspace hierarchy
        pb_window = self.parent()
        while pb_window and not hasattr(pb_window, 'worker_dispatcher'):
            pb_window = pb_window.parent()

        if not pb_window:
            return

        # Dispatch based on step_key
        try:
            if media_type == "audio":
                self._dispatch_audio_analysis(pb_window, media_id, title, step_key)
            else:
                self._dispatch_video_analysis(pb_window, media_id, title, step_key)
        except Exception as e:
            import logging
            logging.error("Failed to dispatch analysis for %s: %s", step_key, e, exc_info=True)

    def _dispatch_audio_analysis(self, pb_window, audio_id: int, title: str, step_key: str):
        """Dispatch audio analysis worker based on step_key."""
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session as DBSession
        from services.task_manager import TaskManagerProxy
        import workers

        task_manager = TaskManagerProxy()

        # Get file_path and bpm from DB
        with DBSession(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                return
            file_path = track.file_path
            bpm = track.bpm

        # Map step_key to worker
        worker = None
        task_name = ""

        if step_key == "bpm_detection":
            task_name = f"BPM: {title}"
            task = task_manager.create_task(task_name, "BPM + Beat-Analyse")
            worker = workers.AnalysisWorker(audio_id, title)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[BPM] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[BPM] Done: {res.get('bpm', '?')} BPM, {len(res.get('beat_positions', []))} beats"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "waveform_analysis":
            task_name = f"Waveform: {title}"
            task = task_manager.create_task(task_name, "3-Band Waveform")
            worker = workers.WaveformAnalysisWorker(audio_id)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Waveform] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[Waveform] Done: {res.get('num_samples', 0)} samples"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "key_detection":
            task_name = f"Key: {title}"
            task = task_manager.create_task(task_name, "Key-Erkennung")
            worker = workers.KeyDetectionWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Key] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[Key] {res.get('key', '?')} ({res.get('camelot', '?')})"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "lufs_analysis":
            task_name = f"LUFS: {title}"
            task = task_manager.create_task(task_name, "LUFS-Analyse")
            worker = workers.LUFSAnalysisWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[LUFS] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[LUFS] {res.get('integrated', 0):.1f} dB"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "mood_genre_classify":
            task_name = f"Classify: {title}"
            task = task_manager.create_task(task_name, "Mood/Genre AI")
            worker = workers.AudioClassifyWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Classify] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[Classify] {res.get('mood', '?')} / {res.get('genre', '?')}"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "spectral_analysis":
            task_name = f"Spectral: {title}"
            task = task_manager.create_task(task_name, "8-Band Spektral")
            worker = workers.SpectralAnalysisWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Spectral] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[Spectral] Done"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "structure_detection":
            task_name = f"Structure: {title}"
            task = task_manager.create_task(task_name, "Song-Struktur")
            worker = workers.StructureDetectionWorker(audio_id, file_path, bpm=bpm)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Structure] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[Structure] {len(res.get('segments', []))} segments"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        elif step_key == "stem_separation":
            task_name = f"Stems: {title}"
            task = task_manager.create_task(task_name, "Demucs Stem Separation")
            worker = workers.StemSeparationWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Stems] {msg}"))
            worker.finished.connect(lambda tid, res: (
                pb_window._console_append(f"[Stems] {len(res.get('stems', []))} stems created"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.audio_analysis_panel.refresh(),
            ))

        if worker:
            worker.error.connect(lambda tid, err: (
                pb_window._console_append(f"[{step_key}] Error: {err}"),
                self.audio_analysis_panel.refresh(),
            ))
            pb_window.worker_dispatcher._start_worker_thread(worker)
            pb_window.console_text.append(f"[{step_key}] Starting analysis for '{title}'...")

    def _dispatch_video_analysis(self, pb_window, video_id: int, title: str, step_key: str):
        """Dispatch video analysis worker based on step_key.

        Note: Most video steps are part of the full pipeline.
        For now, we trigger the full pipeline for any video step.
        """
        from services.task_manager import TaskManagerProxy
        import workers

        task_manager = TaskManagerProxy()

        # For video, most steps are part of the full pipeline
        # Trigger the full pipeline worker
        task_name = f"Video Pipeline: {title}"
        task = task_manager.create_task(task_name, "Full Video Analysis Pipeline")

        worker = workers.VideoAnalysisPipelineWorker(video_id)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: pb_window._console_append(f"[Video] {msg}"))
        worker.finished.connect(lambda vid, res: (
            pb_window._console_append(f"[Video] Pipeline complete for {title}"),
            pb_window.media_table_controller._refresh_media_table_debounced(),
            self.video_analysis_panel.refresh(),
        ))
        worker.error.connect(lambda vid, err: (
            pb_window._console_append(f"[Video] Error: {err}"),
            self.video_analysis_panel.refresh(),
        ))

        pb_window.worker_dispatcher._start_worker_thread(worker)
        pb_window.console_text.append(f"[Video] Starting full pipeline for '{title}'...")

    # ── Audio Detail Cards ─────────────────────────────────────
    def _update_audio_detail_cards(self, audio_track):
        """Populate the detail cards + structure bar from an audio track dict/object.

        Expected keys (all optional — missing keys show '--'):
            bpm, beat_count, bpm_confidence, key, camelot,
            mood, energy, genre,
            spectral_centroid, lufs, stems_status, structure_segments
        structure_segments: list of dicts with 'label', 'start', 'end'
            where start/end are fractional (0..1) positions.
        """
        if audio_track is None:
            self.audio_detail_container.setVisible(False)
            return

        self.audio_detail_container.setVisible(True)
        get = (
            audio_track.get
            if isinstance(audio_track, dict)
            else lambda k, d=None: getattr(audio_track, k, d)
        )

        # BPM Card
        bpm = get("bpm", None)
        self._lbl_bpm_value.setText(
            f"{bpm:.1f}" if bpm else "--"
        )
        beat_count = get("beat_count", None)
        self._lbl_beat_count.setText(
            f"Beats: {beat_count}" if beat_count else "Beats: --"
        )
        conf = get("bpm_confidence", None)
        self._lbl_confidence.setText(
            f"Conf: {conf:.0%}" if conf else "Conf: --"
        )
        key = get("key", None)
        self._lbl_key.setText(f"Key: {key}" if key else "Key: --")
        camelot = get("camelot", None)
        self._lbl_camelot.setText(camelot if camelot else "")
        self._lbl_camelot.setVisible(bool(camelot))

        # Classify Card
        mood = get("mood", None)
        self._lbl_mood.setText(f"Mood: {mood}" if mood else "Mood: --")
        energy = get("energy", None)
        if energy and isinstance(energy, str) and energy.startswith("["):
            # energy_curve ist ein JSON-Array — Durchschnitt anzeigen statt rohen String
            try:
                import json as _json
                vals = _json.loads(energy)
                avg = sum(vals) / len(vals) if vals else 0
                self._lbl_energy.setText(f"Energy: {avg:.2f} avg ({len(vals)} pts)")
            except (json.JSONDecodeError, ValueError):
                self._lbl_energy.setText("Energy: vorhanden")
        elif energy:
            self._lbl_energy.setText(f"Energy: {energy}")
        else:
            self._lbl_energy.setText("Energy: --")
        genre = get("genre", None)
        self._lbl_genre.setText(
            f"Genre: {genre}" if genre else "Genre: --"
        )

        # Status Card
        spectral = get("spectral_centroid", None)
        self._lbl_spectral.setText(
            f"Spectral: {spectral:.0f} Hz" if spectral else "Spectral: --"
        )
        lufs = get("lufs", None)
        self._lbl_lufs.setText(
            f"LUFS: {lufs:.1f}" if lufs is not None else "LUFS: --"
        )
        stems = get("stems_status", None)
        self._lbl_stems_status.setText(
            f"Stems: {stems}" if stems else "Stems: --"
        )

        # Structure
        segments = get("structure_segments", None) or []
        self._lbl_structure_count.setText(
            f"Segments: {len(segments)}" if segments else "Segments: --"
        )
        bar_data = []
        for seg in segments:
            label = seg.get("label", "?") if isinstance(seg, dict) else str(seg)
            start = seg.get("start", 0) if isinstance(seg, dict) else 0
            end = seg.get("end", 0) if isinstance(seg, dict) else 0
            bar_data.append((label, start, end))
        self.structure_bar.set_segments(bar_data)
