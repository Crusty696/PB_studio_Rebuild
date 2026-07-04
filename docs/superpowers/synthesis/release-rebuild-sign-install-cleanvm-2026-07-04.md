---
status: release-ready-user-fixed-marker-pending
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify / Release-Distribution evidence refresh
date: 2026-07-04
---

# Release Rebuild, Private-Signing Policy, Installed-App, Clean-VM Evidence - 2026-07-04

## Result

Current local release evidence is green for the rebuilt private v0.5.0
distribution artifacts. The installer is intentionally unsigned under the
2026-07-04 user decision: PB Studio is a private/free distribution for the
David/Michael path; Authenticode signing and certificates are optional and must
not block readiness.

- `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest -q
  --basetemp %TEMP%\pb_pytest_full_release_final` -> `2835 passed, 34 skipped,
  35 warnings in 1182.73s`.
- `tools/release_gate.py` -> `RELEASE-GATE OK: keine offenen Deferred Gates
  oder Produktionsblocker.`
- `scripts/diag/verify_release_evidence_matrix.py` -> `status=pass`,
  `release_ready=true`, `open_items=[]`.
- `scripts/diag/verify_release_cutover_manifest.py` -> `status=pass`,
  `release_ready=true`, `required_actions=[]`.
- Installed-app GUI live proof accepted by gate:
  `docs/superpowers/synthesis/installed-app-gui-live-proof-2026-07-04.md`.
- Clean Windows Sandbox install proof accepted by gate:
  `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-04.md`.

## Artifact Identity

- Installer:
  `dist/pb_studio_setup_v0.5.0.exe`
  SHA256 `722E6EED2D15CB44903DDDC8106998F32C2FF29FD8A84BB7A65A4F7F5E901D50`
- NSISBI payload:
  `dist/pb_studio_setup_v0.5.0.nsisbin`
  SHA256 `2BA8F99B4F9EDA9222A589BE9861C3F8500EB731395D969903BB577CDF2FF7A9`
- Distribution ZIP:
  `dist/PB_Studio_v0.5.0_distribution.zip`
  SHA256 `1C4420D91078EA3274B0E2E63A6B36AE765CB7A0FE917527C5CD4F55C21A4A40`
- Frozen/installed app EXE:
  `dist/pb_studio/pb_studio.exe` and
  `C:\Users\David_Lochmann\AppData\Local\PB Studio\pb_studio.exe`
  SHA256 `5EDD2D1AAF7B556900C65E4EE577B6EBB2D89476C900609EF7C3BE210F3A5D4E`

## Verification Run

- Rebuilt release artifacts via `installer/build_installer.bat`.
- User decision 2026-07-04: PB Studio is private-only distribution for the
  user/Michael path. Authenticode signing/certificates are optional and must
  not block release readiness.
- `scripts/diag/verify_signing_readiness.py` -> `release_signing_ready=true`,
  Authenticode `NotSigned`, `unsigned_installer_allowed_for_private_distribution=true`.
- `scripts/diag/verify_release_artifact_pair.py` -> `status=pass`,
  Authenticode signed `false`, unsigned allowed by private policy, version
  sources normalize to `0.5.0`.
- `scripts/diag/create_distribution_bundle.py` -> `status=pass`.
- `scripts/diag/verify_distribution_bundle_candidate.py` -> `status=pass`,
  `distribution_candidate_ready=true`, `release_ready=true`.
- Silent installed current installer into
  `C:\Users\David_Lochmann\AppData\Local\PB Studio`.
- `scripts/diag/verify_installed_app_gui_workflow.py --write-proof` launched
  the installed EXE, found a responsive `PB_studio v0.5.0 - Director's Cockpit`
  window, observed project/material/schnitt/export labels, and wrote the
  installed-app proof.
- `scripts/diag/run_vm001_windows_sandbox.ps1` launched Windows Sandbox.
  Sandbox installed the current installer, found the HKCU uninstall registry
  entry, launched the installed app, and wrote the clean-VM proof with current
  installer/payload SHA256 values.
- Release focused pytest:
  `tests/test_scripts/test_release_cutover_manifest.py`,
  `tests/test_scripts/test_release_evidence_matrix.py`,
  `tests/test_scripts/test_release_gate_cli.py`,
  `tests/test_scripts/test_distribution_bundle_candidate.py`,
  `tests/test_scripts/test_signing_readiness.py`,
  `tests/test_scripts/test_installed_app_gui_readiness.py`,
  `tests/test_scripts/test_installed_app_gui_workflow.py`,
  `tests/test_scripts/test_clean_vm_readiness.py` -> `19 passed in 38.75s`.

## Evidence Files

- `tests/qa_artifacts/release_artifact_pair_audit.json`
- `tests/qa_artifacts/distribution_bundle.json`
- `tests/qa_artifacts/distribution_bundle_candidate.json`
- `tests/qa_artifacts/signing_readiness.json`
- `tests/qa_artifacts/installed_app_gui_readiness.json`
- `tests/qa_artifacts/installed_app_gui_workflow.json`
- `tests/qa_artifacts/clean_vm_sandbox_probe.json`
- `tests/qa_artifacts/release_evidence_matrix.json`
- `docs/superpowers/synthesis/installed-app-gui-live-proof-2026-07-04.md`
- `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-04.md`

## Honest Limits

- This does not prove public Microsoft SmartScreen reputation or a public CA
  publisher identity. Current private-only distribution does not require that.
- The installer and installed `pb_studio.exe` are `NotSigned`. This is not a
  release blocker under the private-only decision, but it remains true.
- This does not upload the ZIP to a distribution channel.
- This does not set any OTK-021 `fixed` marker. User confirmation is still
  required for status promotion.
