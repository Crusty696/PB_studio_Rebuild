---
status: product-path-pass-open
task: OTK-021 90 Live-Verify steps 1-2
date: 2026-07-03
fixed_marker_allowed: false
---

# OTK-021 Step 1-2 Product-Path Verification - 2026-07-03

## Task Quote

Source: `docs/superpowers/archive/2026-05-19-global-storage-provenance/90_LIVE_VERIFY.md`

1. Migration: existing V2 + Plan-A data registered into `by_sha/` via junctions.
2. SCHNITT audio subtab still works without code touch.

Acceptance stays unchanged: all seven 90 Live-Verify steps without stacktrace,
SCHNITT functional, V2 pipeline still writes provenance. Only then `fixed`.

## What Ran

New verifier:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_migration_schnitt_audio_product_path.py
```

Result: exit 0, JSON `status=pass`.

Focused regression:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_storage_migration.py tests\ui\test_schnitt_audio_adapter.py tests\ui\test_schnitt_audio_binder.py -q --basetemp tests\qa_artifacts\pytest-otk021-migration-schnitt
```

Result: `11 passed in 8.70s`.

Additional checks:

- `python -m py_compile scripts\diag\verify_otk021_migration_schnitt_audio_product_path.py` passed.
- `git diff --check` passed.
- Screenshot artifact inspected.

## Evidence

Artifacts:

- `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_result.json`
- `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_schnitt_audio.png`

Step 1 checks in JSON:

- `step_1_migration_existing_v2_plan_a_by_sha_junctions=pass`
- `audio_by_sha_root_exists=true`
- `video_by_sha_root_exists=true`
- `linked_stem_dir_exists=true`
- `linked_stem_dir_reparse_or_symlink=true`
- all linked stems exist and bytes match original legacy stems
- `project_sources_count=2`
- `jobs.audio.v2.stems=done`
- `jobs.video.plan_a.outputs=done`
- artifact roles include `vocals_stem`, `drums_stem`, `bass_stem`, `other_stem`, `proxy`, `embeddings`, `motion`
- audio and video provenance manifests each contain one job with artifacts

Step 2 checks in JSON:

- `step_2_schnitt_audio_subtab_product_widget=pass`
- real `SchnittTabAudio` widget visible offscreen
- real `SchnittAudioBinder` used
- `stem_workspace_info="Track #1 ... 4/4 Stems"`
- `lufs_label="LUFS: -13.2"`
- `key_label="Tonart: Fm ... 4A"`
- `waveform_scene_has_items=true`
- screenshot saved

## Honest Limit

This is product-path evidence through `ProjectManager.open_project()` and real
SCHNITT audio Qt widgets, not a manual installed-app GUI click. The screenshot
shows waveform and four stem lanes; some text renders as square glyphs in the
offscreen capture. Machine-readable label checks in the JSON are green.

No `fixed` marker is allowed from this alone. OTK-021 overall still depends on
the full seven-step 90 Live-Verify verdict and user confirmation.
