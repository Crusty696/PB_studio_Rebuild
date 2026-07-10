"""MEDIA Workspace: Import, analyze, manage audio and video files.

Flip-switch design — VIDEO MODUS and AUDIO MODUS as two exclusive pages.
"""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QTableView, QHeaderView,
    QStackedWidget, QFrame, QSizePolicy, QTableWidget, QGridLayout, QTextEdit,
)
from PySide6.QtCore import Qt, QRect, QMimeData
from PySide6.QtGui import QPainter, QColor, QDrag

from services.stem_player import StemPlayer
from ui.widgets.media_grid import MediaPoolGrid
from ui.widgets.analysis_status_panel import AnalysisStatusPanel
from ui.models.media_table_model import MediaTableModel, PagedProxyModel
from ui.widgets.workflow_components import SectionTabs

# MIME type for internal clip drag & drop
CLIP_MIME_TYPE = "application/x-pb-studio-clip"


class DraggablePoolView(QTableView):
    """QTableView that supports drag-start for Timeline Drag & Drop (Fix F-006).

    Bug E (Media-Pool-Checkbox-Fix): mit setDragEnabled(True) + SelectRows
    interpretiert Qt jeden Single-Click als Selection + potentieller
    Drag-Start, und gibt den Click NICHT an die ItemIsUserCheckable-Logik
    weiter. Resultat: einzelne Checkboxen liessen sich nicht aktivieren,
    nur der "Alle"-Button (der toggle_all am Model direkt aufruft).

    Fix: mousePressEvent overriden — Click auf die Checkbox-Spalte (col 0)
    toggelt explizit die Check-State und verhindert die Drag-Initiierung
    fuer diesen Click. Andere Spalten verhalten sich unveraendert
    (Selection + Drag).
    """

    # Spalte 0 ist in MediaTableModel die "_chk"-Spalte (siehe
    # ui/models/media_table_model.py:28-32).
    _CHECKBOX_COLUMN: int = 0

    def __init__(self, track_type: str, parent=None):
        super().__init__(parent)
        self._track_type = track_type  # "audio" or "video"
        self.setDragEnabled(True)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTableView.DragDropMode.DragOnly)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)

    def mousePressEvent(self, event):  # noqa: N802 — Qt override
        """Click auf Checkbox-Spalte → toggelt; sonst Default-Verhalten.

        Wir muessen das vor super().mousePressEvent abfangen, weil sonst
        Qt's Drag-Initiation-Pfad den Click verbraucht.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.column() == self._CHECKBOX_COLUMN:
                model = self.model()
                if model is not None:
                    current = model.data(index, Qt.ItemDataRole.CheckStateRole)
                    new_state = (
                        Qt.CheckState.Unchecked
                        if current == Qt.CheckState.Checked
                        else Qt.CheckState.Checked
                    )
                    model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                    event.accept()
                    return
        super().mousePressEvent(event)

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


def _toolbar_btn(text: str, tip: str, *, danger: bool = False, width: int | None = None) -> QPushButton:
    """Kompakter 24-px Toolbar-Button (P9-C)."""
    b = QPushButton(text)
    b.setFixedHeight(24)
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setStatusTip(tip)
    if width is not None:
        b.setFixedWidth(width)
    if danger:
        b.setObjectName("btn_danger")
    else:
        b.setObjectName("btn_secondary")
    return b

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
        # Surface Book 2 Fix: Maximale Groesse begrenzen damit
        # CreateDIBSection bei vielen Medien nicht crasht
        self.setMaximumSize(3840, 2160)
        self._build_ui()

    # ── public helpers ────────────────────────────────────────
    def switch_to_video(self):
        self.btn_mode_video.setChecked(True)

    def switch_to_audio(self):
        self.btn_mode_audio.setChecked(True)

    # ── UI construction ───────────────────────────────────────
    def _build_ui(self):
        # P9-Step3a: kompakte Margins (vorher 8/8/8/4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        # B-296 Phase F: Onboarding-Banner mit Workflow-Hinweis.
        from ui.widgets.onboarding_banner import OnboardingBanner
        self.onboarding_banner = OnboardingBanner(
            banner_id="media_workspace_workflow",
            message=(
                "Schritt 2: Material analysieren. Importiere Audio + Video, "
                "wähle Tracks per Checkbox oder 'Alle', klicke 'Komplett-Analyse' "
                "oder 'Video-Pipeline'. Status pro Schritt rechts im Panel."
            ),
            parent=self,
        )
        layout.insertWidget(0, self.onboarding_banner)

        # P9-Step3a: Mode-Toggle als schmale Tab-Bar (vorher 2 Buttons à 42 px,
        # nahmen 1200×92 px Platz weg). Jetzt kompakte Tab-Bar 24 px.
        _TAB_STYLE = (
            "QPushButton { background:transparent; color:#6b7280; border:none;"
            " border-bottom:2px solid transparent; padding:2px 14px; min-height:18px;"
            " font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }"
            "QPushButton:hover { color:#9ca3af; background:rgba(255,255,255,0.03); }"
            "QPushButton:checked { color:#f0c866; border-bottom:2px solid #d4a44a;"
            " background:rgba(212,164,74,0.08); }"
        )
        mode_bar = QHBoxLayout()
        mode_bar.setContentsMargins(0, 0, 0, 0)
        mode_bar.setSpacing(0)

        self.btn_mode_video = QPushButton("VIDEO")
        self.btn_mode_video.setCheckable(True)
        self.btn_mode_video.setAutoExclusive(True)
        self.btn_mode_video.setChecked(True)
        self.btn_mode_video.setFixedHeight(22)
        self.btn_mode_video.setMinimumWidth(80)
        self.btn_mode_video.setStyleSheet(_TAB_STYLE)
        self.btn_mode_video.setAccessibleName("Video Modus")
        self.btn_mode_video.setToolTip(
            "Video-Modus: Videos importieren, Szenen erkennen, Motion/SigLIP analysieren und Clips auswaehlen."
        )
        self.btn_mode_video.setStatusTip("Wechselt in den Video-Modus: Video-Pool und Analyse-Pipeline")

        self.btn_mode_audio = QPushButton("AUDIO")
        self.btn_mode_audio.setCheckable(True)
        self.btn_mode_audio.setAutoExclusive(True)
        self.btn_mode_audio.setFixedHeight(22)
        self.btn_mode_audio.setMinimumWidth(80)
        self.btn_mode_audio.setStyleSheet(_TAB_STYLE)
        self.btn_mode_audio.setAccessibleName("Audio Modus")
        self.btn_mode_audio.setToolTip(
            "Audio-Modus: Tracks importieren, BPM/Beats, LUFS, Tonart, Struktur und Stems analysieren."
        )
        self.btn_mode_audio.setStatusTip("Wechselt in den Audio-Modus: Audio-Pool und Stem-Analyse")

        mode_bar.addWidget(self.btn_mode_video)
        mode_bar.addWidget(self.btn_mode_audio)
        mode_bar.addStretch()
        layout.addLayout(mode_bar)

        # ── Stacked Widget ───────────────────────────────────
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_video_page())   # index 0
        self.mode_stack.addWidget(self._build_audio_page())   # index 1
        layout.addWidget(self.mode_stack, stretch=1)

        # ── Shared Bottom Bar (always visible) ──── P9-Step3a kompakter
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 2, 0, 0)
        bottom_bar.setSpacing(4)

        self.btn_add_to_timeline = QPushButton("Zur Timeline hinzufuegen")
        self.btn_add_to_timeline.setObjectName("btn_accent")
        self.btn_add_to_timeline.setFixedHeight(24)
        self.btn_add_to_timeline.setMaximumWidth(220)
        self.btn_add_to_timeline.setToolTip("Markierte Datei auf Timeline legen")
        self.btn_add_to_timeline.setAccessibleName("Zur Timeline hinzufuegen")
        self.btn_add_to_timeline.setStatusTip("Markierte Datei auf die Edit-Timeline legen")
        bottom_bar.addWidget(self.btn_add_to_timeline)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Analyse laeuft...")
        self.progress_bar.setFixedHeight(20)  # P9-Step3a
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
        self.media_table.setToolTip(
            "Legacy-Medientabelle fuer interne Auswahlkompatibilitaet; sichtbar ist der Video-/Audio-Pool."
        )
        self.media_table.setVisible(False)

        # ── Connect mode toggle ──────────────────────────────
        self.btn_mode_video.toggled.connect(self._on_mode_toggled)
        self.btn_mode_audio.toggled.connect(lambda checked: self.mode_stack.setCurrentIndex(1 if checked else 0))

    def _analysis_side_panel(self, title: str, summary: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("workflow_card")
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(520)  # P3: 460 deckelte das Panel -> 64:36; 520 -> ~60:40 (Golden Ratio)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        panel.setStyleSheet(
            "QFrame#workflow_card { background:#111821; border:1px solid rgba(255,255,255,18); "
            "border-radius:8px; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        heading = QLabel(title)
        heading.setStyleSheet("color:#f9fafb; font-size:14px; font-weight:800;")
        layout.addWidget(heading)

        text = QLabel(summary)
        text.setWordWrap(True)
        text.setStyleSheet("color:#9ca3af; font-size:11px;")
        layout.addWidget(text)
        return panel

    def _configure_analysis_button(
        self,
        button: QPushButton,
        text: str,
        tooltip: str,
        *,
        primary: bool = False,
    ) -> QPushButton:
        button.setText(text)
        button.setVisible(True)
        button.setHidden(False)
        button.setFixedHeight(30)
        button.setToolTip(tooltip)
        button.setAccessibleName(text)
        button.setStatusTip(tooltip)
        if primary:
            button.setObjectName("btn_accent")
        elif button.objectName() == "btn_accent":
            button.setObjectName("btn_secondary")
        return button

    def attach_preflight_button(self, button: QPushButton) -> None:
        """Place Convert/Preflight entry inside the video analysis context."""
        if not hasattr(self, "_video_preflight_layout"):
            return
        button.setParent(self._video_preflight_panel)
        # B-525: oeffnet jetzt den modalen Ziel-Format-Dialog (Ellipsis-Konvention).
        button.setText("Videos standardisieren…")
        button.setFixedHeight(30)
        button.setVisible(True)
        button.setToolTip(
            "Was macht es? Standardisiert Videoquellen fuer Proxy, Format, FPS und Codec. "
            "Wann nutzen? Vor Analyse, wenn Clips unterschiedliche Formate haben. "
            "Voraussetzung? Mindestens ein importiertes Video. Ergebnis? Stabilere Analyse und Export-Pipeline."
        )
        self._video_preflight_layout.insertWidget(0, button)

    def attach_preflight_format(self, widget: QWidget) -> None:
        """Surface the Convert target-format selectors next to the preflight button.

        Without this, resolution/fps/format live in a ConvertWorkspace that is
        never shown, so the standardize button always ran on its defaults.
        """
        if not hasattr(self, "_video_preflight_layout"):
            return
        widget.setParent(self._video_preflight_panel)
        widget.setVisible(True)
        self._video_preflight_layout.insertWidget(0, widget)

    # ── VIDEO PAGE ────────────────────────────────────────────
    def _build_video_page(self):
        """P9-C: Sidebar entfernt — Toolbar oben, Pool im Zentrum,
        Sub-Tabs (ANALYSE / STATUS / FILTER) unten, Paginierung 16 Zeilen.
        """
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 2, 4, 2)
        page_layout.setSpacing(4)

        # -------- Model + Proxy (Paginierung) --------
        self.video_pool_model = MediaTableModel(media_type="Video")
        # UI-Ueberholung 2026-06-13 (User-Feedback "Tabelle groesser"): mehr
        # Zeilen pro Seite, damit mehr Files auf einmal sichtbar sind.
        self._video_pool_proxy = PagedProxyModel(page_size=30)
        self._video_pool_proxy.setSourceModel(self.video_pool_model)

        self.video_pool_table = DraggablePoolView(track_type="video")
        self.video_pool_table.setModel(self._video_pool_proxy)
        vh = self.video_pool_table.horizontalHeader()
        vh.setStretchLastSection(True)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        vh.resizeSection(0, 36)
        vh.resizeSection(1, 40)
        vh.resizeSection(2, 260)
        vh.resizeSection(3, 90)
        vh.resizeSection(4, 50)
        vh.resizeSection(5, 70)
        vh.resizeSection(6, 80)
        self.video_pool_table.verticalHeader().setDefaultSectionSize(26)
        self.video_pool_table.verticalHeader().setVisible(False)
        # UI-Ueberholung 2026-06-13: fixe Hoehe (448px/16 Zeilen) entfernt — die
        # Tabelle fuellt jetzt die verfuegbare Spaltenhoehe (Expanding), zeigt also
        # deutlich mehr Files auf einmal.
        self.video_pool_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.video_grid = MediaPoolGrid(media_type="video")
        self._video_pool_stack = QStackedWidget()
        self._video_pool_stack.addWidget(self.video_pool_table)
        self._video_pool_stack.addWidget(self.video_grid)
        self._video_pool_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # -------- Toolbar (Import + Aktionen + Pager + View + Select) --------
        tb = QHBoxLayout()
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(4)

        self.btn_import_video = _toolbar_btn("+ Video", "Video importieren")
        self.btn_import_folder = _toolbar_btn("+ Ordner", "Ordner importieren")
        self.btn_delete_selected_video = _toolbar_btn(
            "Loeschen", "Ausgewaehlte Videos loeschen", danger=True,
        )
        self.btn_trash = _toolbar_btn(
            "Papierkorb",
            "Soft-geloeschte Medien anzeigen, wiederherstellen oder endgueltig loeschen",
        )
        tb.addWidget(self.btn_import_video)
        tb.addWidget(self.btn_import_folder)
        tb.addWidget(self.btn_delete_selected_video)
        tb.addWidget(self.btn_trash)

        tb.addSpacing(10)
        lbl = QLabel("SigLIP")
        lbl.setStyleSheet(
            "color: #9ca3af; font-weight: 700; font-size: 9px; padding: 2px 6px; "
            "background: #0f1318; border: 1px solid rgba(255,255,255,15); border-radius: 3px;"
        )
        lbl.setFixedHeight(24)
        tb.addWidget(lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Semantische Suche: 'person dancing on stage'…")
        self.search_input.setFixedHeight(24)
        self.search_input.setToolTip(
            "Semantische Videosuche mit SigLIP-Embeddings. Beschreibe Motiv, Stimmung oder Szene in Englisch."
        )
        tb.addWidget(self.search_input, stretch=1)

        self.btn_search = _toolbar_btn("Suchen", "Semantische Suche starten")
        tb.addWidget(self.btn_search)
        self.btn_search_clear = _toolbar_btn("X", "Suche zuruecksetzen", danger=True, width=28)
        tb.addWidget(self.btn_search_clear)

        tb.addSpacing(10)
        self.btn_select_all_video = _toolbar_btn("Alle", "Alle Videos an-/abwaehlen", width=48)
        self.btn_select_all_video.setObjectName("btn_select_toggle")
        tb.addWidget(self.btn_select_all_video)

        self.btn_video_list_view = _toolbar_btn("☰", "Listen-Ansicht", width=28)
        self.btn_video_list_view.setCheckable(True)
        self.btn_video_list_view.setChecked(True)
        self.btn_video_list_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        tb.addWidget(self.btn_video_list_view)

        self.btn_video_grid_view = _toolbar_btn("⊞", "Kachel-Ansicht", width=28)
        self.btn_video_grid_view.setCheckable(True)
        self.btn_video_grid_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        tb.addWidget(self.btn_video_grid_view)

        tb.addSpacing(10)
        self.btn_video_page_prev = _toolbar_btn("◀", "Vorherige Seite", width=28)
        self.btn_video_page_next = _toolbar_btn("▶", "Naechste Seite", width=28)
        self._lbl_video_page = QLabel("Seite 1 / 1")
        self._lbl_video_page.setStyleSheet("color:#9ca3af; font-size:10px; font-weight:600;")
        self._lbl_video_page.setFixedHeight(24)
        tb.addWidget(self.btn_video_page_prev)
        tb.addWidget(self._lbl_video_page)
        tb.addWidget(self.btn_video_page_next)

        page_layout.addLayout(tb)

        # -------- Pool + context actions --------
        self._video_content_row = QHBoxLayout()
        self._video_content_row.setContentsMargins(0, 0, 0, 0)
        self._video_content_row.setSpacing(16)  # P3: mehr Luft zwischen Tabelle und Analyse-Panel

        video_pool_column = QWidget()
        video_pool_layout = QVBoxLayout(video_pool_column)
        video_pool_layout.setContentsMargins(0, 0, 0, 0)
        video_pool_layout.setSpacing(4)
        video_pool_layout.addWidget(self._video_pool_stack)
        self._video_content_row.addWidget(video_pool_column, stretch=3)
        page_layout.addLayout(self._video_content_row, stretch=1)

        # -------- Sub-Tabs (ANALYSE / STATUS / FILTER) --------
        self._video_sub_tabs = SectionTabs()
        self._video_sub_tabs.setToolTip(
            "Video-Unterbereiche: Analyse starten, Status pruefen und Pool verwalten."
        )

        # ANALYSE
        analyse = QWidget()
        alay = QHBoxLayout(analyse)
        alay.setContentsMargins(8, 6, 8, 6)
        alay.setSpacing(6)
        self.btn_analyze_video = _toolbar_btn(
            "Szenen-Erkennung", "Szenen-Schnitte und Shot-Boundaries erkennen",
        )
        # B-296/R-15: btn_motion_analysis + btn_siglip_embeddings entfernt
        # (waren Aliase auf denselben Handler _start_video_pipeline wie
        # btn_video_pipeline). btn_video_pipeline ist Primary.
        # B-296/phase-E-fix I-2: orphan video_expert_actions Wrapper entfernt;
        # btn_analyze_video direkt im Parent-Layout (war 1-element-Loop).
        self.btn_video_pipeline = _toolbar_btn(
            "Voll-Pipeline (Szenen + KI)",
            "3-Schritt Pipeline: Szenen + Keyframes + SigLIP",
        )
        self.btn_video_pipeline.setObjectName("btn_accent")
        self.btn_video_pipeline.setText("Videoanalyse starten")
        self.btn_analyze_video.setVisible(False)
        alay.addWidget(self.btn_video_pipeline)
        alay.addWidget(self.btn_analyze_video)
        alay.addStretch()
        self._video_sub_tabs.addTab(analyse, "ANALYSE")
        self._video_sub_tabs.setTabToolTip(0, "Video-Analysen fuer markierte Clips oder komplette Pipeline starten.")

        # STATUS
        self.video_analysis_panel = AnalysisStatusPanel()
        self.video_analysis_panel.setVisible(True)  # B-292

        # FILTER (Sammlungsverwaltung + Platzhalter fuer Filter)
        filt = QWidget()
        flay = QHBoxLayout(filt)
        flay.setContentsMargins(8, 6, 8, 6)
        flay.setSpacing(6)
        self.btn_clear_all = _toolbar_btn(
            "Sammlung bereinigen", "Alle Medien aus DB und Ansicht entfernen",
            danger=True,
        )
        flay.addWidget(self.btn_clear_all)
        flay.addStretch()
        self._video_sub_tabs.addTab(filt, "FILTER")
        self._video_sub_tabs.setTabToolTip(1, "Video-Pool verwalten, Auswahl loeschen und Pool-Filter nutzen.")

        self._video_sub_tabs.setVisible(False)
        self._build_video_analysis_side_panel()

        # -------- Wiring --------
        self.btn_video_list_view.clicked.connect(lambda: self._toggle_video_view(0))
        self.btn_video_grid_view.clicked.connect(lambda: self._toggle_video_view(1))
        self.video_pool_table.selectionModel().selectionChanged.connect(
            self._on_video_selection_changed,
        )
        self.video_analysis_panel.analysis_requested.connect(self._on_analysis_requested)
        self.video_grid.item_selected.connect(
            lambda mid: self._on_grid_item_selected("video", mid),
        )
        self.video_grid.show_status_requested.connect(
            lambda mid: self._on_grid_show_status("video", mid),
        )
        self.video_grid.run_all_requested.connect(
            lambda mid: self._on_grid_run_all("video", mid),
        )

        self.btn_video_page_prev.clicked.connect(self._video_pool_proxy.prev_page)
        self.btn_video_page_next.clicked.connect(self._video_pool_proxy.next_page)
        self._video_pool_proxy.pagesChanged.connect(self._refresh_video_pager)
        self._refresh_video_pager()
        return page

    def _build_video_analysis_side_panel(self) -> None:
        side = self._analysis_side_panel(
            "Video-Clips analysieren",
            "Waehle links ein Video oder mehrere Clips. Starte danach direkt hier die komplette Pipeline "
            "oder einzelne Schritte fuer Nacharbeit.",
        )
        layout = side.layout()

        self.btn_video_pipeline = self._configure_analysis_button(
            self.btn_video_pipeline,
            "Video komplett analysieren",
            "Was macht es? Fuehrt Metadaten, Szenen, Motion, Keyframes und SigLIP nacheinander aus. "
            "Wann nutzen? Standardweg fuer neue Video-Clips. Voraussetzung? Mindestens ein Video ist importiert "
            "oder links gewaehlt. Ergebnis? Clips sind fuer Suche, Matching und Auto-Schnitt vorbereitet.",
            primary=True,
        )
        layout.addWidget(self.btn_video_pipeline)

        steps = QGridLayout()
        steps.setHorizontalSpacing(6)
        steps.setVerticalSpacing(6)
        # B-296/R-15: btn_motion_analysis + btn_siglip_embeddings entfernt
        # (Aliase auf _start_video_pipeline). btn_video_pipeline (Primary) +
        # btn_analyze_video (Szenen) + btn_keyframe_string bilden Grid.
        video_steps = (
            (
                self.btn_analyze_video,
                "Szenen",
                "Was macht es? Erkennt Shot-Grenzen und Szenenwechsel. Wann nutzen? Vor Auto-Schnitt "
                "oder wenn Keyframes fehlen. Voraussetzung? Video ausgewaehlt. Ergebnis? Clips werden in "
                "sinnvolle Szenenbereiche geteilt.",
            ),
        )
        for idx, (button, text, tip) in enumerate(video_steps):
            self._configure_analysis_button(button, text, tip)
            steps.addWidget(button, idx // 2, idx % 2)

        self.btn_keyframe_string = _toolbar_btn(
            "Keyframe-String",
            "Was macht es? Erzeugt lesbare Szenen-/Motion-Strings aus analysierten Video-Clips. "
            "Wann nutzen? Nach Szenen- und Motion-Analyse. Voraussetzung? Video-Clips im Projekt. "
            "Ergebnis? Text-Kontext fuer Prompting, Debugging und Review.",
        )
        self.btn_keyframe_string.setObjectName("btn_ai")
        self.btn_keyframe_string.setFixedHeight(30)
        # B-296/phase-E-fix I-3: vorher (1,1) -> Diagonal-Loch. Jetzt (0,1)
        # -> kompakte 1x2-Reihe nach Alias-Removal.
        steps.addWidget(self.btn_keyframe_string, 0, 1)
        layout.addLayout(steps)

        self._video_preflight_panel = QFrame()
        self._video_preflight_panel.setStyleSheet(
            "background:#0f1318; border:1px solid rgba(255,255,255,14); border-radius:6px;"
        )
        self._video_preflight_layout = QVBoxLayout(self._video_preflight_panel)
        self._video_preflight_layout.setContentsMargins(8, 8, 8, 8)
        self._video_preflight_layout.setSpacing(6)
        # B-525: Frueher lag hier ein mehrzeiliges Hinweis-Label, das zusammen mit
        # dem reparenteten Standardisieren-Button + dem (inzwischen in den Dialog
        # ausgelagerten) Ziel-Format-GroupBox in der engen Spalte ueberlappte.
        # Der Hinweis ist jetzt im modalen Dialog; das Panel haelt nur noch den
        # Trigger-Button (via attach_preflight_button) -> keine Ueberlappung.
        layout.addWidget(self._video_preflight_panel)

        self.keyframe_text = QTextEdit()
        self.keyframe_text.setReadOnly(True)
        self.keyframe_text.setMaximumHeight(118)
        self.keyframe_text.setPlaceholderText("Keyframe-Strings werden hier nach der Videoanalyse angezeigt...")
        self.keyframe_text.setToolTip(
            "Was zeigt es? Ausgabe der generierten Szenen-/Motion-Strings. Wann nutzen? Nach Keyframe-String. "
            "Voraussetzung? Analysierte Video-Clips. Ergebnis? Kopierbarer Kontext fuer Review und KI-Prompts."
        )
        layout.addWidget(self.keyframe_text)

        layout.addWidget(self.video_analysis_panel, stretch=1)
        self._video_content_row.addWidget(side, stretch=2)

    # ── AUDIO PAGE ────────────────────────────────────────────
    def _build_audio_page(self):
        """P9-C: gleiches Schema wie Video-Page — Toolbar + Pool + Sub-Tabs."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 2, 4, 2)
        page_layout.setSpacing(4)

        # -------- Model + Proxy --------
        self.audio_pool_model = MediaTableModel(media_type="Audio")
        self._audio_pool_proxy = PagedProxyModel(page_size=30)  # UI-Ueberholung 2026-06-13: mehr Zeilen
        self._audio_pool_proxy.setSourceModel(self.audio_pool_model)

        self.audio_pool_table = DraggablePoolView(track_type="audio")
        self.audio_pool_table.setModel(self._audio_pool_proxy)
        ah = self.audio_pool_table.horizontalHeader()
        ah.setStretchLastSection(True)
        ah.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        ah.resizeSection(0, 36)
        ah.resizeSection(1, 40)
        ah.resizeSection(2, 260)
        ah.resizeSection(3, 60)
        ah.resizeSection(4, 50)
        ah.resizeSection(5, 60)
        ah.resizeSection(6, 80)
        self.audio_pool_table.verticalHeader().setDefaultSectionSize(26)
        self.audio_pool_table.verticalHeader().setVisible(False)
        # UI-Ueberholung 2026-06-13: fixe Hoehe raus -> Tabelle fuellt die Spalte.
        self.audio_pool_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.audio_grid = MediaPoolGrid(media_type="audio")
        self._audio_pool_stack = QStackedWidget()
        self._audio_pool_stack.addWidget(self.audio_pool_table)
        self._audio_pool_stack.addWidget(self.audio_grid)
        self._audio_pool_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # -------- Toolbar --------
        tb = QHBoxLayout()
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(4)

        self.btn_import_audio = _toolbar_btn("+ Audio", "Audio importieren")
        self._btn_import_folder_audio = _toolbar_btn(
            "+ Ordner", "Alle Audio-/Video-Dateien aus Ordner importieren",
        )
        self._btn_import_folder_audio.clicked.connect(
            lambda: self.btn_import_folder.click()
        )
        self.btn_delete_selected_audio = _toolbar_btn(
            "Loeschen", "Ausgewaehlte Audio-Dateien loeschen", danger=True,
        )
        tb.addWidget(self.btn_import_audio)
        tb.addWidget(self._btn_import_folder_audio)
        tb.addWidget(self.btn_delete_selected_audio)

        tb.addStretch()

        self.btn_select_all_audio = _toolbar_btn(
            "Alle", "Alle Audio-Checkboxen an-/abwaehlen", width=48,
        )
        self.btn_select_all_audio.setObjectName("btn_select_toggle")
        tb.addWidget(self.btn_select_all_audio)

        self.btn_audio_list_view = _toolbar_btn("☰", "Listen-Ansicht", width=28)
        self.btn_audio_list_view.setCheckable(True)
        self.btn_audio_list_view.setChecked(True)
        self.btn_audio_list_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        tb.addWidget(self.btn_audio_list_view)

        self.btn_audio_grid_view = _toolbar_btn("⊞", "Kachel-Ansicht", width=28)
        self.btn_audio_grid_view.setCheckable(True)
        self.btn_audio_grid_view.setStyleSheet(_VIEW_TOGGLE_STYLE)
        tb.addWidget(self.btn_audio_grid_view)

        tb.addSpacing(10)
        self.btn_audio_page_prev = _toolbar_btn("◀", "Vorherige Seite", width=28)
        self.btn_audio_page_next = _toolbar_btn("▶", "Naechste Seite", width=28)
        self._lbl_audio_page = QLabel("Seite 1 / 1")
        self._lbl_audio_page.setStyleSheet("color:#9ca3af; font-size:10px; font-weight:600;")
        self._lbl_audio_page.setFixedHeight(24)
        tb.addWidget(self.btn_audio_page_prev)
        tb.addWidget(self._lbl_audio_page)
        tb.addWidget(self.btn_audio_page_next)

        page_layout.addLayout(tb)
        self._audio_content_row = QHBoxLayout()
        self._audio_content_row.setContentsMargins(0, 0, 0, 0)
        self._audio_content_row.setSpacing(16)  # P3: mehr Luft zwischen Tabelle und Analyse-Panel

        self._audio_pool_column = QWidget()
        self._audio_pool_layout = QVBoxLayout(self._audio_pool_column)
        self._audio_pool_layout.setContentsMargins(0, 0, 0, 0)
        self._audio_pool_layout.setSpacing(4)
        self._audio_pool_layout.addWidget(self._audio_pool_stack)
        self._audio_content_row.addWidget(self._audio_pool_column, stretch=3)
        page_layout.addLayout(self._audio_content_row, stretch=1)

        # -------- Sub-Tabs (ANALYSE / STATUS / FILTER) --------
        self._audio_sub_tabs = SectionTabs()
        self._audio_sub_tabs.setToolTip(
            "Audio-Unterbereiche: Analyse starten, Status pruefen und Filter nutzen."
        )

        # ANALYSE
        analyse = QWidget()
        alay = QVBoxLayout(analyse)
        alay.setContentsMargins(8, 6, 8, 6)
        alay.setSpacing(4)
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        audio_expert_actions = QWidget(analyse)
        audio_expert_actions.setVisible(False)
        audio_expert_layout = QHBoxLayout(audio_expert_actions)
        audio_expert_layout.setContentsMargins(0, 0, 0, 0)
        audio_expert_layout.setSpacing(4)
        self.btn_analyze = _toolbar_btn("BPM/Beats", "BPM, Beats, Energie")
        self.btn_waveform = _toolbar_btn("Wellenform", "3-Band Wellenform + Beatgrid")
        self.btn_key_detect = _toolbar_btn("Key", "Tonart + Camelot")
        self.btn_lufs_analyze = _toolbar_btn("LUFS", "Lautheit / True Peak")
        self.btn_mood_classify = _toolbar_btn("Mood/Genre", "AI Mood/Genre Klassifikation")
        self.btn_spectral_analyze = _toolbar_btn("Spektral", "8-Band Spektral-Analyse")
        self.btn_structure_detect = _toolbar_btn("Struktur", "Intro/Buildup/Drop/...")
        self.btn_stem_separate = _toolbar_btn("Stems", "Demucs Vocals/Drums/Bass/Other")
        for b in (
            self.btn_analyze, self.btn_waveform, self.btn_key_detect,
            self.btn_lufs_analyze, self.btn_mood_classify, self.btn_spectral_analyze,
            self.btn_structure_detect, self.btn_stem_separate,
        ):
            b.setVisible(False)
            audio_expert_layout.addWidget(b)
        self.btn_auto_duck = _toolbar_btn("Auto-Ducking", "Musik bei Sprache absenken")
        self.btn_auto_duck.setVisible(False)
        audio_expert_layout.addWidget(self.btn_auto_duck)
        self.btn_analyze_all = _toolbar_btn(
            "Audioanalyse starten", "Alle noetigen Audio-Analysen nacheinander",
        )
        self.btn_analyze_all.setObjectName("btn_accent")
        row1.addWidget(self.btn_analyze_all)
        row1.addWidget(audio_expert_actions)
        row1.addStretch()
        alay.addLayout(row1)
        alay.addStretch()
        self._audio_sub_tabs.addTab(analyse, "ANALYSE")
        self._audio_sub_tabs.setTabToolTip(0, "Audio-Analysen fuer markierte Tracks starten: BPM, Stems, Struktur und Loudness.")

        # STATUS
        self.audio_analysis_panel = AnalysisStatusPanel()
        self.audio_analysis_panel.setVisible(True)  # B-292

        # FILTER
        filt = QWidget()
        flay = QHBoxLayout(filt)
        flay.setContentsMargins(8, 6, 8, 6)
        flay.setSpacing(6)
        # Shared clear-all button lives on video page; hier nur Hinweis.
        hint = QLabel("Filter/Sortierung folgen (Shared: 'Sammlung bereinigen' auf VIDEO-Tab FILTER).")
        hint.setStyleSheet("color: #6b7280; font-size: 10px;")
        flay.addWidget(hint)
        flay.addStretch()
        self._audio_sub_tabs.addTab(filt, "FILTER")
        self._audio_sub_tabs.setTabToolTip(1, "Audio-Pool nach BPM, Key, Genre und weiteren Metadaten filtern.")

        self._audio_sub_tabs.setVisible(False)

        # -------- Wiring --------
        self.btn_audio_list_view.clicked.connect(lambda: self._toggle_audio_view(0))
        self.btn_audio_grid_view.clicked.connect(lambda: self._toggle_audio_view(1))
        self.btn_audio_page_prev.clicked.connect(self._audio_pool_proxy.prev_page)
        self.btn_audio_page_next.clicked.connect(self._audio_pool_proxy.next_page)
        self._audio_pool_proxy.pagesChanged.connect(self._refresh_audio_pager)
        self._refresh_audio_pager()

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

        # P9-C: Detail-Container bleibt im Pool-Kontext unter der Auswahl.
        self._audio_pool_layout.addWidget(self.audio_detail_container)
        self._build_audio_analysis_side_panel()

        # Pool-Selektion -> Analysis Panel
        self.audio_pool_table.selectionModel().selectionChanged.connect(
            self._on_audio_selection_changed
        )
        self.audio_analysis_panel.analysis_requested.connect(
            self._on_analysis_requested
        )
        self.audio_grid.item_selected.connect(
            lambda mid: self._on_grid_item_selected("audio", mid)
        )
        self.audio_grid.show_status_requested.connect(
            lambda mid: self._on_grid_show_status("audio", mid)
        )
        self.audio_grid.run_all_requested.connect(
            lambda mid: self._on_grid_run_all("audio", mid)
        )
        return page

    def _build_audio_analysis_side_panel(self) -> None:
        side = self._analysis_side_panel(
            "Audio-Track analysieren",
            "Waehle links den Track. Starte dann hier den kompletten Analyse-Lauf oder einzelne Schritte, "
            "wenn nur ein Ergebnis fehlt.",
        )
        layout = side.layout()

        self.btn_analyze_all = self._configure_analysis_button(
            self.btn_analyze_all,
            "Audio komplett analysieren",
            "Was macht es? Fuehrt BPM/Beatgrid, Wellenform, Tonart, LUFS, Mood/Genre, Spektral-Analyse, Songstruktur und Stems "
            "in sinnvoller Reihenfolge aus. Wann nutzen? Standardweg fuer neue Tracks. Voraussetzung? "
            "Ein Audio-Track ist importiert oder links gewaehlt. Ergebnis? Audio-Daten sind fuer "
            "Pacing und Auto-Schnitt bereit.",
            primary=True,
        )
        layout.addWidget(self.btn_analyze_all)

        steps = QGridLayout()
        steps.setHorizontalSpacing(6)
        steps.setVerticalSpacing(6)
        audio_steps = (
            (
                self.btn_analyze,
                "BPM / Beatgrid",
                "Was macht es? Erkennt Tempo, Beats und Grundenergie. Wann nutzen? Immer vor Auto-Schnitt. "
                "Voraussetzung? Audio-Track gewaehlt. Ergebnis? Beat-synchroner Schnitt wird moeglich.",
            ),
            (
                self.btn_waveform,
                "Wellenform",
                "Was macht es? Erzeugt sichtbare Wellenform und Beatgrid-Anzeige. Wann nutzen? Wenn Review "
                "oder Timeline keine Audioform zeigt. Voraussetzung? Audio-Track gewaehlt. Ergebnis? Bessere "
                "visuelle Kontrolle.",
            ),
            (
                self.btn_key_detect,
                "Tonart",
                "Was macht es? Erkennt Key und Camelot-Wert. Wann nutzen? Fuer musikalische Stimmung und "
                "spaetere Matching-Regeln. Voraussetzung? Audio-Track gewaehlt. Ergebnis? Harmonische Metadaten.",
            ),
            (
                self.btn_lufs_analyze,
                "LUFS",
                "Was macht es? Misst Loudness und Peak. Wann nutzen? Vor Export oder Lautheitskontrolle. "
                "Voraussetzung? Audio-Track gewaehlt. Ergebnis? Lautheitswerte fuer Qualitaetssicherung.",
            ),
            (
                self.btn_mood_classify,
                "Mood / Genre",
                "Was macht es? Klassifiziert Musikrichtung und emotionale Stimmung. Wann nutzen? Fuer die passende Trackauswahl. "
                "Voraussetzung? Audio-Track gewaehlt. Ergebnis? Genre- und Mood-Metadaten.",
            ),
            (
                self.btn_spectral_analyze,
                "Spektralanalyse",
                "Was macht es? Analysiert die Frequenzverteilung in 8 Baendern. Wann nutzen? Fuer detaillierte Equalizer- und Mixing-Entscheidungen. "
                "Voraussetzung? Audio-Track gewaehlt. Ergebnis? 8-Band Frequenzdaten.",
            ),
            (
                self.btn_structure_detect,
                "Songstruktur",
                "Was macht es? Findet Intro, Buildup, Drop, Breakdown und Outro. Wann nutzen? Vor Auto-Schnitt. "
                "Voraussetzung? BPM/Beats vorhanden. Ergebnis? Pacing kennt Musikabschnitte.",
            ),
            (
                self.btn_stem_separate,
                "Stems",
                "Was macht es? Trennt Vocals, Drums, Bass und Other via Demucs. Wann nutzen? Fuer bessere "
                "Drop-, Vocal- und Energie-Entscheidungen. Voraussetzung? GPU/VRAM bereit. Ergebnis? Stem-Daten "
                "fuer Analyse und Mix.",
            ),
        )
        for idx, (button, text, tip) in enumerate(audio_steps):
            self._configure_analysis_button(button, text, tip)
            steps.addWidget(button, idx // 2, idx % 2)
        layout.addLayout(steps)

        layout.addWidget(self.audio_analysis_panel, stretch=1)
        self._audio_content_row.addWidget(side, stretch=2)

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
        """Update video analysis panel when selection changes.

        P9-C: nutzt das View-Model (Proxy), damit die Seiten-Indizes stimmen.
        """
        indexes = self.video_pool_table.selectionModel().selectedRows()
        if not indexes:
            return
        idx = indexes[0]
        model = self.video_pool_table.model()
        video_id = model.index(idx.row(), 1).data()
        title = model.index(idx.row(), 2).data()
        if video_id is not None:
            self.video_analysis_panel.set_media("video", int(video_id), str(title or ""))

    def _on_audio_selection_changed(self):
        """Update audio analysis panel when selection changes."""
        indexes = self.audio_pool_table.selectionModel().selectedRows()
        if not indexes:
            return
        idx = indexes[0]
        model = self.audio_pool_table.model()
        audio_id = model.index(idx.row(), 1).data()
        title = model.index(idx.row(), 2).data()
        if audio_id is not None:
            self.audio_analysis_panel.set_media("audio", int(audio_id), str(title or ""))

    # ── Pager helpers ─────────────────────────────────────────
    def _refresh_video_pager(self):
        p = self._video_pool_proxy
        self._lbl_video_page.setText(f"Seite {p.page() + 1} / {p.page_count()}")
        self.btn_video_page_prev.setEnabled(p.page() > 0)
        self.btn_video_page_next.setEnabled(p.page() < p.page_count() - 1)

    def _refresh_audio_pager(self):
        p = self._audio_pool_proxy
        self._lbl_audio_page.setText(f"Seite {p.page() + 1} / {p.page_count()}")
        self.btn_audio_page_prev.setEnabled(p.page() > 0)
        self.btn_audio_page_next.setEnabled(p.page() < p.page_count() - 1)

    # ── Grid view context menu handlers ──────────────────────────

    def _get_media_title(self, media_type: str, media_id: int) -> str:
        """Look up the title for a media_id from the loaded items."""
        grid = self.video_grid if media_type == "video" else self.audio_grid
        for item in grid._all_items:
            if item.get("id") == media_id:
                return item.get("title", f"{media_type.title()} {media_id}")
        return f"{media_type.title()} {media_id}"

    def _on_grid_item_selected(self, media_type: str, media_id: int):
        """Update analysis panel when a grid card is clicked."""
        title = self._get_media_title(media_type, media_id)
        panel = self.video_analysis_panel if media_type == "video" else self.audio_analysis_panel
        panel.set_media(media_type, media_id, title)

    def ensure_status_panel_selection(self, videos: list, audios: list) -> None:
        """B-473: Analyse-Status-Panels nie leer lassen.

        Sobald der Medien-Pool geladen ist und noch keine Datei gewaehlt wurde,
        wird automatisch die erste gesetzt. Vorher blieb das Panel dauerhaft
        auf "Keine Datei ausgewählt" stehen, bis der User von selbst eine Karte
        anklickte — das Feld wirkte funktionslos (Click-Log 2026-06-04).
        """
        import logging
        try:
            if videos and self.video_analysis_panel._media_id is None:
                v = videos[0]
                logging.info("[StatusPanel] auto-select video id=%s", v.get("id"))
                self.video_analysis_panel.set_media(
                    "video", int(v["id"]), str(v.get("title") or "")
                )
        except (AttributeError, RuntimeError, KeyError, ValueError, TypeError) as e:
            logging.debug("auto-select video status panel failed: %s", e)
        try:
            if audios and self.audio_analysis_panel._media_id is None:
                a = audios[0]
                logging.info("[StatusPanel] auto-select audio id=%s", a.get("id"))
                self.audio_analysis_panel.set_media(
                    "audio", int(a["id"]), str(a.get("title") or "")
                )
        except (AttributeError, RuntimeError, KeyError, ValueError, TypeError) as e:
            logging.debug("auto-select audio status panel failed: %s", e)

    def _on_grid_show_status(self, media_type: str, media_id: int):
        """Show analysis status panel for a grid card (context menu)."""
        title = self._get_media_title(media_type, media_id)
        panel = self.video_analysis_panel if media_type == "video" else self.audio_analysis_panel
        panel.set_media(media_type, media_id, title)
        panel.setVisible(True)

    def _on_grid_run_all(self, media_type: str, media_id: int):
        """Run all pending analyses for a media item (context menu)."""
        from services import analysis_status_service as svc

        title = self._get_media_title(media_type, media_id)
        panel = self.video_analysis_panel if media_type == "video" else self.audio_analysis_panel
        panel.set_media(media_type, media_id, title)
        panel.setVisible(True)

        # Get current status and dispatch each pending/error step
        steps = svc.VIDEO_STEPS if media_type == "video" else svc.AUDIO_STEPS
        status_map = svc.get_status(media_type, media_id)

        pb_window = self.parent()
        while pb_window and not hasattr(pb_window, 'worker_dispatcher'):
            pb_window = pb_window.parent()
        if not pb_window:
            return

        # B-111 / BUG-11-b: removed dead `dispatched` flag (was never
        # consumed) and changed silent-continue on dispatch error to
        # ``break`` so a failed first step does not compound into a
        # second registered task with broken state.
        for step_key in steps:
            entry = status_map.get(step_key)
            if entry is None or entry.status in ("pending", "error"):
                try:
                    if media_type == "audio":
                        self._dispatch_audio_analysis(pb_window, media_id, title, step_key)
                    else:
                        self._dispatch_video_analysis(pb_window, media_id, title, step_key)
                        break  # Video dispatches full pipeline in one call
                except Exception as e:
                    import logging
                    logging.error("Grid run-all dispatch error: %s", e, exc_info=True)
                    break

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
        from services.task_manager import TaskManagerProxy
        import workers

        task_manager = TaskManagerProxy()

        # B-088: NullPool + Raw-SQL statt ORM-Session(engine).get(...) im
        # Main-Thread. Vorher: ``DBSession(engine).get(AudioTrack, ...)``
        # hydrierte das volle Objekt inkl. Lazy-Load-Relationships und
        # konnte bei SQLite-WAL-busy-Lock 1-5 s blocken — UI-Freeze.
        # Wir brauchen aber nur ``file_path`` + ``bpm``: zwei Spalten,
        # ein einziger Read, NullPool damit es keinen Pool-Lock zieht.
        from database import nullpool_session
        from sqlalchemy import text as _sql_text
        with nullpool_session() as session:
            row = session.execute(
                _sql_text(
                    "SELECT file_path, bpm FROM audio_tracks "
                    "WHERE id = :id AND deleted_at IS NULL"
                ),
                {"id": audio_id},
            ).first()
            if row is None:
                return
            file_path, bpm = row[0], row[1]

        # Map step_key to worker
        worker = None
        task_name = ""

        if step_key == "bpm_detection":
            task_name = f"BPM: {title}"
            task = task_manager.create_task(task_name, "BPM + Beat-Analyse")
            worker = workers.AnalysisWorker(audio_id, title)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[BPM] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[BPM] Done: {res.get('bpm', '?')} BPM, {len(res.get('beat_positions', []))} beats"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "waveform_analysis":
            task_name = f"Waveform: {title}"
            task = task_manager.create_task(task_name, "3-Band Waveform")
            worker = workers.WaveformAnalysisWorker(audio_id)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[Waveform] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[Waveform] Done: {res.get('num_samples', 0)} samples"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "key_detection":
            task_name = f"Key: {title}"
            task = task_manager.create_task(task_name, "Key-Erkennung")
            worker = workers.KeyDetectionWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[Key] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[Key] {res.get('key', '?')} ({res.get('camelot', '?')})"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "lufs_analysis":
            task_name = f"LUFS: {title}"
            task = task_manager.create_task(task_name, "LUFS-Analyse")
            worker = workers.LUFSAnalysisWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[LUFS] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[LUFS] {res.get('integrated', 0):.1f} dB"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "mood_genre_classify":
            task_name = f"Classify: {title}"
            task = task_manager.create_task(task_name, "Mood/Genre AI")
            worker = workers.AudioClassifyWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[Classify] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[Classify] {res.get('mood', '?')} / {res.get('genre', '?')}"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "spectral_analysis":
            task_name = f"Spectral: {title}"
            task = task_manager.create_task(task_name, "8-Band Spektral")
            worker = workers.SpectralAnalysisWorker(audio_id, file_path)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[Spectral] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[Spectral] Done"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "structure_detection":
            task_name = f"Structure: {title}"
            task = task_manager.create_task(task_name, "Song-Struktur")
            worker = workers.StructureDetectionWorker(audio_id, file_path, bpm=bpm)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[Structure] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[Structure] {len(res.get('segments', []))} segments"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        elif step_key == "stem_separation":
            task_name = f"Stems: {title}"
            task = task_manager.create_task(task_name, "Demucs Stem Separation")
            worker = workers.StemSeparationWorker(audio_id)
            worker.task_id = task.task_id
            worker.progress.connect(
                lambda pct, msg: pb_window._console_append(f"[Stems] {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )
            worker.finished.connect(
                lambda tid, res: (
                    pb_window._console_append(f"[Stems] {len(res.get('stems', []))} stems created"),
                    pb_window.media_table_controller._refresh_media_table_debounced(),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )

        if worker:
            worker.error.connect(
                lambda tid, err: (
                    pb_window._console_append(f"[{step_key}] Error: {err}"),
                    self.audio_analysis_panel.refresh(),
                ),
                Qt.ConnectionType.QueuedConnection,
            )
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
        worker.progress.connect(
            lambda pct, msg: pb_window._console_append(f"[Video] {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda vid, res: (
                pb_window._console_append(f"[Video] Pipeline complete for {title}"),
                pb_window.media_table_controller._refresh_media_table_debounced(),
                self.video_analysis_panel.refresh(),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda vid, err: (
                pb_window._console_append(f"[Video] Error: {err}"),
                self.video_analysis_panel.refresh(),
            ),
            Qt.ConnectionType.QueuedConnection,
        )

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
        if energy and isinstance(energy, (list, tuple)):
            # H7-FIX: Column(JSON) liefert direkt eine Liste
            vals = energy
            avg = sum(vals) / len(vals) if vals else 0
            self._lbl_energy.setText(f"Energy: {avg:.2f} avg ({len(vals)} pts)")
        elif energy and isinstance(energy, str) and energy.startswith("["):
            # Backward-compat: alte doppelt-serialisierte Daten
            try:
                import json as _json
                vals = _json.loads(energy)
                avg = sum(vals) / len(vals) if vals else 0
                self._lbl_energy.setText(f"Energy: {avg:.2f} avg ({len(vals)} pts)")
            except (ValueError, TypeError):
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
