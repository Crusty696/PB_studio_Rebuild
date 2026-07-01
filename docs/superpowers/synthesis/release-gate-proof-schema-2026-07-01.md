# Release Gate Proof Schema 2026-07-01

Status: `gate-proof-schema-hardened-release-blocked`

## Scope

The production release gate proof detection was hardened so random Markdown
files cannot accidentally clear VM or installed-app GUI blockers.

No product app logic changed. No release or `fixed` status is claimed.

## Changed

- `services/release_readiness.py`
  - VM proof now requires frontmatter:
    - `release_gate_proof: true`
    - `proof_type: clean-vm-install`
    - `status: pass`
    - `evidence_level: live`
  - installed-app GUI proof now requires:
    - `release_gate_proof: true`
    - `proof_type: installed-app-gui`
    - `status: pass`
    - `evidence_level: live`
- `tests/test_services/test_release_readiness.py`
  - added regression that a random `PASS` Markdown file does not clear VM proof
  - added regression that a schema-valid clean-VM proof clears only `VM-001`

## Verification

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile services\release_readiness.py tests\test_services\test_release_readiness.py tools\release_gate.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests\test_services\test_release_readiness.py tests\test_scripts\test_release_gate_cli.py -q
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" tools\release_gate.py
```

Results:

- `py_compile`: Exit 0.
- Focus pytest: `5 passed in 3.68s`.
- `release_gate.py`: blocked, as expected.

Current blockers remain:

- `DG-001`: H1 replacement-medium user decision open.
- `SIGN-001`: installer Authenticode status `NotSigned`.
- `VM-001`: no schema-valid `clean-vm-install` live proof.
- `GUI-001`: no schema-valid `installed-app-gui` live proof.

## Honest Limits

This change improves proof quality and prevents false gate clearance. It does
not run the missing VM install, does not run installed-app GUI verification,
does not sign the installer, and does not resolve DG-001.
