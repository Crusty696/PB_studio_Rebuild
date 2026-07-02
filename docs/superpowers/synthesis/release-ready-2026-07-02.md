---
status: pass
release_gate_proof: true
proof_type: release-ready
evidence_level: live
date: 2026-07-02
---

# PB Studio Release Ready - 2026-07-02

## Result

PB Studio v0.5.0 local release gate is green for the current artifacts.

## Evidence

- `tools/release_gate.py`: Exit 0, no open Deferred Gates or production blockers.
- `scripts/diag/vm001_sandbox_probe.ps1`: Windows Sandbox clean install proof passed at 2026-07-02 16:46 local time.
- `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-02.md`: `proof_type=clean-vm-install`, `status=pass`, `evidence_level=live`.
- `docs/superpowers/synthesis/installed-app-gui-live-proof-2026-07-01.md`: `proof_type=installed-app-gui`, `status=pass`, `evidence_level=live`.
- `scripts/diag/verify_signing_readiness.py`: installer Authenticode `Valid`, signer `CN=PB Studio Self-Signed Code Signing`.
- `scripts/diag/verify_distribution_bundle_candidate.py`: `status=pass`, `release_ready=true`, distribution ZIP entries complete.
- `scripts/diag/verify_release_evidence_matrix.py`: `status=pass`, `release_ready=true`, no open items.
- `scripts/diag/verify_release_cutover_manifest.py`: `status=pass`, `release_ready=true`, no required actions.
- Release-focused pytest command: `17 passed in 108.49s`.

## Distribution Artifacts

- Distribution ZIP: `dist/PB_Studio_v0.5.0_distribution.zip`
- Distribution ZIP SHA256: `822CB97A676D519AFCDA3A071AF06658724E93020DEBE3050D76DD19BE282B6B`
- Installer: `dist/pb_studio_setup_v0.5.0.exe`
- Installer SHA256: `CF708E253DE9715EB2DFF08F134B3E8ED4C09B044347CE6A4D12332B97CC4D70`
- Payload: `dist/pb_studio_setup_v0.5.0.nsisbin`
- Payload SHA256: `9088E7EF67D8D59ED8EA95F11D44C408CBD621B6D38083142329DB2497671CF5`
- Checksums: `dist/PB_Studio_v0.5.0_SHA256SUMS.txt`

## Honest Limits

- The installer uses a self-signed certificate. It verifies as `Valid` on this machine because the certificate is locally trusted. It does not provide public publisher reputation or SmartScreen reputation.
- The distribution ZIP was created locally and was not uploaded to a release channel.
- Full repository test suite was not run in this final pass; the final pass covered release gate, packaging, signing, clean VM proof, installed GUI proof, evidence matrix, cutover manifest, and focused release tests.
