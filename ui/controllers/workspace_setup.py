"""WorkspaceSetupController — Refactored from WorkspaceSetupMixin."""

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QFrame, QWidget, QMenu,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from ui.base_component import PBComponent

class WorkspaceSetupController(PBComponent):
    """Controller fuer MainWindow: Workspace-Erstellung und Top-Bar-Aufbau."""

    def _build_top_bar(self, main_layout, app_version: str):
        """Erstellt die kompakte Top-Bar (P9-LAYOUT: 28 px statt 36)."""
        top_bar = QWidget()
        top_bar.setObjectName("top_bar")
        top_bar.setFixedHeight(28)  # P9: -8 px
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 0, 8, 0)
        top_layout.setSpacing(4)

        app_title = QLabel(f"PB_studio v{app_version}")
        app_title.setStyleSheet("color: #e8e6e3; font-weight: 700; font-size: 11px; background: transparent;")
        top_layout.addWidget(app_title)

        btn_new_project = QPushButton("+ Neu")
        btn_new_project.setObjectName("btn_secondary")
        btn_new_project.setFixedHeight(22)
        btn_new_project.clicked.connect(self.window.project_management._new_project)
        top_layout.addWidget(btn_new_project)

        btn_open_project = QPushButton("Oeffnen")
        btn_open_project.setObjectName("btn_secondary")
        btn_open_project.setFixedHeight(22)
        btn_open_project.clicked.connect(self.window.project_management._open_project)
        top_layout.addWidget(btn_open_project)

        self.window._btn_recent = QPushButton("Zuletzt \u25be")
        self.window._btn_recent.setObjectName("btn_secondary")
        self.window._btn_recent.setFixedHeight(22)
        self.window._btn_recent.clicked.connect(self._show_recent_projects_menu)
        top_layout.addWidget(self.window._btn_recent)

        btn_save_as = QPushButton("Speichern unter")
        btn_save_as.setObjectName("btn_secondary")
        btn_save_as.setFixedHeight(22)
        btn_save_as.clicked.connect(self.window.project_management._save_project_as)
        top_layout.addWidget(btn_save_as)

        self.window._project_name_label = QLabel("")
        self.window._project_name_label.setObjectName("title")
        self.window._project_name_label.setStyleSheet("color: #d4a44a; padding: 0 8px; font-size: 11px;")
        top_layout.addWidget(self.window._project_name_label)

        top_layout.addStretch()

        self.window._btn_toggle_tasks = QPushButton("Tasks")
        self.window._btn_toggle_tasks.setCheckable(True)
        self.window._btn_toggle_tasks.setChecked(True)
        self.window._btn_toggle_tasks.setFixedHeight(22)
        top_layout.addWidget(self.window._btn_toggle_tasks)

        self.window._btn_toggle_console = QPushButton("Konsole")
        self.window._btn_toggle_console.setCheckable(True)
        self.window._btn_toggle_console.setChecked(True)
        self.window._btn_toggle_console.setFixedHeight(22)
        top_layout.addWidget(self.window._btn_toggle_console)

        self.window._btn_toggle_chat = QPushButton("KI Chat")
        self.window._btn_toggle_chat.setCheckable(True)
        self.window._btn_toggle_chat.setChecked(False)
        self.window._btn_toggle_chat.setFixedHeight(22)
        top_layout.addWidget(self.window._btn_toggle_chat)

        # P16: Studio Brain entry-point. Opens the 4-tab window
        # (Struktur / Gedächtnis / Audit / Steer). Ctrl+B is the shortcut.
        btn_brain = QPushButton("🧠 Brain")
        btn_brain.setToolTip(
            "Studio Brain öffnen (Ctrl+B) — Übersicht über Szenen, Lerndaten, "
            "Pacing-Runs und Steuerung."
        )
        btn_brain.setMaximumWidth(90)
        btn_brain.setFixedHeight(22)
        btn_brain.clicked.connect(self.window._open_studio_brain)
        top_layout.addWidget(btn_brain)

        btn_settings = QPushButton("⚙ Einstellungen")
        btn_settings.setMaximumWidth(110)
        btn_settings.setFixedHeight(22)
        btn_settings.clicked.connect(self.window.project_management._show_settings)
        top_layout.addWidget(btn_settings)

        btn_about = QPushButton("About")
        btn_about.setMaximumWidth(64)
        btn_about.setFixedHeight(22)
        btn_about.clicked.connect(self.window.project_management._show_about)
        top_layout.addWidget(btn_about)

        btn_help = QPushButton("?")
        btn_help.setFixedSize(22, 22)
        btn_help.clicked.connect(self.window.project_management._show_shortcut_help)
        top_layout.addWidget(btn_help)

        main_layout.addWidget(top_bar)

    def _show_recent_projects_menu(self):
        """Zeigt ein Dropdown-Menue mit den zuletzt geoeffneten Projekten."""
        from pathlib import Path
        from services.recent_projects import RecentProjectsManager
        menu = QMenu(self.window)
        menu.setStyleSheet(
            "QMenu { background-color: #1e1e1e; color: #e8e6e3; border: 1px solid #3a3a3a; }"
            "QMenu::item:selected { background-color: #2a2a2a; color: #FFD700; }"
            "QMenu::separator { height: 1px; background: #3a3a3a; margin: 2px 4px; }"
        )
        recent = RecentProjectsManager.get_all()
        if not recent:
            empty = QAction("(Keine letzten Projekte)", self.window)
            empty.setEnabled(False)
            menu.addAction(empty)
        else:
            for path_str in recent:
                p = Path(path_str)
                action = QAction(p.name, self.window)
                action.setData(path_str)
                action.triggered.connect(
                    lambda checked=False, ps=path_str: self._open_recent_project(ps)
                )
                menu.addAction(action)
            menu.addSeparator()
            clear_action = QAction("Liste leeren", self.window)
            clear_action.triggered.connect(self._clear_recent_projects)
            menu.addAction(clear_action)

        menu.exec(self.window._btn_recent.mapToGlobal(
            self.window._btn_recent.rect().bottomLeft()
        ))

    def _open_recent_project(self, path_str: str) -> None:
        """Oeffnet ein Projekt direkt aus der Recent-Liste."""
        from pathlib import Path
        path = Path(path_str)
        try:
            meta = self.window._project_manager.open_project(path)
            self.window.panel_setup._console_append(f"[Projekt] Geoeffnet: {meta.get('name', path.name)}")
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            from services.recent_projects import RecentProjectsManager
            QMessageBox.critical(self.window, "Fehler", str(exc))
            self.window.panel_setup._console_append(f"[Projekt-Fehler] {exc}")
            RecentProjectsManager.clear_entry(path_str)

    def _clear_recent_projects(self) -> None:
        """Loescht die gesamte Recent-Projekte-Liste."""
        from services.recent_projects import RecentProjectsManager
        RecentProjectsManager.clear()
        if hasattr(self.window, "status_bar"):
            self.window.status_bar.showMessage("Letzte Projekte geleert.", 3000)

    def _create_workspaces(self):
        """Creates all 5 workspaces, promotes widgets, wires signals."""
        from ui.workspaces import (
            MediaWorkspace, EditWorkspace, StemsWorkspace,
            ConvertWorkspace, DeliverWorkspace,
        )

        self.window._media_ws = MediaWorkspace()
        self.window.workspace_stack.addWidget(self.window._media_ws)

        # Promote widgets
        self.window.btn_analyze = self.window._media_ws.btn_analyze
        self.window.btn_analyze_video = self.window._media_ws.btn_analyze_video
        self.window.btn_video_pipeline = self.window._media_ws.btn_video_pipeline
        self.window.btn_waveform = self.window._media_ws.btn_waveform
        self.window.btn_stem_separate = self.window._media_ws.btn_stem_separate
        self.window.btn_auto_duck = self.window._media_ws.btn_auto_duck
        self.window.btn_add_to_timeline = self.window._media_ws.btn_add_to_timeline
        self.window.progress_bar = self.window._media_ws.progress_bar
        self.window.search_input = self.window._media_ws.search_input
        self.window.btn_search = self.window._media_ws.btn_search
        self.window.btn_search_clear = self.window._media_ws.btn_search_clear
        self.window.btn_select_all_video = self.window._media_ws.btn_select_all_video
        self.window.video_pool_table = self.window._media_ws.video_pool_table
        self.window.video_pool_model = self.window._media_ws.video_pool_model
        self.window.btn_delete_selected_video = self.window._media_ws.btn_delete_selected_video
        self.window.btn_select_all_audio = self.window._media_ws.btn_select_all_audio
        self.window.audio_pool_table = self.window._media_ws.audio_pool_table
        self.window.audio_pool_model = self.window._media_ws.audio_pool_model
        self.window.btn_delete_selected_audio = self.window._media_ws.btn_delete_selected_audio
        self.window.stem_player = self.window._media_ws.stem_player
        self.window.media_table = self.window._media_ws.media_table

        # Wire MEDIA signals
        self.window._media_ws.btn_import_video.clicked.connect(self.window.import_media._import_video)
        self.window._media_ws.btn_import_audio.clicked.connect(self.window.import_media._import_audio)
        self.window._media_ws.btn_import_folder.clicked.connect(self.window.import_media._import_folder)
        self.window._media_ws.btn_clear_all.clicked.connect(self.window.import_media._clear_all_media)
        self.window.btn_analyze.clicked.connect(self.window.audio_analysis._analyze_selected_audio)
        self.window.btn_analyze_video.clicked.connect(self.window.video_analysis._analyze_selected_video)
        self.window.btn_video_pipeline.clicked.connect(self.window.video_analysis._start_video_pipeline)
        self.window.btn_waveform.clicked.connect(self.window.audio_analysis._analyze_waveform)
        self.window.btn_stem_separate.clicked.connect(self.window.stems._start_stem_separation)
        self.window.btn_auto_duck.clicked.connect(self.window.stems._start_auto_ducking)
        self.window._media_ws.btn_analyze_all.clicked.connect(self.window.audio_analysis._analyze_all_sequential)
        self.window.btn_add_to_timeline.clicked.connect(self.window.edit_workspace._add_selected_to_timeline)
        self.window.search_input.returnPressed.connect(self.window.search._run_semantic_search)
        self.window.btn_search.clicked.connect(self.window.search._run_semantic_search)
        self.window.btn_search_clear.clicked.connect(self.window.search._clear_search)
        self.window.btn_select_all_video.clicked.connect(
            lambda: self.window.media_table_controller._toggle_all_checkboxes(self.window.video_pool_table)
        )
        self.window.btn_select_all_audio.clicked.connect(
            lambda: self.window.media_table_controller._toggle_all_checkboxes(self.window.audio_pool_table)
        )
        self.window.btn_delete_selected_video.clicked.connect(
            lambda: self.window.import_media._delete_selected_media("video")
        )
        self.window.btn_delete_selected_audio.clicked.connect(
            lambda: self.window.import_media._delete_selected_media("audio")
        )
        # Selection sync (Fix F-006: Model/View)
        self.window.video_pool_table.selectionModel().currentChanged.connect(
            lambda curr, prev: self.window.video_analysis._on_video_pool_selected(curr.row(), curr.column(), prev.row(), prev.column())
        )
        self.window.audio_pool_table.selectionModel().currentChanged.connect(
            lambda curr, prev: self.window.audio_analysis._on_audio_pool_selected(curr.row(), curr.column(), prev.row(), prev.column())
        )
        self.window.stem_player.playback_finished.connect(self.window.stems._on_stem_playback_finished)

        # Phase 4: Media-Buttons
        if hasattr(self.window._media_ws, 'btn_key_detect'):
            self.window._media_ws.btn_key_detect.clicked.connect(self.window.audio_analysis._detect_key)
        if hasattr(self.window._media_ws, 'btn_lufs_analyze'):
            self.window._media_ws.btn_lufs_analyze.clicked.connect(self.window.audio_analysis._analyze_lufs)
        if hasattr(self.window._media_ws, 'btn_structure_detect'):
            self.window._media_ws.btn_structure_detect.clicked.connect(self.window.audio_analysis._detect_structure)
        if hasattr(self.window._media_ws, 'btn_motion_analysis'):
            self.window._media_ws.btn_motion_analysis.clicked.connect(self.window.video_analysis._start_video_pipeline)
        if hasattr(self.window._media_ws, 'btn_siglip_embeddings'):
            self.window._media_ws.btn_siglip_embeddings.clicked.connect(self.window.video_analysis._start_video_pipeline)

        # --- EDIT workspace ---
        self.window._edit_ws = EditWorkspace()
        self.window.workspace_stack.addWidget(self.window._edit_ws)

        # Promote widgets
        self.window.video_preview = self.window._edit_ws.video_preview
        self.window.btn_preview_play = self.window._edit_ws.btn_preview_play
        self.window.btn_preview_stop = self.window._edit_ws.btn_preview_stop
        self.window.preview_time_label = self.window._edit_ws.preview_time_label
        self.window.btn_toggle_inspector = self.window._edit_ws.btn_toggle_inspector
        self.window.inspector_panel = self.window._edit_ws.inspector_panel
        self.window.audio_combo = self.window._edit_ws.audio_combo
        self.window.video_combo = self.window._edit_ws.video_combo
        self.window.vibe_input = self.window._edit_ws.vibe_input
        self.window.cut_rate_combo = self.window._edit_ws.cut_rate_combo
        self.window.energy_reactivity_slider = self.window._edit_ws.energy_reactivity_slider
        self.window.energy_reactivity_spin = self.window._edit_ws.energy_reactivity_spin
        self.window.breakdown_combo = self.window._edit_ws.breakdown_combo
        self.window.btn_generate = self.window._edit_ws.btn_generate
        self.window.btn_auto_edit = self.window._edit_ws.btn_auto_edit
        self.window.anchor_list = self.window._edit_ws.anchor_list
        self.window.btn_add_anchor = self.window._edit_ws.btn_add_anchor
        self.window.btn_remove_anchor = self.window._edit_ws.btn_remove_anchor
        self.window.btn_sync_anchors = self.window._edit_ws.btn_sync_anchors
        self.window.btn_learn_ai = self.window._edit_ws.btn_learn_ai
        self.window.btn_keyframe_string = self.window._edit_ws.btn_keyframe_string
        self.window.keyframe_text = self.window._edit_ws.keyframe_text
        self.window.pacing_curve = self.window._edit_ws.pacing_curve
        self.window.timeline_view = self.window._edit_ws.timeline_view
        self.window.cut_info_label = self.window._edit_ws.cut_info_label

        # Wire EDIT signals
        self.window.btn_preview_play.clicked.connect(self.window.edit_workspace._toggle_preview_play)
        self.window.btn_preview_stop.clicked.connect(self.window.video_preview.stop)
        self.window.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        self.window.video_combo.currentIndexChanged.connect(self.window.edit_workspace._on_video_combo_changed)
        self.window.audio_combo.currentIndexChanged.connect(self.window.edit_workspace._on_audio_combo_changed)
        self.window.btn_generate.clicked.connect(self.window.edit_workspace._generate_timeline)
        self.window.btn_auto_edit.clicked.connect(self.window.edit_workspace._auto_edit_to_beat)
        self.window.btn_add_anchor.clicked.connect(self.window.edit_workspace._add_anchor_dialog)
        self.window.btn_remove_anchor.clicked.connect(self.window.edit_workspace._remove_selected_anchor)
        self.window.btn_sync_anchors.clicked.connect(self.window.edit_workspace._sync_anchors)
        self.window.btn_learn_ai.clicked.connect(self.window.edit_workspace._learn_anchor_as_ai_rule)
        self.window.btn_keyframe_string.clicked.connect(self.window.edit_workspace._show_keyframe_strings)
        if hasattr(self.window.pacing_curve, 'curve_changed'):
            self.window.pacing_curve.curve_changed.connect(self.window.edit_workspace._generate_timeline)
        if hasattr(self.window._edit_ws, 'btn_thumbs_up'):
            self.window._edit_ws.btn_thumbs_up.clicked.connect(self.window.edit_workspace._rl_feedback_positive)
        if hasattr(self.window._edit_ws, 'btn_thumbs_down'):
            self.window._edit_ws.btn_thumbs_down.clicked.connect(self.window.edit_workspace._rl_feedback_negative)
        if hasattr(self.window._edit_ws, 'style_preset_combo'):
            self.window._edit_ws.style_preset_combo.currentIndexChanged.connect(self.window.edit_workspace._apply_style_preset)
        self.window.timeline_view.clip_moved.connect(self.window.edit_workspace._on_timeline_clip_moved)

        # Undo/Redo
        from PySide6.QtGui import QAction, QKeySequence
        undo_action = QAction("Undo", self.window)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.window.timeline_view.undo_stack.undo)
        self.window.addAction(undo_action)
        redo_action = QAction("Redo", self.window)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.window.timeline_view.undo_stack.redo)
        self.window.addAction(redo_action)

        self.window.video_preview.position_changed.connect(self.window.edit_workspace._on_preview_position_changed)
        self.window.video_preview.playback_state_changed.connect(self.window.edit_workspace._on_preview_state_changed)

        self.window.timeline_view.play_pause_toggled.connect(self.window.video_preview.toggle_play)
        self.window.timeline_view.stop_requested.connect(self.window.video_preview.stop)
        self.window.timeline_view.seek_forward.connect(lambda delta: self.window.video_preview.seek_relative(delta))
        self.window.timeline_view.seek_backward.connect(lambda delta: self.window.video_preview.seek_relative(-delta))
        self.window.timeline_view.jump_to_start.connect(lambda: self.window.video_preview.seek_to(0.0))
        self.window.timeline_view.jump_to_end.connect(lambda: self.window.video_preview.seek_to(self.window.video_preview.duration))
        self.window.timeline_view.zoom_in_requested.connect(lambda: self.window.timeline_view.zoom_by_factor(1.25))
        self.window.timeline_view.zoom_out_requested.connect(lambda: self.window.timeline_view.zoom_by_factor(1.0 / 1.25))
        self.window.video_preview.position_changed.connect(lambda cur, _total: self.window.timeline_view.set_playhead_time(cur))

        self.window.media_table_controller._refresh_director_combos()

        # --- STEMS workspace ---
        self.window._stems_ws = StemsWorkspace()
        self.window.workspace_stack.addWidget(self.window._stems_ws)
        self.window.stem_workspace = self.window._stems_ws.stem_widget
        self.window.stem_workspace.stem_volume_changed.connect(self.window.stem_player.set_volume)
        self.window.stem_workspace.stem_mute_toggled.connect(self.window.stem_player.set_mute)
        self.window.stem_workspace.play_requested.connect(self.window.stem_player.play)
        self.window.stem_workspace.pause_requested.connect(self.window.stem_player.pause)
        self.window.stem_workspace.stop_requested.connect(self.window.stem_player.stop)
        self.window.stem_workspace.seek_requested.connect(self.window.stem_player.seek)
        self.window.stem_player.position_changed.connect(self.window.stem_workspace.update_position)
        self.window.stem_player.state_changed.connect(self.window.stem_workspace.update_playback_state)

        # --- CONVERT workspace ---
        self.window._convert_ws = ConvertWorkspace()
        self.window.workspace_stack.addWidget(self.window._convert_ws)

        # Promote widgets
        self.window.convert_resolution = self.window._convert_ws.convert_resolution
        self.window.convert_fps = self.window._convert_ws.convert_fps
        self.window.convert_format = self.window._convert_ws.convert_format
        self.window.btn_standardize_all = self.window._convert_ws.btn_standardize_all
        self.window.convert_progress = self.window._convert_ws.convert_progress
        self.window.convert_log = self.window._convert_ws.convert_log
        self.window.effects_clip_combo = self.window._convert_ws.effects_clip_combo
        self.window.brightness_slider = self.window._convert_ws.brightness_slider
        self.window.brightness_label = self.window._convert_ws.brightness_label
        self.window.contrast_slider = self.window._convert_ws.contrast_slider
        self.window.contrast_label = self.window._convert_ws.contrast_label
        self.window.crossfade_slider = self.window._convert_ws.crossfade_slider
        self.window.crossfade_label = self.window._convert_ws.crossfade_label
        self.window.effects_preview = self.window._convert_ws.effects_preview
        self.window.btn_apply_effects = self.window._convert_ws.btn_apply_effects

        self.window.btn_standardize_all.clicked.connect(self.window.convert._standardize_all_videos)
        self.window.effects_clip_combo.currentIndexChanged.connect(self.window.convert._on_effects_clip_changed)
        self.window.btn_apply_effects.clicked.connect(self.window.convert._apply_effects)

        # --- DELIVER workspace ---
        self.window._deliver_ws = DeliverWorkspace()
        self.window.workspace_stack.addWidget(self.window._deliver_ws)

        # Promote widgets
        self.window.production_info = self.window._deliver_ws.production_info
        self.window.export_name_input = self.window._deliver_ws.export_name_input
        self.window.resolution_combo = self.window._deliver_ws.resolution_combo
        self.window.fps_combo = self.window._deliver_ws.fps_combo
        self.window.preset_combo = self.window._deliver_ws.preset_combo
        self.window.btn_export = self.window._deliver_ws.btn_export
        self.window.btn_preview = self.window._deliver_ws.btn_preview
        self.window.btn_refresh_production = self.window._deliver_ws.btn_refresh_production
        self.window.export_progress = self.window._deliver_ws.export_progress
        self.window.export_log = self.window._deliver_ws.export_log
        self.window.render_estimate_label = self.window._deliver_ws.render_estimate_label

        self.window.btn_export.clicked.connect(self.window.export._start_export)
        self.window.btn_preview.clicked.connect(self.window.export._start_preview_export)
        self.window.btn_refresh_production.clicked.connect(self.window.export._refresh_production_info)
        self.window.resolution_combo.currentIndexChanged.connect(lambda: self.window.export._update_render_estimate())
        self.window.fps_combo.currentIndexChanged.connect(lambda: self.window.export._update_render_estimate())
        self.window.preset_combo.currentIndexChanged.connect(lambda: self.window.export._update_render_estimate())
        self.window._deliver_ws.btn_preview_play.clicked.connect(self.window.export._play_preview)
        self.window._deliver_ws.btn_preview_stop.clicked.connect(self.window.export._stop_preview)

    def _on_workspace_changed(self, index: int):
        self.window.workspace_stack.setCurrentIndex(index)
        if index == 3:
            if hasattr(self.window, 'convert'):
                 self.window.convert._refresh_effects_combos()
        elif index == 4:
            if hasattr(self.window, 'export'):
                self.window.export._refresh_production_info()

    def _save_window_state(self) -> None:
        """P9-Step2: Splitter und Docks gibt's nicht mehr — nur den aktiven
        Workspace-Index speichern. Geometrie ist via setFixedSize fest."""
        from PySide6.QtCore import QSettings
        settings = QSettings("PBStudio", "PBStudioApp")
        try:
            settings.setValue("window/workspaceIndex", self.window.workspace_stack.currentIndex())
        except Exception as exc:
            self.logger.debug("save workspaceIndex: %s", exc)
        try:
            settings.setValue("window/rightTabIndex", self.window.right_panel.currentIndex())
        except Exception as exc:
            self.logger.debug("save rightTabIndex: %s", exc)

    def _restore_window_state(self) -> None:
        """P9-Step2: Nur Workspace + Right-Panel-Tab wiederherstellen."""
        from PySide6.QtCore import QSettings
        settings = QSettings("PBStudio", "PBStudioApp")
        workspace_idx = settings.value("window/workspaceIndex")
        if workspace_idx is not None:
            try:
                self.window.nav_bar.set_workspace(int(workspace_idx))
            except (ValueError, TypeError):
                pass
        right_idx = settings.value("window/rightTabIndex")
        if right_idx is not None:
            try:
                self.window.right_panel.setCurrentIndex(int(right_idx))
            except (ValueError, TypeError):
                pass

    def _toggle_inspector(self):
        if self.window.inspector_panel.isVisible():
            self.window.inspector_panel.hide()
            self.window.btn_toggle_inspector.setText("\u25C0")
        else:
            self.window.inspector_panel.show()
            self.window.btn_toggle_inspector.setText("\u25B6")

    def _create_compact_slider(self, label: str, min_val: int, max_val: int, default: int):
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
