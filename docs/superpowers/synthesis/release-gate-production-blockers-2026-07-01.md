# Release Gate Production Blockers 2026-07-01

Status: `gate-expanded-release-blocked`

## Scope

`tools/release_gate.py` was expanded from a Deferred-Gates-only check to a
combined hard release gate.

This is tooling/test work only. No product app logic changed. No release or
`fixed` status is claimed.

## Changed

- Added `services/release_readiness.py`.
- Updated `tools/release_gate.py`.
- Added `tests/test_services/test_release_readiness.py`.
- Updated `tests/test_scripts/test_release_gate_cli.py`.

## Gate Coverage

The release gate now blocks on:

- active Deferred Gates from `docs/superpowers/DEFERRED_GATES.md`
- missing frozen app folder / installer pair
- too-small NSISBI payload
- unsigned installer
- missing clean Windows VM install proof
- missing installed-app full GUI workflow proof

## Verification

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile services\release_readiness.py tools\release_gate.py tests\test_services\test_release_readiness.py tests\test_scripts\test_release_gate_cli.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests\test_services\test_release_readiness.py tests\test_scripts\test_release_gate_cli.py -q
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" tools\release_gate.py
```

Results:

- `py_compile`: Exit 0.
- Focus pytest: `3 passed in 4.38s`.
- `release_gate.py`: blocked, as expected.

Current blockers reported:

- `DG-001`: H1 replacement-medium user decision open.
- `SIGN-001`: installer Authenticode status `NotSigned`.
- `VM-001`: clean Windows VM install proof missing.
- `GUI-001`: installed-app full GUI workflow proof missing.

## Honest Limits

The gate now prevents a false release-ready claim more reliably. It does not
perform the missing work:

- no installer signing was performed
- no clean VM install was executed
- no installed-app full GUI workflow was executed
- no DG-001 user decision was made
