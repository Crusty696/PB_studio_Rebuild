"""MEDIA Workspace: Import, analyze, manage audio and video files.

Flip-switch design — VIDEO MODUS and AUDIO MODUS as two exclusive pages.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QProgressBar, QTableWidget, QHeaderView,
    QSplitter, QStackedWidget,
)
from PySide6.QtCore import Qt

from services.stem_player import StemPlayer

_MODE_BTN_STYLE = """
    QPushButton {
        font-size: 14px;
        font-weight: 700;
        padding: 8px 16px;
        border: 2px solid #333333;
        border-radius: 6px;
        background: #1A1A1A;
        color: #808080;
    }
    QPushButton:checked {
        border: 2px solid #D4AF37;
        color: #FFFFFF;
        background: #2A2A2A;
    }
    QPushButton:hover {
        background: #252525;
    }
"""


class MediaWorkspace(QWidget):
    """Media workspace — import, pool tables, analysis, search.

    All buttons/widgets are stored as attributes for PBWindow signal wiring.
    StemPlayer is created here because it must exist before the STEMS workspace.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
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

        # Analyse
        grp = QGroupBox("Analyse")
        gl = QVBoxLayout(grp)

        self.btn_analyze_video = QPushButton("Video analysieren")
        self.btn_analyze_video.setObjectName("btn_action")
        self.btn_analyze_video.setFixedHeight(35)
        self.btn_analyze_video.setMaximumWidth(300)
        self.btn_analyze_video.setToolTip("Aufloesung, FPS, Codec + Proxy erstellen")
        gl.addWidget(self.btn_analyze_video)

        self.btn_video_pipeline = QPushButton("Video-Pipeline (Szenen + KI)")
        self.btn_video_pipeline.setToolTip(
            "Vollstaendige 3-Schritt Pipeline:\n"
            "1. Szenen-Erkennung + Motion-Analyse\n"
            "2. Keyframe-Extraktion\n"
            "3. SigLIP Embeddings -> LanceDB"
        )
        self.btn_video_pipeline.setObjectName("btn_ai")
        self.btn_video_pipeline.setFixedHeight(35)
        self.btn_video_pipeline.setMaximumWidth(300)
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
            "color: #909090; font-weight: 700; font-size: 9px; padding: 2px 6px; "
            "background: #1A1A1A; border: 1px solid #333333; border-radius: 3px;"
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
            "color: #B0B0B0; font-weight: 700; font-size: 11px; "
            "padding: 2px 4px; background: #0E0E0E;"
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
        vh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        vh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
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
        self.btn_analyze.setFixedHeight(35)
        self.btn_analyze.setMaximumWidth(300)
        self.btn_analyze.setToolTip("BPM, Beats und Energie-Verlauf erkennen")
        gl.addWidget(self.btn_analyze)

        self.btn_waveform = QPushButton("Rekordbox Wellenform")
        self.btn_waveform.setToolTip(
            "Frequenz-Wellenform (Low/Mid/High) + Beatgrid berechnen"
        )
        self.btn_waveform.setObjectName("btn_ai")
        self.btn_waveform.setFixedHeight(35)
        self.btn_waveform.setMaximumWidth(300)
        gl.addWidget(self.btn_waveform)
        gl.addStretch()
        ll.addWidget(grp)

        # KI-Werkzeuge
        grp = QGroupBox("KI-Werkzeuge")
        gl = QVBoxLayout(grp)

        self.btn_stem_separate = QPushButton("KI Stem Separation")
        self.btn_stem_separate.setObjectName("btn_ai")
        self.btn_stem_separate.setFixedHeight(35)
        self.btn_stem_separate.setMaximumWidth(300)
        self.btn_stem_separate.setToolTip(
            "Demucs: Vocals, Drums, Bass, Other trennen"
        )
        gl.addWidget(self.btn_stem_separate)

        self.btn_auto_duck = QPushButton("Auto-Ducking")
        self.btn_auto_duck.setObjectName("btn_ai")
        self.btn_auto_duck.setFixedHeight(35)
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
            "color: #D4AF37; font-weight: 700; font-size: 11px; "
            "padding: 2px 4px; background: #0E0E0E;"
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
        ah.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        ah.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        rl.addWidget(self.audio_pool_table)

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
