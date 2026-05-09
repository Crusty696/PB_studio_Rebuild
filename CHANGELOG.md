# Changelog

All notable changes to PB Studio.

## [Unreleased] — feat/schnitt-redesign-2026-05-09

### SCHNITT Workspace Redesign (2026-05-09)

Complete rebuild of the Auto-Edit and Review areas into one unified **SCHNITT** tab. Top-level navigation reduced from 5 to 4 tabs.

**Branch:** `feat/schnitt-redesign-2026-05-09`
**Commit range:** `3476b33` … `bf998fc` + Tier 1-5 hardening (`a5f5194` … `bf998fc`)
**Spec:** `docs/superpowers/specs/2026-05-09-schnitt-workspace-redesign.md`
**Plan:** `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/`

#### Added
- **SCHNITT tab** — Master workspace replacing `AUTO-SCHNITT` + `REVIEW`. `QStackedWidget` with three states: Empty (preset Quick-Lane), Loading (worker stage progress), Editor (4 sub-tabs).
- **Sub-Tabs** (Editor state):
  - *Schnitt* — Preview 640×360 + Transport + `InteractiveTimeline` with per-clip Lock-icons (gold border + DB-persistence via `ToggleClipLockCommand`).
  - *Pacing & Anker* — `PacingCurveWidget` (≥ 280 px), Cut-Rate / Style (9 presets) / Breakdown / Reactivity / Vibe inputs, Re-Generate button, Anchor TreeWidget.
  - *Audio* — `WaveformGraphicsItem` with beatgrid + structure markers (Intro/Drop/Outro/Buildup/Breakdown), `StemWorkspace` mixer, LUFS + Tonart in header.
  - *RL & Notes* — RL feedback buttons + `QListWidget` event-list + Markdown `QTextEdit` with auto-save (1 s debounce, `ProjectNotesService`).
- **Persistent `ClipInspectorPanel`** as right-column across all 4 sub-tabs (HBox stretch 3:1).
- **Data services** (`services/`):
  - `pacing_profile.py` — `PacingProfile` dataclass + 4 presets (Techno/Cinematic/House/Festival) + `to_advanced_settings()`.
  - `timeline_state.py` — `TimelineState` with `load(project_id)` + `save_snapshot(label)`.
  - `timeline_snapshot_service.py` — `create_snapshot` / `list_snapshots` / `restore_snapshot` (lock-aware DELETE/INSERT).
  - `project_notes_service.py` — `get_notes(pid) -> str`, `update_notes(pid, content_md) -> datetime` (SQLite Upsert via `ON CONFLICT(project_id) DO UPDATE`).
  - `ui_binder.py` — `PacingProfileBinder` bidirectional with `dispose()`, `QSignalBlocker` re-entrancy guard, case-insensitive `findText`, `@Slot` decorators, range-mismatch assertion.
- **Building blocks**:
  - `ui/widgets/wheel_guard.py` — Application-wide `QObject.eventFilter` blocking wheel events on `QComboBox`/`QSlider`/`QSpinBox`/`QDoubleSpinBox` when unfocused. Mounted on `app` in `main.py`.
  - `ui/widgets/lock_icon_item.py` — `QGraphicsRectItem` lock-state visual (top-right of each clip).
  - `ui/undo_commands.py::ToggleClipLockCommand` — `QUndoCommand` with DB-write + view-sync + `mergeWith` (within 500 ms).
- **Worker stage-progress**:
  - `workers/edit.py::AutoEditWorker.progress` — overloaded `Signal((str, float), (int, str))` for new + B-076-legacy.
  - `EditWorkspaceController._generate_timeline_impl::_CutsWorker.progress` — `Signal(str, float)`.
  - `services/auto_edit_worker.py` — re-export shim.
- **Controller**:
  - `ui/controllers/schnitt_controller.py::SchnittController` — instantiates `PacingProfileBinder`, routes worker `progress` → `workspace.show_progress`, handles `cancel_requested`, drives Empty-State preset clicks → `request_auto_edit_with_profile`, drives `btn_regenerate` → `confirm_regenerate` → `request_regenerate`. Selection-source wiring `InteractiveTimeline → ClipInspectorPanel.set_clip()`.

#### Changed
- **Top navigation** (`ui/widgets/nav_bar.py`): `["PROJEKT", "MATERIAL & ANALYSE", "SCHNITT", "EXPORT"]` (was `["PROJEKT", "MATERIAL & ANALYSE", "AUTO-SCHNITT", "REVIEW", "EXPORT"]`). Tooltips, accessible_names, status_tips updated.
- **Workspace stack** (`ui/controllers/workspace_setup.py`): 4 widgets at indices 0/1/2/3.
- **Cockpit orchestrator** (`services/cockpit_orchestrator.py`): new `ACTIONS["open_schnitt"]`. Legacy `open_auto_edit` and `open_review` aliased to `key="open_schnitt"`. `open_export.target_workspace`: 4 → 3.
- **`apply_auto_edit_segments`** (`services/timeline_service.py::_do_apply_segments`) — now lock-aware. Locked video entries are preserved; new segments overlapping a locked range are clamped or discarded; sorted `locked_ranges` for deterministic order.
- **DB Schema**:
  - `TimelineEntry.locked` BOOLEAN DEFAULT 0 (idempotent migration).
  - New `TimelineSnapshot(id, project_id, version, label, payload_json, created_at)`.
  - New `ProjectNote(id, project_id UNIQUE, content_md, updated_at)`.
- **QSettings migration v2** (`ui/controllers/workspace_setup.py::_migrate_workflow_stage_index`) — idempotent via `window/workflowStageMigratedV2`. Mapping `{0:0, 1:1, 2:2, 3:2, 4:3}`.
- **`e2e_render_test.py:141`** — `setCurrentIndex(4)` → `(3)` (4-tab layout).

#### Removed
- **`ui/workspaces/edit_workspace.py`** — `EditWorkspace` widget class (~483 LOC) deleted as part of Tier-3 Sunset (commit `db275a0`). All 12 widget promotions migrated to Sub-Tab sources. `_apply_style_preset` now reads from `tab_pacing_anker` widgets.
- **`btn_toggle_inspector`** (workspace_setup + edit_workspace) — dead code; the persistent inspector replaces toggle behavior.
- Test entry `"btn_toggle_inspector"` removed from `tests/ui/test_tooltip_coverage_static.py`.

#### Tests
- 29 new test files / suites covering DB migrations, all 5 Phase-02 services, all 3 Phase-03 building blocks, all Sub-Tabs, lock-aware `_do_apply_segments`, SchnittController wiring, QSettings migration, lock-icon click, parametrized clamp cases, multi-lock, backward-compat `video_id` key.
- Coverage sweep (Tier 5): +47 tests across `ProjectNotesService`, `PacingProfileBinder`, `WheelGuard`, `LockIconItem`, `ToggleClipLockCommand`, `_do_apply_segments`, `SchnittWorkspace`, `TimelineClipItem-Lock`, `TimelineSnapshotService`, `Confirm-Dialog`, `SchnittController`.
- Final regression: **1427 passed**, 1 failed (`test_b222a_pipeline_worker_has_preflight` — pre-existing, unrelated), 2 skipped.

#### Status
Plan-implementation complete on branch `feat/schnitt-redesign-2026-05-09`. **Pending:** user live-verify (16-step click-walkthrough in `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/12_LIVE_VERIFY_USER_GUIDE.md`). User sets vault `status: fixed` after verify.

---
