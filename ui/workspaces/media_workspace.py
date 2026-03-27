"""MEDIA Workspace: Import, analyze, manage audio and video files.

Flip-switch design — VIDEO MODUS and AUDIO MODUS as two exclusive pages.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QProgressBar, QTableWidget, QHeaderView,
    QSplitter, QStackedWidget, QFrame, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor

from services.stem_player import StemPlayer

_MODE_BTN_STYLE = """
    QPushButton {
        font-size: 14px;
        font-weight: 700;
        padding: 8px 16px;
        border: 2px solid rgba(255,255,255,15);
        border-radius: 6px;
        background: #0f1318;
        color: #6b7280;
    }
    QPushButton:checked {
        border: 2px solid #d4a44a;
        color: #e8e6e3;
        background: #1e2632;
    }
    QPushButton:hover {
        background: #161c26;
    }
"""


_CARD_STYLE = """
    QFrame {
        background: #0f1318;
        border: 1px solid rgba(255,255,255,15);
        border-radius: 6px;
        padding: 8px;
    }
"""

_CARD_TITLE_STYLE = (
    "color: #d4a44a; font-weight: 700; font-size: 10px; "
    "letter-spacing: 1px; margin-bottom: 2px;"
)
_CARD_VALUE_STYLE = (
    "color: #ffffff; font-size: 18px; font-weight: 700;"
)
_CARD_LABEL_STYLE = (
    "color: #6b7280; font-size: 9px;"
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

        self.btn_mode_audio = QPushButton("\U0001f3b5  AUDIO MODUS")
        self.btn_mode_audio.setCheckable(True)
        self.btn_mode_audio.setAutoExclusive(True)
        self.btn_mode_audio.setFixedHeight(42)
        self.btn_mode_audio.setStyleSheet(_MODE_BTN_STYLE)

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
        gl.addWidget(self.btn_import_video)

        self.btn_import_folder = QPushButton("Ordner importieren")
        self.btn_import_folder.setObjectName("btn_action")
        self.btn_import_folder.setFixedHeight(35)
        self.btn_import_folder.setMaximumWidth(300)
        self.btn_import_folder.setToolTip(
            "Alle Audio- und Video-Dateien aus einem Ordner importieren"
        )
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
        gl.addWidget(self.btn_analyze_video)

        self.btn_motion_analysis = QPushButton("Video analysieren")
        self.btn_motion_analysis.setObjectName("btn_action")
        self.btn_motion_analysis.setFixedHeight(32)
        self.btn_motion_analysis.setMaximumWidth(300)
        self.btn_motion_analysis.setToolTip(
            "Startet die Video-Analyse (Metadaten + Proxy)"
        )
        gl.addWidget(self.btn_motion_analysis)

        self.btn_siglip_embeddings = QPushButton("Voll-Pipeline")
        self.btn_siglip_embeddings.setObjectName("btn_ai")
        self.btn_siglip_embeddings.setFixedHeight(32)
        self.btn_siglip_embeddings.setMaximumWidth(300)
        self.btn_siglip_embeddings.setToolTip(
            "Startet die komplette Pipeline (Szenen + Motion + Embeddings)"
        )
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
        search_row.addWidget(self.search_input, stretch=1)

        self.btn_search = QPushButton("Suchen")
        self.btn_search.setFixedWidth(80)
        self.btn_search.setToolTip("Semantische Suche starten (SigLIP + LanceDB)")
        search_row.addWidget(self.btn_search)

        self.btn_search_clear = QPushButton("X")
        self.btn_search_clear.setFixedSize(35, 35)
        self.btn_search_clear.setObjectName("btn_danger")
        self.btn_search_clear.setToolTip("Suche zuruecksetzen")
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
        hdr_row.addWidget(self.btn_select_all_video)
        rl.addLayout(hdr_row)

        # Video pool table
        self.video_pool_table = QTableWidget()
        self.video_pool_table.setColumnCount(7)
        self.video_pool_table.setHorizontalHeaderLabels(
            ["Auswahl", "ID", "Titel", "Aufloesung", "FPS", "Codec", "Dateipfad"]
        )
        self.video_pool_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.video_pool_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.video_pool_table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )
        self.video_pool_table.setAlternatingRowColors(True)
        self.video_pool_table.setToolTip(
            "Video Pool: Alle importierten Video-Dateien"
        )
        vh = self.video_pool_table.horizontalHeader()
        vh.setStretchLastSection(True)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        vh.resizeSection(0, 45)   # Auswahl
        vh.resizeSection(1, 35)   # ID
        vh.resizeSection(2, 200)  # Titel
        vh.resizeSection(3, 70)   # Aufloesung
        vh.resizeSection(4, 40)   # FPS
        vh.resizeSection(5, 60)   # Codec
        # Spalte 6 (Dateipfad) stretcht automatisch
        rl.addWidget(self.video_pool_table)

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
        del_row.addWidget(self.btn_delete_selected_video)
        del_row.addStretch()
        rl.addLayout(del_row)

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
        gl.addWidget(self.btn_analyze)

        self.btn_waveform = QPushButton("Wellenform")
        self.btn_waveform.setToolTip(
            "Frequenz-Wellenform (Low/Mid/High) + Beatgrid berechnen"
        )
        self.btn_waveform.setObjectName("btn_action")
        self.btn_waveform.setFixedHeight(32)
        self.btn_waveform.setMaximumWidth(300)
        gl.addWidget(self.btn_waveform)

        self.btn_key_detect = QPushButton("Key erkennen")
        self.btn_key_detect.setObjectName("btn_action")
        self.btn_key_detect.setFixedHeight(32)
        self.btn_key_detect.setMaximumWidth(300)
        self.btn_key_detect.setToolTip(
            "Tonart und Camelot-Wert erkennen"
        )
        gl.addWidget(self.btn_key_detect)

        self.btn_lufs_analyze = QPushButton("LUFS / Loudness")
        self.btn_lufs_analyze.setObjectName("btn_action")
        self.btn_lufs_analyze.setFixedHeight(32)
        self.btn_lufs_analyze.setMaximumWidth(300)
        self.btn_lufs_analyze.setToolTip(
            "Integrierte Lautheit (LUFS), True Peak und Dynamik messen"
        )
        gl.addWidget(self.btn_lufs_analyze)

        self.btn_structure_detect = QPushButton("Struktur erkennen")
        self.btn_structure_detect.setObjectName("btn_action")
        self.btn_structure_detect.setFixedHeight(32)
        self.btn_structure_detect.setMaximumWidth(300)
        self.btn_structure_detect.setToolTip(
            "Song-Struktur erkennen (Intro, Buildup, Drop, Breakdown, Outro)"
        )
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
        gl.addWidget(self.btn_stem_separate)

        self.btn_auto_duck = QPushButton("Auto-Ducking")
        self.btn_auto_duck.setObjectName("btn_ai")
        self.btn_auto_duck.setFixedHeight(32)
        self.btn_auto_duck.setMaximumWidth(300)
        self.btn_auto_duck.setToolTip(
            "Musik bei Sprache automatisch absenken"
        )
        gl.addWidget(self.btn_auto_duck)
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
        rl.addLayout(hdr_row)

        # Audio pool table
        self.audio_pool_table = QTableWidget()
        self.audio_pool_table.setColumnCount(7)
        self.audio_pool_table.setHorizontalHeaderLabels(
            ["Auswahl", "ID", "Titel", "BPM", "Key", "Stems", "Dateipfad"]
        )
        self.audio_pool_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.audio_pool_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.audio_pool_table.setAlternatingRowColors(True)
        self.audio_pool_table.setToolTip(
            "Audio Pool: Alle importierten Audio-Dateien"
        )
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
        rl.addWidget(self.audio_pool_table, stretch=3)

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

        rl.addWidget(self.audio_detail_container)

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
        rl.addLayout(del_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 6)
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)
        splitter.setSizes([220, 1200])

        page_layout.addWidget(splitter)
        return page

    # ── Slot ──────────────────────────────────────────────────
    def _on_mode_toggled(self, checked: bool):
        self.mode_stack.setCurrentIndex(0 if checked else 1)

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
        self._lbl_energy.setText(
            f"Energy: {energy}" if energy else "Energy: --"
        )
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
