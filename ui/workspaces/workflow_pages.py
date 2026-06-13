"""Workflow-oriented wrapper pages for the Director's Cockpit."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ui.widgets.workflow_components import SectionTabs, WorkflowHeader

_COCKPIT_ACTION_LABELS = (
    "Projekt starten",
    "Material importieren",
    "Audio analysieren",
    "Video analysieren",
    "Auto-Schnitt starten",
    "Timeline pruefen",
    "Export vorbereiten",
)


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

    action_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._current_action_key = "open_project"
        self._refresh_debounce_timer = QTimer(self)
        self._refresh_debounce_timer.setSingleShot(True)
        self._refresh_debounce_timer.setInterval(750)
        self._refresh_debounce_timer.timeout.connect(self._refresh_current_project)
        self._build_ui()
        self.refresh_requested.connect(
            self.request_refresh_debounced,
            Qt.ConnectionType.QueuedConnection,
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        title_block.addWidget(_title("PB Studio Cockpit"))
        title_block.addWidget(_subtitle(
            "Gefuehrter Ablauf: Das Cockpit zeigt, was bereit ist, was fehlt "
            "und welche Aktion als Naechstes sinnvoll ist."
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

        self.next_card = self._card("Naechste Aktion")
        next_layout = QVBoxLayout(self.next_card)
        next_layout.setContentsMargins(16, 14, 16, 14)
        next_layout.setSpacing(8)
        self.next_step = QLabel("Projekt starten")
        self.next_step.setStyleSheet("font-size: 22px; font-weight: 800; color: #f0c866;")
        self.next_reason = QLabel("Lege ein Projekt an oder oeffne ein bestehendes Projekt.")
        self.next_reason.setWordWrap(True)
        self.next_reason.setStyleSheet("color:#d1d5db; font-size:12px;")
        self.btn_next_step = QPushButton("Projekt starten")
        self.btn_next_step.setObjectName("btn_accent")
        self.btn_next_step.setFixedHeight(38)
        self.btn_next_step.clicked.connect(self._emit_next_action)
        next_layout.addWidget(self.next_step)
        next_layout.addWidget(self.next_reason)
        next_layout.addStretch(1)
        next_layout.addWidget(self.btn_next_step)
        body.addWidget(self.next_card, stretch=3)

        self.status_card = self._card("Projekt")
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

        self.system_card = self._card("Systemstatus")
        system_layout = QVBoxLayout(self.system_card)
        system_layout.setContentsMargins(14, 12, 14, 12)
        system_layout.setSpacing(7)
        system_title = QLabel("Systemstatus")
        system_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f9fafb;")
        system_layout.addWidget(system_title)
        self.system_labels: list[QLabel] = []
        for text in (
            "GPU: beim Pipeline-Start pruefen",
            "Ollama: ueber KI-Status sichtbar",
            "FFmpeg: fuer Convert/Export erforderlich",
            "Tasks: keine laufenden Cockpit-Aktionen",
        ):
            label = QLabel(text)
            label.setStyleSheet("color:#9ca3af;")
            label.setWordWrap(True)
            system_layout.addWidget(label)
            self.system_labels.append(label)
        system_layout.addStretch(1)
        body.addWidget(self.system_card, stretch=1)
        layout.addLayout(body, stretch=1)

        readiness = self._card("Readiness")
        readiness_layout = QGridLayout(readiness)
        readiness_layout.setContentsMargins(14, 12, 14, 12)
        readiness_layout.setHorizontalSpacing(10)
        readiness_layout.setVerticalSpacing(10)
        self.readiness_cards: dict[str, tuple[QFrame, QLabel, QLabel]] = {}
        for idx, (key, title, detail) in enumerate((
            ("audio", "Audio", "Beats, Waveform, Struktur"),
            ("video", "Video", "Szenen, Bewegung, Suchdaten"),
            ("auto_edit", "Auto-Schnitt", "bereit fuer Timeline"),
            ("export", "Export", "Timeline vorhanden"),
        )):
            card, state_label, detail_label = self._readiness_card(title, detail)
            readiness_layout.addWidget(card, idx // 2, idx % 2)
            self.readiness_cards[key] = (card, state_label, detail_label)
        layout.addWidget(readiness)

        warnings = self._card("Qualitaetswarnungen")
        warnings_layout = QVBoxLayout(warnings)
        warnings_layout.setContentsMargins(14, 12, 14, 12)
        warnings_layout.setSpacing(6)
        self.warning_labels: list[QLabel] = []
        for _ in range(3):
            label = QLabel("Keine Warnung")
            label.setWordWrap(True)
            label.setStyleSheet("color:#9ca3af;")
            warnings_layout.addWidget(label)
            self.warning_labels.append(label)
        layout.addWidget(warnings)

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

    def _readiness_card(self, title: str, detail: str) -> tuple[QFrame, QLabel, QLabel]:
        frame = QFrame()
        frame.setObjectName("readiness_card")
        frame.setMinimumHeight(76)
        frame.setStyleSheet(
            "QFrame#readiness_card { background:#0f1318; border:1px solid rgba(255,255,255,18); "
            "border-radius:6px; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#f9fafb; font-weight:800; font-size:13px;")
        state_label = QLabel("Fehlt")
        state_label.setStyleSheet("color:#ef4444; font-weight:700;")
        detail_label = QLabel(detail)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        layout.addWidget(title_label)
        layout.addWidget(state_label)
        layout.addWidget(detail_label)
        return frame, state_label, detail_label

    # B-292/D: Convenience properties — Tests / Externe greifen auf
    # benannte Card-Attribute zu (audio_card, video_card, ...). Die Frames
    # liegen intern in self.readiness_cards[key][0].
    @property
    def audio_card(self) -> QFrame | None:
        entry = self.readiness_cards.get("audio")
        return entry[0] if entry else None

    @property
    def video_card(self) -> QFrame | None:
        entry = self.readiness_cards.get("video")
        return entry[0] if entry else None

    @property
    def auto_edit_card(self) -> QFrame | None:
        entry = self.readiness_cards.get("auto_edit")
        return entry[0] if entry else None

    @property
    def export_card(self) -> QFrame | None:
        entry = self.readiness_cards.get("export")
        return entry[0] if entry else None

    def refresh(self, project_id: int | None) -> None:
        from services.cockpit_orchestrator import get_cockpit_readiness

        self._project_id = project_id
        self.set_readiness(get_cockpit_readiness(project_id))

    def request_refresh_debounced(self) -> None:
        self._refresh_debounce_timer.start()

    def _refresh_current_project(self) -> None:
        self.refresh(self._project_id)

    def set_readiness(self, readiness) -> None:
        self._project_id = readiness.project_id
        self.update_project(readiness.project_name, readiness.project_path)
        self._current_action_key = readiness.next_action.key
        self.next_step.setText(readiness.next_action.label)
        self.next_reason.setText(readiness.next_action.description)
        self.btn_next_step.setText(readiness.next_action.label)
        self.btn_next_step.setEnabled(readiness.next_action.enabled)
        self.btn_next_step.setToolTip(readiness.next_action.description)

        for key, state in readiness.cards.items():
            if key not in self.readiness_cards:
                continue
            card, state_label, _detail = self.readiness_cards[key]
            ready = state == "ready"
            state_label.setText("Bereit" if ready else "Fehlt")
            state_label.setStyleSheet(
                "color:#4ade80; font-weight:700;" if ready else "color:#ef4444; font-weight:700;"
            )
            card.setStyleSheet(
                "QFrame#readiness_card { background:#0f1812; border:1px solid rgba(74,222,128,70); border-radius:6px; }"
                if ready
                else "QFrame#readiness_card { background:#181214; border:1px solid rgba(239,68,68,70); border-radius:6px; }"
            )

        messages = list(readiness.blockers) + list(readiness.warnings)
        if not messages:
            messages = ["Keine Warnung"]
        for idx, label in enumerate(self.warning_labels):
            text = messages[idx] if idx < len(messages) else ""
            label.setText(text)
            label.setVisible(bool(text))

        # B-292/D: Tooltip mit fehlenden Steps fuer blocked Cards.
        msf = getattr(readiness, "missing_steps_per_card", {}) or {}
        try:
            from ui.widgets.analysis_status_panel import STEP_NAMES
        except Exception:
            STEP_NAMES = {}
        synthetic_labels = {
            "kein_audio": "Kein Audio importiert",
            "kein_video": "Kein Video importiert",
            "kein_projekt": "Kein Projekt geladen",
            "audio_video_unvollstaendig": "Audio/Video-Analyse unvollstaendig",
            "timeline_leer": "Timeline leer — Auto-Edit fehlt",
        }
        for card_key, card_widget in (
            ("audio", self.audio_card),
            ("video", self.video_card),
            ("auto_edit", self.auto_edit_card),
            ("export", self.export_card),
        ):
            if card_widget is None:
                continue
            steps = msf.get(card_key) or []
            if not steps:
                card_widget.setToolTip("Bereit.")
                continue
            pretty = ", ".join(synthetic_labels.get(s, STEP_NAMES.get(s, s)) for s in steps)
            card_widget.setToolTip(f"Fehlt: {pretty}")

    def _emit_next_action(self) -> None:
        self.action_requested.emit(self._current_action_key)

    def update_project(self, name: str | None, path: str | None, project_id: int | None = None) -> None:
        if project_id is not None:
            self._project_id = project_id
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


class MaterialAnalysisWorkspace(QWidget):
    """Single working surface: select media and run analysis beside it."""

    def __init__(
        self,
        media_widget: QWidget,
        convert_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.media_widget = media_widget
        self.convert_widget = convert_widget
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addWidget(WorkflowHeader(
            "Material & Analyse",
            "Datei auswaehlen und passende Analyse direkt daneben starten. "
            "Audio und Video bleiben im selben Arbeitskontext.",
        ))
        layout.addWidget(self.media_widget, stretch=1)

        if self.convert_widget is not None and hasattr(self.media_widget, "attach_preflight_button"):
            self.media_widget.attach_preflight_button(self.convert_widget.btn_standardize_all)
            # B-525: Das "Ziel-Format"-GroupBox wird NICHT mehr inline in die enge
            # Material-Spalte reparentet (verursachte Layout-Ueberlappung). Auf-
            # loesung/FPS/Container/Copy werden jetzt in einem modalen Dialog
            # gewaehlt (Profi-Pattern), den der Standardisieren-Button oeffnet.
            # Nur der Button bleibt als Trigger in der Spalte.
            # UI-Ueberholung 2026-06-13 (User-Feedback): Der ConvertWorkspace
            # (EFFEKTE-Tab) wird NICHT mehr unter den Medien-Bereich gemountet.
            # Er fraß mit der leeren 360px-Vorschau (effects_preview) den unteren
            # Bereich des Material-Tabs als toten Platz. Per-Clip-Effekte
            # (Helligkeit/Kontrast/Crossfade) sind im SCHNITT Clip-Inspector
            # verfuegbar; der Standardisieren-Button bleibt als Trigger erhalten.
            # convert_widget bleibt konstruiert (Controller-Referenzen + Dialog),
            # nur unsichtbar (kein Layout-Mount).

        self.btn_stems = self.media_widget.btn_stem_separate
        self.btn_video_pipeline = self.media_widget.btn_video_pipeline
        self.btn_audio_complete = self.media_widget.btn_analyze_all
        self.btn_keyframe_string = self.media_widget.btn_keyframe_string
        self.keyframe_text = self.media_widget.keyframe_text
        self.audio_analysis_panel = self.media_widget.audio_analysis_panel
        self.video_analysis_panel = self.media_widget.video_analysis_panel


class LegacyAnalysisWorkspace(QWidget):
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
        # B-296/R-15: btn_motion_analysis + btn_siglip_embeddings entfernt
        # (Aliase auf _start_video_pipeline). btn_video_pipeline ist Primary
        # (oben). Szenen-Erkennung bleibt als optionaler Einzelschritt.
        video_steps = [
            (
                media_widget.btn_analyze_video,
                "Szenen erkennen",
                "Findet Shot-Grenzen und Szenenwechsel. Notwendig, damit PB Studio Clips in sinnvolle "
                "Einheiten schneiden und spaeter passend auswaehlen kann.",
            ),
        ]
        for idx, (button, text, tip) in enumerate(video_steps):
            button.setText(text)
            self._configure_step_button(button, tip)
            grid.addWidget(button, idx // 3, idx % 3)
        layout.addLayout(grid)
        # B-296/phase-E-fix I-4: nach Alias-Removal nur noch ein Einzelschritt-Button.
        # Hint-Label fuer User-Klarheit, dass btn_video_pipeline (oben) Standard ist.
        hint = QLabel("Einzelschritt (optional). Standardweg ist die Voll-Pipeline oben.")
        hint.setStyleSheet("color: #6b7280; font-size: 10px; font-style: italic;")
        layout.addWidget(hint)
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


AnalysisWorkspace = MaterialAnalysisWorkspace


def set_tab_if_available(widget: QWidget, index: int) -> None:
    """Switch a workspace's internal tab widget without hard dependency."""
    tabs = getattr(widget, "_tabs", None)
    if tabs is not None and hasattr(tabs, "setCurrentIndex"):
        tabs.setCurrentIndex(index)
