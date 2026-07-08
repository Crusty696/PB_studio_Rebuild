# AUFRÄUM- & REFACTOR-PLAN (DRAFT) — 2026-07-08

- **plan_id:** `PB-STUDIO-AUFRAEUM-REFACTOR-2026-07-08`
- **status:** `draft` — reine Analyse, **kein Code angefasst**. Ausführung
  erst nach den Gates unten, jeweils mit pro-Kategorie-User-Freigabe.
- **Quelle:** 5 parallele Read-only-Analyse-Agenten (2026-07-08), während
  User-Live-Test. Kein Produktcode berührt.

---

## ⛔ Governance-Gates (Pflicht — bevor irgendwas ausgeführt wird)

1. **Reihenfolge (nicht verhandelbar):**
   (a) User-Live-Test + `fixed` des Audit-Fixplans →
   (b) Vollintegrations-Plan fertig + Merge in `codex` →
   (c) **erst dann** Aufräumen/Refactor auf **einem** konsolidierten Stand.
   Grund: paralleler Vollintegrations-Agent + laufender Test = jede
   gleichzeitige Änderung erzeugt Konflikte/verfälscht Verifikation.
2. **Keine Löschung / kein Refactor ohne pro-Kategorie-User-OK** (Hartregel).
3. **NEUBAU-Dateien** (timeline.py, main.py, media_workspace.py,
   pacing_service.py, pacing_edit_helpers.py, pacing_beat_grid.py,
   edit_workspace.py, timeline_service.py, video_pipeline/, pacing/,
   models.py, migrations.py) **erst nach Merge** anfassen.
4. **DEAD-009 `storage_provenance/`** = aktive OTK-021-WIP (3 Wochen alt) →
   **nicht anfassen ohne explizite Rückfrage.**

---

## TEIL A — AUFRÄUMEN

### A1 — Disk-/Artefakt-Cleanup (~15 GB, alles gitignored, risikofrei)
Alles untracked/gitignored, regenerierbar. Kein Git-Impact.
- **Sicher löschbar:** `dist/` (~11 GB Build*), `outputs/6262626` (835 MB),
  `outputs/final-check` (621 MB), lose `outputs/*.log`, `test-report/` (12 MB),
  `logs/` alte clicklog/monitor-Rotationen, `__pycache__`/`.pytest_cache`/
  `.ruff_cache`, leere Dirs (`test_reports/`, `Test-ergebniss/`,
  `storage/stems`, 0-Byte `storage/pb_studio.db`).
- **NICHT löschen:** `outputs/a0-smoke/` (Test-Beweise track1/2b/4),
  `outputs/21` + `outputs/55test` (**dein laufender Live-Test**),
  `pb_studio.db` (aktiv), `storage/backups/` (Backup-Zweck).
- *dist/: nur wenn v0.5.0 nicht die aktuell ausgelieferte Release ist →
  User-Entscheidung; ggf. Setup-.exe behalten.*
- **Risiko: null. Aufwand: S. Kann direkt nach Test-Ende laufen** (kein Merge
  nötig, da kein getrackter Code).

### A2 — Toter Code löschen (nur die WIRKLICH toten, ~700 Zeilen)
Von Agent 2 doppelt geprüft (Haupt-Branch + Vollintegrations-Branch).
- **SICHER LÖSCHBAR** (tot in beiden Branches, 0 Produkt-Refs):
  - `services/audio_pipeline/auto_save_scheduler.py` (80, **0 Refs repo-weit**)
  - `services/audio_pipeline/cleanup.py` + `migration.py` + `vram_guard.py` (231, nur-tests)
  - `services/auto_edit_worker.py` (13, Re-Export-Shim)
  - `services/brain/audio/subtrack_detector.py`, `brain/storage/embedding_repository.py`,
    `brain/onnx_export.py`, `brain/video/visual_curves.py`, `brain/schemas/audio.py`+`video.py`
    (~1.130 zusammen) — **ACHTUNG: NICHT `brain_v3_schemas.py`** (live!)
  - `_ProgressRelay` (model_manager_dialog), `PrimaryActionBar` (workflow_components),
    `LegacyAnalysisWorkspace` (workflow_pages) (~150)
- **NICHT löschen (jetzt Vollintegrations-Ziel, auf Branch B verdrahtet):**
  DEAD-001 Slice-1-Pacing-Cluster, DEAD-002 SetupWizard, DEAD-008
  video_pipeline-Module, DEAD-013 Timeline-Snapshots + USE-001/002/004/007/008/009/012.
- **USER-ENTSCHEIDUNG:** DEAD-009 storage_provenance-4er (OTK-021-WIP, Rückfrage!),
  DEAD-010 `release_readiness.py` (nicht tot — falsch platziert unter services/,
  eher nach tools/ verschieben), `PrepareWorkspace` (exportiert in `__init__`).
- **Risiko: niedrig. Aufwand: S-M. Pro-Modul-OK + Tests grün. Nach Merge.**

### A3 — Doku aufräumen
- `.agents/skills/pb-rebuild-*/references/module-map.md` (4 identische Kopien):
  beschreiben gelöschte **Mixin**-Architektur → auf Controller-Realität fixen
  oder auf 1 Quelle deduplizieren. (DOKU-FIX, M)
- 10 unregistrierte Alt-Pläne in `docs/superpowers/plans/` → nach `archive/`
  (2026-04-23-studio-brain-*, 2026-04-29-full-app-green, u.a.). (ARCHIVIEREN, M)
- `PLAN_REGISTRY.md` 2 kaputte Pfade: Z.30 (fehlt `\Vaults\`), Z.39 (externe
  Maschinen-Referenz). (DOKU-FIX, S)
- Dateierte Root-Reports (`AUDIT_REPORT_2026-05-01.md`, `STATUS_REPORT_*`,
  `CUDA_*`/`GPU_*`-Diagnosen) → `docs/archive/`. (ARCHIVIEREN, S-M)
- `docs/superpowers/synthesis/` (98 flache Dateien) → Archiv-Split. (M-L)
- Doppelte `PB_Studio_App_Beschreibung.md` vs `_Detailed.md` (identisches TOC),
  `docs/*graph_system*.md` freischwebend, README-Preset-Namen-Drift vs
  GUI_TEST_MATRIX. (USER-ENTSCHEIDUNG)
- Audit-Synthese Z.111 selbst leicht ungenau ("CLAUDE.md '8 Mixin'" — steht
  dort NICHT; CLAUDE.md/AGENTS.md sind mixin-sauber). (DOKU-FIX, S)

### A4 — IDE-Config-Karteileichen (USER-ENTSCHEIDUNG)
`.clinerules/`, `.cursor/`, `.opencode/`, `.windsurf/` — je 1 Regel-Datei,
seit 2026-05-26 eingefroren, ungenutzte IDE-Tools. `.agents/` bleibt (aktiv).

---

## TEIL B — REFACTORING

### B1 — Sofort machbar (nach Merge; nicht NEUBAU-blockiert, gutes Nutzen/Risiko)
- `services/actions/edit_actions.py` (1488 LOC, 39 Fn) → Split nach Domäne
  (project/timeline/media/anchors/export) + `_common.py`. Risiko niedrig-mittel, M.
- `services/ingest_service.py` (1107, 21 Fn) → Split audio/video/queries/soft_delete,
  Project-Resolve (3× dupliziert) konsolidieren. Risiko niedrig-mittel, M.
- `services/structure_detection_service.py` (1337, 26 Meth) → FeatureExtractor /
  SectionLabeler / Genre-Templates trennen. Risiko mittel, L.
- `services/brain/legacy_sqlite.py` (1952) → **ZUERST Usage-Check**: noch aktiv
  oder totes Legacy? Falls tot → löschen (max. Nutzen). Risiko niedrig/S.

### B2 — Größerer Nutzen, höheres Risiko (nach Merge; nicht NEUBAU)
- `services/export_service.py` (1780, 3 Fn >250 Z.) → probe/preprocess/audio_norm/
  ffmpeg_runner/backends/api. GPU/NVENC-Verhalten exakt erhalten. Risiko mittel-hoch, L.
- `services/video_analysis_service.py` (1718) → scenes/motion_raft/embeddings/
  captioning/persistence/search/pipeline. Risiko hoch, L.
- `services/ai_audio_service.py` (1439, `StemSeparator.separate` **401 Z.**) →
  ein Modul pro Klasse. GPU/VRAM exakt erhalten. Risiko mittel-hoch, M-L.
- `agents/orchestrator_agent.py` (1172) → Chat-Loop/Tool-Dispatch extrahieren. M.

### B3 — Duplikation konsolidieren (nach Merge)
- **4× File-Hash** (stem_cache/stream_hasher/source_identity/brain.hashing) →
  ein `services/util/file_hash.py`. **Vorsicht:** unterschiedliche Chunks →
  Cache-Invalidierung. Risiko mittel, M.
- **NVENC-Args** über 3 Services (convert/export/video_service) → `nvenc_video_args()`
  + `libx264_fallback_args()` zentral. Risiko niedrig, S.
- **Path-Resolver** (`_proxy_dir`/`_app_root`/`_storage_root` mehrfach) → zentrale
  `paths.py` (existiert als `services/brain/paths.py`). Risiko niedrig, S.
- **DB-Session-Boilerplate** (25+ inline `with Session(engine)`) → `session_scope()`.
  Risiko niedrig, M (viele Callsites).
- **STOP+ASK — mood/energy-Score:** 3-4 konkurrierende Formeln
  (scorer.py kategorisch vs mood_match_score/energy_match_reward embedding vs
  pacing_edit_helpers inline). `scorer.mood_match/energy_match` werden von Callern
  gar nicht genutzt. **Welche ist Truth?** Zusammenführen ändert Schnitt-Ergebnisse
  → User-Entscheidung, nicht eigenmächtig. Überlappt NEUBAU (pacing/).
- **STOP+ASK — 2 Migrationssysteme:** Alembic + `migrations.py::_run_legacy_migrations`
  (~60 ALTERs, FROZEN). Ein System = Alembic; Legacy langfristig entfernen sobald
  alle DBs über Baseline. Risiko hoch (Live-DB). User-Entscheidung.
- **STOP+ASK — requirements:** `requirements.txt` vs `requirements-py310-cu113.txt`
  (kanonisch laut CLAUDE.md) → Alt-Datei deprecaten. Setup-Docs hängen dran.

### B4 — NEUBAU-blockiert (ERST NACH VOLLINTEGRATIONS-MERGE)
Größte absolute Schmerzpunkte, aber Branch B ändert sie gerade:
- `ui/timeline.py` (3005 LOC, `InteractiveTimeline` **128 Methoden**) → Items
  auslagern, Interaktions-Controller extrahieren, Waveform-Load als Service.
- `services/pacing_service.py` (`_sections_from_structure_db` **777-Zeilen-Funktion**)
  → in benannte Teilschritte zerlegen.
- `main.py` (1983, God-`QMainWindow`) → app_bootstrap/cuda_env/Update-Controller.
- `ui/workspaces/media_workspace.py` (1697, Page-Builder 535 Z.) → Widget-Klassen.
- **DEAD-015 Video-Engine-Doppelung** (Monolith `run_full_pipeline` vs DAG-Engine)
  → nach Merge auf DAG konsolidieren, Monolith entfernen.
- **Proxy-Generator-Dedup** (video_service vs video_pipeline/proxy_generator).

---

## Offene User-Entscheidungen (gesammelt)
1. `dist/` löschen? (v0.5.0 = aktuelle Release?)
2. IDE-Config-Karteileichen (.clinerules/.cursor/.opencode/.windsurf) löschen?
3. DEAD-009 storage_provenance-4er: WIP oder tot? (nicht anfassen ohne Antwort)
4. mood/energy-Score: welche Formel ist Truth?
5. 2 Migrationssysteme auf Alembic konsolidieren?
6. `requirements.txt` deprecaten zugunsten `requirements-py310-cu113.txt`?
7. Doppelte App-Beschreibung / Graph-System-Docs: konsolidieren/archivieren?
8. `legacy_sqlite.py`: Usage-Check-Ergebnis abwarten (tot → löschen).

## Empfohlene Ausführungs-Reihenfolge (nach Gates)
1. **A1** Disk-Cleanup (risikofrei, direkt nach Test-Ende möglich).
2. Nach Merge: **A2** toter Code → **A3** Doku → **B1** sichere Refactors →
   **B3** kleine Dedups (Hash/NVENC/Path).
3. Dann **B2** große God-Objects, **B4** NEUBAU-Dateien, Migrations-Konsolidierung
   — jeweils einzeln, mit User-OK + Tests grün + Live-Verify pro Schritt.
