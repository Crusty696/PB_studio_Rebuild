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
