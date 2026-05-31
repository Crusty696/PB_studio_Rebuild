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
