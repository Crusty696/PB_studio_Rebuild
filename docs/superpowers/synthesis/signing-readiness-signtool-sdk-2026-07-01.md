---
status: blocked
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Signing Readiness SDK Signtool Check

Scope: improve signing-readiness evidence by checking Windows Kits for
`signtool.exe` when it is not on `PATH`.

Updated verifier: `scripts/diag/verify_signing_readiness.py`.

Output artifact: `tests/qa_artifacts/signing_readiness.json`.

Expected current result:

- `release_signing_ready=false`.
- Installer remains unsigned.
- Code-signing certificate remains missing unless a real certificate exists in
  `CurrentUser\My` or `LocalMachine\My`.
- `signtool_path_source` records `PATH`, `Windows Kits`, or `missing`.

Honest limit: finding `signtool.exe` does not sign the installer and does not
clear `SIGN-001` without a trusted code-signing certificate and a valid
signature on the installer.
