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
- Unit pytest did not run: `pytest`/`uv` unavailable in the clean clone.
- Old local venv failed earlier with `uv trampoline failed to spawn Python child process`.

## Open

- Create PR manually or authenticate GitHub CLI with `gh auth login`.
- Repair Python test environment.
- Run:

```powershell
python -m pytest tests\test_services\test_ingest_service.py::TestGetAllMedia::test_get_all_video_backfills_metadata_analysis_percent -q
```

## Guardrails

- DG-001 remains open; no release/fixed claim.
- Current Vault path:
  `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio`

## Manual PR URL

https://github.com/Crusty696/PB_studio_Rebuild/pull/new/codex/recover-local-analysis-percent-2026-06-16
