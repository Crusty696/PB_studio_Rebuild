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
