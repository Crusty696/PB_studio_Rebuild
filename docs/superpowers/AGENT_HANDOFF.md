# PB Studio Agent Handoff

This file is a repository-local continuity checkpoint for all agents.

## Perf-DB-Cleanup code-complete-live-pending 2026-07-13 (newest)

- **Main:** `686aaae` vor finalem Handoff-Doku/Lesson-Commit; E1-E10
  Produktcommit-Kette vollständig, E9 `1cc0f0f`; Governance `17654d9`;
  System-Ollama-Packaging-Fix `686aaae`.
- **Status:** Registry/Plan `code-complete-live-pending`; Active Plan bleibt
  ausgewählt für Live-Follow-up. Kein `fixed`.
- **Gesamtverify:** DB-Core 221 PASS/3 skipped; D-069/E10 70 PASS + reale
  5/5 JPG-SHA-Parität; E1-E8 15 Fokus + 84 angrenzend PASS; E9 zusätzlich
  5 Fokus + 56 DB/Undo + 78/78 Deep-DB PASS. Detached-Audit ohne Fund.
- **Perf-Flake:** einmal Scorer 34.88ms >30ms unter Parallel-/Suite-Last;
  danach 6/6 kontrolliert PASS (10.52–14.77ms plus 13.76ms).
- **FFmpeg/Frozen:** `bin/` bleibt ignoriert; Resolver/Manifest pinnt
  FFmpeg/ffprobe v6.1.1 + SHA. Frozen-App neu gebaut: 14,839 Dateien,
  5,926,420,584 Bytes; Bundle-SHAs exakt Manifest; `smoke_test.py` PASS.
- **Installer FERTIG 2026-07-13:** NSISBI war lokal vorhanden unter
  `%LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1\nsis-binary-7069-1\Bin\makensis.exe`
  — ZIP entpackte mit Extra-Ebene `nsis-binary-7069-1`, Build-Script-Default
  (`nsisbi-7069-1\Bin\`) fand ihn daher nicht -> stiller Standard-NSIS-Fallback.
  Fix ohne Code-Change: `PB_NSISBI_MAKENSIS`-Env-Override. Build mit
  `PB_SKIP_PYINSTALLER=1` (Dist wiederverwendet, Smoke erneut PASS) Exit 0,
  Log bestaetigt `Using NSISBI from PB_NSISBI_MAKENSIS`. Artefakte:
  `pb_studio_setup_v0.5.0.exe` 424,755 B SHA256
  `E9FD73132E0CEC7476715B9595F36D5A6B7DF10C4914A37ABC57A57AC9F1FFD7`;
  `pb_studio_setup_v0.5.0.nsisbin` 2,817,285,191 B SHA256
  `FF1A80ACD3ADC91A23E87B10EF209D6BCEBED288BEB63091392A23877757F76D`.
  Buildlog: `test-report/installer-build-nsisbi-20260713.log`.
- **Release-Gate 2026-07-13:** `tools/release_gate.py` -> `RELEASE-GATE OK`,
  EXIT=0 (ART-002/ART-003 durch neue Artefakte frei). Evidence-Matrix
  `status=pass`, `release_ready=true`. **Ehrliches Limit:** neuer Installer ist
  `NotSigned`; akzeptierte Signing-/Clean-VM-/Installed-App-Proofs
  (2026-07-01..05) referenzieren die ALTEN Artefakt-Hashes — Gate/Matrix
  pruefen Proof-Existenz, nicht Hash-Bindung an aktuelle Artefakte.
- **Frozen-GUI-Live 2026-07-13 PASS:** `verify_frozen_gui_workflow.py` Exit 0:
  Fenster responsiv (`PB_studio v0.5.0 — Director's Cockpit`),
  `uia_label_count=63`, alle 4 Workflow-Gruppen beobachtet, Prozess nach 5s
  alive, Screenshot `tests/qa_artifacts/frozen_gui_workflow_20260713_072304.png`.
  Danach keine pb_studio-Prozesse.
- **Lernen:** `8421e27` + Lessons; Start lädt Regeln, Handoff verlangt Lesson.
- **Offen:** reale GUI-/App-Livepfade E1/E3/E4/E5/E7/E8/E9/E10,
  Signierung des neuen Installers (Cert-Entscheid User), Installed-App-Install
  (braucht Admin-Elevation), Clean-VM gegen NEUE Hashes, User-`fixed`.
- **Naechster sicherer Schritt:** keine neue Codearbeit. Installer signieren
  (falls User Self-Signed-Cert `EB0DF8D8...` weiter akzeptiert), dann
  Installed-App-Install mit Admin + `verify_installed_app_gui_workflow.py`,
  dann Windows-Sandbox-Clean-VM-Proof gegen die neuen Hashes
  (E9FD73... / FF1A80...). Installer-Build reproduzierbar via
  `PB_NSISBI_MAKENSIS` + `PB_SKIP_PYINSTALLER=1`.
- **Synthese:**
  `docs/superpowers/synthesis/perf-db-cleanup-abschluss-2026-07-13.md` und
  Vault `wiki/synthesis/perf-db-cleanup-abschluss-2026-07-13.md`.

## Codex Quellstand-Konsolidierung 2026-06-22 (historical)

- **Branch:** `codex/OTK-021-source-consolidation-2026-06-22`
- **B-538 long-audio service E2E 2026-07-05:** commit `8aeb1ec` adds
  isolated project/AppData/json-output support to
  `scripts/diag/e2e_audio_pipeline_orchestrator.py` and documents the run in
  `docs/superpowers/synthesis/b538-long-audio-service-e2e-2026-07-05.md`.
  Real user WAV `C:\Users\David_Lochmann\Music\02 Mai19 - Kopie.wav`
  (5531.005s) completed the service orchestrator with JSON `status=pass`,
  `failed=false`, `total_seconds=3600.46`. Evidence: StemGen CUDA GTX 1060
  `198/198`, BeatGrid `12569` beats, Structure `341` segments, LUFS `-14.83`,
  AV-Pacing `55311` samples, 4 stem WAVs each `1463504060` bytes. Verification:
  `py_compile` PASS, script `--help` PASS, `git diff --check` EXIT=0 with only
  CRLF/LF warning, `tools/release_gate.py` EXIT=0 after commit. Honest limits:
  no visible GUI workflow to Timeline/Export/Playback, DB has `waveform_data=0`,
  `hotcues=0`, `timeline_entries=0`, and Onset warns `Audio truncated to 1800
  sec`; B-538 remains `partial-fix`, no `fixed` marker.
- **Release governance sync 2026-07-04:** fixed stale governance/test wording
  after DG-001 moved to `live-verified`. `tests/test_services/test_deferred_gates.py`
  now asserts the real repo DG-001 row is parsed but inactive instead of
  expecting an active blocker. `PLAN_REGISTRY.md`, `ACTIVE_PLAN.md`, the OTK
  masterplan, and the Vault mirror now say: DG-001 live-verified, release gate
  exits 0, fixed marker still user-confirmation-only. Verification:
  release-governance focused tests `14 passed in 2.47s`,
  `verify_release_evidence_matrix.py` -> `status=pass`,
  `release_ready=true`, `deferred_count=0`, `blockers=0`, `open_items=0`;
  `tools/release_gate.py` -> `EXIT=0`.
- **Release rebuild/sign/install/clean-VM evidence 2026-07-04:** ART-005 stale
  artifact blocker is cleared for the current local v0.5.0 distribution
  identity. Rebuilt with `installer/build_installer.bat`, signed installer with
  self-signed CurrentUser code-signing cert
  `EB0DF8D8AFBEDE5D7F8B3021076F502C3F04549F`, recreated distribution ZIP, ran
  installed-app GUI live proof, and ran fresh Windows Sandbox clean install
  proof against the current hashes. Current hashes: installer
  `1BB5F755C805437D9EDDDA5E2A31FFAD52B0FEB0BCF94C0D1A8FD31B90C9B758`,
  payload `8E15A1876216369F2F48FC83027A53993F74A6BDCF337BAB59541FEE4F36B4C9`,
  ZIP `53B6F8ECA07C477AFA057B51A95AF7207C296B786433C21179EEC13A54ABC77D`.
  `verify_release_evidence_matrix.py` -> `status=pass`, `release_ready=true`;
  `tools/release_gate.py` -> `RELEASE-GATE OK`, `EXIT=0`. Proofs:
  `docs/superpowers/synthesis/installed-app-gui-live-proof-2026-07-04.md`,
  `docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-04.md`,
  `docs/superpowers/synthesis/release-rebuild-sign-install-cleanvm-2026-07-04.md`.
  Honest limits: no public CA/SmartScreen reputation, installed inner EXE is
  not individually signed, ZIP not uploaded, no OTK-021 `fixed` marker without
  user confirmation.
- **Release gate stale artifact guard 2026-07-04 (historical, superseded by
  rebuild above):** release gate was intentionally BLOCKED by `ART-005`.
  Initial reason: product commit `29aaf37`
  (`2026-07-03T13:43:45+02:00`, `ui/timeline.py`) was newer than the current
  frozen EXE, installer, NSISBI payload, and distribution ZIP from 2026-07-01/02.
  After the guard commit, `ART-005` reports the newest release-relevant commit
  on the branch until distribution artifacts are rebuilt. Added guard in
  `services/release_readiness.py` and tests
  in `tests/test_services/test_release_readiness.py`; CLI encoding regression
  now accepts truthful gate states `0` or `2`. Verification:
  `py_compile` pass, focused release-readiness/CLI tests `8 passed in 2.99s`,
  `tools/release_gate.py` -> `RELEASE-GATE BLOCKED`, `ART-005`, `EXIT=2`.
  Synthesis:
  `docs/superpowers/synthesis/release-gate-stale-artifact-guard-2026-07-04.md`.
  Superseded by the 2026-07-04 rebuild/sign/install/clean-VM evidence above.
  No `fixed` marker.
- **OTK-021 90 Live-Verify current audit 2026-07-04:** on HEAD
  `29aaf37`, reran the short verifiers for steps 1-5 and checked release gate.
  Results: Step 1-2 migration/SCHNITT verifier `status=pass`; Step 3
  cross-project reuse import/notify verifier `status=pass`; Step 4 file-tracking
  open-project verifier `status=pass`; Step 5 Storage-Browser visible-delete
  verifier `ok=true`; focused regression `43 passed in 16.92s`; release gate
  OK at that moment, now superseded by `ART-005` stale-artifact guard above.
  Steps 6-7 remain backed by the 2026-07-02 Windows Sandbox VM service-level
  proof. Synthesis:
  `docs/superpowers/synthesis/otk021-90-live-verify-current-audit-2026-07-04.md`.
  Honest limits: product-path/offscreen/service evidence, not full manual
  installed-app GUI click-through; Step 5 temp DB/storage; VM proof service-level;
  Antigravity commit `29aaf37` body says `(unverified -- pending user test)` for
  B-553 and this audit did not verify B-553. No `fixed` marker.
- **Release-ready local package 2026-07-02 (historical, now stale):**
  `tools/release_gate.py` exited 0 before commit `29aaf37` and before the
  `ART-005` guard. It is not current release-ready evidence. Windows Sandbox
  clean install proof passed (`docs/superpowers/synthesis/clean-vm-sandbox-install-proof-2026-07-02.md`),
  installed-app GUI proof is accepted, installer Authenticode is `Valid` with
  locally trusted self-signed cert, and distribution ZIP exists at
  `dist/PB_Studio_v0.5.0_distribution.zip` with SHA256
  `822CB97A676D519AFCDA3A071AF06658724E93020DEBE3050D76DD19BE282B6B`.
  Final release-focused verification passed: distribution bundle verifier,
  release evidence matrix, cutover manifest, release gate, signing readiness,
  clean-VM readiness, BOM handling, prune guard tests (`17 passed`). Honest
  limits: no public Publisher/SmartScreen reputation, ZIP not uploaded to any
  release channel, full repository suite not run in the final pass. Synthesis:
  `docs/superpowers/synthesis/release-ready-2026-07-02.md`.
- **OTK-021 Step 1-2 product-path proof 2026-07-03:** added
  `scripts/diag/verify_otk021_migration_schnitt_audio_product_path.py`.
  It creates a real project folder/SQLite DB with legacy Audio-V2 stems and
  Plan-A video outputs, reopens through `ProjectManager.open_project()`, then
  checks `by_sha` source roots, junction/reparse stem link, ProjectSource rows,
  provenance jobs/artifacts, manifest artifacts, and real SCHNITT
  `SchnittTabAudio` + `SchnittAudioBinder` offscreen. Result:
  `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_result.json`
  has `status=pass`, step 1 pass, step 2 pass. Screenshot:
  `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_schnitt_audio.png`.
  Focused regression `tests/test_services/test_storage_migration.py`
  `tests/ui/test_schnitt_audio_adapter.py` `tests/ui/test_schnitt_audio_binder.py`
  passed: `11 passed in 8.70s`; `py_compile` and `git diff --check` passed.
  Honest limit: product-path/offscreen-widget proof, not manual installed-app
  GUI click; screenshot text has square glyphs, machine label checks are green.
  No `fixed` marker.
- **OTK-021 VM portability live proof 2026-07-02:** added
  `scripts/diag/run_otk021_windows_sandbox.ps1` and
  `scripts/diag/otk021_sandbox_probe.ps1`. Windows Sandbox ran the real
  Project-Bundle and Backup/Restore service verifiers inside the guest using a
  mapped Python runtime and a sandbox-local temp workdir. Result:
  `tests/qa_artifacts/otk021_vm_portability_probe.json` has `status=pass`;
  Project-Bundle `exit_code=0`, `ok=true`; Backup/Restore `exit_code=0`,
  `ok=true`. Synthesis:
  `docs/superpowers/synthesis/otk021-vm-portability-live-2026-07-02.md`.
  Honest limit: service-level VM proof, not manual installed-app GUI clicks;
  no `fixed` marker. Next OTK-021 work: audit 90_LIVE_VERIFY steps 1-5 against
  existing evidence.
- **OTK-021 90 Live-Verify audit 2026-07-02:** synthesis
  `docs/superpowers/synthesis/otk021-90-live-verify-audit-2026-07-02.md`
  maps all seven mandatory steps. Current verdict: steps 5, 6, and 7 have
  current strong evidence within documented limits; steps 1-4 are still
  `partial`/`open` because no fresh current product-live proof exists for real
  migration, SCHNITT-audio adapter with migrated stems, two-project reuse
  import/toast/green status, or moved-file repair through the app. No `fixed`
  marker. Next best work: build/run product-live verifier for step 3
  Cross-Project-Reuse or step 1 migration.
- **B-586 / Frozen-vs-installed GUI evidence split 2026-07-01:** added
  `scripts/diag/verify_frozen_gui_workflow.py` and custom output support in
  `verify_installed_app_gui_workflow.py` so frozen evidence writes to
  `tests/qa_artifacts/frozen_gui_workflow.json` and cannot overwrite
  installed-app proof state. `verify_release_evidence_matrix.py` now includes
  `frozen_gui_workflow` separately. Follow-up root cause: the rebuilt frozen
  app was blocked by `faulthandler.enable()` while windowed PyInstaller had
  `sys.stderr is None`. `main.py` now falls back to
  `_internal\logs\freeze_stacks.log` for faulthandler. The wrapper also picks
  a verifier Python with `pygetwindow`/`pywinauto`/`pyautogui` instead of
  blindly using base Conda. Rebuilt frozen app + installer pair. Verification:
  PB-env py_compile OK, focused pytest `19 passed`, direct
  `verify_frozen_gui_workflow.py` PASS after rebuild
  (`window_responsive=true`, `uia_label_count=73`, screenshot
  `tests/qa_artifacts/frozen_gui_workflow_20260701_210511.png`). Release
  matrix still `release_ready=false`; `release_gate.py` still blocks
  `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`. Vault bug
  `B-586-frozen-gui-wrapper-no-window` has `agent_status:
  live-pass-user-fixed-marker-open`, not `fixed`. Synthesis:
  `docs/superpowers/synthesis/frozen-gui-workflow-evidence-split-2026-07-01.md`.
- **GUI-001 installed-app silent install attempt 2026-07-01:** attempted
  `dist\pb_studio_setup_v0.5.0.exe /S` from the current non-admin agent
  process. Windows/Start-Process blocked it with
  `Der angeforderte Vorgang erfordert erhöhte Rechte`. After the attempt,
  `C:\Program Files\PB Studio\pb_studio.exe` still did not exist. Refreshed
  `installed_app_gui_readiness.json` and `installed_app_gui_workflow.json`:
  readiness blockers remain `installer-requires-admin-current-process-not-admin`,
  `installed-exe-missing`, `installed-app-registry-entry-missing`, and
  `installer-not-signed`; workflow remains `status=blocked`,
  `installed-exe-missing`. Release matrix and release gate still block
  `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/installed-app-silent-install-attempt-2026-07-01.md`.
- **Frozen GUI workflow verifier update 2026-07-01:** first live attempt
  against `dist\pb_studio\pb_studio.exe` exposed stale verifier labels and a
  transient `(Keine Rückmeldung)` title. Updated
  `scripts/diag/verify_installed_app_gui_workflow.py` to wait for a responsive
  window and accept current UI labels (`PROJEKT`, `MATERIAL ANALYSE`,
  `SCHNITT`, `EXPORT`) plus legacy workflow labels. Focused tests passed
  (`6 passed`). Frozen GUI rerun passed: responsive window, process alive after
  5s, `uia_label_count=250`, all label groups observed, screenshot
  `tests/qa_artifacts/installed_app_gui_workflow_20260701_171050.png`,
  `proof_written=false`. This is a frozen-dist GUI preflight only; `GUI-001`
  remains open because no installed-app GUI proof exists. Synthesis:
  `docs/superpowers/synthesis/frozen-gui-workflow-verifier-update-2026-07-01.md`.
- **Installed-app GUI readiness install detection 2026-07-01:** updated
  `scripts/diag/verify_installed_app_gui_readiness.py` to report installed EXE
  candidates (`Program Files`, `Program Files (x86)`, `LocalAppData`, and
  `PB_INSTALLED_EXE`) plus PB Studio uninstall registry entries from HKLM/HKCU.
  Direct verifier run Exit 0 and
  `tests/qa_artifacts/installed_app_gui_readiness.json` report
  `installed_app_gui_ready=false`: no installed EXE candidate, no registry
  uninstall entry, current process not admin, and installer unsigned.
  Verification: py_compile OK, installed-app/evidence/cutover pytest
  `6 passed`, `release_gate.py` still blocks on `DG-001`, `SIGN-001`,
  `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/installed-app-gui-readiness-install-detection-2026-07-01.md`.
- **Clean-VM readiness tool detection 2026-07-01:** updated
  `scripts/diag/verify_clean_vm_readiness.py` so Hyper-V `Get-VM` is checked
  as a PowerShell command, while `vmrun`/`VBoxManage` use PATH plus known
  install paths. Direct verifier run Exit 0 and
  `tests/qa_artifacts/clean_vm_readiness.json` report installer/payload present
  but `clean_vm_ready=false`: current process is not admin and no VM control
  tool is available. Verification: py_compile OK, clean-vm/evidence/cutover
  pytest `6 passed`, `release_gate.py` still blocks on `DG-001`, `SIGN-001`,
  `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/clean-vm-readiness-tool-detection-2026-07-01.md`.
- **Signing readiness SDK signtool check 2026-07-01:** updated
  `scripts/diag/verify_signing_readiness.py` to search Windows Kits for
  `signtool.exe` when it is not on PATH. Direct verifier run Exit 0 and
  `tests/qa_artifacts/signing_readiness.json` now reports
  `signtool_path_source=Windows Kits` with
  `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe`.
  Release signing remains blocked: no CurrentUser/LocalMachine code-signing
  certificate, installer Authenticode unsigned, `release_signing_ready=false`.
  Verification: py_compile OK, signing/evidence/cutover pytest `6 passed`,
  `release_gate.py` still blocks on `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`.
  Synthesis:
  `docs/superpowers/synthesis/signing-readiness-signtool-sdk-2026-07-01.md`.
- **Release cutover manifest 2026-07-01:** added
  `scripts/diag/verify_release_cutover_manifest.py` plus regression test
  `tests/test_scripts/test_release_cutover_manifest.py`. Direct verifier
  run Exit 0 and `tests/qa_artifacts/release_cutover_manifest.json` report
  `status=blocked`, `release_ready=false`, and required actions for
  `DG-001`, `SIGN-001`, `VM-001`, and `GUI-001`. The manifest records exact
  follow-up commands/proof frontmatter but does not clear any blocker. Checks:
  py_compile OK, focused pytest `2 passed`, `release_gate.py` still blocks as
  expected. Synthesis:
  `docs/superpowers/synthesis/release-cutover-manifest-2026-07-01.md`.
- **Distribution bundle candidate 2026-07-01:** added
  `scripts/diag/verify_distribution_bundle_candidate.py` plus regression test
  `tests/test_scripts/test_distribution_bundle_candidate.py`. Direct verifier
  run Exit 0 and `tests/qa_artifacts/distribution_bundle_candidate.json`
  report `artifact_pair_ready=true` for current local installer pair:
  `dist/pb_studio_setup_v0.5.0.exe` (422,926 bytes, SHA256
  `22DA36C7E077DFEF3BDF01E2F8F61157FFB4105A62D8461DACF44BAD0A500E62`)
  and `dist/pb_studio_setup_v0.5.0.nsisbin` (2,815,066,504 bytes, SHA256
  `305687BCF6AED0031B9AFC0A9B6255B7FF310614628B7A85C3BC298B41B21619`).
  Required distribution docs/license exist. The verifier deliberately keeps
  `distribution_candidate_ready=false`, `can_create_distribution_zip=false`,
  and `release_ready=false` while release blockers remain. Verification:
  py_compile OK, focused pytest `2 passed`, `release_gate.py` still blocked
  by `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/distribution-bundle-candidate-2026-07-01.md`.
- **Packaging Gate partial 2026-06-30:** Zielruntime-Build wurde mit
  `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe`
  ausgefuehrt (Python 3.10.20, torch 1.12.1+cu113, CUDA True,
  NVIDIA GeForce GTX 1060). `dist/pb_studio` wurde erzeugt
  (nach Prune: 14,758 Dateien, 5.52 GB). `installer/smoke_test.py` und
  `SMOKE_TEST_LAUNCH=1 installer/smoke_test.py` beide Exit 0; EXE launchte
  und wurde nach 5s beendet. `tests/test_export_convert_real.py` mit
  synthetischer NVENC-Fixture via `PB_TEST_VIDEO_PATH` -> 21/21 PASS.
  Geaendert: PyInstaller Pins in `requirements-py310-cu113.txt`,
  Brain-SQL-Migration-Pfad in `pb_studio.spec`, Smoke-Test Exit-Policy,
  Export-Test Env-Override/Exit-Policy, Runtime-Hook DLL paths,
  PyInstaller-Prune, NSISBI mode, `.gitignore` fuer `build/`/`dist/`.
  Standard-NSIS scheiterte an grossem Payload; NSISBI 7069-1 erzeugte
  `dist/pb_studio_setup_v0.5.0.exe` (422,872 bytes) plus
  `dist/pb_studio_setup_v0.5.0.nsisbin` (2,816,861,307 bytes). Build-Script
  Proof: `PB_SKIP_PYINSTALLER=1 cmd /c installer\build_installer.bat` Exit 0.
  Warntriage update: `pb_studio.spec` entfernt stale `workers.debug`
  hidden import; Full-Build nach Patch mit
  `test-report/packaging-build-warntriage-filtered-20260630.log` Exit 0,
  Smoke PASS, NSISBI Installer neu erzeugt. Nicht sauber: `torch.distributed*`,
  `torch.utils.tensorboard`, `torch.utils.benchmark`, `pyqtgraph.opengl` und
  optionale DLL-Warnungen bleiben offen. Weiter blockiert: kein Clean-VM-Test,
  keine Signatur, Installer nicht installiert/gestartet, kein
  Full-Frozen-GUI-Workflow, DG-001 User-Entscheid H1-Ersatzmedium offen. Details:
  `docs/superpowers/synthesis/packaging-gate-audit-2026-06-30.md`.
- **Packaging Warntriage follow-up 2026-06-30:** local PyInstaller hooks now
  filter non-runtime torch/pyqtgraph submodule collection:
  `installer/hooks/hook-torch.py`, `installer/hooks/hook-pyqtgraph.py`, and
  matching `pb_studio.spec` excludes. Full build
  `test-report/packaging-build-hookfiltered3-20260630.log` Exit 0; static
  smoke and launch smoke Exit 0. Removed from build log: previous failed
  collection warnings for `torch.utils.tensorboard`, `torch.utils.benchmark`,
  `pyqtgraph.opengl`, `pyqtgraph.jupyter`, and the explicit
  `torch.distributed.*` hidden-import flood. New artifacts:
  `pb_studio_setup_v0.5.0.exe` 423,231 bytes SHA256
  `560B1321158AD524A4BEEE3D43973BE9C1B6B1BE9B316CA62E2D73C589A2A3DA`;
  `pb_studio_setup_v0.5.0.nsisbin` 2,816,073,535 bytes SHA256
  `3BB9E7C2423EF0A11CAC02D1A9E18CFC7E14DA0F452BFAFCE7C8462AE2EF2123`.
  Still not release-clean: pycparser/tzdata/scipy/sqlalchemy hidden imports,
  Qt SQL/WebView, TensorRT, TBB, torchaudio FFmpeg DLL warnings, no Clean-VM,
  no signing, no full frozen GUI workflow, DG-001 H1 user decision open.
- **Packaging optional warning follow-up 2026-06-30:** `pb_studio.spec`
  filters optional QtSql Mimer/Postgres plugin binaries, QtWebView QML, Numba
  TBB pool, and optional hidden imports (`pycparser`, `tzdata`, scipy cdflib,
  `pysqlite2`, `MySQLdb`). Added `installer/hooks/hook-onnxruntime.py` to
  keep ONNX Runtime CUDA/CPU provider packaging while excluding TensorRT
  provider DLL. Full build
  `test-report/packaging-build-onnxfiltered-20260630.log` Exit 0; static
  smoke, launch smoke, and focus regression (`38 passed in 66.39s`) passed.
  New artifacts: EXE SHA256
  `AD3A5182767E3A41C99969D38F1B662D6B7129022B6C2DD0CC5E784362EF33FF`,
  NSISBIN SHA256
  `23DC12FA7B98F053A515B6D0302CD823266D6B7F57C3E0F5EF55F2C0CDBA1FA3`.
  Build log now still has torchaudio FFmpeg DLL warnings only. Still blocked:
  no Clean-VM, no signing, no full frozen GUI workflow, DG-001 H1 decision.
- **Packaging torchaudio warning follow-up 2026-06-30:** added
  `installer/hooks/hook-torchaudio.py` and matching `pb_studio.spec` excludes
  for `_torchaudio_ffmpeg.pyd` and `libtorchaudio_ffmpeg.pyd`. Target runtime
  torchaudio backend is `soundfile`; PB Studio uses chunked soundfile first and
  managed `bin/ffmpeg.exe` CLI fallback. Full build
  `test-report/packaging-build-torchaudiofiltered-20260630.log` Exit 0; no
  `Library not found` warnings remain in build log; static smoke, launch
  smoke, and focus regression (`34 passed in 57.88s`) passed. New artifacts:
  EXE SHA256 `2F9853539694C139C1F71A5B82F2A063FE844DA74D076C09CF64C2314578A21A`,
  NSISBIN SHA256
  `0F7DE9A1CA950D895893D5ED2EFC4FF87BC176D937DBC9F1CE5CC55E91CF06FE`.
  Still blocked: no Clean-VM install, no signing, no full frozen audio/GPU GUI
  workflow, DG-001 H1 decision.
- **Packaging frozen-audio verifier follow-up 2026-06-30:** added
  env-gated `PB_FROZEN_AUDIO_SMOKE` in `main.py`, `SMOKE_TEST_FROZEN_AUDIO=1`
  in `installer/smoke_test.py`, early-exit failure for launch smoke, and
  missing `workers.brain_v3_hashing` hidden import in `pb_studio.spec`.
  Full build
  `test-report/packaging-build-frozen-audio-smoke-hiddenimport-20260630.log`
  Exit 0; buildlog has no Library-not-found/Traceback/ModuleNotFoundError
  hits. Combined
  `SMOKE_TEST_LAUNCH=1 SMOKE_TEST_FROZEN_AUDIO=1 installer/smoke_test.py`
  Exit 0: frozen EXE stayed alive for 5s launch smoke, then frozen audio
  selftest returned `frozen=true`, `passed=true`, `ffmpeg_exists=true`,
  waveform shape `[2, 8820]`. Focus regression `34 passed in 42.54s`;
  `release_gate.py` still Exit 1 because DG-001 H1 replacement-medium user
  decision remains open. New artifacts: EXE SHA256
  `AA07928CB4EE8EB3F73940FEA949C5FF3A031629B67A1DFFA3743C16478CF01C`,
  NSISBIN SHA256
  `305687BCF6AED0031B9AFC0A9B6255B7FF310614628B7A85C3BC298B41B21619`.
  Still blocked: no Clean-VM install, no signing, no full installed-app GUI
  workflow, DG-001 H1 decision.
- **Release artifact pair audit 2026-07-01:** added
  `scripts/diag/verify_release_artifact_pair.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/release_artifact_pair_audit.json` prove current
  local artifact pair exists and is structurally coherent: version sources all
  normalize to `0.5.0`, `dist/pb_studio` size is 5,921,283,899 bytes, installer
  stub exists (422,926 bytes), NSISBI payload exists (2,815,066,504 bytes),
  required Qt/CUDA/Torch/FFmpeg/resource patterns are present, and hashes were
  recorded. Authenticode status is `NotSigned`; `release_ready=false`. Synthesis:
  `docs/superpowers/synthesis/release-artifact-pair-audit-2026-07-01.md`.
  Still blocked: no code signing, no Clean-VM install, no installed-app full GUI
  workflow, DG-001 H1 replacement-medium user decision open.
- **Release-Gate production blocker expansion 2026-07-01:** added
  `services/release_readiness.py`, updated `tools/release_gate.py`, and added
  tests. The gate now blocks on Deferred Gates plus production blockers:
  missing/invalid artifact pair, unsigned installer, missing clean-VM install
  proof, and missing installed-app full GUI proof. Verification:
  `tests/test_services/test_release_readiness.py tests/test_scripts/test_release_gate_cli.py`
  -> `3 passed in 4.38s`; direct `release_gate.py` reports DG-001 plus
  `SIGN-001`, `VM-001`, and `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/release-gate-production-blockers-2026-07-01.md`.
- **Release-Gate proof-schema hardening 2026-07-01:** `services/release_readiness.py`
  now requires explicit synthesis frontmatter for VM/App-GUI proof:
  `release_gate_proof: true`, matching `proof_type`, `status: pass`, and
  `evidence_level: live`. Random Markdown with "PASS" no longer clears a
  production blocker. Verification:
  `tests/test_services/test_release_readiness.py tests/test_scripts/test_release_gate_cli.py`
  -> `5 passed in 3.68s`; direct `release_gate.py` still reports DG-001,
  `SIGN-001`, `VM-001`, and `GUI-001`. Synthesis:
  `docs/superpowers/synthesis/release-gate-proof-schema-2026-07-01.md`.
- **Signing readiness preflight 2026-07-01:** added
  `scripts/diag/verify_signing_readiness.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/signing_readiness.json` show:
  `signtool` missing, CurrentUser/LocalMachine code-signing certificate count
  is 0, installer Authenticode is not signed (`SignerCertificate=null`), and
  `release_signing_ready=false`. Synthesis:
  `docs/superpowers/synthesis/signing-readiness-preflight-2026-07-01.md`.
  `SIGN-001` remains valid; signing cannot be completed here without a signing
  tool and certificate.
- **Clean-VM readiness preflight 2026-07-01:** added
  `scripts/diag/verify_clean_vm_readiness.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/clean_vm_readiness.json` show:
  current process is not admin, `Get-VM`/`vmrun`/`VBoxManage` are missing,
  Hyper-V feature query requires elevated rights, while installer stub and
  NSISBI payload exist. `clean_vm_ready=false`; blockers are
  `not-running-as-admin` and `no-vm-control-tool-found`. Synthesis:
  `docs/superpowers/synthesis/clean-vm-readiness-preflight-2026-07-01.md`.
  `VM-001` remains valid.
- **Installed-app GUI readiness preflight 2026-07-01:** added
  `scripts/diag/verify_installed_app_gui_readiness.py`. Direct run Exit 0 and
  JSON artifact `tests/qa_artifacts/installed_app_gui_readiness.json` show:
  installer stub and NSISBI payload exist, but current process is not admin,
  default installed EXE `C:\Program Files\PB Studio\pb_studio.exe` is missing,
  installer policy requests admin / Program Files / HKLM uninstall key, and
  installer Authenticode is not signed. `installed_app_gui_ready=false`;
  blockers are `installer-requires-admin-current-process-not-admin`,
  `installed-exe-missing`, and `installer-not-signed`. Synthesis:
  `docs/superpowers/synthesis/installed-app-gui-readiness-preflight-2026-07-01.md`.
  `GUI-001` remains valid.
- **Installed-app GUI workflow verifier 2026-07-01:** added
  `scripts/diag/verify_installed_app_gui_workflow.py`. The verifier launches
  the installed EXE, waits for a visible GUI window, records a screenshot,
  checks the four workflow tabs via UIA, and writes a schema-valid
  `release_gate_proof` only on real PASS with explicit `--write-proof`.
  Current direct run blocks with `installed-exe-missing` because
  `C:\Program Files\PB Studio\pb_studio.exe` does not exist; JSON artifact:
  `tests/qa_artifacts/installed_app_gui_workflow.json`.
  `proof_written=false`. Synthesis:
  `docs/superpowers/synthesis/installed-app-gui-workflow-verifier-2026-07-01.md`.
  `GUI-001` remains valid.
- **Release evidence matrix 2026-07-01:** added
  `scripts/diag/verify_release_evidence_matrix.py`. Direct run Exit 0 and JSON
  artifact `tests/qa_artifacts/release_evidence_matrix.json` aggregate active
  Deferred Gates, production blockers, release-proof frontmatter, and QA JSON
  artifacts for artifact pair, signing, clean VM, installed-app GUI readiness,
  and installed-app GUI workflow. Current result: `release_ready=false`,
  `status=blocked`, accepted release proofs `0`, open items `DG-001`,
  `SIGN-001`, `VM-001`, `GUI-001`. Added regression
  `tests/test_scripts/test_release_evidence_matrix.py`; focused run
  `2 passed`. Synthesis:
  `docs/superpowers/synthesis/release-evidence-matrix-2026-07-01.md`.
- **B-547 Storage-Browser delete live follow-up 2026-06-30:** added
  `scripts/diag/verify_b547_storage_browser_delete_visible.py`. Direct run
  Exit 0 with a visible real `StorageBrowserDialog`, temporary real SQLite DB,
  temporary real `storage/by_sha`, physical-delete checkbox enabled, and real
  QMessageBox confirmation/success dialogs clicked. Evidence: row count
  `1 -> 0`, summary `1 Quellen / 4.0 KB -> 0 Quellen / 0 B`,
  source root existed before and was gone after, `analysis_jobs=0`,
  `analysis_artifacts=0`, `project_sources=1`, success text reported
  `1 Speicherordner geloescht, 4.0 KB freigegeben`. Regression:
  `tests/test_services/test_storage_browser.py tests/test_ui/test_storage_browser.py`
  -> `10 passed in 2.34s`; synthesis
  `docs/superpowers/synthesis/b547-storage-browser-delete-live-2026-06-30.md`.
  Honest limit: not clean-VM, not full OTK-021 7-step live verify, no agent
  `fixed` marker.
- **OTK-021 Backup/Restore portable follow-up 2026-06-30:** added
  `scripts/diag/verify_otk021_backup_restore_portable.py`. Direct run Exit 0
  with real `StoragePortabilityBackupService`, temporary WAL-mode SQLite DB,
  real `storage/by_sha` files, ZIP manifest, restore into a second temp project
  root, DB content check, and SHA256 comparison of restored files. Evidence:
  `backup_storage_file_count=2`, `restore_storage_file_count=2`,
  restored DB `user_version=21`, restored value `wal-visible`, storage hashes
  matched, manifest schema/model/storage fields correct. Regression:
  `tests/test_services/test_backup.py` -> `2 passed in 1.09s`; synthesis
  `docs/superpowers/synthesis/otk021-backup-restore-portable-2026-06-30.md`.
  Honest limit: local roundtrip only; Backup/Restore on VM still open.
- **OTK-021 Project-Bundle follow-up 2026-06-30:** added
  `scripts/diag/verify_otk021_project_bundle_roundtrip.py`. Direct run Exit 0
  with real `ProjectBundleService`, separate file-backed export/import SQLite
  DBs, separate source/target `storage/by_sha` roots, real `.pbbundle`, two
  sources, two jobs, two artifacts, two files, manifest verification, imported
  DB verification, and restored file SHA256 comparison. Regression:
  `tests/test_services/test_project_export.py` -> `3 passed in 1.36s`;
  synthesis
  `docs/superpowers/synthesis/otk021-project-bundle-roundtrip-2026-06-30.md`.
  Honest limit: local roundtrip only; Project-Export + Import on another VM
  still open.
- **OTK-021 Disk-Budget follow-up 2026-06-30:** added
  `scripts/diag/verify_otk021_disk_budget_real.py`. Direct run Exit 0 with
  real `DiskBudgetService`, file-backed SQLite DB, real `storage/by_sha`
  files, two projects, two used sources, one old unused source, one recent
  unused source, summary/project usage check, cleanup estimate check, and real
  free-space probe. Evidence:
  `tests/qa_artifacts/otk021_disk_budget_real_result.json` reports
  `total_bytes=10000`, `source_count=4`, cleanup `reclaimable_bytes=3000`,
  and real disk free-space probe passed. Low-space guard uses patched
  `disk_usage(free=10)`; disk filling was intentionally not done. Regression:
  `tests/test_services/test_disk_budget_global.py` -> `3 passed in 1.17s`;
  synthesis
  `docs/superpowers/synthesis/otk021-disk-budget-real-2026-06-30.md`.
  Honest limit: local service verification only; installed-app/VM path still
  open.
- **DG-001 G.* neu belegt 2026-06-30:** added
  `scripts/diag/verify_dg001_g_schnitt_gui.py` and versioned synthesis
  `docs/superpowers/synthesis/dg001-g-schnitt-gui-live-2026-06-30.md`.
  Direct run with `pb-studio` env exited 0 / `passed=True`: visible
  `SchnittWorkspace`, editor state, tabs `Schnitt`, `Pacing & Anker`,
  `Audio`, `RL & Notes`, 2 timeline clips, 1 locked video clip, 1 waveform,
  RL Notes DB roundtrip, real `QMessageBox` Re-Generate warning, and `No`
  emitted no regenerate signal. Honest limit: synthetic minimal project, not
  historical `test55655`, not a full all-workspaces product run. Release-Gate
  still blocks: DG-001 now waits on the User decision whether the H1 looped
  medium is accepted as replacement for the lost historical H1 original.
- **Latest B-564 code-fix 2026-06-29:** branch contains B-564 work after
  `d69115f`. Completion-Bridge now refreshes the active Video/Audio analysis
  status panel when its `media_type` and `media_id` match the completed step.
  Verification: B-564 focus `2 passed in 2.27s`; affected Statuspanel/
  Completion regression `16 passed in 9.54s`; `py_compile` PASS;
  `git diff --check` PASS. No GUI pipeline live retest yet; status remains
  `code-fix-pending-live-verification`, not `fixed`.
- **B-569 status 2026-06-29:** current code already contains the A1-lane
  audio dropdown fix in `MediaTableController._a1_audio_combo_index()` and
  uses it in both sync `_refresh_director_combos()` and async
  `_apply_refreshed_data()`. Focus tests are green:
  `tests/ui/test_b569_audio_dropdown_reflects_a1.py`
  `tests/ui/test_b577_async_dropdown_reflects_a1.py` -> `2 passed in 6.66s`.
  Vault status moved to `code-fix-pending-live-verification`; no fresh visible
  GUI retest in this session, not `fixed`.
- **B-562 status 2026-06-30:** current code already contains the Cockpit
  full-refresh fix in `ProjectManagementController._on_project_changed()`.
  Focus test refreshed:
  `tests/ui/test_b562_project_open_refreshes_cockpit.py -q` ->
  `2 passed in 3.70s`. Vault frontmatter moved from stale `open` to
  `code-fix-pending-live-verification`. No fresh visible GUI retest in this
  session, not `fixed`.
- **B-567 status 2026-06-30:** current code contains the persistent
  `PBWindow.show_status_error()` path and Brain-V3 error bridge. Focus tests:
  `tests/test_ui/test_b567_brain_v3_error_statusbar.py`
  plus
  `tests/test_services/test_brain_v3_embedding_scheduler.py::test_failed_job_emits_error_text`
  -> `3 passed in 10.16s`. Vault frontmatter moved from stale `open` to
  `code-fix-pending-live-verification`. The exact AudioPipelineV2/Demucs GUI
  path was not freshly live-triggered in this session, not `fixed`.
- **B-573 status 2026-06-30:** current code already contains the frame-sampler
  EOF prevention for late RAFT timestamps. Focus test refreshed:
  `tests/test_services/test_video_frame_sampler.py -q` ->
  `8 passed in 0.67s`. Vault frontmatter moved from stale `open` to
  `code-fix-pending-live-verification`. Prior Agent-Live-PASS remains noted in
  the bugfile; no new 4h RAFT product live retest in this session, not
  `fixed`.
- **Previous push 2026-06-29:** `d69115f test(OTK-021): fix storage browser UI test hang`
  is pushed to origin.
- **Current OTK-021 preflight 2026-06-29:** Startup system check with
  `pb-studio` env and start-script env vars is green: local
  `bin/ffmpeg.exe` 6.1.1, `ffprobe`, real `h264_nvenc`, CUDA on
  GTX 1060, Python 3.10.20, Ollama, `beat_this`, and Demucs all OK.
  Earlier NVENC failure was PATH/WinGet FFmpeg, not the app-resolved binary.
- **Current OTK-021 regression 2026-06-29:** OTK-021 combined non-live slice
  is green: `66 passed in 21.13s`. Storage-Browser UI hang was test-only:
  the test patched the wrong `QMessageBox` object and opened a real offscreen
  modal. Product code unchanged.
- **Current release status 2026-06-30:** `python tools\release_gate.py`
  exits 1. DG-001 remains active
  (`h1-3-h3-g-reverified-PLUS-h1-user-decision-open`): H1
  replacement-medium decision still prevents `fixed` or release status.
- **Worktree:** `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild`
- **Basis:** `origin/main=9570374` (Agent_Tests PR #5).
- **Merge:** `5f428ec` integriert 16 Commits aus
  `origin/claude/B-539-cross-project-reuse-by-sha-2026-06-18`, inkl.
  B-539, B-543..B-546, B-548, Recovery-/Dependency-/beat_this-Arbeit.
- **B-549:** `91d62c1` — Audio-V2 cooperative cancellation aus Fremdrepo-Commit
  `0f7fc3e` diffgenau rekonstruiert. Fokus: `3 passed`.
- **B-554:** `d833492` — dirty Originaldiff byteidentisch übernommen:
  lokaler HF-Cache zuerst, persistente Embedder, Unload beim Scheduler-Stop.
  Fokus: `8 passed`; frühere GUI-Live-Evidenz 52 Clips/1 Modell-Load/76 s.
- **BUG-A:** `7de108a` — SCHNITT-State nach Auto-Edit refresht; dirty
  Originaldatei byteidentisch übernommen. Fokus: `30 passed`.
- **B-570 status 2026-06-30:** codefix is still in place and now has a
  visible verifier. Added `scripts/diag/verify_b570_shutdown_visible.py`, which
  launches a real visible Qt window with `PBWindow.closeEvent`, creates a
  cancelled-but-still-running QThread, closes the window, clicks the real
  `Laufende Tasks` QMessageBox via pywinauto, and checks process exit. Clean
  run: `python scripts/diag/verify_b570_shutdown_visible.py --timeout-s 60`
  -> exit 0; result artifact says `clicked_dialog=true`,
  `clicked_button=Yes`, `returncode=0`, `alive_after=false`. Focus regression
  after that:
  `tests/test_services/test_b570_shutdown_tasks.py`
  `tests/test_services/test_b570_shutdown_process.py` -> `3 passed in 14.80s`.
  Versioned evidence:
  `docs/superpowers/synthesis/b570-visible-shutdown-2026-06-30.md`.
  Honest limit: this is a minimal PBWindow/live-QThread verifier, not the full
  original production case with five concurrent analysis pipelines. Status
  remains `code-fix-pending-live-verification`, not `fixed`.
- **DG-001 H3 neu belegt 2026-06-23:** finaler Run `20260623-050437`
  auf GTX1060. Echter `htdemucs_ft`-Lauf (`reused=False`, vier Stems,
  Audio 8/8) parallel zur echten SigLIP+RAFT-Video-Pipeline (7/7).
  Beide Threads beendet, Wall 36.375 s, Peak 4534/6144 MiB, kein
  Deadlock/OOM. Runner:
  `scripts/diag/verify_dg001_h3_concurrency.py`; versionierter Beleg:
  `docs/superpowers/synthesis/dg001-h3-concurrency-live-2026-06-23.md`.
  DG-001 bleibt wegen H1-Ersatzmedium-User-Entscheid blockiert.
- **Kombinierte Suite:** `80 passed in 9.07s`; `compileall`, Ruff und
  `git diff --check` grün.
- **Vollsuite-Gate BLOCKIERT:** `pytest -q -m "not gui and not e2e and not
  live_gpu and not long_form"` bricht während Collection ab:
  `tests/test_video_analysis_real.py:93` ruft import-time `sys.exit(1)` auf.
  Kein Vollsuite-Testverdikt; nicht als Regression des Integrationsdiffs
  eingeordnet oder gefixt.
- **Originalrepo:** dirty Zustand nicht verändert.
- **Statussprache:** Integration test-grün; kein neuer vollständiger GUI-/GPU-E2E,
  keine neuen `fixed`-Marker.
- **Push:** Branch auf `origin` vorhanden.
- **Nächster Schritt:** offene OTK-021 Live-Bugs weiter triagieren/fixen.
  B-570 braucht weiter sichtbaren GUI-Klickpfad; B-562/B-567 haben bereits
  Code-/Live-Hinweise im Bugfile, aber keine User-`fixed`-Freigabe.

## ⛔ VERIFIKATIONS-AUDIT 2026-06-18 — viele „fixed/PASS"-Marker sind NICHT gedeckt
Ein 4-Agenten-Audit (read-only) ergab: von 23 geprüften OTK/DG-001/Bug-Markern sind nur **7
nachprüfbar, 12 nicht überprüfbar (Evidenz gelöscht/nie im Clone), 4 ehrlich offen**.
NICHT überprüfbar (reine Doku, NICHT als grün behandeln, vor Release neu fahren):
**DG-001 H1/H1.3/H2.1-alt/H3/G.\***, **OTK-016/017/018/019**, **B-505, B-520**.
Einzeln nachgeprüft 2026-06-18: **B-512** (fixed widerspricht eigenem Body „Live offen", kein Test) + **B-532**
(nur Linter, defensives try-except) = belegfrei, geflaggt. **B-527 + B-528 sind belegt** (existierende Tests
`test_backup_service.py` 15p / `test_project_save_action.py` 4p selbst grün, ehrliche Vorbehalte, User-Freigabe) —
der Pauschal-Verdacht des Forensik-Agenten war für diese beiden falsch.
Echt gedeckt (Screenshots vorhanden): **OTK-003/004/008/009/010** (09.06.).
Per DB-Seed statt voll-E2E verifiziert (Integration NICHT bewiesen): **B-539 T32, Tier 31, Block 1**
(Backup-70 + Disk-Budget-71 sind sogar toter Code ohne App-Aufruf).
**B-539 `fixed` wurde zurückgezogen** → `fixed-with-critical-gaps` (siehe B-543..B-546).
Vollständig: `wiki/synthesis/verifikations-gesamtaudit-2026-06-18.md`. OTK-021 ist NICHT release-/fixed-reif.

## Codex Recovery Session 2026-06-16 (newest)

- **Scope:** Restore local-only progress from the non-git folder
  `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild`
  into a clean GitHub clone without overwriting the old folder.
- **Current working repo:** `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild_github_compare`.
  Use this repo/worktree, not the old non-git folder.
- **Branch:** `codex/recover-local-analysis-percent-2026-06-16`.
- **Commit:** `137c15e chore(recovery): restore local analysis percent progress`.
- **Remote:** branch pushed to
  `origin/codex/recover-local-analysis-percent-2026-06-16`.
- **Recovered files:** `services/analysis_status_service.py`,
  `services/ingest_service.py`, `tests/conftest.py`,
  `tests/test_services/test_ingest_service.py`.
- **Recovered behavior:** bulk analysis-status inference and percent map,
  bulk media-list `analysis_percent` refresh, and regression coverage for
  video metadata not showing as `0%`.
- **Verification:** `git diff --check` passed; `py_compile` passed for the
  four recovered files. Targeted regression test passed in a temporary local
  Python 3.10 conda env:
  `tests\test_services\test_ingest_service.py::TestGetAllMedia::test_get_all_video_backfills_metadata_analysis_percent`
  -> `1 passed in 6.80s`. The temporary `.conda-test` env was removed after
  the run.
- **Full small-data audio E2E 2026-06-16:** User requested a full test run
  with few data and a 4-minute audio. A local `.conda-pb-full` env was created
  from Python 3.10 plus `requirements-py310-cu113.txt`. Smoke check reported
  `torch 1.12.1+cu113`, `cuda_available True`, GPU `NVIDIA GeForce GTX 1060`,
  and `pipeline_import_ok 8`. Synthetic 4-minute WAV:
  `test-report\e2e-audio-4min-20260616\synthetic_4min.wav`.
  Command:
  `.\.conda-pb-full\python.exe scripts\diag\e2e_audio_pipeline_orchestrator.py --audio test-report\e2e-audio-4min-20260616\synthetic_4min.wav`.
  Result: `EXITCODE=0`; orchestrator log reports `failed=False`,
  `total=274.3s`; stages completed: `stem_gen`, `beat_grid`, `onset`, `key`,
  `structure`, `lufs`, `spectral`, `av_pacing`. Evidence log:
  `test-report\e2e-audio-4min-20260616\e2e_audio_pipeline.log` (ignored by
  git).
- **Full small-data audio E2E limits:** `vendor/beat_this` submodule cannot be
  initialized because remote commit `7ecf41375b9be919099b1ea2ecdd9fe5df937fa3`
  is not available from `https://github.com/CPJKU/beat_this.git`. Therefore
  beat detection used the built-in librosa fallback and returned `bpm=0.0` for
  the synthetic test file. This is not proof that the `beat_this` path works.
- **Current request follow-up:** Added context-budget clean-stop discipline
  to `AGENTS.md`: when context/capacity is low, stop starting new work,
  finish only the smallest safe unit, write exact handoff, run
  `tools\agent_handoff.ps1`, and leave no hidden dirty state.
- **Vault path correction:** use
  `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio`
  for current Vault logging. Older docs may still mention
  `C:\Brain-Bug\projects\pb-studio`.
- **Open:** Recovery branch has not been merged to `main`. Full PB Studio test
  environment is still not restored; only the targeted regression test above
  passed. DG-001 remains open; no release/fixed claim allowed.
- **Next safe step:** create/review PR for the recovery branch, then decide
  whether to merge after broader test coverage or restore the full
  `pb-studio` Python environment.

## Cowork-Agent-Session 2026-06-15 (newest)

- **Scope:** Status-Review-Folgearbeit + Release-Gate + E2E-Live-Abnahme + DG-001 Teil-Live-Verify.
  Alle Aenderungen committet + auf `origin/main` gepusht (head `855ae32` zum Schreibzeitpunkt; H1-Lauf laeuft noch).
- **Alembic-CRITICAL (13.06.) = bereits gefixt + test-abgesichert** (11 passed); Orphan-Index-Drop-Revision
  `f0a1b2c3d4e5` hinzugefuegt (idempotent, gegen Live-DB verifiziert). Commit `cbfbca4`.
- **Release-Gate (neu):** `services/deferred_gates.py`, `tools/release_gate.py` (Exit 2 bei offenen Gates),
  `tools/agent_handoff.ps1 -ReleaseGate`, weiches Start-Banner in `services/startup_checks.py`
  (LIVE in GUI bestaetigt). Pflicht-Checklisten: `docs/superpowers/E2E_LIVE_ACCEPTANCE.md`,
  `docs/superpowers/DG-001_LIVE_VERIFY.md`.
- **E2E-Live-Abnahme** (Service + GUI, GTX 1060): Phasen 1-4 PASS. Beleg
  `test-report/e2e-live-acceptance-20260615/RESULT.md`. **DG-001 H3** (Demucs+Video parallel) PASS,
  **G.\*** SCHNITT-GUI live PASS, **H2.1** NVENC-Export. **H1** 62-Min-Scale-Lauf laeuft (VRAM stabil).
- **Neue Bugs gefixt:** **B-536** PacingStrategist Fence-Parse-Mislabel (Commit `dd90d87`),
  **B-537** Diag-Skripte Repo-Root (Commit `2fb7f4d`). Status beide `code-fix-pending-live-verification`.
- **OTK-008:** Audio-"fehlt"-Blockade ist nur Such-String-Fehler (`Crusty_Progressive Psy Set2.mp3`
  mit Unterstrich existiert) -> aufhebbar. Doku `docs/superpowers/E2E_FINDINGS_2026-06-15.md` (`b162015d`).
- **Next agent:** H1-Endergebnis aus `outputs/h1_scale.log` (`H1_EXIT`) lesen; offen bleiben user-only
  H1.3 (4h), H2.2 (Playback-Verdikt), CRF-D1/D2/D3. KEIN `fixed`-Marker gesetzt.

## Latest Governance Update

- **Date:** 2026-06-14
- **Active plan:** `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`
- **Repo plan:** `docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md`
- **Vault mirror:** `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md`
- **Decision:** `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md`
- **Status:** CRF executable fix waves are complete per CRF Vault mirror; B-498..B-520 and B-523..B-529 are recorded fixed after live/user confirmation. `ACTIVE_PLAN.md` selects the OTK masterplan only. OTK-018 was live-verified-complete on 2026-06-14 after user broad autonomous release. OTK-019 technical rest-probe passed; user decided to defer the heavy 4h live gate for later.
- **CRF remaining:** CRF-D1 Brain deprecation, CRF-D2 Vault sync, CRF-D3 cu121/torch-2.x migration remain user decisions, not agent app-code tasks.
- **Next task:** `OTK-021 90 Live-Verify`. User approved prerequisite waiver on 2026-06-14, with deferred gates tracked in `docs/superpowers/DEFERRED_GATES.md`.
- **Parallel work rule:** user gave broad release on 2026-06-14, but AGENTS.md still forbids parallel half-finished app-code work in the same repo. Parallel teams may only do read-only analysis or work in isolated worktrees after one task is selected.
- **OTK-018 verification:** focused Audio-V2 package `82 passed`; fresh GTX-1060 service E2E ran stem_gen, beat_grid, onset, key, structure, lufs, spectral, av_pacing with `failed=False` in 276.4s; real GUI selected audio and clicked `Audio analysieren`, console showed V2 default route start and completion with no V2 error. Evidence: `test-report/e2e-audio-v2-otk018-2026-06-14-fresh.log`, `test-report/otk018-audio-v2-gui-live-2026-06-14.log`, `test_reports/otk018_audio_v2_gui_live_20260614.py`.
- **OTK-019 2026-06-14:** focused technical tests `39 passed`; `test_reports/otk019_remaining_verify_20260614.py` exit 0. Passed: proxy generation/decode (size ratio 0.1301, 5s decode in 0.344s), 3-keyframe contact sheet, process-kill resume from checkpoint, synthetic 4h coverage guard 100%, GPU-lock wait behind simulated Audio-V2 holder. Honest limits: no human/QMediaPlayer smoothness verdict, no full 4h video through all model stages, no real concurrent Demucs+Video run. User decision: defer heavy 4h gate for later, status `deferred-heavy-live-gate`.
- **OTK-021 2026-06-14:** prerequisite re-check only. Audio-V2 is now agent-live-verified-complete, but Plan A heavy live gate is deferred, Plan B Tier-1/2 completion is not proven, and no explicit Plan-C prerequisite waiver/user V2 acceptance exists. Status remains `blocked-prerequisite-rechecked-2026-06-14`.
- **OTK-022 2026-06-14:** Phase-2 review completed. Read `_lib/build_edl_v7.py` and PB pacing counterparts. Thematic Chapter Sequencing is useful design pattern, but port would introduce new PB feature/architecture surface. No code port. Status `completed-no-port-design-pattern`.
- **OTK-021 waiver 2026-06-14:** user approved proceeding despite missing OTK-019 heavy gate, explicitly requiring the deferred work not be forgotten. DG-001 tracks full 4h model-pipeline, human playback acceptance, and real Demucs+Video coexistence before fixed/release status.
- **OTK-021 Tier 1 2026-06-14:** DB-Provenance tables and Storage-Layout helper are code/tests complete. Added Alembic revision `e5f6a7b8c9d0`, ORM models, `services/storage_provenance/layout.py`, and focused tests. Verification: `6 passed` focused, `5 passed` migration regressions, `2 passed` Alembic roundtrip, py_compile, `git diff --check`. No fixed marker.
- **OTK-021 Tier 2 2026-06-14:** Building blocks are code/tests complete: `source_identity.py`, `file_tracking.py`, `dedup_lookup.py`, `adapter_layer.py`, plus focused tests. Verification: Tier-2 `9 passed`; Tier1+Tier2 combined `15 passed`; py_compile; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 Tier 3/30 2026-06-14:** Storage-Migration-Service code/tests complete. Registers existing V2 stems and Plan-A video outputs into provenance tables; audio stems use Junction/Symlink under `by_sha`. Verification: storage migration/layout `6 passed`; OTK-021 service suite `18 passed`; py_compile; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 Tier 3/31 2026-06-14:** SCHNITT-Audio-Adapter code/tests complete. `ProjectManager.open_project()` runs adapter defensively after DB init; service builds missing stem Junctions idempotently. Verification: adapter/storage-migration `5 passed`; OTK-021 Slice `20 passed`; py_compile; `git diff --check`. No GUI live click; no fixed marker.
- **OTK-021 Tier 3/32 2026-06-15:** Cross-Project-Reuse UX code/tests complete. Added `services/storage_provenance/cross_project_reuse.py`; import path applies reusable provenance to `analysis_status`; status panel shows provenance tooltips; import controller shows non-modal reuse notice with project-scoped "Nicht mehr fragen". Verification: cross-project reuse focus `5 passed`; OTK-021 Slice `20 passed`; py_compile; `git diff --check`. No product live re-import verification; no fixed marker.
- **OTK-021 Tier 3/33 2026-06-15:** Storage-Browser UI code/tests complete. Added `services/storage_provenance/storage_browser.py`, `ui/dialogs/storage_browser_dialog.py`, and Settings button. Browser lists sources sorted with project usage, stage count, byte total, last-used, unused/age filters, per-row delete, and bulk delete with confirm. Verification: storage-browser focus `5 passed`; OTK-021 Slice `27 passed`; py_compile; `git diff --check`. No Settings GUI live click; no fixed marker.
- **OTK-021 Tier 3/34 2026-06-15:** Project-Export + Import code/tests complete. Added `services/storage_provenance/project_bundle.py` and tests. Exports `.pbbundle` zip with manifest, project subset, project_sources, analysis_jobs/artifacts, and referenced `by_sha` files; import validates manifest/file SHA, preserves existing artifacts on conflict, creates project and sources. Verification: project-export focus `3 passed`; OTK-021 Slice `30 passed`; py_compile; `git diff --check`. No real same-machine/other-machine export-import live verification; no fixed marker.
- **OTK-021 40 Caller-Migration 2026-06-15:** Caller-Migration code/tests complete. Added `services/storage_provenance/caller_migration.py`; Audio V2 `StemGenStage` writes `analysis_jobs`/`analysis_artifacts` for generated or reused stems; Plan-A `VideoAnalysisPipeline` writes done-stage provenance artifacts. Verification: caller-migration focus `3 passed`; OTK-021 Slice `33 passed`; py_compile; `git diff --check`. No product live V2/Plan-A GUI workflow verification; no fixed marker.
- **OTK-021 50 Service-Coverage 2026-06-15:** Service-Coverage code/tests complete for `services/storage_provenance/*`. Added tests only in `tests/test_services/test_cross_project_reuse.py`, `tests/test_services/test_file_tracking.py`, `tests/test_services/test_storage_browser.py`, and `tests/ui/test_schnitt_audio_adapter.py`. Verification on `pb-studio` env: `41 passed`; total storage provenance coverage `93.31%`; every `services/storage_provenance` file at least `87%`; `compileall`; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 51 Controller-Coverage 2026-06-15:** Controller-Coverage code/tests complete. Added `ui/widgets/cross_project_reuse_toast.py`, delegated `ImportMediaController._show_cross_project_reuse_notice()` to it, and added real Qt tests for storage browser dialog, reuse toast, and SCHNITT audio binder. Verification: UI focused `15 passed`; coverage total `90.24%`; `ui/dialogs/storage_browser_dialog.py` 88%, `ui/widgets/cross_project_reuse_toast.py` 88%, `ui/controllers/schnitt_audio_binder.py` 96%, `services/storage_provenance/schnitt_audio_adapter.py` 100%; OTK-021 Slice `48 passed`; `compileall`; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 60 Test-Infra 2026-06-15:** Test-Infra code/tests complete. Added `tmp_storage_root`, `mock_v2_stems`, `mock_project_with_artifacts`, and `directory_link_factory` fixtures in `tests/conftest.py`, plus offline proof test `tests/test_services/test_storage_provenance_test_infra.py`. Verification: infra focus `1 passed`; OTK-021 Slice `49 passed`; `compileall`; `git diff --check`. No product live verification; no fixed marker.
- **OTK-021 70 Backup-Portability 2026-06-15:** Backup-Portability code/tests complete. Added `services/storage_provenance/backup_portability.py` with portable ZIP backup manifest, SQLite backup API snapshot, `storage/by_sha` full-copy payload, restore extraction, and frequency settings validation. Verification: `tests/test_services/test_backup.py` `2 passed`; OTK-021 Slice later `51 passed`; `compileall`; `git diff --check`. No VM restore/live verification; no fixed marker.
- **OTK-021 71 Disk-Budget Global 2026-06-15:** Disk-Budget code/tests complete. Added `services/storage_provenance/disk_budget.py` with total/project usage summary, unused-old cleanup estimate, and free-space migration probe; Storage-Browser summary now shows total bytes. Verification: disk-budget + storage-browser focus `7 passed`; OTK-021 Slice `54 passed`; `compileall`; `git diff --check`. No product live verification; no fixed marker.

## Previous Governance Update

- **Date:** 2026-06-09
- **Active plan:** `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09`
- **Repo plan:** `docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md`
- **Vault mirror:** `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-offene-tasks-konsolidierung-masterplan-2026-06-09.md`
- **Decision:** `C:\Brain-Bug\projects\pb-studio\wiki\decisions\D-061-offene-tasks-konsolidierung-masterplan.md`
- **Status:** previous registry plans with open work were marked `superseded` and transferred into OTK tasks. No app-code change. No product bug marked `fixed`.
- **OTK-001:** Governance drift in this handoff file was cleaned on 2026-06-09. Older FFmpeg/B-471/B-458/B-462/B-463 details remain represented in the OTK masterplan, not as active-plan authority here.
- **OTK-002:** Completed by user continuation release plus agent review. No blocking issue found in `.agents/skills/pb-agent-team-architect`, `pb-live-verify-orchestrator`, `pb-concurrency-strike-team`, or `pb-release-readiness-team`. No claim that the user read every file line-by-line.
- **OTK-003:** Agent-side check ran on 2026-06-09 and later autonomous GUI verification passed for project `test55655`: waveform, thumbnails, zoom controls, cut list, and clip inspector observed. User explicitly approved `fixed` marker on 2026-06-09.
- **OTK-020/B-473:** User authorized switching focus on 2026-06-09. Root cause evidence: app settings pointed at `http://legacy:8080` with `legacy-model`, while local Ollama answered on `localhost:11434`; full PB system prompt caused `OllamaClient.chat()` timeout beyond 120s; ChatDock watchdog was 60s. Code now falls back from stale configured URL to localhost, reselects missing model, caps LocalAgent system prompt for GTX-1060 latency, and uses a 180s ChatDock watchdog. User settings were reset to `http://localhost:11434` / `gemma3:4b` after backup. Standalone agent smoke returned `OK` in 67.34s. Autonomous GUI verification passed and user approved `fixed` marker on 2026-06-09.
- **Filled checklist update 2026-06-09:** `C:\Users\David Lochmann\Desktop\PB-Studio-Pruefcheckliste-2026-06-09-AUSGEFUELLT.md` reports OTK-020, OTK-003, OTK-004, OTK-008 as GUI PASS; OTK-010, OTK-015, OTK-019 as PARTIAL; remaining listed tasks as decision/scope. The checklist explicitly says no agent-side `fixed` marker.
- **Autonomous GUI verification 2026-06-09:** Agent used real PB Studio GUI with `pywinauto`. OTK-020 PASS (ChatDock/Ollama UI answer, KI-Agent tasks finished); OTK-003 PASS (project `test55655`, SCHNITT timeline/waveform/thumbnails/zoom/cut list/inspector); OTK-004 PARTIAL PASS (media table and analyzed clips observed, no new import); OTK-008 PASS for GUI navigation (Pacing/Anker, Audio, RL Notes, Schnitt tabs). Evidence: `test_reports/live_autonomous_20260609_*.png`; Vault synthesis `wiki/synthesis/functional-test-otk-autonomous-gui-2026-06-09.md`. `fixed` markers were set only after explicit user approval.
- **OTK-020/B-473:** User explicitly approved `fixed` marker on 2026-06-09 after autonomous GUI verification.
- **OTK-004:** User gave broad release, then agent executed missing GUI import/live resolver path. Video import dialog opened, 1 MP4 selected, FolderImport and BrainV3Hashing finished, media table stayed populated, no checked Traceback/ERROR/resolver failure. OTK-004 marked `fixed`.
- **OTK-008:** User selected `test55655` and wrote `freigegeben`. Agent ran substitute GUI verification on existing project `test55655`: SCHNITT opened, RL Notes text was written, app restarted, project reopened, and the same RL Notes text was still present. Agent also checked `cut_rate_combo` wheel protection by hover+wheel-scroll; combo crop stayed pixel-identical (`diff_sum=0.0`). Notes-editor undo also passed: suffix appended, `Ctrl+Z`, exact original text returned. Pacing regenerate mouse-automation attempts did not show the dialog, but UIA `Invoke()` on the same visible enabled button showed the expected QMessageBox; B-474 corrected to `cannot-reproduce` as app bug. Evidence: `test_reports/live_autonomous_20260609_otk008_rl_notes_after_reload.png`, `test_reports/live_autonomous_20260609_otk008_cut_rate_after_wheel.png`, `test_reports/live_autonomous_20260609_otk008_undo_notes_after_ctrlz.png`, `test_reports/live_autonomous_20260609_otk008_regenerate_dialog_invoke.png`; repo synthesis `docs/superpowers/synthesis/functional-test-otk008-test55655-substitute-2026-06-09.md`. Honest status: partial substitute verification only; formal Phase-12 criteria still open, so no `fixed` marker.
- **OTK-008 autonomous limit:** Formal Phase-12 completion is blocked because `Crusty Progressive Psy Set2.mp3` was not found and the available Solo_Natur folder contains 124 MP4 files instead of the plan's 103. Substitute checks passed only for `test55655` navigation, RL Notes persistence, combo-wheel protection, notes-editor undo, and regenerate dialog via UIA Invoke. No `fixed` marker.
- **OTK-009:** Completed on 2026-06-09. B-310 and B-313 live-verified on `test55655`; SCHNITT timeline, thumbnails, cut list, audio metadata/stems/waveform, and sub-tab tooltip were observed. B-316..B-320 current Vault state is fixed; no remaining contradiction found.
- **OTK-010:** Fixed on 2026-06-09 for masterplan scope. Brain V3 boot health, GpuSerializer init, EmbeddingScheduler active, Brain V3 GUI panel, Brain V3 tests (`37 passed`), isolated NVENC 1-frame encode, existing B-276 Brain+NVENC serializer live evidence, adopted D-035 Pacing decision, and B-370 GUI Auto-Edit with Studio-Brain flag were verified. GUI Auto-Edit on `test55655` produced 767 segments / 767 cuts and 1447 `mem_decision` rows.
- **OTK-011:** Completed on 2026-06-09 as decision/transfer task. Original area audit completed all 10 audit areas and final synthesis; user-approved follow-up fixplan already exists as `PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25`. Remaining B-348..B-430 fix/live work is tracked as OTK-007.
- **OTK-012:** Completed on 2026-06-09 as decision/transfer task. Full project file audit completed as read-only static audit; user-approved follow-up fixplan exists as `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31` via D-055. Remaining fixplan work is tracked as OTK-005.
- **OTK-013:** Completed on 2026-06-09 as decision/transfer task. Conflict-quality audit completed as static audit; user decision exists as D-058 for FFmpeg resolver fix CQ-004/CQ-005. That follow-up was transferred to OTK-004 and live-verified there. No new broad fixplan was invented for candidate-only findings.
- **OTK-016:** Completed on 2026-06-09. B-327 fixed (M4A FFmpeg fallback E2E), B-332 fixed (preview anchored to first video), B-197/B-198 fixed (live via OTK-010 + guard tests), B-331 cannot-reproduce (chunk-51 hang), B-265 wontfix (SB2 dGPU intermittent, no code bug). No agent `fixed` marker on product bugs without user.
- **OTK-017:** Completed on 2026-06-10. 11 bugs user-confirmed fixed after GUI live-verify (B-458/459/460/463/464/465/466/467/468/470/472); B-469 stays parked-monitoring. Commits 88fd73b/b9d6b63/a7776d2/8075a92/683f048. New findings B-490/B-491 filed open (out of scope).
- **Next task:** `OTK-017 completed. User selects next among open OTK tasks (OTK-005/007/018/019/021/022) or triage B-490/B-491.`

## Current Protocol

1. Start every agent session with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\agent_start.ps1
   ```

2. End or switch every agent session with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\agent_handoff.ps1
   ```

3. Source of truth order:

   - Git commits on the current branch.
   - `docs/superpowers/ACTIVE_PLAN.md`.
   - Vault living plan and `C:\Brain-Bug\projects\pb-studio\log.md`.
   - This file.

4. Chat history is not source of truth. If it is not in Git or Vault, next
   agent must treat it as unknown.

## Current Branch

`codex/OTK-021-source-consolidation-2026-06-22`

Latest pushed product/tool commit:

```text
d37e710 fix(B-555): make release gate console-safe
```

Push status: `origin/codex/OTK-021-source-consolidation-2026-06-22...HEAD 0 0`
after commit `d37e710`.

## Current Active Plan

See `docs/superpowers/ACTIVE_PLAN.md`.

Active plan:

```text
PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
```

Current next task:

```text
Quellstand konsolidiert. Folgeblocker B-556/B-559/B-557/B-560/B-561
sequenziell korrigiert. Finale vollständige Nicht-Live-Suite:
2762 passed, 45 skipped, 5 deselected, 0 failed.
OTK-021 Live-Preflight 2026-06-22 ist BLOCKED:
GTX 1060 `CM_PROB_PHANTOM`, CUDA false, H.264/HEVC NVENC
`CUDA_ERROR_NO_DEVICE`. App nicht gestartet; Intel/CPU-Ersatz verboten.
Nach Hardware-Recovery Preflight wiederholen, dann GUI/DG-001 fortsetzen.
Main-Integration/Release bleiben gestoppt.
```

Current OTK-021 Step 3 status:

```text
2026-07-03 product-path live pass, manual GUI click pending.
Real ProjectManager project A/B, real ingest_audio import into both projects,
global by_sha manifest + real stem artifacts, Project B AnalysisStatus
stem_separation=done, stem paths exist, and ImportMediaController
_notify_cross_project_reuse() created the reuse message and non-modal notice.
Evidence:
docs/superpowers/synthesis/otk021-step3-cross-project-reuse-import-notify-2026-07-03.md
and tests/qa_artifacts/otk021_cross_project_reuse_import_notify_result.json.
Verifier: scripts/diag/verify_otk021_cross_project_reuse_import_notify.py status=pass.
Focused tests: cross-project reuse 17 passed; manifest robustness 8 passed.
Honest limit: no manual import-dialog GUI click. OTK-021 overall remains open;
Steps 1-2 still need current product-live evidence.
```

Current OTK-021 Step 4 status:

```text
2026-07-03 product-path live pass, GUI live pending.
ProjectManager.open_project() now repairs stale ProjectSource paths by SHA
inside the opened project folder. Evidence:
docs/superpowers/synthesis/otk021-step4-file-tracking-open-project-live-2026-07-03.md
and tests/qa_artifacts/otk021_file_tracking_open_project_result.json.
Verifier: scripts/diag/verify_otk021_file_tracking_open_project.py status=pass.
Unit: tests/test_services/test_file_tracking.py 3 passed.
Syntax: py_compile Exit 0.
Honest limit: no manual GUI click. OTK-021 overall remains open; Steps 1-2
still need product-live evidence.
```

Current OTK-003 status:

```text
fixed: autonomous GUI SCHNITT/timeline workflow passed, and user explicitly approved `fixed` marker on 2026-06-09.
```

Current OTK-020 status:

```text
fixed: standalone service smoke green, autonomous GUI ChatDock/Ollama test passed, and user explicitly approved `fixed` marker on 2026-06-09.
```

Current OTK-004 status:

```text
fixed: autonomous GUI media/import workflow passed after user broad release; FolderImport and BrainV3Hashing finished, no checked resolver failure.
```

Current OTK-008 status:

```text
partial-substitute-live-verification-formal-open: `test55655` SCHNITT/RL Notes persistence passed after restart/reload; `cut_rate_combo` wheel protection passed by crop diff; notes-editor undo passed; Pacing regenerate dialog appeared via UIA Invoke; B-474 now `cannot-reproduce`; formal Phase-12 guide remains open.
```

Current OTK-009 status:

```text
fixed: contradiction check found B-316..B-320 current fixed; B-310/B-313 live-verified on test55655 and marked fixed.
```

## Consolidated Open Work

All older active/inactive plan work is consolidated in:

```text
docs/superpowers/plans/2026-06-09-offene-tasks-konsolidierung-masterplan.md
```

Use OTK task order only. Do not resume old registry plans directly.

## Required Handoff State

Handoff must be one of:

- clean commit;
- named stash with exact reason and path list;
- explicit user-approved dirty state documented in Vault and chat.

Unknown dirty changes block work.
