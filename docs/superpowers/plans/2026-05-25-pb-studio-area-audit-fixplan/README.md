# PB Studio Area Audit Fixplan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the approved findings from `PB-STUDIO-AREA-AUDIT-2026-05-24` in priority order, starting with B-348 so global pytest collection becomes usable again.

**Architecture:** Work one bug at a time. Each bug needs root-cause read, failing/proving test, minimal code/test change, targeted verification, Vault update, and honest live status. No `fixed` marker unless the relevant real app workflow is live-verified.

**Tech Stack:** Python 3.10 conda env `pb-studio`, pytest, PySide6 offscreen tests, SQLite/SQLAlchemy, Windows PowerShell, Vault notes.

---

## Scope

Authorized by user on 2026-05-25 after final audit synthesis.

This plan authorizes fixes for documented audit bugs B-348 through B-430. Work order is strict:

1. B-348 first.
2. High severity in bug-ID order unless a direct dependency forces a narrower prerequisite.
3. Medium severity in bug-ID order.
4. Low severity in bug-ID order.

No unrelated refactors, feature work, library swaps, model changes, Audio-V2 porting, or unlisted fixes.

## Current Task

### Task 34: B-396 Export source range not bounded by clip duration

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-396-export-source-range-not-bounded-by-clip-duration.md`

- [ ] **Step 1: Read B-396 and source range duration bounds**
- [ ] **Step 2: Reproduce/prove the documented defect with a failing test**
- [ ] **Step 3: Minimal fix**
- [ ] **Step 4: Run targeted tests + global collect-only**
- [ ] **Step 5: Update Vault and status with exact evidence**

## Completed Tasks

### Task 33: B-395 Export source range can be zero or negative

Result 2026-05-26: `services/export_service.py` validates `source_duration <= 0`
before Export/FFmpeg for timeline export and preview. Pre-fix RED reached export path;
post-fix direct `1 passed`; Export-near `6 passed`; Core ExportService `1 passed`;
collect-only `2251 tests collected`. Vault `code-fix-pending-live-verification`; no live export.

### Task 32: B-394 Agent export action passes output_path as output_name

Result 2026-05-26: `services/actions/edit_actions.py` validates agent `output_path`
as filename-only and updates schema wording. Pre-fix RED emitted absolute path as
`output_name`; post-fix direct `2 passed`; Agent/Wiring-near `53 passed`; collect-only
`2250 tests collected`. Vault `code-fix-pending-live-verification`; no live action workflow run.

### Task 31: B-393 Export output_name can escape export dir

Result 2026-05-26: `services/export_service.py` validates `output_name` before DB/FFmpeg
as filename-only; absolute paths, drive names, separators and `..` are rejected.
Pre-fix RED opened DB before validation; post-fix direct `1 passed`; Export-near
`5 passed`; Core ExportService `1 passed`; collect-only `2248 tests collected`.
Vault `code-fix-pending-live-verification` because no live export was run.

### Task 30: B-392 ConvertWorkspace smoke test contract drift

Result 2026-05-26: `tests/ui/test_workspaces_smoke.py` expects documented
Convert tabs `PREFLIGHT` and `EFFEKTE`. Pre-fix RED `2 == 1`; post-fix direct
`1 passed`; Workspace-Smoke `7 passed`; Convert/tooltip-near `3 passed`; collect-only
`2247 tests collected`. Vault `fixed`; no app code changed.

### Task 29: B-391 FrameExtract error message can lose root cause

Result 2026-05-26: `workers/video.py` ffmpeg `-v quiet` → `-v error`; Exitcode-Fallback
bei leerem stderr. Pre-fix FAIL; post-fix B-391 `2 passed`; collect-only `2247`.
Vault `code-fix-pending-live-verification`.

### Task 28: B-390 Convert effect preview stale worker can overwrite latest preview

Result 2026-05-26: `ui/controllers/convert.py` monotone `_effect_request_seq`; `_on_effect_frame_ready`
verwirft aeltere Requests. Pre-fix FAIL; post-fix B-390 `2 passed`; collect-only `2245`.
Vault `code-fix-pending-live-verification`.

### Task 27: B-389 Media grid thumbnail late signal can target deleted card

Result 2026-05-26: `ui/widgets/media_grid.py` neue Static-Method `_apply_thumbnail` faengt
`RuntimeError` (geloeschte Card) ab; done-Slot nutzt sie. Pre-fix FAIL; post-fix B-389
`2 passed`; media-grid `11 passed`; collect-only `2243`. Vault `code-fix-pending-live-verification`.

### Task 26: B-388 Media grid thumbnail worker creates QPixmap off GUI thread

Result 2026-05-26: `_ThumbWorker._extract()` liefert `QImage`; neuer `_placeholder_image`;
GUI-Thread-Slot wandelt via `QPixmap.fromImage`. Pre-fix FAIL; post-fix B-388 `2 passed`;
media-grid `9 passed`; collect-only `2241`. Vault `code-fix-pending-live-verification`.

### Task 25: B-387 VideoPreview can show stale frame after load_video

Result 2026-05-25: `_active_request_path` getrackt; `_on_frame_ready` verwirft Frames
fremder Pfade. Pre-fix FAIL; post-fix B-387 `2 passed`; preview-nah `4 passed`;
collect-only `2239`. Vault `code-fix-pending-live-verification`.

### Task 24: B-386 Waveform band length mismatch can crash paint

Result 2026-05-25: `WaveformGraphicsItem.__init__` normalisiert band_mid/high auf
`len(band_low)` (`_fit_band_length`). Pre-fix FFF (IndexError); post-fix B-386 `3 passed`;
waveform `5 passed`; collect-only `2237`. Vault `code-fix-pending-live-verification`.

### Task 23: B-385 Schnitt audio grid render clears waveform

Result 2026-05-25: `render_grid_lines` leert die Scene nicht mehr; Grid-Lines via
`_grid_line_items` getrackt; Waveform bleibt erhalten. Pre-fix FAIL; post-fix B-385
`2 passed`; audio-subtab `11 passed`; collect-only `2234`. Vault `code-fix-pending-live-verification`.

### Task 22: B-384 Invisible anchors cannot be removed from context menu

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-384-invisible-anchors-cannot-be-removed-from-context-menu.md`

**Files:**
- Modify: `ui/timeline.py`
- Test: `tests/ui/test_schnitt_controller_wiring.py`
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-384-invisible-anchors-cannot-be-removed-from-context-menu.md`

- [x] **Step 1: Read B-384 and timeline context-menu / anchor paths**
- [x] **Step 2: Reproduce/prove remove action missing for invisible anchors**
- [x] **Step 3: Gate remove action on `_anchor_markers or _all_anchor_offsets`**
- [x] **Step 4: Run targeted Schnitt UI tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-384 repro pre-fix failed: anchor at 50s (x_px >> width 100px) produced no marker; context menu lacked "Alle Anker entfernen".
- Direct B-384 test: Exit 0, `1 passed`.
- `tests/ui/test_schnitt_controller_wiring.py`: Exit 0, `20 passed`.
- `tests/ui` package: `419 passed, 2 failed`; both failures pre-existing (verified via `git stash`), unrelated to B-384.
- `pytest --collect-only -q`: Exit 0, `2232 tests collected`.
- Vault `B-384`: `code-fix-pending-live-verification` (live GUI by user).

### Task 21: B-383 Timeline load has Brain V3 state write side effect (user-gated)

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-383-timeline-load-has-brain-v3-write-side-effect.md`

Code-fix committed in `925a5fc` (sync removed from `TimelineDBWorker` load path). Status
`code-fix-pending-live-verification`; user skipped on 2026-05-25 pending live GUI verify.

### Task 20: B-382 Timeline anchor sync can write negative start_time to DB

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-382-timeline-anchor-sync-can-write-negative-start-time.md`

**Files:**
- Modify: `ui/timeline.py`
- Test: Timeline anchor sync negative start regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-382-timeline-anchor-sync-can-write-negative-start-time.md`

- [x] **Step 1: Read B-382 and timeline anchor sync DB update path**
- [x] **Step 2: Reproduce/prove negative DB start_time**
- [x] **Step 3: Clamp DB start_time to same value as UI position**
- [x] **Step 4: Run targeted timeline anchor tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-382 repro pre-fix failed: DB `TimelineEntry.start_time` became `-4.0` while UI x was clamped to 0.
- Direct B-382 test: Exit 0, `1 passed`.
- Timeline/Schnitt nearby package: Exit 0, `60 passed`.
- `pytest --collect-only -q`: Exit 0, `2231 tests collected`.
- Vault `B-382`: `fixed`.

### Task 19: B-381 Timeline anchor sync cache stale after add or remove

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-381-timeline-anchor-sync-cache-stale-after-add-or-remove.md`

**Files:**
- Modify: `ui/timeline.py`
- Test: Timeline anchor cache sync regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-381-timeline-anchor-sync-cache-stale-after-add-or-remove.md`

- [x] **Step 1: Read B-381 and timeline anchor add/remove/sync paths**
- [x] **Step 2: Reproduce/prove `_anchor_map` remains stale**
- [x] **Step 3: Update anchor cache on add/remove before sync**
- [x] **Step 4: Run targeted timeline anchor tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-381 repro pre-fix failed: `_anchor_map` stayed empty after `add_anchor_at()` without reload.
- Direct B-381 test: Exit 0, `1 passed`.
- Timeline/Schnitt nearby package: Exit 0, `59 passed`.
- `pytest --collect-only -q`: Exit 0, `2230 tests collected`.
- Vault `B-381`: `fixed`.

### Task 18: B-380 ClipInspector async load can apply stale clip values

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-380-clip-inspector-async-load-stale-result-race.md`

**Files:**
- Modify: `ui/clip_inspector.py`
- Test: ClipInspector stale async load regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-380-clip-inspector-async-load-stale-result-race.md`

- [x] **Step 1: Read B-380 and ClipInspector async load paths**
- [x] **Step 2: Reproduce/prove stale load can overwrite current UI**
- [x] **Step 3: Include entry_id in async load signal and ignore stale results**
- [x] **Step 4: Run targeted ClipInspector tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-380 repro pre-fix failed: stale A values overwrote visible B values.
- Direct B-380 test: Exit 0, `1 passed`.
- Schnitt UI nearby package: Exit 0, `34 passed`.
- `pytest --collect-only -q`: Exit 0, `2229 tests collected`.
- Vault `B-380`: `fixed`.

### Task 17: B-379 ClipInspector debounce can write to wrong selected clip

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-379-clip-inspector-debounce-can-write-wrong-clip.md`

**Files:**
- Modify: `ui/clip_inspector.py`
- Test: ClipInspector debounce entry-id regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-379-clip-inspector-debounce-can-write-wrong-clip.md`

- [x] **Step 1: Read B-379 and ClipInspector debounce paths**
- [x] **Step 2: Reproduce/prove pending edit can land on new selection**
- [x] **Step 3: Capture entry_id with pending debounced change**
- [x] **Step 4: Run targeted ClipInspector tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-379 repro pre-fix failed: Clip A remained unchanged after edit+selection switch; pending write targeted current Clip B.
- Direct B-379 test: Exit 0, `1 passed`.
- Schnitt UI nearby package: Exit 0, `33 passed`.
- `pytest --collect-only -q`: Exit 0, `2228 tests collected`.
- Vault `B-379`: `fixed`.

### Task 16: B-378 Memory updater can run synchronously on GUI thread or double-flush

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-378-memory-updater-can-run-synchronously-or-double-flush.md`

**Files:**
- Modify: `workers/memory_updater.py`
- Test: memory updater thread-safety / no GUI-thread synchronous flush tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-378-memory-updater-can-run-synchronously-or-double-flush.md`

- [x] **Step 1: Read B-378 and memory updater / timeline feedback paths**
- [x] **Step 2: Reproduce/prove synchronous GUI-path flush or double flush**
- [x] **Step 3: Make feedback notification non-blocking and single-flush guarded**
- [x] **Step 4: Run targeted memory updater tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-378 repro pre-fix failed: batch trigger blocked caller for 2 seconds; concurrent threshold trigger started two flushes.
- Memory updater thread-safety tests: Exit 0, `3 passed`.
- Memory updater / Brain wiring / Pattern nearby package: Exit 0, `26 passed`.
- `pytest --collect-only -q`: Exit 0, `2227 tests collected`.
- Vault `B-378`: `fixed`.

### Task 15: B-376 RL verdict vocabulary does not match pattern aggregator

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-376-rl-verdict-vocabulary-does-not-match-pattern-aggregator.md`

**Files:**
- Modify: `services/pacing/pattern_aggregator.py`
- Test: RL verdict normalization / pattern aggregation regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-376-rl-verdict-vocabulary-does-not-match-pattern-aggregator.md`

- [x] **Step 1: Read B-376 and RL memory / pattern aggregator paths**
- [x] **Step 2: Reproduce/prove good/bad verdicts are ignored**
- [x] **Step 3: Normalize verdict vocabulary at writer or aggregator boundary**
- [x] **Step 4: Run targeted RL memory / pattern aggregator tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-376 repro pre-fix failed: `good`/`bad` created no `mem_learned_pattern` row.
- Direct B-376 test: Exit 0, `1 passed`.
- RL/Pattern nearby package: Exit 0, `40 passed`.
- `pytest --collect-only -q`: Exit 0, `2226 tests collected`.
- Vault `B-376`: `fixed`.

### Task 14: B-375 Legacy pacing memory ignores soft-delete

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-375-legacy-pacing-memory-ignores-soft-delete.md`

**Files:**
- Modify: `services/pacing_memory.py`
- Test: legacy pacing memory soft-delete regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-375-legacy-pacing-memory-ignores-soft-delete.md`

- [x] **Step 1: Read B-375 and legacy pacing memory paths**
- [x] **Step 2: Reproduce/prove soft-deleted media is used**
- [x] **Step 3: Filter active AudioTrack/Scene rows before memory writes**
- [x] **Step 4: Run targeted pacing memory tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-375 repro pre-fix failed: soft-deleted AudioTrack, Scene via soft-deleted VideoClip, and RL feedback still wrote `AIPacingMemory`.
- `tests/test_services/test_pacing_memory.py`: Exit 0, `18 passed`.
- Pacing/Memory nearby package: Exit 0, `206 passed`.
- `pytest --collect-only -q`: Exit 0, `2225 tests collected`.
- Vault `B-375`: `fixed`.

### Task 13: B-372 Brain V3 embedding cache model variants

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-372-brain-v3-embedding-cache-skips-or-overwrites-model-variants.md`

**Files:**
- Modify: `services/brain_v3/embedding_scheduler.py`
- Modify: `services/brain_v3/storage/embedding_cache.py`
- Add: `services/brain_v3/storage/sql_migrations/embedding_cache/003_embedding_index_model_variant_pk.sql`
- Test: Brain V3 embedding cache variant tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-372-brain-v3-embedding-cache-skips-or-overwrites-model-variants.md`

- [x] **Step 1: Read B-372 and Brain V3 embedding cache/scheduler paths**
- [x] **Step 2: Reproduce/prove variant skip/overwrite**
- [x] **Step 3: Make cache key include model_name + model_version everywhere**
- [x] **Step 4: Run targeted Brain V3 cache tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-372 repro pre-fix failed: variant 1 lookup returned `None`; Scheduler returned `job_id=None` on other-variant cache row.
- Brain V3 cache/scheduler tests: Exit 0, `21 passed`.
- Brain V3 nearby package: Exit 0, `89 passed`.
- `pytest --collect-only -q`: Exit 0, `2222 tests collected`.
- Vault `B-372`: `fixed`.

### Task 12: B-369 Video soft-deleted clips can still be processed or returned

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-369-video-soft-deleted-clips-can-still-be-processed-or-returned.md`

**Files:**
- Modify: `services/video_analysis_service.py`
- Modify: `services/actions/video_actions.py`
- Modify: `workers/video.py`
- Test: soft-delete filtering/processing regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-369-video-soft-deleted-clips-can-still-be-processed-or-returned.md`

- [x] **Step 1: Read B-369 and soft-delete video query/processing paths**
- [x] **Step 2: Reproduce/prove soft-deleted clips can be processed or returned**
- [x] **Step 3: Filter/guard soft-deleted clips in affected paths**
- [x] **Step 4: Run targeted soft-delete/video tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-369 repros: Exit 0, `3 passed`.
- Video/action/search-near package: Exit 0, `57 passed`.
- `pytest --collect-only -q`: Exit 0, `2221 tests collected`.
- Vault `B-369`: `fixed`.

### Task 11: B-368 Video VectorDB stale/orphan embeddings

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-368-video-vectordb-can-retain-stale-or-orphan-embeddings.md`

**Files:**
- Modify: `services/video_analysis_service.py`
- Test: video VectorDB stale/orphan regression tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-368-video-vectordb-can-retain-stale-or-orphan-embeddings.md`

- [x] **Step 1: Read B-368 and video VectorDB store/delete order**
- [x] **Step 2: Reproduce/prove stale or orphan VectorDB rows**
- [x] **Step 3: Make VectorDB delete failure transactional and prevent orphan writes**
- [x] **Step 4: Run targeted video/vector tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-368 repros: Exit 0, `2 passed`.
- Video/vector-near package: Exit 0, `30 passed`.
- `pytest --collect-only -q`: Exit 0, `2218 tests collected`.
- Vault `B-368`: `fixed`.

### Task 10: B-364 Video orchestrator unload on listener/checkpoint failure

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-364-video-orchestrator-can-skip-gpu-unload-if-listener-or-checkpoint-fails.md`

**Files:**
- Modify: `services/video_pipeline/orchestrator.py`
- Test: video-pipeline unload safety tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-364-video-orchestrator-can-skip-gpu-unload-if-listener-or-checkpoint-fails.md`

- [x] **Step 1: Read B-364 and orchestrator listener/checkpoint/unload order**
- [x] **Step 2: Reproduce/prove unload is skipped when listener/checkpoint throws**
- [x] **Step 3: Guarantee stage unload in failure paths**
- [x] **Step 4: Run targeted orchestrator unload tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-364 adjacent tests: Exit 0, `13 passed`.
- Video-pipeline-near package: Exit 0, `30 passed`.
- `pytest --collect-only -q`: Exit 0, `2216 tests collected`.
- Vault `B-364`: `fixed`.

### Task 9: B-363 Video pipeline cancel checkpoint status

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-363-video-pipeline-cancel-can-be-checkpointed-as-done.md`

**Files:**
- Modify: `services/video_pipeline/stages/raft_motion_stage.py`
- Modify: `services/video_pipeline/stages/siglip_embed_stage.py`
- Modify: `services/video_pipeline/stages/keyframe_extract_stage.py`
- Modify: `services/video_pipeline/orchestrator.py`
- Test: video-pipeline stage cancel checkpoint tests
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-363-video-pipeline-cancel-can-be-checkpointed-as-done.md`

- [x] **Step 1: Read B-363 and affected video-pipeline stage cancel paths**
- [x] **Step 2: Reproduce/prove cancelled stages can return done**
- [x] **Step 3: Return non-done status on cancel and prevent done checkpoint**
- [x] **Step 4: Run targeted video-pipeline stage/orchestrator tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- B-363 repros: Exit 0, `4 passed`.
- Video-pipeline-near package: Exit 0, `28 passed`.
- `pytest --collect-only -q`: Exit 0, `2214 tests collected`.
- Vault `B-363`: `fixed`.

### Task 8: B-362 ProxyCreationWorker cancel terminal signal

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-362-proxycreationworker-cancel-can-emit-no-terminal-signal.md`

**Files:**
- Modify: `workers/import_export.py`
- Modify: `ui/controllers/video_analysis.py`
- Test: proxy worker cancel test and controller cancel-status test
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-362-proxycreationworker-cancel-can-emit-no-terminal-signal.md`

- [x] **Step 1: Read B-362 and ProxyCreationWorker cancel paths**
- [x] **Step 2: Reproduce/prove cancel can return without terminal signal**
- [x] **Step 3: Emit exactly one terminal signal for pre-start and post-acquire cancel**
- [x] **Step 4: Run targeted proxy worker tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- Repro test: pre-fix `finished == []` for pre-start and post-acquire cancel.
- Worker/Controller-near package: Exit 0, `37 passed`.
- `pytest --collect-only -q`: Exit 0, `2210 tests collected`.
- Vault `B-362`: `fixed`.

### Task 7: B-357 Audio analysis cancel handling

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-357-audio-analysis-cancel-does-not-stop-base-workers.md`

**Files:**
- Modify: `workers/audio_analysis.py`
- Test: audio-analysis worker cancel test
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-357-audio-analysis-cancel-does-not-stop-base-workers.md`

- [x] **Step 1: Read B-357 and BaseAnalysisWorker cancel path**
- [x] **Step 2: Reproduce/prove cancelled worker can persist after cancel**
- [x] **Step 3: Add cancel checks before/after analysis and before DB save**
- [x] **Step 4: Run targeted audio worker tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- Repro test: cancel during `_analyze()` no longer persists after cancel.
- Audio-near package: Exit 0, `13 passed`.
- `pytest --collect-only -q`: Exit 0, `2206 tests collected`.
- Vault `B-357`: `fixed`.

### Task 6: B-354 StemSeparationWorker constructor mismatch

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-354-media-workspace-stem-worker-constructor-mismatch.md`

**Files:**
- Modify: `ui/workspaces/media_workspace.py`
- Test: MediaWorkspace pipeline unit/Qt test
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-354-media-workspace-stem-worker-constructor-mismatch.md`

- [x] **Step 1: Read B-354 and current MediaWorkspace stem path**
- [x] **Step 2: Reproduce/prove constructor mismatch with targeted test**
- [x] **Step 3: Fix worker construction to match `StemSeparationWorker(track_id)`**
- [x] **Step 4: Run targeted MediaWorkspace/audio worker tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- Repro test: pre-fix `TypeError`; post-fix Exit 0, `1 passed`.
- MediaWorkspace-near package: Exit 0, `9 passed`.
- `pytest --collect-only -q`: Exit 0, `2205 tests collected`.
- Vault `B-354`: `fixed`.
- Separate known failure: full `tests/ui/test_workspaces_smoke.py` still fails in ConvertWorkspace tab-count expectation; not B-354.

### Task 5: B-353 audio worker error QThread cleanup

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-353-audio-worker-error-can-leave-qthread-running.md`

**Files:**
- Modify: `ui/controllers/worker_dispatcher.py`
- Test: Qt offscreen worker-dispatcher test under `tests/`
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-353-audio-worker-error-can-leave-qthread-running.md`

- [x] **Step 1: Read B-353 and WorkerDispatcher/audio-worker error paths**
- [x] **Step 2: Reproduce/prove error-without-finished thread leak with targeted Qt test**
- [x] **Step 3: Connect worker error path to thread quit/cleanup without double-finish regression**
- [x] **Step 4: Run targeted Qt/offscreen worker tests**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- Repro test: pre-fix thread stayed running; post-fix Exit 0, `1 passed`.
- Dispatcher-near tests: Exit 0, `26 passed`.
- `pytest --collect-only -q`: Exit 0, `2204 tests collected`.
- Vault `B-353`: `fixed`.

## Out-of-Order Code Pending

### Task 4: B-351 GUI import tools drift

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-351-gui-import-tools-drift-from-media-ui.md`

**Files:**
- Modify: `tools/gui/gui_audio_import.py`
- Modify: `tools/gui/gui_video_import.py`
- Test: static GUI-tool drift check or existing tool smoke where possible
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-351-gui-import-tools-drift-from-media-ui.md`

- [x] **Step 1: Read B-351 and current media UI/tool selectors**
- [x] **Step 2: Reproduce/prove selector drift with targeted check**
- [x] **Step 3: Update tools to current Media UI controls and dialog titles**
- [x] **Step 4: Run syntax/static tests**
- [ ] **Step 5: Live tool smoke in running PB Studio**

Status 2026-05-25: `code-fix-pending-live-verification`, not `fixed`. This Medium task was started out of order before remaining High bugs. Continue High bugs first.

## Completed Tasks

### Task 3: B-350 delete_selected_media VectorDB orphan rollback

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-350-delete-selected-media-can-leave-vectordb-orphans.md`

**Files:**
- Modify: `services/ingest_service.py`
- Test: existing or new targeted ingest-service test under `tests/`
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-350-delete-selected-media-can-leave-vectordb-orphans.md`

- [x] **Step 1: Read B-350 and current delete paths**
- [x] **Step 2: Reproduce/prove VectorDB failure orphan path with targeted test**
- [x] **Step 3: Implement minimal transaction-safe behavior**
- [x] **Step 4: Verify failed VectorDB path and successful delete path**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- failing VectorDB path: pre-fix no `RuntimeError`; post-fix rollback + raise.
- B-350 tests: Exit 0, `2 passed`.
- ingest/vector-near package: Exit 0, `20 passed`.
- `pytest --collect-only -q`: Exit 0, `2201 tests collected`.
- Vault `B-350`: `fixed`.

### Task 2: B-349 Save Project As task_id propagation

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-349-save-project-as-self-blocks-open-project.md`

**Files:**
- Modify: `services/project_manager.py`
- Test: existing or new targeted ProjectManager/SaveAsWorker test under `tests/`
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-349-save-project-as-self-blocks-open-project.md`

- [x] **Step 1: Read B-349 and current ProjectManager flow**
- [x] **Step 2: Reproduce or prove current self-blocking path with a targeted test**
- [x] **Step 3: Implement minimal `task_id` propagation into internal `open_project` call**
- [x] **Step 4: Run targeted tests for ProjectManager / SaveAsWorker**
- [x] **Step 5: Update Vault and status with exact evidence**

Result 2026-05-25:

- direct regression: pre-fix failed with `task_id=None`; post-fix green in package.
- self-running-task service workflow: Exit 0, `1 passed`.
- project-manager/worker-near package: Exit 0, `24 passed`.
- `pytest --collect-only -q`: Exit 0, `2199 tests collected`.
- Vault `B-349`: `fixed`.

### Task 1: B-348 pytest collect compatibility

**Bug:** `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-348-pytest-collect-blocked-by-standalone-db-deep.md`

**Files:**
- Modify: `tests/test_db_deep.py`
- Maybe modify: `pyproject.toml` only if collection exclusion is chosen and preserves standalone runner behavior.
- Vault update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-348-pytest-collect-blocked-by-standalone-db-deep.md`

- [x] **Step 1: Read bug and current test file**

Read `tests/test_db_deep.py` top-level execution, repo-root calculation, and module-end `sys.exit`.

- [x] **Step 2: Reproduce current failure**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest --collect-only -q
```

Expected before fix: pytest `INTERNALERROR` from `tests/test_db_deep.py` with `SystemExit`.

- [x] **Step 3: Preserve standalone runner behavior**

Run direct script:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" tests/test_db_deep.py
```

Record exit code and main failure causes. Do not mark fixed based on standalone success unless command is green.

- [x] **Step 4: Implement minimal collection-safe change**

Preferred fix: move standalone execution behind `if __name__ == "__main__":` and ensure pytest collection imports definitions without running the deep standalone suite. Keep standalone script callable.

- [x] **Step 5: Verify collect**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest --collect-only -q
```

Expected after fix: no pytest `INTERNALERROR`.

- [x] **Step 6: Verify standalone runner**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" tests/test_db_deep.py
```

Expected: no pytest import-time crash; standalone behavior is explicit. If standalone still reports existing DB assertions, document exact output and status as partial or code-fix-pending.

- [x] **Step 7: Run targeted nearby tests**

Run:

```powershell
& "$env:USERPROFILE\miniconda3\envs\pb-studio\python.exe" -m pytest -q tests/test_database.py tests/database/test_project_notes_table.py tests/database/test_timeline_snapshot_table.py tests/database/test_schnitt_migrations_idempotent.py
```

- [x] **Step 8: Vault and status**

Result 2026-05-25:

- `pytest --collect-only -q`: Exit 0, `2197 tests collected`.
- `python tests/test_db_deep.py`: Exit 0, `78 PASS / 0 FAIL`.
- nearby DB tests: Exit 0, `57 passed`.
- Vault `B-348`: `fixed`.

Update B-348 with evidence. Use `fixed` only if collect is green and standalone intended behavior is verified. Otherwise use `code-fix-pending-live-verification` or keep `open` with exact blocker.

## Later Tasks

After Task 1, continue High bugs in order from the final audit:

- B-349 through B-430 according to `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\pb-studio-area-audit-final-2026-05-25.md`.
- For each bug: one root-cause read, one targeted failing/proving test, minimal fix, targeted verification, Vault update.

## Definition of Done

- Current bug has exact verification evidence.
- No `fixed` without real workflow where required.
- No unrelated files changed.
- Vault updated per bug.
- Commit only when a logically complete verified change exists and user workflow status is honestly described.
