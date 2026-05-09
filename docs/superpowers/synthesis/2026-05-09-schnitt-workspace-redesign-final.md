---
type: synthesis
date: 2026-05-09
status: code-fix-pending-live-verification
scope: schnitt-workspace-redesign-complete
branch: feat/schnitt-redesign-2026-05-09
commit_range_phases: 3476b33..bf998fc
plan: 2026-05-09-schnitt-workspace-redesign
spec: docs/superpowers/specs/2026-05-09-schnitt-workspace-redesign.md
vault_mirror: C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-redesign-final-2026-05-09.md
---

# SCHNITT Workspace Redesign — Repo-Synthese (Final)

> Repo-Mirror der Vault-Synthese `wiki/synthesis/schnitt-redesign-final-2026-05-09.md`. Beide Quellen müssen pro Sub-Schritt aktuell gehalten werden (CLAUDE.md / AGENTS.md Vault-Update-Pflicht).

## Status

**Plan-Code-Implementation 100 % komplett auf Branch `feat/schnitt-redesign-2026-05-09`.** User-Live-Verify (16 Klick-Schritte aus `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/12_LIVE_VERIFY_USER_GUIDE.md`) steht aus. `status: fixed` setzt nur User nach Verify.

## Phasen-Übersicht (Plan)

| Phase | Status | Letzter Commit |
|---|---|---|
| 01 DB-Migrationen | ✅ code-fix | `18f6ab5` |
| 02 Data-Services | ✅ code-fix | `e6f8071` |
| 03 Building Blocks | ✅ code-fix | `6c9b6c8` |
| 04 SchnittWorkspace Skeleton | ✅ code-fix | `c208f52` |
| 05 Sub-Tab Schnitt | ✅ code-fix | `e3fafaf` |
| 06 Sub-Tab Pacing & Anker | ✅ code-fix | `c8ee9b8` |
| 07 Sub-Tab Audio | ✅ code-fix (Skeleton) | `bd865f9` |
| 08 Sub-Tab RL & Notes | ✅ code-fix | `136138f` |
| 09 Worker Stage-Progress + Controller | ✅ code-fix | `b0a26b1` |
| 10 Nav + Integration | ✅ code-fix | `102f259` |
| 11 Tests-Update | ✅ code-fix | `2d96522` |
| 12 Cleanup + Verify-Doku | ✅ code-fix (12.1 + 12.3); 12.2 als Tier-3-Sunset abgeschlossen | `75f1a5c` |

## Tier-Hardening (post-Plan, autonom)

| Tier | Status | Inhalt | Commits |
|---|---|---|---|
| 1 Wiring | ✅ | SchnittController Binder + Re-Generate-Slot + Inspector-Selection-Source + ToggleClipLockCommand View-Sync + STATE_LOADING-Konflikt-Schutz | `a5f5194` `5c1798d` `36be3d2` `9f72e1f` `e5bd4d2` |
| 2 Audio Voll-Ausbau | ✅ | WaveformGraphicsItem-Einbindung + Strukturmarker-API + LUFS rechts oben + PPS-Constant + Tonart-Format Em-Dash | `5ee8eb8` `edd9d14` `a37a759` `ce58520` `aacd6ab` |
| 3 EditWorkspace Sunset | ✅ | Hidden `_edit_ws` parallel-Host komplett entfernt, `EditWorkspace`-Klasse gelöscht (~483 LOC), 12 Promotionen migriert | `4af557b` `d69817e` `c0a6df0` `a761bc5` `ba71341` `4a2d831` `db275a0` |
| 4 Hardening | ✅ | ProjectNotesService SQLite-Upsert + meta-return; PacingProfileBinder D3-D10; WheelGuard GC-safe; StrongFocus; NaN-Clamp; mergeWith; Inspector min-width; Multi-Lock-Sortierung | `548d713` `4055398` `8459074` `d949cf8` `c5b9ec6` `86cbd6e` `042ddb2` `166ea74` `9b3fff9` |
| 5 Coverage-Sweep | ✅ | +47 Tests über alle Komponenten | `2f3038e` `5375f2e` `4ec0f81` `65dfea2` `687dfe4` `d2777ea` `5066852` `f0d9dd9` `b889436` `b2516c8` `bf998fc` |

## Test-Status

- **Final regression:** 1427 passed, 1 failed (`test_b222_model_warmup.py::test_b222a_pipeline_worker_has_preflight` — pre-existing, NICHT durch SCHNITT verursacht), 2 skipped.
- 29 neue Test-Dateien aus Plan-Phasen + 47 Tests aus Tier 5 Coverage-Sweep.

## Architektur-Endstand

### Top-Navigation (4 Tabs)
`PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT` (`ui/widgets/nav_bar.py`).

### SCHNITT-Workspace
`ui/workspaces/schnitt_workspace.py` mit `QStackedWidget`:
- **STATE_EMPTY** — `SchnittEmptyView` (4 Preset-Buttons + „Eigene Einstellungen…")
- **STATE_LOADING** — `SchnittLoadingView` (rotierender Status, Progress-Bar, Cancel)
- **STATE_EDITOR** — `SchnittEditorView` (4 Sub-Tabs + persistenter `ClipInspectorPanel` rechts, HBox stretch 3:1)

### Sub-Tabs (Editor State)

| Tab | File | Inhalt |
|---|---|---|
| Schnitt | `ui/workspaces/schnitt/tab_schnitt.py` | Preview 640×360 + Transport (Play/Stop/Time) + `InteractiveTimeline` mit Lock-Icons + DB-Persistenz |
| Pacing & Anker | `ui/workspaces/schnitt/tab_pacing_anker.py` | `PacingCurveWidget` ≥ 280 px + Cut-Rate (5) / Style (9) / Breakdown (3) / Reaktivität / Vibe + Re-Gen-Btn (gold) + Anker-TreeWidget mit Toolbar |
| Audio | `ui/workspaces/schnitt/tab_audio.py` | `WaveformGraphicsItem` mit Beatgrid-LOD + Strukturmarker-API (Intro/Drop/Outro/Buildup/Breakdown) + `StemWorkspace` + LUFS + Tonart in Header rechts oben |
| RL & Notes | `ui/workspaces/schnitt/tab_rl_notes.py` | RL-Buttons + Event-Liste + Markdown-Notes-Editor + Auto-Save 1 s Debounce + ProjectNotesService-Upsert |

### Daten-Services (Phase 02)
- `services/pacing_profile.py` — `PacingProfile` + 4 Presets + `to_advanced_settings()`.
- `services/timeline_state.py` — `TimelineState` mit `load`/`save_snapshot`.
- `services/timeline_snapshot_service.py` — `create_snapshot`/`list_snapshots`/`restore_snapshot`.
- `services/project_notes_service.py` — `get_notes`/`update_notes(...)→ datetime` (SQLite-Upsert).
- `services/ui_binder.py` — `PacingProfileBinder` mit `dispose()`, `QSignalBlocker`, case-insensitive `findText`, `@Slot`-Decorators, Range-Assertion.

### Worker (Phase 09)
- `workers/edit.py::AutoEditWorker.progress` — Overloaded `Signal((str,float),(int,str))`.
- `EditWorkspaceController._generate_timeline_impl::_CutsWorker.progress` — `Signal(str, float)`.
- `services/auto_edit_worker.py` — Re-Export-Shim.
- `ui/controllers/schnitt_controller.py::SchnittController` — Bindeglied Worker→LoadingView, Cancel, Re-Gen, Empty-State-Preset-Klick, Selection-Source-Wiring.

### Lock-aware Auto-Edit (Phase 06 + Tier 4)
`services/timeline_service.py::_do_apply_segments`:
- Sortiert `locked_ranges` deterministisch.
- DELETE nur `locked=False`.
- Klemmt überlappende Segmente an Locked-Range-Boundaries.
- Verwirft komplett-innerhalb-Locked-Segmente.
- Backward-Compat `media_id`/`video_id` (Worker-Migration Folge-Plan).

### DB-Schema
- `TimelineEntry.locked` BOOLEAN DEFAULT 0 (idempotent).
- Neue `TimelineSnapshot(id, project_id, version, label, payload_json, created_at)`.
- Neue `ProjectNote(id, project_id UNIQUE, content_md, updated_at)`.

### QSettings-Migration v2
`ui/controllers/workspace_setup.py::_migrate_workflow_stage_index` idempotent via `window/workflowStageMigratedV2`. Mapping `{0:0, 1:1, 2:2, 3:2, 4:3}` (alte 5-Tab-Indizes → 4-Tab-Layout).

### Cockpit
`services/cockpit_orchestrator.py::ACTIONS["open_schnitt"]` neu. Legacy `open_auto_edit`/`open_review` aliasen auf `key="open_schnitt"`. `open_export.target_workspace` 4→3.

## Risiko-Register Final

| # | Status |
|---|---|
| 1 TimelineEntry.locked Column | ✅ resolved |
| 2 LockIconItem Visual + Toggle | ✅ resolved |
| 3 Auto-Edit lock-aware | ✅ resolved (Phase 06 + Multi-Lock-Sortierung Tier 4) |
| 4 Test 4-Tab-Namen | ✅ resolved |
| 5 test_workspaces_smoke State-Tests | ✅ resolved |
| 6 e2e-Index-Bug | ✅ resolved |
| 7 Cockpit open_schnitt zusammenführen | ✅ resolved |
| 8 workspace_setup 4 Tabs | ✅ resolved |
| 9 _on_workspace_changed 4 Branches | ✅ resolved |
| 10 QSettings-Migration | ✅ resolved |
| 11 NavBar 4 Tabs | ✅ resolved |
| 12 PacingProfile-Dataclass + Binder | ✅ resolved (Tier 1) |
| 13 TimelineState + Snapshot | ✅ resolved |
| 14 Undo Hybrid | ✅ resolved |
| 15 Worker Stage-Progress | ✅ resolved |
| 16 Empty-State-Detection | ✅ resolved |
| 17 Inspector persistent | ✅ resolved |
| 18 Notes-Service | ✅ resolved |
| 19 Wheel-Filter Maus-Schutz | ✅ resolved |
| 20 btn_toggle_inspector raus | ✅ resolved |
| 21 Brain-V3-Confidence bei locked Clips | offen — Brain-V3 Phase 4+ (R-B Pen-Konflikt mit Lock-Goldrand) |
| 22 style_preset_combo | ✅ gestrichen (Spec) |

## Plan-Abweichungs-Register (alle dokumentiert + sound)

1. **DBSession→Session** durchgängig (Phase 01-12). DBSession existiert nicht im Repo.
2. **`init_db()`+DBSession → `test_engine`-Fixture + `monkeypatch.setattr(<module>, "engine", test_engine)`** für DB-isolierte Tests.
3. **`Project(... path="/tmp/...")`** wegen `path` NOT-NULL.
4. **`alignment=0x84` → `Qt.AlignmentFlag.AlignCenter`** (bit-identisch).
5. **`StemWorkspaceWidget`→`StemWorkspace`** (real-Klassenname).
6. **Test 5.2 `anchors=[]`** Plan-Lücke gegen Prod-DB-Read.
7. **Test 5.3 Direktpfad statt `tl.load_from_db()`** wegen Cross-Thread :memory:-Isolation.
8. **`nullpool_session()` statt `DBSession(engine)` in Service** (B-079 Single-Source).
9. **`media_id`/`video_id` Backward-Compat** (Plan vs Worker-Realität).
10. **Expliziter `session.commit()`** (M5-FIX-konform mit Auto-Commit-Skip in `_NullPoolSessionContext`).
11. **AutoEditWorker `services/auto_edit_worker.py` → `workers/edit.py`** + Shim re-exportiert.
12. **Overloaded Signal `Signal((str,float),(int,str))`** für Plan + B-076-Legacy.
13. **`_CutsWorker` lokal in `_generate_timeline_impl`** → Test via `inspect.getsource`+`exec`.
14. **`_edit_ws` parallel hidden Host** (Phase 12 vertagt) — Tier 3 vollständig migriert + entfernt.
15. **`PBWindow(app_version=...) → PBWindow()`** (echte Signatur).
16. **Phase-12.2 verschoben → Tier-3-Sunset autonom abgeschlossen**.
17. **Test 8.1 Debounce 80→120 ms** gegen Win-Scheduler-Jitter.
18. **Emoji-Glyphs `\U0001F44D/E`** wegen Win-cp1252.

## Folge-Punkte

### Brain-V3 Phase 4+
- **Risiko #21 / R-B:** Decision-File `D-XXX-lock-vs-confidence-pen` einplanen — Lock-Goldrand vs Brain-V3-Confidence-Pen. Visualisierungsentscheidung.

### Test-Infrastruktur (Tier 6, läuft async)
- StaticPool-Umstellung von `test_engine` für Cross-Thread-Worker-Tests.
- Session-scoped `qapp`-Fixture in `tests/conftest.py`.
- `patched_schnitt_engine`-Fixture-Helper.

### User-Aktion (BLOCKER für `status: fixed`)
1. App: `"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" main.py`
2. 16 Klick-Schritte aus `12_LIVE_VERIFY_USER_GUIDE.md`
3. Pro Schritt Screenshot in `C:\Brain-Bug\projects\pb-studio\screenshots\schnitt-verify-2026-05-09\`
4. Bei Fehlschlag: Bug-File `wiki/bugs/B-XXX-schnitt-verify-step-NN.md`
5. Bei Erfolg: Vault-Plan `status: fixed` setzen
6. Spec-Status `draft-approved-for-planning` → `done`
7. Repo-Synthese (diese Datei) Status → `fixed-live-verified`

## Vault-Spiegelung
- Living-Plan: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md`
- Phase-Synthesen: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-redesign-phase-{01..06}-done-2026-05-09.md`
- Final-Synthese (Vault): `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-redesign-final-2026-05-09.md`

## Branch-Status
- `feat/schnitt-redesign-2026-05-09` lokal, **kein Push**, **kein Merge auf main**.
- Live-Verify entscheidet Merge.
