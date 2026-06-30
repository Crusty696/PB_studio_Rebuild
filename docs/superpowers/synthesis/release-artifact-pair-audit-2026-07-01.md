# Release Artifact Pair Audit 2026-07-01

Status: `artifact-pair-pass-release-blocked`

## Scope

This audit checks the current local release artifact pair and frozen runtime
folder for PB Studio v0.5.0.

It does not prove clean-VM installation, installed-app GUI behavior, model
download behavior, or user acceptance of DG-001 H1 replacement media.

## Command

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_release_artifact_pair.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_release_artifact_pair.py
```

## Result

- `py_compile`: Exit 0.
- `scripts/diag/verify_release_artifact_pair.py`: Exit 0.
- JSON artifact:
  `tests/qa_artifacts/release_artifact_pair_audit.json`.
- Script status: `pass`.
- `release_ready`: `false`.

## Evidence

Version sources all resolve to `0.5.0`:

- `pyproject.toml`
- `installer/pb_studio.nsi`
- `installer/build_installer.bat`
- `installer/version_info.txt`
- `README.md`

Current local artifacts:

- Frozen app folder:
  `dist/pb_studio`
- Frozen app size:
  `5,921,283,899` bytes
- Installer stub:
  `dist/pb_studio_setup_v0.5.0.exe`
- Installer stub size:
  `422,926` bytes
- Installer payload:
  `dist/pb_studio_setup_v0.5.0.nsisbin`
- Installer payload size:
  `2,815,066,504` bytes

SHA256:

- `pb_studio.exe`:
  `AA07928CB4EE8EB3F73940FEA949C5FF3A031629B67A1DFFA3743C16478CF01C`
- `pb_studio_setup_v0.5.0.exe`:
  `22DA36C7E077DFEF3BDF01E2F8F61157FFB4105A62D8461DACF44BAD0A500E62`
- `pb_studio_setup_v0.5.0.nsisbin`:
  `305687BCF6AED0031B9AFC0A9B6255B7FF310614628B7A85C3BC298B41B21619`

Runtime content checks passed:

- `pb_studio.exe`
- Qt6 DLLs
- CUDA/Torch DLL patterns
- `ffmpeg.exe`
- `ffprobe.exe`
- `resources`
- `knowledge`
- `config`
- `translations`

Installer resource checks passed:

- `resources/pb_studio.ico`
- `resources/installer_header.bmp`
- `resources/installer_welcome.bmp`
- `LICENSE.txt`

Authenticode:

- checked: `true`
- status: `NotSigned`
- signed: `false`

## Release Blockers

The artifact pair exists and passes local structural checks, but production
release is still blocked by:

- installer not code-signed
- no clean Windows 11 VM install proof
- no installed-app full GUI workflow proof
- DG-001 H1 replacement-medium user decision still open

No `fixed` or release-ready marker may be set from this audit.

Important gate-scope note: `tools/release_gate.py` currently checks only
`docs/superpowers/DEFERRED_GATES.md`. It blocks on DG-001, but it does not
prove code signing, clean-VM installation, or installed-app GUI behavior.
Those release blockers remain separate even after DG-001 is cleared.
