# Recover local analysis percent progress

## Summary

- Recover local-only analysis-status bulk helpers from the non-git
  `PB_studio_Rebuild` folder.
- Apply bulk `analysis_percent` refresh in media-list loading.
- Add regression coverage for video metadata not showing as `0%`.
- Add clean-stop handoff discipline for future agents.

## Branch

`codex/recover-local-analysis-percent-2026-06-16`

## Commits

- `137c15e chore(recovery): restore local analysis percent progress`
- `7e305cb docs(handoff): require clean stop on low context`
- `547d847 docs(recovery): add manual PR handoff`
- `a5e2a4e docs(recovery): record targeted regression pass`

## Files

- `services/analysis_status_service.py`
- `services/ingest_service.py`
- `tests/conftest.py`
- `tests/test_services/test_ingest_service.py`
- `AGENTS.md`
- `docs/superpowers/AGENT_HANDOFF.md`

## Verification

- `git diff --check` passed.
- `py_compile` passed for the recovered Python files.
- Targeted regression test passed in a temporary local Python 3.10 conda env:

```powershell
.\.conda-test\python.exe -m pytest tests\test_services\test_ingest_service.py::TestGetAllMedia::test_get_all_video_backfills_metadata_analysis_percent -q
```

Result:

```text
1 passed in 6.80s
```

- Temporary `.conda-test` env was removed after the run.
- Old local venv failed earlier with `uv trampoline failed to spawn Python child process`.

## Small Full-Audio E2E

User requested a full test run with few data and a 4-minute audio.

Environment:

```text
python 3.10.20
torch 1.12.1+cu113
cuda_available True
cuda_device NVIDIA GeForce GTX 1060
pipeline_import_ok 8
beat_this_ok False
```

Command:

```powershell
.\.conda-pb-full\python.exe scripts\diag\e2e_audio_pipeline_orchestrator.py --audio test-report\e2e-audio-4min-20260616\synthetic_4min.wav
```

Result:

```text
EXITCODE=0
failed=False
total=274.3s
stages: stem_gen, beat_grid, onset, key, structure, lufs, spectral, av_pacing
```

Evidence:

```text
test-report\e2e-audio-4min-20260616\e2e_audio_pipeline.log
```

Limit: `vendor/beat_this` submodule cannot initialize because remote commit
`7ecf41375b9be919099b1ea2ecdd9fe5df937fa3` is unavailable from
`https://github.com/CPJKU/beat_this.git`. Beat-grid used librosa fallback and
returned `bpm=0.0` on the synthetic audio. This does not verify the
`beat_this` path.

## Open

- Create PR manually or authenticate GitHub CLI with `gh auth login`.
- Broader suite not run.

## Guardrails

- DG-001 remains open; no release/fixed claim.
- Current Vault path:
  `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio`

## Manual PR URL

https://github.com/Crusty696/PB_studio_Rebuild/pull/new/codex/recover-local-analysis-percent-2026-06-16
