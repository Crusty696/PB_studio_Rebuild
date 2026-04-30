"""Workflow-oriented wrapper pages for the Director's Cockpit."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ui.widgets.workflow_components import SectionTabs, WorkflowHeader


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("title")
    return label


def _subtitle(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("subtitle")
    label.setWordWrap(True)
    return label


class ProjectDashboard(QWidget):
    """Start screen focused on project state and the next usable step."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        title_block.addWidget(_title("PB Studio Workflow"))
        title_block.addWidget(_subtitle(
            "Gefuehrter Ablauf fuer beat-synchronen Video-Schnitt: Projekt, "
            "Quellen, Analyse, Auto-Schnitt, Review, Export."
        ))
        header.addLayout(title_block, stretch=1)

        self.btn_new_project = QPushButton("+ Neues Projekt")
        self.btn_new_project.setObjectName("btn_accent")
        self.btn_new_project.setFixedHeight(34)
        self.btn_open_project = QPushButton("Projekt oeffnen")
        self.btn_open_project.setFixedHeight(34)
        header.addWidget(self.btn_new_project)
        header.addWidget(self.btn_open_project)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.status_card = self._card("Projektstatus")
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(8)
        self.project_name = QLabel("Kein Projekt geladen")
        self.project_name.setStyleSheet("font-size: 18px; font-weight: 700; color: #f9fafb;")
        self.project_path = QLabel("Lege ein Projekt an oder oeffne ein bestehendes Projekt.")
        self.project_path.setWordWrap(True)
        self.project_path.setStyleSheet("color: #9ca3af;")
        status_layout.addWidget(self.project_name)
        status_layout.addWidget(self.project_path)
        status_layout.addStretch(1)
        body.addWidget(self.status_card, stretch=2)

        self.next_card = self._card("Naechster sinnvoller Schritt")
        next_layout = QVBoxLayout(self.next_card)
        next_layout.setContentsMargins(14, 12, 14, 12)
        next_layout.setSpacing(8)
        self.next_step = QLabel("Quellen vorbereiten")
        self.next_step.setStyleSheet("font-size: 18px; font-weight: 700; color: #f0c866;")
        self.next_reason = QLabel("Importiere zuerst Audio und Video, danach werden Analyse und Auto-Schnitt freigeschaltet.")
        self.next_reason.setWordWrap(True)
        self.btn_next_step = QPushButton("Zu Quellen vorbereiten")
        self.btn_next_step.setObjectName("btn_accent")
        self.btn_next_step.setFixedHeight(34)
        next_layout.addWidget(self.next_step)
        next_layout.addWidget(self.next_reason)
        next_layout.addStretch(1)
        next_layout.addWidget(self.btn_next_step)
        body.addWidget(self.next_card, stretch=2)

        self.system_card = self._card("Systemstatus")
        system_layout = QVBoxLayout(self.system_card)
        system_layout.setContentsMargins(14, 12, 14, 12)
        system_layout.setSpacing(7)
        system_title = QLabel("Systemstatus")
        system_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f9fafb;")
        system_layout.addWidget(system_title)
        for text in (
            "GPU: beim Pipeline-Start pruefen",
            "Ollama: ueber KI-Status sichtbar",
            "FFmpeg: fuer Convert/Export erforderlich",
        ):
            label = QLabel(text)
            label.setStyleSheet("color:#9ca3af;")
            label.setWordWrap(True)
            system_layout.addWidget(label)
        system_layout.addStretch(1)
        body.addWidget(self.system_card, stretch=1)
        layout.addLayout(body, stretch=1)

        checklist = self._card("Workflow-Checkliste")
        checklist_layout = QHBoxLayout(checklist)
        checklist_layout.setContentsMargins(14, 12, 14, 12)
        checklist_layout.setSpacing(10)
        self.step_labels: list[QLabel] = []
        for text in (
            "1 Projekt",
            "2 Quellen",
            "3 Analyse",
            "4 Auto-Schnitt",
            "5 Review",
            "6 Export",
        ):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(42)
            label.setStyleSheet(
                "background:#0f1318; border:1px solid rgba(255,255,255,18); "
                "border-radius:6px; color:#9ca3af; font-weight:700;"
            )
            checklist_layout.addWidget(label)
            self.step_labels.append(label)
        layout.addWidget(checklist)

    def _card(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("workflow_card")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setStyleSheet(
            "QFrame#workflow_card { background:#111821; border:1px solid rgba(255,255,255,18); "
            "border-radius:8px; }"
        )
        frame.setProperty("card_title", title)
        return frame

    def update_project(self, name: str | None, path: str | None) -> None:
        if name:
            self.project_name.setText(name)
            self.project_path.setText(path or "")
        else:
            self.project_name.setText("Kein Projekt geladen")
            self.project_path.setText("Lege ein Projekt an oder oeffne ein bestehendes Projekt.")


class PrepareWorkspace(QWidget):
    """Sources stage: media import/pool plus early proxy/convert work."""

    def __init__(self, media_widget: QWidget, convert_widget: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addWidget(WorkflowHeader(
            "Quellen vorbereiten",
            "Import, Medienpool und Preflight fuer einheitliche Videoquellen.",
        ))

        self.tabs = SectionTabs()
        self.tabs.addTab(media_widget, "Medienpool")
        self.tabs.addTab(convert_widget, "Preflight")
        self.tabs.setTabToolTip(0, "Audio und Video importieren, auswaehlen und pruefen.")
        self.tabs.setTabToolTip(1, "Videoquellen vor Analyse und Schnitt standardisieren.")
        layout.addWidget(self.tabs, stretch=1)


class AnalysisWorkspace(QWidget):
    """Analysis stage: individual audio/video steps plus complete runs."""

    def __init__(
        self,
        stems_widget: QWidget,
        media_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._build_ui(stems_widget, media_widget)

    def _build_ui(self, stems_widget: QWidget, media_widget: QWidget | None) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(WorkflowHeader(
            "Analyse",
            "Hier entstehen die Daten fuer gutes Pacing: Beats, Struktur, Stems, "
            "Szenen, Motion und SigLIP-Embeddings.",
        ))

        self.tabs = SectionTabs()
        if media_widget is not None:
            self.tabs.addTab(self._build_audio_page(media_widget), "Audio")
            self.tabs.addTab(self._build_video_page(media_widget), "Video")
            self.tabs.addTab(self._build_status_page(stems_widget, media_widget), "Stems / Status")
        else:
            self.tabs.addTab(stems_widget, "Stems / Status")
        layout.addWidget(self.tabs, stretch=1)

        self.btn_open_sources = QPushButton("Quellen pruefen")
        self.btn_open_sources.setVisible(False)
        self.btn_open_sources.setToolTip(
            "Springt zur Quellen-Seite, wenn Audio oder Video fehlt. Dort importierst du Medien "
            "oder pruefst Preflight/Standardisierung, bevor Analyse und Auto-Schnitt weiterlaufen."
        )

    def _configure_step_button(self, button: QPushButton, tooltip: str, *, primary: bool = False) -> QPushButton:
        button.setParent(self)
        button.setVisible(True)
        button.setHidden(False)
        button.setFixedHeight(30)
        button.setToolTip(tooltip)
        if primary:
            button.setObjectName("btn_accent")
        elif button.objectName() == "btn_accent":
            button.setObjectName("btn_secondary")
        return button

    def _build_audio_page(self, media_widget: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        header = QLabel(
            "Audio zuerst analysieren: der komplette Lauf macht alle Schritte nacheinander. "
            "Einzelschritte sind fuer Nacharbeit, Fehlerbehebung oder schnelle Teilpruefung."
        )
        header.setWordWrap(True)
        header.setStyleSheet("color:#9ca3af; font-size:11px;")
        layout.addWidget(header)

        primary = QHBoxLayout()
        self.btn_audio_complete = media_widget.btn_analyze_all
        self._configure_step_button(
            self.btn_audio_complete,
            "Fuehrt die noetigen Audio-Analysen in sinnvoller Reihenfolge aus: BPM/Beatgrid, "
            "Wellenform, Tonart, LUFS, Songstruktur und Stems. Nutze das als Standardweg, "
            "wenn ein Track neu importiert wurde oder du sicherstellen willst, dass alle "
            "Daten fuer Auto-Schnitt und Pacing vorhanden sind.",
            primary=True,
        )
        primary.addWidget(self.btn_audio_complete)
        primary.addStretch(1)
        layout.addLayout(primary)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        audio_steps = [
            (
                media_widget.btn_analyze,
                "BPM / Beatgrid",
                "Analysiert Tempo, Beat-Positionen und Grundenergie des Tracks. Dieser Schritt ist "
                "Pflicht fuer beat-synchrones Schneiden und sollte vor Auto-Schnitt erfolgreich sein.",
            ),
            (
                media_widget.btn_waveform,
                "Wellenform",
                "Erzeugt die sichtbare Wellenform inklusive Beatgrid-Anzeige. Sinnvoll, wenn die Timeline "
                "oder Review-Ansicht noch keine saubere Audioform zeigt.",
            ),
            (
                media_widget.btn_key_detect,
                "Tonart",
                "Bestimmt Tonart und Camelot-Wert. Relevant fuer spaetere Musik-/Mood-Entscheidungen, "
                "aber nicht zwingend fuer den ersten Schnitt.",
            ),
            (
                media_widget.btn_lufs_analyze,
                "LUFS",
                "Misst Lautheit und True Peak. Wichtig fuer Export-Qualitaet und konsistente Lautstaerke, "
                "aber kein kreativer Pacing-Schritt.",
            ),
            (
                media_widget.btn_structure_detect,
                "Songstruktur",
                "Findet Intro, Buildup, Drop, Breakdown und Outro. Diese Einteilung steuert spaeter "
                "Schnittdichte und passende Clip-Auswahl.",
            ),
            (
                media_widget.btn_stem_separate,
                "Stems",
                "Trennt Vocals, Drums, Bass und Other via Demucs. Braucht GPU/VRAM und dauert laenger, "
                "liefert aber bessere Drop-/Vocal-/Energie-Entscheidungen.",
            ),
        ]
        for idx, (button, text, tip) in enumerate(audio_steps):
            button.setText(text)
            self._configure_step_button(button, tip)
            grid.addWidget(button, idx // 3, idx % 3)
        layout.addLayout(grid)
        self.btn_stems = media_widget.btn_stem_separate
        layout.addStretch(1)
        return page

    def _build_video_page(self, media_widget: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        header = QLabel(
            "Video danach analysieren: die komplette Pipeline bereitet Clips fuer semantische Suche, "
            "Motion-Matching und Auto-Schnitt vor. Einzelschritte helfen, wenn nur ein Teil fehlt."
        )
        header.setWordWrap(True)
        header.setStyleSheet("color:#9ca3af; font-size:11px;")
        layout.addWidget(header)

        primary = QHBoxLayout()
        self.btn_video_pipeline = media_widget.btn_video_pipeline
        self._configure_step_button(
            self.btn_video_pipeline,
            "Fuehrt die komplette Videoanalyse aus: Szenen erkennen, Keyframes gewinnen, Motion bewerten "
            "und SigLIP-Embeddings fuer semantische Suche/Mood-Matching erzeugen. Das ist der Standardweg "
            "fuer neu importierte Videoclips vor Auto-Schnitt.",
            primary=True,
        )
        primary.addWidget(self.btn_video_pipeline)
        primary.addStretch(1)
        layout.addLayout(primary)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        video_steps = [
            (
                media_widget.btn_analyze_video,
                "Szenen erkennen",
                "Findet Shot-Grenzen und Szenenwechsel. Notwendig, damit PB Studio Clips in sinnvolle "
                "Einheiten schneiden und spaeter passend auswaehlen kann.",
            ),
            (
                media_widget.btn_motion_analysis,
                "Motion bewerten",
                "Analysiert Bewegung und visuelle Energie. Hilft, ruhige Parts mit ruhigem Material und "
                "Drops mit dynamischeren Clips zu verbinden.",
            ),
            (
                media_widget.btn_siglip_embeddings,
                "SigLIP Embeddings",
                "Erzeugt semantische Bild-Embeddings fuer Suche und Mood-Matching. Danach funktionieren "
                "Suchbegriffe wie 'stage lights' oder 'dancing crowd' deutlich besser.",
            ),
        ]
        for idx, (button, text, tip) in enumerate(video_steps):
            button.setText(text)
            self._configure_step_button(button, tip)
            grid.addWidget(button, idx // 3, idx % 3)
        layout.addLayout(grid)
        layout.addStretch(1)
        return page

    def _build_status_page(self, stems_widget: QWidget, media_widget: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        status_tabs = SectionTabs()
        status_tabs.addTab(stems_widget, "Stems")
        status_tabs.addTab(media_widget.audio_analysis_panel, "Audio-Status")
        status_tabs.addTab(media_widget.video_analysis_panel, "Video-Status")
        status_tabs.setTabToolTip(0, "Stem-Player und Stem-Analyse fuer den aktuell ausgewaehlten Track.")
        status_tabs.setTabToolTip(1, "Status aller Audio-Schritte inklusive Fehler und fehlender Ergebnisse.")
        status_tabs.setTabToolTip(2, "Status aller Video-Schritte inklusive Szenen, Motion und Embeddings.")
        layout.addWidget(status_tabs, stretch=1)
        return page


def set_tab_if_available(widget: QWidget, index: int) -> None:
    """Switch a workspace's internal tab widget without hard dependency."""
    tabs = getattr(widget, "_tabs", None)
    if tabs is not None and hasattr(tabs, "setCurrentIndex"):
        tabs.setCurrentIndex(index)
