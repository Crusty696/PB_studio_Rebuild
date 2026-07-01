# Signing Readiness Preflight 2026-07-01

Status: `signing-not-ready-release-blocked`

## Scope

This preflight checks whether the current machine can sign the PB Studio
installer and whether the current installer is already signed.

It does not create certificates, import secrets, or sign files.

## Command

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_signing_readiness.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_signing_readiness.py
```

## Result

- `py_compile`: Exit 0.
- `scripts/diag/verify_signing_readiness.py`: Exit 0.
- JSON artifact: `tests/qa_artifacts/signing_readiness.json`.
- `release_signing_ready`: `false`.

## Evidence

Installer:

- `dist/pb_studio_setup_v0.5.0.exe`
- Exists: `true`

Signing tooling:

- `signtool`: missing
- `certutil`: available from Windows, but certutil does not sign installers

Code-signing certificates:

- `Cert:\CurrentUser\My -CodeSigningCert`: count `0`
- `Cert:\LocalMachine\My -CodeSigningCert`: count `0`

Authenticode:

- checked: `true`
- status: `2` / `NotSigned`
- `SignerCertificate`: `null`

Blockers:

- `signtool-missing`
- `code-signing-certificate-missing`
- `installer-not-signed`

## Verdict

`SIGN-001` remains valid. The installer cannot be signed on this machine with
the currently available tools/certificates.

Required before clearing `SIGN-001`:

- install Windows SDK / `signtool.exe`, or provide another approved signing tool
- provide/import a real code-signing certificate
- sign `dist/pb_studio_setup_v0.5.0.exe`
- verify `Get-AuthenticodeSignature` returns `Valid`
- record a signed-installer synthesis

No release-ready marker may be set from this preflight.
