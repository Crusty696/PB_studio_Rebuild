"""WorkspaceSetupController — Refactored from WorkspaceSetupMixin."""

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QFrame, QWidget, QMenu,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from ui.base_component import PBComponent


def _migrate_workflow_stage_index(settings) -> None:
    """SCHNITT-Redesign 2026-05-09: alte 5-Tab-Indizes auf 4-Tab-Layout mappen.

    Mapping (5 -> 4):
        0 PROJEKT             -> 0 PROJEKT
        1 MATERIAL & ANALYSE  -> 1 MATERIAL & ANALYSE
        2 AUTO-SCHNITT        -> 2 SCHNITT
        3 REVIEW              -> 2 SCHNITT (collapsed into SCHNITT)
        4 EXPORT              -> 3 EXPORT
    Idempotent via ``window/workflowStageMigratedV2`` flag.
    """
    if settings.value("window/workflowStageMigratedV2", False, type=bool):
        return
    raw = settings.value("window/workflowStageIndex")
    if raw is None:
        settings.setValue("window/workflowStageMigratedV2", True)
        return
    try:
        old = int(raw)
    except (TypeError, ValueError):
        old = 0
    mapping = {0: 0, 1: 1, 2: 2, 3: 2, 4: 3}
    settings.setValue("window/workflowStageIndex", mapping.get(old, 0))
    settings.setValue("window/workflowStageMigratedV2", True)

class WorkspaceSetupController(PBComponent):
    """Controller fuer MainWindow: Workspace-Erstellung und Top-Bar-Aufbau."""

    def _build_top_bar(self, main_layout, app_version: str):
        """Builds the compact workflow top bar."""
        top_bar = QWidget()
        top_bar.setObjectName("top_bar")
        top_bar.setFixedHeight(34)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 0, 10, 0)
        top_layout.setSpacing(6)

        app_title = QLabel(f"PB Studio v{app_version}")
        app_title.setStyleSheet("color: #e8e6e3; font-weight: 700; font-size: 12px; background: transparent;")
        top_layout.addWidget(app_title)

        self.window._project_name_label = QLabel("Kein Projekt")
        self.window._project_name_label.setObjectName("title")
        self.window._project_name_label.setStyleSheet("color: #d4a44a; padding: 0 8px; font-size: 11px;")
        top_layout.addWidget(self.window._project_name_label)

        self.window._save_state_label = QLabel("gespeichert")
        self.window._save_state_label.setStyleSheet("color: #6b7280; font-size: 10px; background: transparent;")
        top_layout.addWidget(self.window._save_state_label)

        top_layout.addStretch()

        self.window._btn_context_panel = QPushButton("Kontext")
        self.window._btn_context_panel.setCheckable(True)
        self.window._btn_context_panel.setChecked(False)
        self.window._btn_context_panel.setFixedHeight(24)
        self.window._btn_context_panel.setToolTip(
            "Kontextpanel mit Tasks, Log und KI-Assistent ein- oder ausklappen."
        )
        top_layout.addWidget(self.window._btn_context_panel)

        self.window._btn_open_brain = QPushButton("Brain")
        self.window._btn_open_brain.setFixedHeight(24)
        self.window._btn_open_brain.setToolTip(
            "Studio Brain direkt oeffnen (Ctrl+B). Zeigt Projektwissen, interne App-Erinnerungen, "
            "Analyse-/Audit-Ansichten und Steuerung. Dieser Bereich ist wichtig genug fuer einen "
            "sichtbaren Top-Bar-Zugriff und liegt deshalb nicht mehr versteckt im Tools-Menue."
        )
        self.window._btn_open_brain.clicked.connect(self.window._open_studio_brain)
        top_layout.addWidget(self.window._btn_open_brain)

        btn_settings = QPushButton("Einstellungen")
        btn_settings.setMaximumWidth(120)
        btn_settings.setFixedHeight(22)
        btn_settings.setToolTip(
            "Einstellungen oeffnen: LLM/Ollama-Backend, Modellwahl und Tastaturkuerzel."
        )
        btn_settings.clicked.connect(self.window.project_management._show_settings)
        top_layout.addWidget(btn_settings)

        self.window._btn_toggle_tasks = QPushButton("Tasks", top_bar)
        self.window._btn_toggle_console = QPushButton("Konsole", top_bar)
        self.window._btn_toggle_chat = QPushButton("KI Chat", top_bar)
        self.window._btn_toggle_tasks.setToolTip("Tasks im Kontextpanel anzeigen.")
        self.window._btn_toggle_console.setToolTip("Log im Kontextpanel anzeigen.")
        self.window._btn_toggle_chat.setToolTip("KI Chat im Kontextpanel anzeigen.")
        for hidden_btn in (
            self.window._btn_toggle_tasks,
            self.window._btn_toggle_console,
            self.window._btn_toggle_chat,
        ):
            hidden_btn.hide()

        tools = QMenu(self.window)
        tools.addAction("Tasks anzeigen", self.window._btn_toggle_tasks.click)
        tools.addAction("Log anzeigen", self.window._btn_toggle_console.click)
        tools.addAction("KI Chat anzeigen", self.window._btn_toggle_chat.click)
        tools.addSeparator()
        tools.addAction("Neues Projekt", self.window.project_management._new_project)
        tools.addAction("Projekt oeffnen", self.window.project_management._open_project)
        tools.addAction("Speichern unter", self.window.project_management._save_project_as)
        tools.addAction("Zuletzt geoeffnete Projekte", self._show_recent_projects_menu)
        tools.addSeparator()
        tools.addAction("Studio Brain (Ctrl+B)", self.window._open_studio_brain)
        tools.addAction("Tastaturkuerzel", self.window.project_management._show_shortcut_help)
        tools.addAction("About", self.window.project_management._show_about)
        btn_tools = QPushButton("Tools")
        btn_tools.setFixedHeight(22)
        btn_tools.setMenu(tools)
        btn_tools.setToolTip("Expertenwerkzeuge und Hilfe.")
        top_layout.addWidget(btn_tools)
        self.window._btn_recent = btn_tools

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
        """Creates all 4 workspaces, promotes widgets, wires signals.

        Phase 10 (2026-05-09): Stack reduced to 4 tabs.
        Stack-Order: 0=PROJEKT, 1=MATERIAL & ANALYSE, 2=SCHNITT, 3=EXPORT.
        ``_edit_ws`` is kept as a *hidden* widget host: it owns the controls
        (audio_combo, video_combo, btn_generate, ...) that the new
        ``SchnittWorkspace`` sub-tabs do not yet provide. Phase 12 will
        clean it up.
        """
        from ui.workspaces import (
            MediaWorkspace, EditWorkspace, StemsWorkspace,
            ConvertWorkspace, DeliverWorkspace,
            MaterialAnalysisWorkspace, ProjectDashboard,
        )
        from ui.workspaces.schnitt_workspace import SchnittWorkspace

        self.window._media_ws = MediaWorkspace()

        # Promote widgets
        self.window.btn_analyze = self.window._media_ws.btn_analyze
        self.window.btn_analyze_video = self.window._media_ws.btn_analyze_video
        self.window.btn_video_pipeline = self.window._media_ws.btn_video_pipeline
        self.window.btn_waveform = self.window._media_ws.btn_waveform
        self.window.btn_stem_separate = self.window._media_ws.btn_stem_separate
        self.window.btn_keyframe_string = self.window._media_ws.btn_keyframe_string
        self.window.keyframe_text = self.window._media_ws.keyframe_text
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

        # --- SCHNITT workspace (Phase 10 Redesign) ---
        # Visible workspace: SchnittWorkspace with sub-tabs (Schnitt / Pacing & Anker
        # / Audio / RL & Notes). The legacy EditWorkspace is kept as a hidden
        # widget host until Phase 12 cleanup, because some controls
        # (audio_combo, video_combo, btn_generate, btn_auto_edit, btn_keyframe_string,
        # energy_reactivity_*, preview_time_label) do not yet
        # exist in the new sub-tabs. EditWorkspaceController consumes them via
        # ``self.window.<attr>`` -- we keep the promotions stable.
        self.window._schnitt_ws = SchnittWorkspace()
        self.window._edit_ws = EditWorkspace()
        self.window._edit_ws.hide()  # legacy host, never shown
        _schnitt_tab_schnitt = self.window._schnitt_ws.editor_view.tab_schnitt
        _schnitt_tab_pacing = self.window._schnitt_ws.editor_view.tab_pacing_anker
        _schnitt_tab_rl = self.window._schnitt_ws.editor_view.tab_rl_notes

        # Promote widgets owned by the visible Schnitt sub-tabs
        self.window.video_preview = _schnitt_tab_schnitt.video_preview
        self.window.timeline_view = _schnitt_tab_schnitt.timeline_view
        self.window.cut_info_label = _schnitt_tab_schnitt.cut_info_label
        self.window.inspector_panel = self.window._schnitt_ws.editor_view.inspector_panel
        self.window.pacing_curve = _schnitt_tab_pacing.pacing_curve
        self.window.cut_rate_combo = _schnitt_tab_pacing.cut_rate_combo
        self.window.vibe_input = _schnitt_tab_pacing.vibe_input
        self.window.breakdown_combo = _schnitt_tab_pacing.breakdown_combo
        self.window.anchor_list = _schnitt_tab_pacing.anchor_list
        self.window.btn_add_anchor = _schnitt_tab_pacing.btn_add_anchor
        self.window.btn_remove_anchor = _schnitt_tab_pacing.btn_remove_anchor
        self.window.btn_sync_anchors = _schnitt_tab_pacing.btn_sync_anchors
        self.window.btn_learn_ai = _schnitt_tab_pacing.btn_learn_ai

        # Promote widgets that still live on the hidden EditWorkspace host
        # Tier-3-Sunset T3.2: audio_combo + video_combo wandern in den
        # SchnittEditorView-Header.
        self.window.btn_preview_play = _schnitt_tab_schnitt.btn_play
        self.window.btn_preview_stop = _schnitt_tab_schnitt.btn_stop
        self.window.preview_time_label = _schnitt_tab_schnitt.time_label
        self.window.audio_combo = self.window._schnitt_ws.editor_view.audio_combo
        self.window.video_combo = self.window._schnitt_ws.editor_view.video_combo
        self.window.energy_reactivity_slider = _schnitt_tab_pacing.reactivity_slider
        self.window.energy_reactivity_spin = _schnitt_tab_pacing.reactivity_spin
        self.window.btn_generate = self.window._schnitt_ws.editor_view.btn_generate
        self.window.btn_auto_edit = self.window._schnitt_ws.editor_view.btn_auto_edit
        self.window.review_keyframe_text = self.window._edit_ws.keyframe_text
        self.window.review_btn_keyframe_string = self.window._edit_ws.btn_keyframe_string

        # Wire EDIT signals
        self.window.btn_preview_play.clicked.connect(self.window.edit_workspace._toggle_preview_play)
        self.window.btn_preview_stop.clicked.connect(self.window.video_preview.stop)
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

        # Tier-3-Sunset T3.5: btn_preview_play/stop sind jetzt der Schnitt-Tab.
        # Doppelte Verdrahtung wäre Doppel-Click, also nur noch die spezifischen
        # Sub-Tab-Signale wiren, die nicht über die Promotion abgedeckt sind.
        _schnitt_tab_pacing.btn_regenerate.clicked.connect(self.window.edit_workspace._generate_timeline)
        _schnitt_tab_rl.feedback_positive.connect(self.window.edit_workspace._rl_feedback_positive)
        _schnitt_tab_rl.feedback_negative.connect(self.window.edit_workspace._rl_feedback_negative)

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

        # --- Workflow shell pages ---
        self.window._project_dashboard = ProjectDashboard()
        self.window._material_analysis_ws = MaterialAnalysisWorkspace(
            self.window._media_ws,
            self.window._convert_ws,
        )
        self.window._analysis_ws = self.window._material_analysis_ws

        self.window._project_dashboard.btn_new_project.clicked.connect(
            self.window.project_management._new_project
        )
        self.window._project_dashboard.btn_open_project.clicked.connect(
            self.window.project_management._open_project
        )
        self.window._project_dashboard.action_requested.connect(self._handle_cockpit_action)

        from services import analysis_status_service

        self.window._cockpit_completion_listener = (
            lambda _media_type, _media_id, _step_key, _summary: (
                self.window._project_dashboard.refresh_requested.emit()
            )
        )
        analysis_status_service.register_completion_listener(
            self.window._cockpit_completion_listener
        )
        self.window.destroyed.connect(
            lambda *_args: self._unregister_cockpit_listener()
        )

        self.window.workspace_stack.addWidget(self.window._project_dashboard)        # 0
        self.window.workspace_stack.addWidget(self.window._material_analysis_ws)     # 1
        self.window.workspace_stack.addWidget(self.window._schnitt_ws)               # 2
        self.window.workspace_stack.addWidget(self.window._deliver_ws)               # 3

    def _handle_cockpit_action(self, action_key: str):
        """Fuehrt genau die vom Guided Cockpit empfohlene Aktion aus."""
        if action_key == "open_project":
            self.window.project_management._open_project()
            return
        if action_key == "open_material_analysis":
            self.window.nav_bar.set_workspace(1)
            return
        if action_key == "run_audio_complete":
            self.window.nav_bar.set_workspace(1)
            if hasattr(self.window._media_ws, "switch_to_audio"):
                self.window._media_ws.switch_to_audio()
            self.window.audio_analysis._analyze_all_sequential()
            return
        if action_key == "run_video_pipeline":
            self.window.nav_bar.set_workspace(1)
            if hasattr(self.window._media_ws, "switch_to_video"):
                self.window._media_ws.switch_to_video()
            self.window.video_analysis._start_video_pipeline()
            return
        if action_key in ("open_schnitt", "open_auto_edit", "open_review"):
            # Phase 10: Auto-Edit and Review collapsed into SCHNITT.
            self.window.nav_bar.set_workspace(2)
            return
        if action_key == "open_export":
            self.window.nav_bar.set_workspace(3)
            return
        self.logger.warning("Unbekannte Cockpit-Aktion: %s", action_key)

    def _unregister_cockpit_listener(self):
        listener = getattr(self.window, "_cockpit_completion_listener", None)
        if listener is None:
            return
        try:
            from services import analysis_status_service
            analysis_status_service.unregister_completion_listener(listener)
        except Exception as exc:
            self.logger.debug("cockpit listener unregister failed: %s", exc)
        self.window._cockpit_completion_listener = None

    def _on_workspace_changed(self, index: int):
        self._update_workflow_gates()
        if index == 0:
            self.window.workspace_stack.setCurrentIndex(0)
            self._refresh_project_dashboard()
            return
        if index == 1:
            self.window.workspace_stack.setCurrentIndex(1)
            if hasattr(self.window, 'convert'):
                self.window.convert._refresh_effects_combos()
            return
        if index == 2:
            self.window.workspace_stack.setCurrentIndex(2)
            if hasattr(self.window._schnitt_ws, "refresh_state_from_db"):
                try:
                    self.window._schnitt_ws.refresh_state_from_db()
                except Exception as exc:
                    self.logger.debug("schnitt refresh failed: %s", exc)
            self.window.media_table_controller._refresh_director_combos()
            return
        if index == 3:
            self.window.workspace_stack.setCurrentIndex(3)
            if hasattr(self.window, 'export'):
                self.window.export._refresh_production_info()
            return

    def _update_workflow_gates(self):
        """Keep primary actions honest about their prerequisites."""
        audio_ready = False
        video_ready = False
        try:
            audio_ready = self.window.audio_combo.count() > 0
            video_ready = self.window.video_combo.count() > 0
        except Exception:
            pass
        media_ws = getattr(self.window, "_media_ws", None)
        try:
            if not audio_ready and media_ws is not None:
                audio_ready = media_ws.audio_pool_model.rowCount() > 0
            if not video_ready and media_ws is not None:
                video_ready = media_ws.video_pool_model.rowCount() > 0
        except Exception as exc:
            self.logger.debug("media pool readiness unavailable: %s", exc)

        can_auto_edit = audio_ready and video_ready
        for attr in ("btn_generate", "btn_auto_edit"):
            btn = getattr(self.window, attr, None)
            if btn is not None:
                btn.setEnabled(can_auto_edit)
                if can_auto_edit:
                    btn.setToolTip("Pacing berechnen und Timeline erzeugen.")
                else:
                    btn.setToolTip(
                        "Erst Audio und Video importieren/analysieren. "
                        "Danach ist Auto-Schnitt bedienbar."
                    )

        for attr in ("btn_stem_separate",):
            btn = getattr(self.window, attr, None)
            if btn is not None:
                btn.setEnabled(audio_ready)
                btn.setToolTip(
                    "Stems fuer ausgewaehlte Audiospur erzeugen."
                    if audio_ready
                    else "Erst eine Audiospur importieren oder auswaehlen."
                )
        analysis_ws = getattr(self.window, "_analysis_ws", None)
        if analysis_ws is not None:
            analysis_ws.btn_stems.setEnabled(audio_ready)
            analysis_ws.btn_stems.setToolTip(
                "Stems fuer die aktive Audiospur erzeugen."
                if audio_ready
                else "Stems sind erst mit importierter Audiospur verfuegbar."
            )
            analysis_ws.btn_video_pipeline.setEnabled(video_ready)
            analysis_ws.btn_video_pipeline.setToolTip(
                "Videoanalyse fuer importierte Clips starten."
                if video_ready
                else "Video-Pipeline braucht mindestens einen importierten Clip."
            )

        for attr in ("btn_standardize_all", "btn_apply_effects"):
            btn = getattr(self.window, attr, None)
            if btn is not None:
                btn.setEnabled(video_ready)
                btn.setToolTip(
                    "Videoquellen standardisieren oder Clip-Effekte anwenden."
                    if video_ready
                    else "Convert ist erst mit importiertem Video sinnvoll."
                )

        export_btn = getattr(self.window, "btn_export", None)
        preview_btn = getattr(self.window, "btn_preview", None)
        timeline_ready = False
        try:
            timeline_ready = bool(getattr(self.window.timeline_view, "clip_items", None))
        except Exception:
            timeline_ready = True
        for btn in (export_btn, preview_btn):
            if btn is not None:
                btn.setEnabled(timeline_ready)
                if not timeline_ready:
                    btn.setToolTip("Erst Timeline erzeugen oder Clips hinzufuegen.")

    def _refresh_project_dashboard(self):
        dashboard = getattr(self.window, "_project_dashboard", None)
        if dashboard is None:
            return
        label = getattr(self.window, "_project_name_label", None)
        name = label.text() if label is not None and label.text() else None
        path = None
        manager = getattr(self.window, "_project_manager", None)
        project_id = None
        try:
            current = getattr(manager, "current_project_path", None)
            if current is not None:
                path = str(current)
        except Exception as exc:
            self.logger.debug("dashboard project path unavailable: %s", exc)
        try:
            from database import get_active_project_id
            project_id = get_active_project_id()
        except Exception as exc:
            self.logger.debug("dashboard project id unavailable: %s", exc)
        dashboard.update_project(name, path, project_id=project_id)
        dashboard.refresh(project_id)

    def _save_window_state(self) -> None:
        """Persist workflow stage and context-panel tab."""
        from PySide6.QtCore import QSettings
        settings = QSettings("PBStudio", "PBStudioApp")
        try:
            settings.setValue("window/workflowStageIndex", self.window.nav_bar._current_index)
        except Exception as exc:
            self.logger.debug("save workflowStageIndex: %s", exc)
        try:
            settings.setValue("window/rightTabIndex", self.window.right_panel.currentIndex())
        except Exception as exc:
            self.logger.debug("save rightTabIndex: %s", exc)

    def _restore_window_state(self) -> None:
        """Restore workflow stage and context-panel tab."""
        from PySide6.QtCore import QSettings
        settings = QSettings("PBStudio", "PBStudioApp")
        _migrate_workflow_stage_index(settings)
        workspace_idx = settings.value("window/workflowStageIndex")
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
        slider.setToolTip(
            f"{label}: Wert zwischen {min_val} und {max_val} einstellen."
        )
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
