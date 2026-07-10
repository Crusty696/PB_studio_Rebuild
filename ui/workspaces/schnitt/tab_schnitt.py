"""Sub-Tab 'Schnitt' im SCHNITT-Editor: Preview + Inspector oben, Timeline unten.

Pro-Editor-Umbau 2026-07-10 (User-Feedback): Der CLIP INSPECTOR sass als
fast leere Spalte ueber die volle Hoehe rechts neben ALLEN Sub-Tabs und nahm
der Timeline die Breite. Jetzt: kompaktes oberes Band (Vorschau + Transport
links, Inspector rechts), darunter Timeline + Cutliste in voller Breite.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSizePolicy,
)
from ui.clip_inspector import ClipInspectorPanel
from ui.widgets.cut_list_panel import CutListPanel
from ui.widgets.video_preview import VideoPreviewWidget
from ui.workspaces.schnitt.timeline_shell import TimelineShell


class SchnittTabSchnitt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        # ── Oberes Band: [Vorschau+Transport | stretch | CLIP INSPECTOR] ──
        top_band = QHBoxLayout()
        top_band.setSpacing(8)

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        self.video_preview = VideoPreviewWidget()
        # 16:9-Monitor, moderat: gross genug fuer die Bildkontrolle, aber die
        # Timeline unten bleibt der dominante Arbeitsbereich.
        self.video_preview.setMinimumSize(400, 225)
        self.video_preview.setMaximumSize(560, 315)
        self.video_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        left_col.addWidget(self.video_preview)

        transport = QHBoxLayout()
        transport.addStretch(1)
        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedSize(28, 24)
        self.btn_play.setToolTip("Vorschau Play / Pause")
        self.btn_play.setAccessibleName("Vorschau Play Pause")
        transport.addWidget(self.btn_play)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedSize(28, 24)
        self.btn_stop.setToolTip("Vorschau Stop")
        self.btn_stop.setAccessibleName("Vorschau stoppen")
        transport.addWidget(self.btn_stop)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #98a2b1; font-size: 10px;")
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        left_col.addLayout(transport)
        top_band.addLayout(left_col, stretch=2)

        top_band.addStretch(1)

        # CLIP INSPECTOR: kompakter Kasten neben der Vorschau (Inhalt ~280px
        # hoch) statt fast-leerer Vollhoehen-Spalte. editor_view aliasiert
        # self.inspector_panel fuer Controller/Wiring (schnitt_controller B5).
        self.inspector_panel = ClipInspectorPanel(self)
        self.inspector_panel.setMinimumWidth(260)
        self.inspector_panel.setMaximumWidth(380)
        top_band.addWidget(self.inspector_panel, stretch=1)

        v.addLayout(top_band)

        self.timeline_shell = TimelineShell()
        # Timeline = Hauptarbeitsbereich -> hohe Mindesthoehe + dominanter
        # Stretch (die kompakte Vorschau oben hat keinen vertikalen Stretch).
        self.timeline_shell.setMinimumHeight(340)
        self.timeline_shell.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.timeline_view = self.timeline_shell.timeline
        self.timeline_view.setToolTip(
            "Timeline: Drag&Drop, Mausrad zum Zoomen, Lock-Icon pro Clip."
        )
        v.addWidget(self.timeline_shell, stretch=4)

        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #98a2b1; font-size: 10px; padding: 1px 4px;")
        v.addWidget(self.cut_info_label)

        # B-295: CutListPanel — textuelle Cutliste unter der Timeline.
        self.cut_list_panel = CutListPanel(self)
        self.cut_list_panel.setMaximumHeight(130)
        v.addWidget(self.cut_list_panel, stretch=0)
        if hasattr(self.timeline_view, "set_playhead_time"):
            self.cut_list_panel.cut_selected.connect(self.timeline_view.set_playhead_time)
        # B-295: Edit-Affordances aus dem Cutlisten-Kontextmenue an die Timeline-Ops
        # (gleiche Undo/DB-Commands wie Lock-Icon / remove_selected_clips).
        self.cut_list_panel.cut_lock_toggle_requested.connect(self._on_cut_lock_toggle)
        self.cut_list_panel.cut_remove_requested.connect(self._on_cut_remove)

    def _on_cut_lock_toggle(self, entry_id: int, new_locked: bool) -> None:
        tv = self.timeline_view
        if hasattr(tv, "toggle_clip_lock_by_id"):
            tv.toggle_clip_lock_by_id(int(entry_id), bool(new_locked))
        self.cut_list_panel.refresh()

    def _on_cut_remove(self, entry_id: int) -> None:
        tv = self.timeline_view
        if hasattr(tv, "remove_clip_by_id"):
            tv.remove_clip_by_id(int(entry_id))
        self.cut_list_panel.refresh()
