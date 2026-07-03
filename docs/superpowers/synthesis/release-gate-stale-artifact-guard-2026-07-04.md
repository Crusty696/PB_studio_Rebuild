---
status: code-fix-pending-distribution-rebuild
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
created: 2026-07-04
---

# Release Gate Stale Artifact Guard 2026-07-04

## Task

OTK-021 90 Live-Verify remains open. During current release-readiness audit,
the local distribution artifacts were found older than the latest product-code
commit.

## Finding

Latest release-relevant product-code commit:

- `29aaf379be1bd986941ddf84ce6e65ffbf2aaca8`
- `2026-07-03T13:43:45+02:00`
- `fix(B-553): ensure database-loaded waveforms have clip item as parent`

Existing release artifacts are older:

- `dist/pb_studio/pb_studio.exe`: `2026-07-01T18:43:46.722482+00:00`
- `dist/pb_studio_setup_v0.5.0.exe`: `2026-07-02T14:56:50.983723+00:00`
- `dist/pb_studio_setup_v0.5.0.nsisbin`: `2026-07-02T14:26:38.988374+00:00`
- `dist/PB_Studio_v0.5.0_distribution.zip`: `2026-07-02T15:04:26.424522+00:00`

Conclusion: the current distribution cannot prove it contains current product
code.

## Change

`services/release_readiness.py` now adds production blocker `ART-005` when
existing release artifacts are older than the newest Git commit touching
release-relevant paths.

The gate checks these artifacts:

- frozen app executable
- installer stub
- NSISBI payload
- distribution ZIP

The CLI regression test no longer assumes release-gate exit `0`; it accepts
the truthful states `0` or `2` and still checks strict `cp1252` output safety.

## Verification

- `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m py_compile services\release_readiness.py tools\release_gate.py` -> pass
- `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_release_readiness.py tests\test_scripts\test_release_gate_cli.py -q --basetemp tests\qa_artifacts\pytest-release-stale-guard-20260704b` -> `8 passed in 2.99s`
- `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe tools\release_gate.py; Write-Output "EXIT=$LASTEXITCODE"` -> `RELEASE-GATE BLOCKED`, `ART-005`, `EXIT=2`

## Honest Status

Code guard verified. Release itself is not ready. After this guard commit,
`ART-005` reports the newest release-relevant commit on the branch until the
distribution artifacts are rebuilt from current HEAD.

Open:

- rebuild distribution from current HEAD
- rerun release artifact pair / distribution bundle checks
- rerun installed-app GUI proof against rebuilt installer/app
- rerun clean VM proof if rebuilt installer changes release artifact identity
- user must still not mark OTK-021 or release as `fixed`
