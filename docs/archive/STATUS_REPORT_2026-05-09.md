# PB Studio Rebuild — Status-Report 2026-05-09

> Quelle: Plan-Set `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/` + Plan
> `docs/superpowers/plans/2026-05-07-bug-und-task-liste-abwicklung.md` + Vault-Bugs/Logs.
> Branch `main` @ `3a9a716` (Merge codex/full-app-green-fix). Working tree dirty:
> 4 mod files (`docs/plan_graph_system_implementation.md`,
> `docs/superpowers/prd/2026-04-23-studio-brain-prd.md`, `ui/dialogs/project_dialog.py`,
> `ui/timeline.py`), 4 untracked (`docs/superpowers/plans/2026-05-07-bug-und-task-liste-abwicklung.md`,
> `scripts/phase1_cache_test.py`, `scripts/phase1_import_test.py`, `test_import_phase1/`).

Vault-Mirror: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\status-report-2026-05-09.md`

---

## 1. Brain V3 Rebuild (Hauptachse)

**Status-Sprache (Plan Hard Rule):** Eine Phase ist DONE nur wenn Code-Status + App-Sync-Status + Real-User-Workflow live verifiziert. Phase-Marker `fixed` setzt ausschliesslich der User.

| Phase | Inhalt | Code | App-Sync | Live-Verify | Status |
|---|---|---|---|---|---|
| 0 | GPU-Coexistenz-Spike, AutoImageProcessor-Lesson | + | + | + | **DONE** (2026-05-03) |
| 1 | media_hash sha256, SubtrackDetector, VisualCurves | + 35 pytest | + Hash-Hook + BrainV3HashingWorker | - 3 Audio + 3 Video Smoke fehlt | code-complete |
| 2 | CLAP + SigLIP-2 + sqlite-vec, Background-Queue | + 70 pytest + 2 Spikes | + EmbeddingScheduler + GpuSerializer | - 5-Mix-/10-Clip-Cache-Hit-Smoke fehlt | code-complete |
| 3 | Beta-Bernoulli, Hierarchical Backoff, BrainStore | + 112 pytest | + Health-Check + Boot-Hook (PBWindow) | - Mock-Klick + Reset-Spike fehlen | code-complete |
| 4 | PacingPipeline-Hook + Reranker + SmartSampler | + 40 pytest, 172 brain_v3 + 293 pacing | + use_brain_v3 in PacingPipeline.select_best | - Live-Pacing-Run mit `use_brain_v3=true` fehlt | code-complete |
| 5 | StatsPanel + FeedbackPopup + LearningDialog + Hotkeys 1-4 | + 7 Widget-Tests | + Tab in PBWindow Right-Panel | - Real-Klick-Workflow + Audio/Video-Preview offen | code-complete |
| 6 | Backup VACUUM INTO, LICENSES.md, Recovery, NVENC-Konflikt | partial: 5 Backup-Tests | - | - Recovery, NVENC-Spike, Perf-Profil, User-Doku, ONNX-Eval, KNN-ANN-Eval offen | partial |

**Brain-V3 Test-Suite gesamt:** 184/184 pytest gruen (Stand 2026-05-05).

**Lizenzen (LICENSES.md, 2026-05-05):** CLAP Apache-2.0, SigLIP-2 Apache-2.0, Demucs MIT, beat_this MIT, sqlite-vec Apache/MIT Dual, librosa ISC, transformers Apache-2.0, PyTorch BSD-3, PySide6 LGPL-v3. Keine Splash-Screen-Pflicht.

---

## 2. App-Funktionen v0.5.0 (Basis vor Brain V3)

| Bereich | Funktionen | Status | Aktive Bugs |
|---|---|---|---|
| Ingest + DB | Audio/Video-Import, Folder-Walk, SQLAlchemy + Alembic, Soft-Delete | + 21/21 real-data | B-175 Soft-Delete-ReImport; B-280 Folder-Import-Fallback |
| Audio-Analyse (9 Services) | beat_this GPU, BPM, Key, Onset, Spectral, Structure, Mood, Energy, Loudness | + 9/9 real-data | B-229 Spectral-Norm; B-231 doppeltes STFT; B-232 Groove-Template ZeroDiv; B-235/236 Onset-DB |
| AI Audio (3 Services) | Demucs htdemucs_ft GPU, FrequencyAnalyzer, AutoDucker | + 7/7 real-data | – |
| Stem Separation | Demucs htdemucs_ft (LOCKED) | + funktional | – |
| Video-Pipeline | OpenCV + PySceneDetect, RAFT Motion, SigLIP-so400m 1152-dim | + funktional | B-259 RAFT-dtype-state; B-279 SigLIP stem-mp4 invalid |
| Pacing/Director | PhD-Spec, 5-Stage-Pipeline, Tune-Reward | + funktional | B-238 none-handling; B-271 Reranker-chosen-score legacy; B-282 Director-combos placeholder |
| Export/Convert | NVENC + DaVinci-Proxy, OTIO, EDL | + nach B-039 | B-269 NVENC-Fallback libx264; B-270 EDL contrib fehlt; B-281 Proxy-Convert NVENC-Fallback |
| Timeline (OTIO) | InteractiveTimeline, Cuts, Drag/Drop | + funktional | B-275 Startup-MetaCall slow |
| Studio-Brain UI | StudioBrainWindow, GraphCockpit, SteerTab, MemoryUpdater | + Code-Fix | B-196/197/198/199 GUI-Verify pending; B-266 GraphCockpit gefixt |
| Agenten-System | Orchestrator + Pacing/Vision/Audio/Editor + ActionRegistry | + funktional | B-243 read-tool-facts gefixt; B-244 describe-audio-track Tool fehlt; B-245/246 gefixt |
| LLM-Integration | Ollama gemma4:e4b + phi3:mini, Tool-Use | + Thinking-Fix B-038, Cold-Load B-242 | B-247 supports-tools optimistisch; B-256 Ollama-Headless; B-278 Startup-Timeout |
| Workflow-UI Redesign | rebuild PB Studio workflow UI (Commit d2c9133) | + auf master gemerged | – |

---

## 3. Bug-Lage

### Open ohne Fix
- **B-175** Re-Import nach Soft-Delete → IntegrityError (Design-Gate)
- **B-219** WinError 32 Proxy-File-Lock Pipeline ↔ BatchAnalysis
- **B-229** Temporal-Bands per-window-norm defeats timbral evolution (Design-Gate)
- **B-231** `analyze_extended` doppeltes y/STFT (Design-Gate)
- **B-265** GTX 1060 nicht als CUDA-Device verfuegbar (Hardware-State — Blocker fuer alle GPU-Live-Tasks)
- **B-270** EDL-Export `opentimelineio-contrib` fehlt (Dependency-Gate)
- **B-277** GUI-Harness Shutdown Force-Fallback

### Code-Fix vorhanden, Live-Verify pending
- **B-196/197/198/199** Studio-Brain GUI (Open-haengt, Brain-Wiring, SteerTab.runRequested, Graph-Cockpit-Populator)
- **B-272** Timeline-Brain-V3-Feedback nicht verdrahtet
- **B-273** Lern-Dialog Audio/Video-Preview fehlt
- **B-274** Timeline Confidence-Bar fehlt
- **B-275** Startup InteractiveTimeline slow MetaCall
- **B-276** NVENC-Render nicht serialisiert mit Brain-Inferenz

### Recent gefixt (Branch codex/full-app-green-fix-2026-04-29)
B-240 (Ollama API-Readiness), B-241 (gemma4-e4b Hardcodes), B-242 (Ollama Cold-Load Timeout), B-243 (Read-Tool-Facts), B-245/246 (Vision Async + Integrated Timeline), B-249 (Vision Caption Fallback), B-266 (Graph-Cockpit Render), B-268 (Embedding-Cache-Hit known-hash).

---

## 4. Tech-Stack (LOCKED)

| Layer | Komponente | Version |
|---|---|---|
| GUI | PySide6 (Qt 6.6-6.7) | >=6.6.0,<6.8.0 |
| ORM | SQLAlchemy 2 + Alembic | >=2.0.20 / >=1.13.0 |
| ML Core | PyTorch CUDA 11.3 | 1.12.1+cu113 |
| Stem Separation | Demucs htdemucs_ft | 4.0.1 |
| Beat Detection | beat_this (CPJKU GPU) | vendored |
| Audio Analysis | librosa | 0.10.2 |
| Video | OpenCV + PySceneDetect | >=4.8.0 / >=0.6.0 |
| Timeline | OpenTimelineIO | >=0.17.0 |
| Embeddings | transformers SigLIP-so400m | 4.38.2 |
| LLM | Gemma 4 E4B via Ollama | gemma4:e4b |
| Python | 3.10.11 | conda pb-studio / .venv310 |

**Hardware:** NVIDIA GeForce GTX 1060 6 GB. Treiber-Update 546.33 / CUDA 12.3 (2026-04-28). Aktuell torch 1.12.1+cu113 stabil; torch 2.x machbar.

---

## 5. Naechste Schritte (Plan 2026-05-07)

Reihenfolge strikt sequentiell:

1. Task 0 — Gate-Check + Working-Tree
2. Task 1 — **B-265 CUDA-Preflight** (Blocker fuer alle GPU-Live)
3. Task 2 — Phase 1 Live-Smoke (3 Audio + 3 Video, V3-DB-Inspect, Re-Import)
4. Task 3 — Phase 2 Embedding-Smoke (5 Mix + 10 Clips, Cache-Hit)
5. Task 4 — Phase 3/4 Brain-Service Live-Path
6. Task 5 — Phase 5 UI-Live (B-272/273/274/275)
7. Task 6 — Phase 6 (B-276 Render+Brain Serialization, B-277 Harness)
8. Task 7 — Studio-Brain GUI-Verify B-196 bis B-199
9. Task 8 — B-175 / B-219 / B-270 (Decisions noetig)
10. Task 9 — B-229 / B-231 (Decisions noetig)
11. Task 10 — Phase-Marker durch User

---

## 6. Offene User-Entscheidungen

- **B-175**: undelete-on-import quick-fix vs. partial-unique-index Migration?
- **B-229**: track-global vs. raw vs. beide Werte exposen?
- **B-231**: refactor-Approval `_analyze_with_audio_buffer()`?
- **B-270**: `opentimelineio-contrib` als Dependency aufnehmen?
- **Phase-Marker 1/2/3/4/5/6**: nach Live-Verify durch User setzen.

---

## 7. Commander-Empfehlung

Erste Aktion: **B-265 CUDA-Preflight**. Wenn GPU nicht verfuegbar → alle GPU-pending-Tasks blockiert (Phase 1/2/4/6 Live-Smoke unmoeglich). Danach Phase 1 Live-Smoke als billigste Verifikation. Working-Tree vor Live-Test entweder commit oder stash. Untracked `test_import_phase1/` + `scripts/phase1_*.py` deuten auf bereits begonnenen Phase-1-Lauf hin — Inhalt sichten bevor neu gestartet wird.

---

## Quellen

- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md`
- `docs/superpowers/plans/2026-05-07-bug-und-task-liste-abwicklung.md`
- `C:\Brain-Bug\projects\pb-studio\PROJECT.md`
- `C:\Brain-Bug\projects\pb-studio\log.md` (Eintrag 2026-05-05)
- `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-1**` … `B-283`
- `git log` Branch `main`

---

## 8. Update 2026-05-09 (Nachmittag) — SCHNITT Workspace Redesign

> Branch `feat/schnitt-redesign-2026-05-09` (NICHT in `main` gemerged). Status `code-fix-pending-live-verification`. User-Live-Verify offen.

### Plan-Implementation komplett (Phasen 01-12)
- DB-Migrationen (`TimelineEntry.locked`, `TimelineSnapshot`, `ProjectNote`).
- Data-Services (`PacingProfile`, `TimelineState`, `TimelineSnapshotService`, `ProjectNotesService`, `PacingProfileBinder`).
- Building-Blocks (`WheelGuard`, `LockIconItem`, `ToggleClipLockCommand`).
- `SchnittWorkspace` mit 3 States (Empty/Loading/Editor) + 4 Sub-Tabs (Schnitt/Pacing & Anker/Audio/RL & Notes) + persistenter `ClipInspectorPanel`.
- Lock-aware `apply_auto_edit_segments` (Risiko #3 resolved).
- Worker Stage-Progress (`AutoEditWorker`, `_CutsWorker`) + `SchnittController`.
- NavBar 5→4 Tabs (PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT).
- Cockpit `open_schnitt` + Legacy-Aliase.
- QSettings-Migration v2 idempotent.

### Tier-Hardening (post-Plan, autonom)
- **Tier 1** Wiring (5 Commits): SchnittController-Binder + Re-Generate-Slot + Inspector-Selection + ToggleClipLockCommand-View-Sync + STATE_LOADING-Schutz.
- **Tier 2** Phase-07-Audio-Voll-Ausbau (5 Commits): WaveformGraphicsItem + Strukturmarker-API + LUFS Header + PPS-Const + Em-Dash. Spec-Lücken A1-A5 resolved.
- **Tier 3** EditWorkspace Sunset (7 Commits): Hidden `_edit_ws` weg, `EditWorkspace`-Klasse gelöscht (~483 LOC), 12 Promotionen migriert.
- **Tier 4** Hardening (9 Commits): SQLite-Upsert + meta-return; Binder D3-D10; WheelGuard GC-safe; StrongFocus; NaN-Clamp; mergeWith; Inspector min-w; Multi-Lock-Sortierung.
- **Tier 5** Coverage +47 Tests.
- **Tier 6** Test-Infra + Repo: StaticPool + qapp-Fixture + patched_schnitt_engine + README/CHANGELOG/Repo-Synthesis-Mirror + Plan-Abweichungs-Register.

### Test-Status
- **131/131 SCHNITT-spezifische Tests grün** (in 18.46s).
- Pre-existing B-222a unverändert.

### Branch-Stats
- 88+ Commits insgesamt (47 Plan + 41 Tier-Hardening + Doku).
- Letzter Commit: `8782b74` (Doku-Sweep).
- Commit-Range: `3476b33` … `8782b74`.

### Risiko-Endstand
- 21/22 resolved.
- Offen nur **#21 Brain-V3 Pen-Konflikt** mit Lock-Goldrand → Decision-File `D-XXX-lock-vs-confidence-pen` für Brain-V3 Phase 4+.

### BLOCKER `status: fixed`
- Nur **User-Live-Verify** (16 Klick-Schritte aus `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/12_LIVE_VERIFY_USER_GUIDE.md`).
- Branch lokal, **kein Push**, **kein Merge auf main**.

### Vault-Spiegelung
- Living-Plan: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md`
- Phase-Synthesen 01-06: `wiki/synthesis/schnitt-redesign-phase-XX-done-2026-05-09.md`
- Final-Synthese: `wiki/synthesis/schnitt-redesign-final-2026-05-09.md`
- Repo-Mirror: `docs/superpowers/synthesis/2026-05-09-schnitt-workspace-redesign-final.md`
