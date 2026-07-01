---
status: blocked-candidate-only
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Distribution Bundle Candidate

Scope: verify current local distribution inputs without creating a sales/release ZIP and without clearing release readiness.

Added verifier: `scripts/diag/verify_distribution_bundle_candidate.py`.

Output artifact: `tests/qa_artifacts/distribution_bundle_candidate.json`.

Expected result:

- `artifact_pair_ready=true` if installer stub and NSISBI payload exist, match version `0.5.0`, and payload is larger than 1 GiB.
- `distribution_candidate_ready=false`.
- `can_create_distribution_zip=false`.
- `release_ready=false`.
- Open blockers must remain visible: `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`.

Honest limit: this proves local bundle inputs only. It does not code-sign the installer, create a release ZIP, run clean-VM install, execute installed-app GUI workflow, or resolve DG-001.
