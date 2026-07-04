---
status: evidence-pass-user-fixed-marker-open
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify / Release-Distribution evidence refresh
date: 2026-07-04
---

# Release Rebuild, Signing, Installed-App, Clean-VM Evidence - 2026-07-04

## Result

Current local release evidence is green for the rebuilt v0.5.0 distribution
artifacts from the current branch state.

- `tools/release_gate.py` -> `RELEASE-GATE OK`, exit `0`.
- `scripts/diag/verify_release_evidence_matrix.py` -> `status=pass`, `release_ready=true`, no open production blockers.
- Installed-app GUI live proof accepted by gate:
  `docs/superpowers/synthesis/installed-app-gui-live-proof-2026-07-04.md`.
- Clean Windows Sandbox install proof accepted by gate:
  `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-04.md`.

## Artifact Identity

- Installer:
  `dist/pb_studio_setup_v0.5.0.exe`
  SHA256 `1BB5F755C805437D9EDDDA5E2A31FFAD52B0FEB0BCF94C0D1A8FD31B90C9B758`
- NSISBI payload:
  `dist/pb_studio_setup_v0.5.0.nsisbin`
  SHA256 `8E15A1876216369F2F48FC83027A53993F74A6BDCF337BAB59541FEE4F36B4C9`
- Distribution ZIP:
  `dist/PB_Studio_v0.5.0_distribution.zip`
  SHA256 `53B6F8ECA07C477AFA057B51A95AF7207C296B786433C21179EEC13A54ABC77D`

## Verification Run

- Rebuilt release artifacts via `installer/build_installer.bat`.
- Signed installer with CurrentUser self-signed code-signing certificate:
  thumbprint `EB0DF8D8AFBEDE5D7F8B3021076F502C3F04549F`.
- `scripts/diag/verify_signing_readiness.py` -> `release_signing_ready=true`,
  Authenticode `Valid`.
- `scripts/diag/verify_release_artifact_pair.py` -> `status=pass`,
  Authenticode signed `true`, version sources normalize to `0.5.0`.
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
  publisher identity. The installer is signed with the local self-signed
  certificate approved for the free-app path.
- The installed `pb_studio.exe` inside LocalAppData is not individually signed;
  the installer is signed and verified as `Valid`.
- This does not upload the ZIP to a distribution channel.
- This does not set any OTK-021 `fixed` marker. User confirmation is still
  required for status promotion.
