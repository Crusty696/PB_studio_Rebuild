# PB Studio Agent Handoff

This file is a repository-local continuity checkpoint for all agents.

## Codex Quellstand-Konsolidierung 2026-06-22 (newest)

- **Branch:** `codex/OTK-021-source-consolidation-2026-06-22`
- **Worktree:** `C:\Users\David_Lochmann\.config\superpowers\worktrees\PB_studio_Rebuild\OTK-021-source-consolidation-2026-06-22`
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
- **Nächster Schritt:** User-Entscheid: Collection-Blocker separat beheben/
  aus pytest ausschließen; erst danach PR/Main-Integration.

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
