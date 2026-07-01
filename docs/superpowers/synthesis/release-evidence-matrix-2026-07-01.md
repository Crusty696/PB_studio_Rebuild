# Release Evidence Matrix 2026-07-01

status: blocked
plan_id: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify

## Scope

`scripts/diag/verify_release_evidence_matrix.py` aggregates current release
evidence into one machine-readable JSON artifact.

Covered sources:

- active deferred gates from `docs/superpowers/DEFERRED_GATES.md`
- production blockers from `services.release_readiness.production_blockers`
- schema-valid release proof frontmatter in `docs/superpowers/synthesis`
- QA JSON artifacts for artifact pair, signing, clean-VM, installed-app GUI
  readiness, and installed-app GUI workflow

## Commands

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_release_evidence_matrix.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_release_evidence_matrix.py
```

## Current Result

- `scripts/diag/verify_release_evidence_matrix.py`: Exit 0.
- JSON artifact: `tests/qa_artifacts/release_evidence_matrix.json`.
- `release_ready=false`.
- `status=blocked`.
- Accepted schema-valid release proofs found: `0`.

Open items:

- `DG-001`: H1 replacement-medium user decision remains open.
- `SIGN-001`: installer Authenticode is `NotSigned`.
- `VM-001`: no schema-valid `clean-vm-install` live proof.
- `GUI-001`: no schema-valid `installed-app-gui` live proof.

Aggregated QA JSON sources:

- `tests/qa_artifacts/release_artifact_pair_audit.json`
- `tests/qa_artifacts/signing_readiness.json`
- `tests/qa_artifacts/clean_vm_readiness.json`
- `tests/qa_artifacts/installed_app_gui_readiness.json`
- `tests/qa_artifacts/installed_app_gui_workflow.json`

## Honest Limit

This matrix aggregates evidence only. It does not sign the installer, run a
clean VM, install PB Studio, execute the installed-app GUI workflow, or resolve
the DG-001 user decision.
