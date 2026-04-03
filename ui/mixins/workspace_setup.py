"""WorkspaceSetupMixin — extrahiert aus main.py (AUD-44).

Kapselt:
  - _build_top_bar()        — Top-Bar Widget-Aufbau
  - _create_workspaces()    — Alle 5 Workspaces erstellen + Signals verdrahten
  - _on_workspace_changed() — Workspace-Wechsel Handler
  - _toggle_inspector()     — Inspector-Panel ein/ausblenden
  - _create_compact_slider() — Slider-Hilfs-Methode
  - _add_separator()        — Trennlinie-Hilfs-Methode
"""

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QFrame, QSlider, QWidget,
)
from PySide6.QtCore import Qt


class WorkspaceSetupMixin:
    """Mixin fuer MainWindow: Workspace-Erstellung und Top-Bar-Aufbau."""

    def _build_top_bar(self, main_layout, app_version: str):
        """Erstellt die Top-Bar (Titel, Projekt-Buttons, Panel-Toggles) und fuegt sie main_layout hinzu."""
        top_bar = QWidget()
        top_bar.setObjectName("top_bar")
        top_bar.setFixedHeight(36)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)

        app_title = QLabel(f"PB_studio v{app_version}")
        app_title.setStyleSheet("color: #e8e6e3; font-weight: 700; font-size: 13px; background: transparent;")
        top_layout.addWidget(app_title)

        btn_new_project = QPushButton("+ Neu")
        btn_new_project.setObjectName("btn_secondary")
        btn_new_project.setFixedHeight(24)
        btn_new_project.setToolTip("Neues Projekt erstellen")
        btn_new_project.clicked.connect(self._new_project)
        top_layout.addWidget(btn_new_project)

        btn_open_project = QPushButton("Oeffnen")
        btn_open_project.setObjectName("btn_secondary")
        btn_open_project.setFixedHeight(24)
        btn_open_project.setToolTip("Bestehendes Projekt oeffnen")
        btn_open_project.clicked.connect(self._open_project)
        top_layout.addWidget(btn_open_project)

        btn_save_as = QPushButton("Speichern unter")
        btn_save_as.setObjectName("btn_secondary")
        btn_save_as.setFixedHeight(24)
        btn_save_as.setToolTip("Projekt unter neuem Namen speichern")
        btn_save_as.clicked.connect(self._save_project_as)
        top_layout.addWidget(btn_save_as)

        self._project_name_label = QLabel("")
        self._project_name_label.setObjectName("title")
        self._project_name_label.setStyleSheet("color: #d4a44a; padding: 0 10px;")
        top_layout.addWidget(self._project_name_label)

        top_layout.addStretch()

        self._btn_toggle_tasks = QPushButton("Tasks")
        self._btn_toggle_tasks.setCheckable(True)
        self._btn_toggle_tasks.setChecked(True)
        self._btn_toggle_tasks.setFixedHeight(24)
        self._btn_toggle_tasks.setToolTip("Hintergrund-Tasks ein/ausblenden")
        top_layout.addWidget(self._btn_toggle_tasks)

        self._btn_toggle_console = QPushButton("Konsole")
        self._btn_toggle_console.setCheckable(True)
        self._btn_toggle_console.setChecked(True)
        self._btn_toggle_console.setFixedHeight(24)
        self._btn_toggle_console.setToolTip("System-Konsole ein/ausblenden")
        top_layout.addWidget(self._btn_toggle_console)

        self._btn_toggle_chat = QPushButton("KI Chat")
        self._btn_toggle_chat.setCheckable(True)
        self._btn_toggle_chat.setChecked(False)
        self._btn_toggle_chat.setFixedHeight(24)
        self._btn_toggle_chat.setToolTip("KI-Chat Panel ein/ausblenden")
        top_layout.addWidget(self._btn_toggle_chat)

        btn_settings = QPushButton("⚙ Einstellungen")
        btn_settings.setMaximumWidth(120)
        btn_settings.setFixedHeight(28)
        btn_settings.setToolTip("LLM-Backend, Ollama-URL und weitere Einstellungen")
        btn_settings.clicked.connect(self._show_settings)
        top_layout.addWidget(btn_settings)

        btn_about = QPushButton("About")
        btn_about.setMaximumWidth(80)
        btn_about.setFixedHeight(28)
        btn_about.setToolTip("Informationen ueber PB_studio anzeigen (Version, Technologie, Credits)")
        btn_about.clicked.connect(self._show_about)
        top_layout.addWidget(btn_about)

        main_layout.addWidget(top_bar)

    def _create_workspaces(self):
        """Creates all 5 workspaces, promotes widgets, wires signals."""
        from ui.workspaces import (
            MediaWorkspace, EditWorkspace, StemsWorkspace,
            ConvertWorkspace, DeliverWorkspace,
        )

        # --- MEDIA workspace ---
        self._media_ws = MediaWorkspace()
        self.workspace_stack.addWidget(self._media_ws)

        # Promote widgets for backward compat
        self.btn_analyze = self._media_ws.btn_analyze
        self.btn_analyze_video = self._media_ws.btn_analyze_video
        self.btn_video_pipeline = self._media_ws.btn_video_pipeline
        self.btn_waveform = self._media_ws.btn_waveform
        self.btn_stem_separate = self._media_ws.btn_stem_separate
        self.btn_auto_duck = self._media_ws.btn_auto_duck
        self.btn_add_to_timeline = self._media_ws.btn_add_to_timeline
        self.progress_bar = self._media_ws.progress_bar
        self.search_input = self._media_ws.search_input
        self.btn_search = self._media_ws.btn_search
        self.btn_search_clear = self._media_ws.btn_search_clear
        self.btn_select_all_video = self._media_ws.btn_select_all_video
        self.video_pool_table = self._media_ws.video_pool_table
        self.btn_delete_selected_video = self._media_ws.btn_delete_selected_video
        self.btn_select_all_audio = self._media_ws.btn_select_all_audio
        self.audio_pool_table = self._media_ws.audio_pool_table
        self.btn_delete_selected_audio = self._media_ws.btn_delete_selected_audio
        self.stem_player = self._media_ws.stem_player
        self.media_table = self._media_ws.media_table

        # Wire MEDIA signals
        self._media_ws.btn_import_video.clicked.connect(self._import_video)
        self._media_ws.btn_import_audio.clicked.connect(self._import_audio)
        self._media_ws.btn_import_folder.clicked.connect(self._import_folder)
        self._media_ws.btn_clear_all.clicked.connect(self._clear_all_media)
        self.btn_analyze.clicked.connect(self._analyze_selected_audio)
        self.btn_analyze_video.clicked.connect(self._analyze_selected_video)
        self.btn_video_pipeline.clicked.connect(self._start_video_pipeline)
        self.btn_waveform.clicked.connect(self._analyze_waveform)
        self.btn_stem_separate.clicked.connect(self._start_stem_separation)
        self.btn_auto_duck.clicked.connect(self._start_auto_ducking)
        self._media_ws.btn_analyze_all.clicked.connect(self._analyze_all_sequential)
        self.btn_add_to_timeline.clicked.connect(self._add_selected_to_timeline)
        self.search_input.returnPressed.connect(self._run_semantic_search)
        self.btn_search.clicked.connect(self._run_semantic_search)
        self.btn_search_clear.clicked.connect(self._clear_search)
        self.btn_select_all_video.clicked.connect(
            lambda: self._toggle_all_checkboxes(self.video_pool_table)
        )
        self.btn_select_all_audio.clicked.connect(
            lambda: self._toggle_all_checkboxes(self.audio_pool_table)
        )
        self.btn_delete_selected_video.clicked.connect(
            lambda: self._delete_selected_media("video")
        )
        self.btn_delete_selected_audio.clicked.connect(
            lambda: self._delete_selected_media("audio")
        )
        self.video_pool_table.currentCellChanged.connect(self._on_video_pool_selected)
        self.audio_pool_table.currentCellChanged.connect(self._on_audio_pool_selected)
        self.stem_player.playback_finished.connect(self._on_stem_playback_finished)

        # Phase 4: Neue Media-Buttons (Stubs — Backend noch nicht implementiert)
        if hasattr(self._media_ws, 'btn_key_detect'):
            self._media_ws.btn_key_detect.clicked.connect(self._detect_key)
        if hasattr(self._media_ws, 'btn_lufs_analyze'):
            self._media_ws.btn_lufs_analyze.clicked.connect(self._analyze_lufs)
        if hasattr(self._media_ws, 'btn_structure_detect'):
            self._media_ws.btn_structure_detect.clicked.connect(self._detect_structure)
        if hasattr(self._media_ws, 'btn_motion_analysis'):
            self._media_ws.btn_motion_analysis.clicked.connect(self._start_video_pipeline)
        if hasattr(self._media_ws, 'btn_siglip_embeddings'):
            self._media_ws.btn_siglip_embeddings.clicked.connect(self._start_video_pipeline)

        # --- EDIT workspace ---
        self._edit_ws = EditWorkspace()
        self.workspace_stack.addWidget(self._edit_ws)

        # Promote widgets
        self.video_preview = self._edit_ws.video_preview
        self.btn_preview_play = self._edit_ws.btn_preview_play
        self.btn_preview_stop = self._edit_ws.btn_preview_stop
        self.preview_time_label = self._edit_ws.preview_time_label
        self.btn_toggle_inspector = self._edit_ws.btn_toggle_inspector
        self.inspector_panel = self._edit_ws.inspector_panel
        self.audio_combo = self._edit_ws.audio_combo
        self.video_combo = self._edit_ws.video_combo
        self.vibe_input = self._edit_ws.vibe_input
        self.cut_rate_combo = self._edit_ws.cut_rate_combo
        self.energy_reactivity_slider = self._edit_ws.energy_reactivity_slider
        self.energy_reactivity_spin = self._edit_ws.energy_reactivity_spin
        self.breakdown_combo = self._edit_ws.breakdown_combo
        self.tempo_slider = self._edit_ws.tempo_slider
        self.energy_slider = self._edit_ws.energy_slider
        self.density_slider = self._edit_ws.density_slider
        self.btn_generate = self._edit_ws.btn_generate
        self.btn_auto_edit = self._edit_ws.btn_auto_edit
        self.anchor_list = self._edit_ws.anchor_list
        self.btn_add_anchor = self._edit_ws.btn_add_anchor
        self.btn_remove_anchor = self._edit_ws.btn_remove_anchor
        self.btn_sync_anchors = self._edit_ws.btn_sync_anchors
        self.btn_learn_ai = self._edit_ws.btn_learn_ai
        self.btn_keyframe_string = self._edit_ws.btn_keyframe_string
        self.keyframe_text = self._edit_ws.keyframe_text
        self.pacing_curve = self._edit_ws.pacing_curve
        self.timeline_view = self._edit_ws.timeline_view
        self.cut_info_label = self._edit_ws.cut_info_label

        # Wire EDIT signals
        self.btn_preview_play.clicked.connect(self._toggle_preview_play)
        self.btn_preview_stop.clicked.connect(self.video_preview.stop)
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        self.video_combo.currentIndexChanged.connect(self._on_video_combo_changed)
        self.audio_combo.currentIndexChanged.connect(self._on_audio_combo_changed)
        self.btn_generate.clicked.connect(self._generate_timeline)
        self.btn_auto_edit.clicked.connect(self._auto_edit_to_beat)
        self.btn_add_anchor.clicked.connect(self._add_anchor_dialog)
        self.btn_remove_anchor.clicked.connect(self._remove_selected_anchor)
        self.btn_sync_anchors.clicked.connect(self._sync_anchors)
        self.btn_learn_ai.clicked.connect(self._learn_anchor_as_ai_rule)
        self.btn_keyframe_string.clicked.connect(self._show_keyframe_strings)
        # W-10 Fix: Pacing-Kurve live-Update → Timeline regenerieren
        if hasattr(self.pacing_curve, 'curve_changed'):
            self.pacing_curve.curve_changed.connect(self._generate_timeline)
        # Phase 4: RL Feedback + Style Preset
        if hasattr(self._edit_ws, 'btn_thumbs_up'):
            self._edit_ws.btn_thumbs_up.clicked.connect(self._rl_feedback_positive)
        if hasattr(self._edit_ws, 'btn_thumbs_down'):
            self._edit_ws.btn_thumbs_down.clicked.connect(self._rl_feedback_negative)
        if hasattr(self._edit_ws, 'style_preset_combo'):
            self._edit_ws.style_preset_combo.currentIndexChanged.connect(self._apply_style_preset)
        self.timeline_view.clip_moved.connect(self._on_timeline_clip_moved)

        # Undo/Redo Shortcuts (Ctrl+Z / Ctrl+Y)
        from PySide6.QtGui import QAction, QKeySequence
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.timeline_view.undo_stack.undo)
        self.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.timeline_view.undo_stack.redo)
        self.addAction(redo_action)

        # VideoPreview: position label + play-button icon state
        self.video_preview.position_changed.connect(self._on_preview_position_changed)
        self.video_preview.playback_state_changed.connect(self._on_preview_state_changed)

        # AUD-71: Wire Timeline keyboard shortcut signals to video preview
        self.timeline_view.play_pause_toggled.connect(self.video_preview.toggle_play)
        self.timeline_view.stop_requested.connect(self.video_preview.stop)
        self.timeline_view.seek_forward.connect(
            lambda delta: self.video_preview.seek_relative(delta))
        self.timeline_view.seek_backward.connect(
            lambda delta: self.video_preview.seek_relative(-delta))
        self.timeline_view.jump_to_start.connect(
            lambda: self.video_preview.seek_to(0.0))
        self.timeline_view.jump_to_end.connect(
            lambda: self.video_preview.seek_to(self.video_preview.duration))
        self.timeline_view.zoom_in_requested.connect(
            lambda: self.timeline_view.zoom_by_factor(1.25))
        self.timeline_view.zoom_out_requested.connect(
            lambda: self.timeline_view.zoom_by_factor(1.0 / 1.25))
        # Sync playhead time back to timeline for I/O points
        self.video_preview.position_changed.connect(
            lambda cur, _total: self.timeline_view.set_playhead_time(cur))

        self._refresh_director_combos()

        # --- STEMS workspace ---
        self._stems_ws = StemsWorkspace()
        self.workspace_stack.addWidget(self._stems_ws)
        self.stem_workspace = self._stems_ws.stem_widget

        # Wire STEMS signals
        self.stem_workspace.stem_volume_changed.connect(self.stem_player.set_volume)
        self.stem_workspace.stem_mute_toggled.connect(self.stem_player.set_mute)
        self.stem_workspace.play_requested.connect(self.stem_player.play)
        self.stem_workspace.pause_requested.connect(self.stem_player.pause)
        self.stem_workspace.stop_requested.connect(self.stem_player.stop)
        self.stem_workspace.seek_requested.connect(self.stem_player.seek)
        self.stem_player.position_changed.connect(self.stem_workspace.update_position)
        self.stem_player.state_changed.connect(self.stem_workspace.update_playback_state)

        # --- CONVERT workspace ---
        self._convert_ws = ConvertWorkspace()
        self.workspace_stack.addWidget(self._convert_ws)

        # Promote widgets
        self.convert_resolution = self._convert_ws.convert_resolution
        self.convert_fps = self._convert_ws.convert_fps
        self.convert_format = self._convert_ws.convert_format
        self.btn_standardize_all = self._convert_ws.btn_standardize_all
        self.convert_progress = self._convert_ws.convert_progress
        self.convert_log = self._convert_ws.convert_log
        self.effects_clip_combo = self._convert_ws.effects_clip_combo
        self.brightness_slider = self._convert_ws.brightness_slider
        self.brightness_label = self._convert_ws.brightness_label
        self.contrast_slider = self._convert_ws.contrast_slider
        self.contrast_label = self._convert_ws.contrast_label
        self.crossfade_slider = self._convert_ws.crossfade_slider
        self.crossfade_label = self._convert_ws.crossfade_label
        self.effects_preview = self._convert_ws.effects_preview
        self.btn_apply_effects = self._convert_ws.btn_apply_effects

        # Wire CONVERT signals
        self.btn_standardize_all.clicked.connect(self._standardize_all_videos)
        self.effects_clip_combo.currentIndexChanged.connect(self._on_effects_clip_changed)
        self.btn_apply_effects.clicked.connect(self._apply_effects)

        # --- DELIVER workspace ---
        self._deliver_ws = DeliverWorkspace()
        self.workspace_stack.addWidget(self._deliver_ws)

        # Promote widgets
        self.production_info = self._deliver_ws.production_info
        self.export_name_input = self._deliver_ws.export_name_input
        self.resolution_combo = self._deliver_ws.resolution_combo
        self.fps_combo = self._deliver_ws.fps_combo
        self.preset_combo = self._deliver_ws.preset_combo
        self.btn_export = self._deliver_ws.btn_export
        self.btn_preview = self._deliver_ws.btn_preview
        self.btn_refresh_production = self._deliver_ws.btn_refresh_production
        self.export_progress = self._deliver_ws.export_progress
        self.export_log = self._deliver_ws.export_log
        self.render_estimate_label = self._deliver_ws.render_estimate_label

        # Wire DELIVER signals
        self.btn_export.clicked.connect(self._start_export)
        self.btn_preview.clicked.connect(self._start_preview_export)
        self.btn_refresh_production.clicked.connect(self._refresh_production_info)
        self.resolution_combo.currentIndexChanged.connect(
            lambda: self._update_render_estimate()
        )
        self.fps_combo.currentIndexChanged.connect(
            lambda: self._update_render_estimate()
        )
        self.preset_combo.currentIndexChanged.connect(
            lambda: self._update_render_estimate()
        )
        self._deliver_ws.btn_preview_play.clicked.connect(self._play_preview)
        self._deliver_ws.btn_preview_stop.clicked.connect(self._stop_preview)

    def _on_workspace_changed(self, index: int):
        """Workspace-Wechsel: Index setzen + workspace-spezifische Refresh-Logik."""
        self.workspace_stack.setCurrentIndex(index)
        # CONVERT workspace (Index 3) — Effects-Combo mit Timeline-Clips befuellen
        if index == 3:
            self._refresh_effects_combos()
        # DELIVER workspace (Index 4) — Renderzeit-Schaetzung aktualisieren
        elif index == 4:
            self._refresh_production_info()

    def _toggle_inspector(self):
        """Toggle inspector panel visibility."""
        if self.inspector_panel.isVisible():
            self.inspector_panel.hide()
            self.btn_toggle_inspector.setText("\u25C0")
        else:
            self.inspector_panel.show()
            self.btn_toggle_inspector.setText("\u25B6")

    def _create_compact_slider(self, label: str, min_val: int, max_val: int, default: int):
        """Compact horizontal slider row: [Label] [=====o=====] [Value]"""
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label)
        lbl.setFixedWidth(46)
        lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        slider.setFixedHeight(16)
        row.addWidget(slider, stretch=1)
        val_lbl = QLabel(str(default))
        val_lbl.setFixedWidth(26)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        val_lbl.setStyleSheet("color: #9ca3af; font-size: 10px;")
        slider.valueChanged.connect(lambda v: val_lbl.setText(str(v)))
        row.addWidget(val_lbl)
        return slider, row

    @staticmethod
    def _add_separator(layout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,6);")
        layout.addWidget(sep)
