"""SchnittEditorView — finale Editor-Stage mit 4 Sub-Tabs + persistentem Inspector.
Sub-Tab-Inhalte werden in Phasen 05–08 ausimplementiert.

Tier-3-Sunset: Header-Row mit Audio-/Video-Combo wandert vom hidden
``_edit_ws`` hierher. Action-Buttons (Generate / Auto-Edit) liegen im
gleichen Header rechts, damit der Controller weiterhin per Name zieht.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QTabWidget, QVBoxLayout, QLabel,
    QComboBox, QPushButton,
)
from ui.clip_inspector import ClipInspectorPanel
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio
from ui.workspaces.schnitt.tab_rl_notes import SchnittTabRlNotes


class SchnittEditorView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_editor")
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        outer.addLayout(self._build_header_row())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)
        self.tab_schnitt = SchnittTabSchnitt(self)
        self.sub_tabs.addTab(self.tab_schnitt, "Schnitt")
        self.sub_tabs.setTabToolTip(0, "Timeline, Vorschau, Cutliste und Clip-Inspector bearbeiten.")
        self.tab_pacing_anker = SchnittTabPacingAnker(self)
        self.sub_tabs.addTab(self.tab_pacing_anker, "Pacing & Anker")
        self.sub_tabs.setTabToolTip(1, "Cut-Rate, Energie-Reaktivitaet, Stil und feste Sync-Anker einstellen.")
        self.tab_audio = SchnittTabAudio(self)
        self.sub_tabs.addTab(self.tab_audio, "Audio")
        self.sub_tabs.setTabToolTip(2, "Waveform, LUFS, Tonart und Stems des aktiven Audio-Tracks pruefen.")
        self.tab_rl_notes = SchnittTabRlNotes(self)
        self.sub_tabs.addTab(self.tab_rl_notes, "RL & Notes")
        self.sub_tabs.setTabToolTip(3, "Auto-Edit-Feedback, Lernereignisse und gespeicherte Notizen verwalten.")
        body.addWidget(self.sub_tabs, stretch=2)

        # Pro-Editor-Layout: CLIP INSPECTOR als breitere rechte Spalte
        # (2:1 statt 3:1 -> ~33 % statt 25 %), damit Properties lesbar sind.
        self.inspector_panel = ClipInspectorPanel(self)
        body.addWidget(self.inspector_panel, stretch=1)

        outer.addLayout(body)

    def _build_header_row(self) -> QHBoxLayout:
        """Header-Row mit Audio/Video-Combo + Generate/Auto-Edit (Tier-3-Sunset)."""
        row = QHBoxLayout()
        row.setSpacing(8)

        a_lbl = QLabel("Audio")
        a_lbl.setStyleSheet("color:#98a2b1; font-size:10px;")
        row.addWidget(a_lbl)
        self.audio_combo = QComboBox()
        self.audio_combo.setToolTip("Audio-Track für BPM-Pacing")
        self.audio_combo.setAccessibleName("Audio-Track Auswahl")
        self.audio_combo.setFixedHeight(22)
        self.audio_combo.setMinimumWidth(180)
        row.addWidget(self.audio_combo, stretch=2)

        v_lbl = QLabel("Video")
        v_lbl.setStyleSheet("color:#98a2b1; font-size:10px;")
        row.addWidget(v_lbl)
        self.video_combo = QComboBox()
        self.video_combo.setToolTip(
            "Video-Clip für Vorschau und manuelle Pacing-Kontrolle wählen."
        )
        self.video_combo.setAccessibleName("Video-Clip Auswahl")
        self.video_combo.setFixedHeight(22)
        self.video_combo.setMinimumWidth(180)
        row.addWidget(self.video_combo, stretch=2)

        row.addStretch(1)

        self.btn_generate = QPushButton("Timeline generieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setFixedHeight(24)
        self.btn_generate.setMaximumWidth(200)
        self.btn_generate.setAccessibleName("Timeline generieren")
        self.btn_generate.setToolTip(
            "Timeline aus Audio, Videoauswahl und Pacing-Einstellungen neu generieren."
        )
        row.addWidget(self.btn_generate)

        self.btn_auto_edit = QPushButton("Auto-Edit")
        self.btn_auto_edit.setObjectName("btn_accent")
        self.btn_auto_edit.setFixedHeight(24)
        self.btn_auto_edit.setMaximumWidth(140)
        self.btn_auto_edit.setAccessibleName("Auto-Edit starten")
        self.btn_auto_edit.setToolTip(
            "Automatischen Beat-Schnitt starten: Pacing berechnet Cuts und wählt passende Clips.\n"
            "Quelle ist der MATERIAL-Pool — die Timeline muss NICHT vorbefüllt werden.\n"
            "Vorauswahl: in MATERIAL & ANALYSE Clips per Checkbox markieren → nur diese werden verwendet.\n"
            "Nichts markiert → die App wählt selbst aus allen analysierten Clips.\n"
            "Nach dem Lauf sind verwendete Clips im Pool grün markiert ([N×])."
        )
        row.addWidget(self.btn_auto_edit)
        return row

    @staticmethod
    def _stub(text: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #98a2b1; font-size: 12px;")
        v.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        v.addStretch(1)
        return w
