# Test Gate Policy - 2026-05-31

plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
task: Task 1 - Honest Test Gate Policy
status: blocked

## What Changed

- Added CI default pytest gate in `.github/workflows/ci.yml`.
- CI gate uses Windows + Python 3.10 to match active target runtime better than Linux/Python 3.11.
- Added `tests/test_ci_policy.py` to prevent silent removal of default pytest gate and manual heavy-suite commands.
- Documented manual heavy-suite commands in `pyproject.toml`.

## TDD Evidence

Initial policy test run:

```text
C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests/test_ci_policy.py -v
2 failed
```

Failures were expected:

- CI had no `Run unit tests` step.
- `pyproject.toml` did not document manual heavy-suite commands.

Final policy test run:

```text
C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests/test_ci_policy.py -v
2 passed in 0.34s
```

## Default Gate Run

Command:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings
```

Result:

```text
collected 2348 items / 6 deselected / 5 skipped / 2342 selected
1 failed, 27 passed, 5 skipped, 6 deselected, 6 warnings in 213.98s
```

First failure:

```text
tests/integration/test_full_enrichment.py::test_full_enrichment_on_tiny_synthetic_library
AssertionError: Expected 54 enriched scenes, got 0
Captured log: StructureEnrichmentWorker: no scenes with embeddings found; check that VectorDB is populated.
```

## Status

Task 1 is blocked by a real default-gate failure outside the narrow CI-policy edit.

No app behavior is fixed. No `fixed` marker written. No live app verification run.

## B-441 Follow-Up Result

Targeted B-441 regression:

```text
tests/integration/test_full_enrichment.py::test_enrichment_fixture_vector_db_visible_to_worker
1 passed
```

Targeted original failure:

```text
tests/integration/test_full_enrichment.py::test_full_enrichment_on_tiny_synthetic_library
1 passed
```

Root cause:

```text
Test fixture patched VectorDB DB_FILE/DB_DIR, but VectorDBService() uses database.session.APP_ROOT via _default_db_file().
Worker therefore read repo VectorDB, not fixture VectorDB.
```

## Next Default Gate Failure

After B-441 targeted fix, default gate progressed to:

```text
1 failed, 308 passed, 10 skipped, 6 deselected, 36 warnings in 829.95s
```

New failure:

```text
tests/test_docs/test_plan_governance.py::test_registry_paths_exist_for_non_draft_plans
_repo_path_exists('docs/superpowers/synthesis/bug-hunt-2026-05-23.md') == False
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-442-plan-registry-missing-bug-hunt-repo-path.md
```

## B-442 Follow-Up Result

Targeted governance test:

```text
tests/test_docs/test_plan_governance.py::test_registry_paths_exist_for_non_draft_plans
1 passed
```

Registry missing-path scan:

```text
MISSING_COUNT=0
```

## Next Default Gate Failure After B-442

Command:

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest -m "not live_gpu and not e2e and not slow" --maxfail=1 --disable-warnings --cache-clear -q
```

Result:

```text
1 failed, 339 passed, 10 skipped, 6 deselected, 36 warnings in 664.44s
```

Failure:

```text
tests/test_new_features.py::TestPacingService::test_calculate_cut_points_with_bpm
assert all(c.source == "beat" for c in cuts)
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-443-default-gate-pacing-cut-points-source-not-beat.md
```

## B-443 Follow-Up Result

Root cause:

```text
services.pacing_beat_grid._get_bpm(audio_id) used lru_cache with audio_id as the only key.
Earlier tests could cache None for audio_id=1 against one patched SQLAlchemy engine.
Later tests patched a different engine with audio_id=1 and bpm=120.0, but received the stale None.
calculate_cut_points then used the energy fallback instead of BPM beat cuts.
```

Regression before fix:

```text
tests/test_new_features.py::TestPacingService::test_calculate_cut_points_bpm_cache_isolated_by_engine
FAILED: pbg._get_bpm(1) returned None after switching to engine with bpm=120.0
```

Targeted tests after fix:

```text
tests/test_new_features.py::TestPacingService::test_calculate_cut_points_bpm_cache_isolated_by_engine
1 passed

tests/test_new_features.py::TestPacingService::test_calculate_cut_points_with_bpm
1 passed
```

Default gate after B-443:

```text
Exitcode -1073741819
Last visible running test: tests/test_grid_stability.py::test_grid_with_invalid_paths
```

Targeted grid test alone:

```text
tests/test_grid_stability.py::test_grid_with_invalid_paths
1 passed
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-444-default-gate-grid-stability-access-violation.md
```

## B-444 Follow-Up Result

Root cause:

```text
MediaPoolGrid started thumbnail worker threads even for missing file paths.
Those workers only produced placeholders, but still created QThreads during invalid-path grid tests.
MediaPoolGrid.deleteLater() also did not synchronously stop running thumbnail threads.
Under the default-gate order this correlated with Windows access-violation crashes at the grid stability test.
```

Targeted tests after fix:

```text
tests/test_grid_stability.py
3 passed
```

Default gate after B-444:

```text
1 failed, 48 passed, 6 skipped, 6 deselected, 8 warnings in 211.30s
```

Next failure:

```text
tests/integration/test_pacing_performance.py::test_scoring_latency_per_cut_under_budget
AssertionError: Scoring latency regression: median=33.63 ms >= 30.0 ms regression limit (budget 20.0 ms).
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-445-default-gate-pacing-scoring-latency-regression.md
```

## B-445 Follow-Up Result

Root cause:

```text
PacingScorer.score() hot path rebuilt static role/mood maps per candidate and repeatedly fingerprinted identical numpy embeddings.
The default gate exposed this as latency variance above the 30 ms regression limit.
```

Targeted tests after fix:

```text
tests/integration/test_pacing_performance.py::test_scoring_latency_per_cut_under_budget
1 passed; median=14.73 ms, p90=22.84 ms

tests/integration/test_pacing_performance.py::test_per_term_scoring_cost
1 passed; single score=54.8 us per call

tests/pacing/test_pacing_scorer.py tests/pacing/test_pacing_configs.py tests/pacing/test_pacing_stages.py
28 passed
```

Default gate after B-445:

```text
Exitcode -1073740791
Last visible running test: tests/test_pre_cache_headless.py::test_pre_cache_headless_mode
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-446-default-gate-pre-cache-headless-crash.md
```

## B-446 Follow-Up Result

Root cause:

```text
tests/test_pre_cache_headless.py patched sys.exit as a no-op. After the --pre-cache branch called sys.exit(0), main.main() continued into GUI startup with mocked PySide6 modules. Real CLI exits at that point; the test harness changed control flow and made the default gate crash-prone under accumulated Qt/native state.
```

Targeted test after fix:

```text
tests/test_pre_cache_headless.py::test_pre_cache_headless_mode
1 passed
```

Default gate after B-446:

```text
1 failed, 722 passed, 28 skipped, 6 deselected, 39 warnings in 639.44s
```

Next failure:

```text
tests/test_services/test_b433_power_status_change_cuda_reprobe.py::test_b433_main_handles_power_status_change
AssertionError: B-433: Der 0x000A-Zweig muss ModelManager.notify_power_resume aufrufen.
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-447-default-gate-b433-power-status-regression.md
```

## B-447 Follow-Up Result

Root cause:

```text
tests/test_services/test_b433_power_status_change_cuda_reprobe.py used a fixed 1400-character source slice for the 0x000A branch. B-435 debounce logic made the branch longer, so the slice ended before the existing ModelManager().notify_power_resume() call. App code still had the required call in the 0x000A branch.
```

Targeted test after fix:

```text
tests/test_services/test_b433_power_status_change_cuda_reprobe.py
2 passed
```

Default gate after B-447:

```text
1 failed, 879 passed, 28 skipped, 6 deselected, 39 warnings in 738.90s
```

Next failure:

```text
tests/test_services/test_brain_v3_performance_profile_script.py::test_performance_profile_collects_pacing_samples
RuntimeError: isolated pacing smoke returned ok=false; checks.learning_session_under_2s=false
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-448-default-gate-brain-v3-performance-profile-learning-timeout.md
```

## B-448 Follow-Up Result

Root cause:

```text
scripts/spike_brain_v3_pacing_smoke.py isolated APPDATA but did not isolate project_root. BrainV3Service(project_root=None) used the default project state and real main DB, so the isolated smoke loaded real timeline preview paths and spent 6143 ms in learning_session().
```

Targeted tests after fix:

```text
tests/test_services/test_brain_v3_performance_profile_script.py::test_performance_profile_collects_pacing_samples
tests/test_services/test_brain_v3_phase4_pacing_smoke_script.py::test_phase4_pacing_smoke_reports_compare_and_timings
2 passed
```

Direct smoke after fix:

```text
ok=True
learning_ms=1058.85
samples=15
has_real_paths=False
learning_session_under_2s=True
```

Default gate after B-448:

```text
Exitcode -1073741819
Last visible running test: tests/test_grid_stability.py::test_grid_delete_later_stops_thumbnail_threads
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-449-default-gate-grid-stability-crash-recurrence.md
```

## B-449 Follow-Up Result

Root cause:

```text
MediaPoolGrid thumbnail signal lambdas captured self. If queued worker.done or thread.finished signals were processed after grid.deleteLater(), the lambdas could touch a deleted Grid C++ wrapper. B-449 replaced those callbacks with a static thumbnail apply call and a captured Python list reference.
```

Targeted tests after fix:

```text
tests/test_grid_stability.py
4 passed
```

Default gate after B-449:

```text
1 failed, 986 passed, 28 skipped, 6 deselected, 39 warnings in 720.67s
```

Next failure:

```text
tests/test_services/test_brain_wiring_b197.py::test_main_pbwindow_has_brain_timeline_nav_slot
AssertionError: B-197 F-2: PBWindow._on_brain_timeline_nav fehlt; PBWindow was MagicMock spec='str'.
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-450-default-gate-brain-wiring-b197-pbwindow-mock.md
```

## B-450 Follow-Up Result

Root cause:

```text
tests/test_pre_cache_headless.py imported main with mocked PySide6 modules and left that mocked main module in sys.modules. Later B-197 wiring tests imported cached main, where PBWindow was MagicMock instead of the real class.
```

Targeted tests after fix:

```text
tests/test_pre_cache_headless.py::test_pre_cache_headless_mode
tests/test_services/test_brain_wiring_b197.py::test_main_pbwindow_has_brain_timeline_nav_slot
2 passed
```

Default gate after B-450:

```text
1 failed, 1562 passed, 28 skipped, 6 deselected, 39 warnings in 719.59s
```

Next failure:

```text
tests/test_services/test_stem_separator_audio_decode.py::test_streaming_stem_writer_crossfades_without_full_accumulator
RuntimeError: "clamp_min_cpu" not implemented for 'Half'
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-451-default-gate-stem-separator-fp16-cpu-clamp.md
```

## B-451 Follow-Up Result

Root cause:

```text
_StreamingStemWriter assumed fade.clamp(min=...) works for all tensor dtypes. Under suite order the fade tensor can be CPU float16, and PyTorch CPU does not implement clamp_min for Half.
```

Targeted test after fix:

```text
tests/test_services/test_stem_separator_audio_decode.py::test_streaming_stem_writer_crossfades_without_full_accumulator
1 passed
```

Default gate after B-451:

```text
1 failed, 1848 passed, 29 skipped, 6 deselected, 61 warnings in 777.70s
```

Next failure:

```text
tests/test_workers/test_video_corrupt_clip.py::test_corrupt_mp4_through_pipeline_does_not_crash
Expected corrupt/unreadable file message, got VideoClip 99 nicht gefunden oder geloescht.
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-452-default-gate-corrupt-video-pipeline-missing-clip-message.md
```

## B-452 Follow-Up Result

Root cause:

```text
The corrupt-video worker test passed a real run_full_pipeline() call with clip_id=99 but did not create VideoClip(id=99) in the active test DB. Under the default gate, a queryable DB schema existed, so run_full_pipeline() stopped with "VideoClip 99 nicht gefunden oder geloescht" before detect_scenes() could reach broken.mp4.
```

Fix:

```text
tests/test_workers/test_video_corrupt_clip.py now uses db_session/project fixtures and inserts VideoClip(id=99, file_path=broken.mp4). The corrupt/unreadable message assertion was not loosened.
```

Targeted tests after fix:

```text
tests/test_workers/test_video_corrupt_clip.py::test_corrupt_mp4_through_pipeline_does_not_crash
1 passed

tests/test_workers/test_video_corrupt_clip.py
5 passed
```

Default gate after B-452:

```text
Exitcode -1073740791
Last visible verbose area: tests/test_grid_stability.py::test_grid_delete_later_stops_thumbnail_threads
Compact rerun ended around 12% before B-452 test was reached.
```

Next bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-453-default-gate-grid-stability-native-crash-after-b452.md
```

## B-453 Follow-Up Result

Root cause:

```text
_ThumbWorker.done connected to a free Python lambda that converted QImage to QPixmap. The callable had no QObject receiver/thread affinity, so QPixmap creation could happen outside the GUI thread when emitted from the thumbnail worker thread.
```

Fix:

```text
VideoCard.apply_thumbnail_image() is now a QObject slot. worker.done connects to card.apply_thumbnail_image, keeping QPixmap.fromImage() on the GUI-thread receiver. Source invariant forbids the free image lambda.
```

Targeted tests after fix:

```text
tests/test_grid_stability.py::test_thumb_loader_callbacks_do_not_capture_grid_self
1 passed

tests/test_grid_stability.py
4 passed
```

Default gate after B-453:

```text
1 failed, 1852 passed, 29 skipped, 6 deselected, 60 warnings in 792.65s
```

Next failure:

```text
tests/test_workers/test_video_pipeline_metadata_snapshot.py::test_pipeline_metadata_snapshot_before_session_close
AssertionError: done_calls == []
Captured log: B-287: metadata_extract for clip 42 failed: '_FakeSession' object has no attribute 'query'
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-454-default-gate-video-pipeline-metadata-snapshot-fake-session.md
```

## B-454 Follow-Up Result

Root cause:

```text
The metadata snapshot test fake session only implemented .get(), but the worker metadata path now uses .query(VideoClip).filter(...).first() to include the soft-delete guard. The fake was stale.
```

Fix:

```text
_FakeSession now implements query(), filter(), and first() for the worker's current DB access contract.
```

Targeted tests after fix:

```text
tests/test_workers/test_video_pipeline_metadata_snapshot.py::test_pipeline_metadata_snapshot_before_session_close
1 passed

tests/test_workers/test_video_pipeline_metadata.py tests/test_workers/test_video_pipeline_metadata_snapshot.py
3 passed
```

Default gate after B-454:

```text
1 failed, 1901 passed, 29 skipped, 6 deselected, 61 warnings in 639.40s
```

Next failure:

```text
tests/ui/test_b309_schnitt_no_project_empty.py::test_b315_workspace_switch_to_schnitt_has_no_direct_duplicate_refresh
AssertionError: assert [] == [((23,), {'allow_active_fallback': False})]
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-455-default-gate-schnitt-workspace-switch-refresh-missing.md
```

## B-455 Follow-Up Result

Root cause:

```text
_on_workspace_changed(2) pushed project state into SCHNITT but did not refresh Director combos for the active project. Putting the refresh into _push_active_project_to_schnitt() violates B-321 because project-change hooks must not synchronously refresh combos.
```

Fix:

```text
The combo refresh now runs only in the workspace-switch branch for index 2, after _push_active_project_to_schnitt(), with explicit project_id and allow_active_fallback=False.
```

Targeted tests after fix:

```text
tests/ui/test_b309_schnitt_no_project_empty.py::test_b315_workspace_switch_to_schnitt_has_no_direct_duplicate_refresh
1 passed

tests/ui/test_b309_schnitt_no_project_empty.py tests/ui/test_b321_project_open_avoids_sync_combo_refresh.py
7 passed
```

Default gate after B-455:

```text
1 failed, 1916 passed, 29 skipped, 6 deselected, 61 warnings in 682.49s
```

Next failure:

```text
tests/ui/test_b389_thumb_late_signal_deleted_card.py::test_apply_thumbnail_ignores_deleted_card
AttributeError: type object 'MediaPoolGrid' has no attribute '_apply_thumbnail'
```

Bugfile:

```text
C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-456-default-gate-thumb-apply-helper-removed.md
```
