# PB Studio — Funktions-Statusaufnahme aller Bereiche (2026-07-26)

Status: Aufnahme abgeschlossen, Produktcode unverändert, kein Fix, keine Bug-Files angelegt
Baseline: `main` / `8e3a7eb8ece54157a410e90ca46be82f3ea1cdd1`
Methode: 14 read-only Subagenten (13 Funktionsbereiche + Backlog-Querschnitt)
Abgrenzung zur Vorgängeraufnahme `app-quality-audit-2026-07-26.md`: jene prüfte **Qualität/Releasefähigkeit**,
diese prüft **jede einzelne Funktion auf Zustand, Weiterarbeit, Optimierbarkeit, Probleme**.

## Ehrlichkeitsrahmen

- **Es wurde nichts ausgeführt.** Keine App gestartet, keine Tests, kein Export, keine GPU belegt.
- Belege sind Quellcode, vorhandene Log-Dateien, Live-DB-Inspektion (lesend) und Unit-Test-Existenz.
- `funktioniert-belegt` wurde nur vergeben, wo Log/Live-Daten/Test es stützen. Ein Agent (Projekt/DB) hat es
  bewusst **nirgends** vergeben.
- Aussagen, die zwingend aus dem Code folgen, aber keinen Laufzeitbeweis haben, sind als HYPOTHESE markiert.
- Der komplette Medienworkflow Import → Analyse → SCHNITT → Export wurde **nicht** neu gefahren.
  Letzter sichtbarer App-Lauf: 2026-07-20.

---

## Gesamturteil

Die App ist funktional weit gebaut und in den Datenpfaden (Import, Analyse, Export-Mechanik, Timeline-Virtualisierung,
DB/Migrationen) solide. Der Bruch liegt woanders: **mehrere zentrale Wirkungsketten sind verdrahtet, aber
wirkungslos** — sie laufen, kosten Zeit und GPU, und beeinflussen das Ergebnis nicht. Dazu kommen Stellen, die
Erfolg melden, ohne etwas getan zu haben.

Das ist die wichtigste Erkenntnis dieser Aufnahme: nicht fehlender Code, sondern **nicht wirksamer Code**.

---

## A. Wirkungslose Ketten (schwerste Kategorie)

### A1 — Section-Pacing + LLM-Strategist wirken nicht (Pacing)

Drei unabhängige Belegstellen:

1. `ui/widgets/pacing_curve.py:21` initialisiert `_density = [0.5] * 200`
2. `get_all_densities()` liefert diese Liste damit immer; `ui/controllers/edit_workspace.py:394` reicht sie durch
3. `services/pacing_edit_helpers.py:136-147` prüft `if pacing_curve and len(...) > 0` → setzt `section_type = ""`

Folge: `SECTION_PACING_MAP`, BUILDUP-Progression (`progress^2.5`), DROP-First-8-Beats und die LLM-Override-Map
`_pacing_map_override` werden nie erreicht. Eine Flach-Kurven-Erkennung existiert nirgends.
Zusätzlich: density 0.5 → `curve_step = 2` → `effective = min(base_cut_rate, 2)`; die Cut-Rate-Combo (4/8/16)
wirkt nach oben nicht.
Kosten: ~85 s LLM-Strategist-Call pro Auto-Edit ohne jeden Effekt.

### A2 — Brain-V3-Reranker verwirft die Pacing-Bewertung und diskriminiert selbst kaum

- `services/pacing/pipeline.py:124` übergibt kein `brain_weight` → `services/brain/reranker.py:54` Default `1.0`
  → bei aktivem Studio-Brain bestimmt **allein** der Brain-Score die Stage-4-Reihenfolge; 15 Pacing-Terme
  (Rolle, Stil, Mood, Genre, Key, Tension, Groove, Collision, Freshness …) werden ignoriert.
  Live-Setting `pacing.use_studio_brain = true`.
- `services/brain/reranker.py:152-171` liest `contribs["brightness"/"saturation"/"color_temp"/"duration_s"/"mood_tags"]`
  — `services/pacing/scorer.py:583-598` liefert diese Keys nicht. 16 der 17 Bridge-Achsen sind pro Cut für alle
  Kandidaten konstant; nur `motion_match_weight` variiert.
  HYPOTHESE (stark gestützt): effektive Auswahl ≈ „Motion am nächsten an Audio-Energie".

### A3 — Die Lernschleife kann das Ranking mathematisch nicht beeinflussen

- `services/brain/feedback_logger.py:70-85` schreibt identische α/β in **alle** 17 Achsen × 6 Level.
- Live-Beleg `%APPDATA%\PB_Studio\brain_v3\weights.db`: alle 17 Achsen Level 0 exakt `positive=165 / negative=249`,
  102 konfidente Buckets.
- Gleiche Gewichte → gewichteter Mittelwert = arithmetisches Mittel (`services/brain/scorer.py:52`)
  → Klicks ändern die Reihenfolge nicht.
- `WeightStore.update()` (`services/brain/weight_store.py:135`), die einzige achsenspezifische API: **0 Callsites**.
- Feedback ist zusätzlich kontextblind: `ui/timeline.py:1049` (`context=None`),
  `ui/widgets/brain_v3_learning_dialog.py:421` (`CutContext()`), `services/feedback_service.py:220` (nur Section)
  → Live-DB hat nur 2 distinkte Level-5-Schlüssel, der 6-stufige Backoff läuft leer.

### A4 — Studio-Brain-Scoring läuft auf degenerierten Features

`services/pacing_beat_grid.py:424-451` lädt pro Szene nur `id/start/end/energy`;
`services/pacing_service.py:1494-1502` liest `role`, `ai_mood`, `style_bucket_id`, `motion_score`.
`services/pacing/bridge_mapping.py:384-388` setzt daher konstant `role="unknown"`, `mood_refined="unknown"`,
`style_bucket_id=0` → `role_fit` konstant 0.3, `mood_match` konstant 0.0, Stage 1 fällt praktisch immer in `soften`.
Die Section×Role-Matrix aus `config/pacing_rules.yaml` ist damit wirkungslos.
`motion_score` ist Szenen-*Energie*, nicht RAFT-Motion.

### A5 — Brain-V3-Embedding-Stack ist write-only

`services/brain/storage/embedding_cache.py:150` (`lookup`) und `:44` (`load_embedding`): **0 Callsites**.
Live liegen 554 Embeddings (537 SigLIP-2 Video + 17 CLAP Audio) auf Platte, die niemand liest.
Der Scheduler startet trotzdem bei jedem GUI-Start (`main.py:859-873`) und belegt GPU.
Doku `services/brain/embedding_scheduler.py:6` behauptet Cache-Hit-Skip — trifft nicht zu.
Zusätzlich SigLIP-Doppelwelt: Brain-V3 768d (`video_embedder.py:37`) vs. Pacing 1152d (`vector_db_service.py:23`).

### A6 — Weitere wirkungslose Stellen

| Was | Stelle |
|---|---|
| System-Prompt fällt immer auf COMPACT (Cap 1200 Z.) → LLM sieht nie die Aktionsliste | `services/local_agent_service.py:623,659` |
| Tool-Use-/History-Pfad toter Code (Orchestrator fängt vorher ab) → Chat ohne Multi-Turn-Kontext | `services/local_agent_service.py:899,917-994` |
| `auto_edit` verwirft alle Pacing-Parameter beim Worker-Mapping | `services/actions/edit/timeline_actions.py:79` + `workers/registry.py:45` |
| Loop-Schutz `_TrackedRegistry` umgangen (Agenten importieren `action_registry` global) | `ui/chat_dock.py:41` |
| „Mit CPU starten" setzt `PB_STUDIO_FORCE_CPU` — repo-weit kein Leser | `ui/dialogs/gpu_recovery_dialog.py:269` |
| Export-Presets nur Label; cq18/15M hart kodiert | `ui/workspaces/deliver_workspace.py:113`, `services/export/ffmpeg_runner.py:41` |
| RL-Stack v2 ohne Leser und ohne Persistenz | `services/feedback_service.py:197`, `services/pacing/rl_memory_v2.py:187` |
| Steer-Overrides nur im Studio-Brain-Pfad; Legacy ignoriert still; keine Persistenz | `services/pacing_service.py:1363` |
| Steer-Tab Profil-Combo + Pins werden explizit ignoriert | `main.py:664-671` |
| i18n tot (nur `.ts`, keine `.qm`) | `main.py:2048-2054` |
| Update-Check zeigt auf falsches GitHub-Repo, Flag ohnehin aus | `services/version_check_service.py:30` |
| kNN-Backend + `build_similarity_edges` ohne Produktiv-Callsite | `services/graph/knn_backend.py`, `graph_service.py:79` |
| Lern-Session ohne Material (Writer hat 0 Callsites, DB 0 Zeilen) | `services/brain/timeline_state.py:86-182,185-287` |
| ART-005/ART-006 prüfen 5 nicht existierende Pfade, nicht die echte Pin-Datei | `services/release_readiness.py:15-32` |
| Marker `live_gpu`/`e2e` nirgends gesetzt — CI-Gate suggeriert Ausschlüsse, die es nicht gibt | `pyproject.toml:101-108`, `.github/workflows/ci.yml:77` |

---

## B. Erfolg gemeldet, nichts getan

| Funktion | Stelle | Was passiert |
|---|---|---|
| `preview_export` (Chat-Action) | `services/actions/edit/timeline_actions.py:512` | kein Worker registriert → No-Op, meldet „Task in Warteschlange" |
| `auto_ducking` | `services/actions/edit/timeline_actions.py:555` | dito |
| `convert_videos` | `services/actions/edit/media_actions.py:168` | dito |
| `explain_clip` | `services/actions/ai_actions.py:647` | emittiert `analyze_video_content`, nicht im Worker-Registry |
| `save_project` | `services/actions/edit/project_actions.py:121` | gibt fest „erfolgreich gespeichert" zurück, speichert nichts; ChatDock markiert danach clean |
| Storage-Browser „Auch Speicherdateien löschen" | `ui/dialogs/storage_browser_dialog.py:97` → `storage_browser.py:163` | `storage_root` fehlt → `layout is None` → `_delete_storage_dirs` übersprungen, meldet „0 Ordner / 0 B" |
| Strg+V in der Timeline | `ui/timeline.py:3851` | schreibt nur Konsolentext |
| In/Out-Punkte (I/O) | `ui/timeline.py:3573-3607` | nur lokal + Log, keine Marker, keine Wirkung |
| `cancel_task` bei Metadaten-Tasks | `services/task_manager.py:505-527` | setzt Status `cancelled`, die synchrone Arbeit läuft weiter |

**Besonders heikel:** Der Verifier für den Storage-Browser
(`scripts/diag/verify_b547_storage_browser_delete_visible.py:138`) patcht eine Subklasse *mit* `storage_root` ein —
er testet am Produktivpfad vorbei und meldet grün.

---

## C. Datenverlust- und Korrektheitsrisiken

| # | Befund | Stelle |
|---|---|---|
| C1 | **Audio-V2 (Default) persistiert stille Fallbacks als echte Messwerte.** V1 hat den B-066-Schutz, V2 nicht. Key-Fehler → hart `Am`/`8A`, Spectral-Fehler → alle 8 Bänder `0.0` **ohne** `is_fallback`-Flag, LUFS-Fallback −14.0 | `services/audio_pipeline/stages.py:105`; `key_detection_service.py:202`; `spectral_analysis_service.py:280` |
| C2 | **Kein `degraded`-Zustand im Status-Modell** — nur pending/running/done/error. Panel zeigt ✓ für geratene Läufe | `services/analysis_status_service.py:89-107` |
| C3 | **Struktur-Analyse löscht erst alle Segmente**, catch-all liefert leeres Result als Erfolg → stiller Datenverlust | `structure_detection_service.py:1192` + `:281` |
| C4 | **Einzel-Aktion „Szenen erkennen"/„Motion" vernichtet alle VLM-Captions** des Clips (`store_scenes_in_db` löscht + schreibt captionlos); zusätzlich ohne `expected_db_url` | `services/actions/video_actions.py:273,340` |
| C5 | **Geöffnete Projekte bekommen nie ein Backup** — Startup-Backup läuft gegen Repo-Root, bevor ein Projekt offen ist. Einziges Projekt-Backup ist der Pre-Migration-Snapshot | `main.py:2091`, `database/migrations.py:429` |
| C6 | **Undo-Stack überlebt Projektwechsel** (kein `undo_stack.clear()`) → Strg+Z kann Zeilen eines anderen Projekts ändern | `ui/controllers/project_management.py:308` |
| C7 | **Ein kaputtes Video killt die ganze Batch** — `FFmpegError`/SQLAlchemy entkommen dem Per-Clip-`except`. Identischer Fehler war B-674, dort gefixt, hier nicht | `workers/video.py:501` |
| C8 | **`delete_all_media` ohne M1-Timeline-Backup** → Restore aus dem Papierkorb bringt Clips ohne Position zurück | `services/ingest_service.py:542` |
| C9 | **Kein Ripple-Modell** — Overlaps nur beim Add aufgelöst; Move/Trim/Delete erzeugen stille Überlappungen | `services/timeline_service.py:378`, `ui/timeline.py:1813` |
| C10 | **Cancel liefert halbes Ergebnis in die Timeline** — Teil-Segmente werden als reguläres `finished` emittiert und angewandt | `services/pacing_service.py:1393`, `workers/edit.py:74`, `ui/controllers/edit_workspace.py:465` |
| C11 | **Manifest-Lock-Timeout löscht fremdes Lockfile** und schreibt ungeschützt | `services/storage_provenance/source_manifest.py:112-129` |
| C12 | **Lock-Verlust bei Remove-Undo** (Snapshot ohne `locked`) | `ui/undo_commands.py:263-275` |
| C13 | **Testsuite schreibt in reale Projekt-DB** (B-727, `test_engine` nicht autouse); 19 weitere Testdateien referenzieren `pb_studio.db` und sind ungeprüft | `tests/conftest.py:80`, `tests/test_workers/test_audio_pipeline_v2_worker.py:24-60` |
| C14 | **`brain_v3/state.db` landet im Repo-Root** und wandert bei Projektwechsel | `services/brain/paths.py:77` |

---

## D. Fehlende Kernfunktionen (nie gebaut, keine Bugs)

| Funktion | Belegstelle / Befund |
|---|---|
| **Clip-Split / Razor** | im gesamten SCHNITT-Scope kein Command, kein Shortcut, kein Menüpunkt |
| **Sichtbarer Playhead** | `ui/timeline.py:3754` speichert nur ein float — kein Item, kein `paint`, kein Repaint |
| **Klick-Seek auf der Zeitachse** | kein Handler; Ruler rein dekorativ |
| **Preview zeigt die Timeline** | `ui/controllers/edit_workspace.py:28-43`, `workspace_setup.py:405` — Vorschau hängt am `video_combo`, nie am Schnitt |
| **Projekt umbenennen / löschen** | keine Implementierung im Repo (`delete_project` nur in der DESTRUCTIVE-Whitelist) |
| **Backup-Restore** | `BackupService` hat kein `restore()`, keine UI, kein CLI |
| **Fenstergeometrie + Dock-Layout speichern** | kein `saveGeometry`/`restoreGeometry`, kein `saveState`/`restoreState` im Repo |
| **Checkpoint/Resume der Videoanalyse** | existiert nicht; Re-Run macht alles neu (nur Keyframes gecacht) |
| **Manueller „Snapshot jetzt"** | nur Restore in der UI; Snapshots entstehen ausschließlich automatisch beim Auto-Edit |
| **Abbrechen-Button im DELIVER-Tab** | Cancel nur über das Task-Panel erreichbar |
| **Token-Streaming im Chat** | alle Ollama-Calls `stream: False`; zusätzlich kein Abbrechen-Button im Chat |
| **Mehrspur-Audio im Export** | nur `audio_entries[0]`, Rest still verworfen (`export_service.py:364`) |
| **EDL-Export bedienbar** | `services/timeline_service.py:795` ohne Produktions-Caller |
| **Audio-Pool sortierbar** | kein `setSortingEnabled(True)` (`media_workspace.py:761`) |
| **Undo für Inspector-Edits** | direkter DB-Write ohne QUndoCommand (`ui/clip_inspector.py:269`) |

---

## E. Falsche Auskunft an den Nutzer

| Was | Stelle |
|---|---|
| Shortcut-Hilfe listet nicht existierende Kürzel (1–5, Ctrl+N, Ctrl+O, Ctrl+,) | `ui/dialogs/shortcut_help_dialog.py:27-39` |
| Shortcut-Hilfe erfindet Stem-Shortcuts (M/S/R/Ctrl+Up/Down) | `ui/dialogs/shortcut_help_dialog.py:64-70` |
| Shortcut-Hilfe nennt veraltete Workspace-Namen (MEDIA/EDIT/STEMS/CONVERT/DELIVER) | dito |
| Settings-Tooltip behauptet „parallelisiert" — V2 ist strict-sequential | `ui/dialogs/settings_dialog.py:483` |
| Menü-Label „Audio-V2 Pipeline (Beta)", obwohl V2 der Default ist | `ui/controllers/workspace_setup.py:159` |
| Kommentar „verhindert Connection Leak" — `with sqlite3.connect(...)` ist Transaktions-CM, kein Closing-CM | `services/project_manager.py:349` |
| Kommentar „Removed duplicate init_db" — `init_db` läuft nachweislich zweimal | `main.py:2199` vs. `main.py:2078` + `workers/startup.py:16` |
| Bug-Files B-572/B-643 behaupten im Fließtext „kein Fix", obwohl Fixes existieren | Vault, Bulk-Reconciliation 2026-07-17 |
| B-618 dokumentiert einen überholten Fix als „GUI-Live-Retest PASS" | Folge-Commit `2e0e739` erklärt den Ansatz für wirkungslos |

---

## F. Performance / Skalierung

| Befund | Stelle |
|---|---|
| **Struktur-Enrichment läuft pro Clip library-weit** (`get_all_embeddings` + UMAP-Fit + volle N×N-Compat-Matrix): live ~2 min/Clip gegen ~6 s Analyse → 103 Clips ≈ 3,5 h | `services/video_analysis_service.py:1477,1706` |
| Enrichment immer `mode=fit` → Buckets werden pro Clip verworfen und neu erfunden | `workers/structure_enrichment.py:359-364` |
| `role_classifier` bekommt `motion` hart 0.5, obwohl `Scene.energy` gefüllt ist → alle `motion_gte`/`motion_lt`-Regeln wirkungslos | `workers/structure_enrichment.py:323-327` vs. `video_analysis_service.py:1193` |
| Cross-Project-Reuse hasht bei **jedem** Import die komplette Datei (`mode="strict"`), synchron im Import-Loop | `services/storage_provenance/cross_project_reuse.py:59` |
| Stem-Reencode lädt jeden Stem komplett in RAM und hebt den Streaming-Writer auf (1,5 h ≈ 2 GB/Stem) | `services/ai_audio_service.py:857` |
| Analyse-Caps bei langen Mixen: Key global 120 s, Key-Modulation 600 s, Spectral 300 s, librosa-Beat-Fallback 600 s — Teilergebnis wird als Vollanalyse persistiert | `key_detection_service.py:228,250`; `spectral_analysis_service.py:191`; `beat_analysis_service.py:275` |
| Cancel wirkt nur an Stage-Grenzen (av_pacing lief 956 s nach) | `services/audio_pipeline/stages.py:53` |
| Sync-DB-Queries im GUI-Thread bei Workspace-Wechsel | `workspace_setup.py:629,683,764` → `cockpit_orchestrator.py:151ff` |
| Sub-Progress nur von 3 von 10 Audio-Stages gefüttert → lange Stages stehen still | `workers/audio_pipeline_v2_worker.py:73-109` |
| Preview-Export nutzt Voll-ORM-Load (B-090/B-636-Fix fehlt dort) | `services/export_service.py:1509-1514` |
| Trim-Release liest DB im GUI-Thread | `ui/timeline.py:3093` |

---

## G. GPU / Nebenläufigkeit — strukturelle Lage

- **Sechs unabhängige VRAM-Owner ohne gemeinsames Budget** auf 6 GB: ModelManager main + aux, Brain-V3 SigLIP-2,
  CLAP, Demucs (lokale Variable, für die Buchhaltung unsichtbar, `ai_audio_service.py:479`), beat_this-Singleton,
  NVENC/Ollama. `check_memory_available` ist nur eine Momentaufnahme ohne Reservierung.
- **RAFT-Teardown außerhalb der `gpu_execution_lease`** (`workers/video.py:596-615`) — exakt die un-serialisierte
  GPU-Op-Klasse aus B-684/B-692 (0xC0000374).
  HYPOTHESE: `raft_m` *ist* `_aux_model`; `.cpu()` verschiebt das gecachte Objekt, `del` löscht nur den Namen →
  bei fehlgeschlagenem SigLIP-Preload liefert `load_raft()` einen CPU-Tensor als CUDA-Cache-Hit.
- **Lock-Inversion LOAD→EXECUTION nur per Kommentar verboten**, kein Runtime-Guard.
- **Perf-Watchdog misst potenziell Unsinn**: `_profiled_notify` hängt an `QCoreApplication::notify` und läuft in
  jedem Thread mit Event-Loop, aber `_call_stack`/`_current_event_*` sind ungeschützt geteilt
  (`services/perf_watchdog.py:103,152-171`). Dauerhaft aktiv. Plausibler Kandidat für die B-621-Messartefakte.
- **Kein `WM_DEVICECHANGE`** im Power-Filter → SB2-Base-Detach setzt kein Suspect-Flag;
  `_ensure_cuda_or_fallback` nur in `load_*`, nicht vor Inferenz.
- **9 QThreads laufen am TaskManager vorbei** → im TASKS-Dock unsichtbar, nicht in `get_shutdown_tasks`.
- **Phantom-Task-IDs** bei `moveToThread`-Fehler und im Shutdown-Pfad (`task_manager.py:264,299`).
- **Geladene Waffe**: `task_manager.py:455` `unload_in_background` ohne Callsite — würde `unload()` inkl.
  `empty_cache` ohne jeden GPU-Lock aus einem Worker-Thread fahren.
- **Cleanup-Bypass**: `main.py:2229` „Beenden" im Startup-Dialog ruft `app.quit()` ohne `window.close()`;
  kein `aboutToQuit`-Hook im Repo → gesamte `closeEvent`-Kette übersprungen.
- **Doppeltes `init_db`** beim Boot (live belegt: zweimal „Alembic-Migrationen abgeschlossen (head)").

---

## H. Backlog-Lage (Querschnitt)

727 Bug-Files gesamt: 495 mit Endstatus (davon 473 `fixed`), **231 ohne Endstatus**.

| Klasse | n |
|---|---|
| `code-fix-pending-live-verification` | 168 |
| **echt `open`** | **23** |
| `reserved-gap` (Platzhalter, keine Bugs) | 20 |
| Sonstige (deferred, parked, partial-fix, superseded-by, Sonderstatus) | 20 |

**Stichprobe 12 × pending gegen `main`: 11 × Fix real im Code, 1 × teilweise, 0 × erfunden.**
Die 168 sind ein **Verifikations**-Rückstand, kein Fix-Rückstand.

Was den Backlog unbrauchbar macht:
- Bulk-Reconciliation 2026-07-17 setzte 30 Files auf pending, ohne die Bodies nachzuziehen (B-572, B-643 widersprechen
  sich intern).
- B-618 doppelt geführt; das zweite File hat kein Frontmatter, keinen Status.
- ~24 IDs für ~6 Root-Causes (BLOB-Load-Freeze allein 7 IDs; Manifest 5; Thumbnail-Threads 3;
  GPU-Lock alt B-502/503/554 vs. neu B-723/725/726 — dieselbe Fehlerklasse zweimal aufgemacht).
- B-441…B-457 (17 IDs) sind Fehlschläge *eines* pytest-Gate-Laufs vom 2026-06-01, keine Produktbugs.
- Wahrscheinlich obsolet mit Code-Beleg: B-270, B-284/285, B-287/288/289.

Real noch schmerzhaft: **B-709** (CI rot, live gegengeprüft: `export_service.py:11` + `:1317` doppelter
`threading`-Import), **B-723/725/726** (GPU-Lock-Klasse zum zweiten Mal), **B-718** (`torch.load` auf ungeprüftem
Checkpoint), **B-433** (nur teilgefixt), **B-572** (Root-Cause ungeklärt, nur Plausibilitäts-Fallback).

---

## I. Was belegbar gut funktioniert

Damit das Bild nicht kippt — folgendes ist durch Logs, Live-Daten oder Tests gestützt:

- **Audio-V2-Volllauf**: track=1 (5531 s, 1,5-h-Mix, 198 Demucs-Chunks) und track=2 (513 s), alle 10 Stages `done`,
  `beat_this` sauber auf `cuda:0` geladen und entladen.
- **Video-Analyse**: SceneDetect, RAFT-Motion (CUDA), Keyframes, SigLIP-Embeddings 1152d — alle log-belegt.
  **VLM-Captions sind kein Stub**: echter Ollama-Vision-Call, „1/1 Szenen" ×10 im Log.
- **Echte xfade-Crossfades verifiziert** (`docs/sandbox-runs/2026-07-24-b707…/verify_log.md`: 94 Segmente, 338,2 s).
- **Export-Mechanik**: B-611-Rundung, B-693-Gap-Schließung, B-677-Wall-Clock-Watchdog, dynamische Timeouts,
  Temp-Cleanup pro Lauf, Pfad-Härtung gegen Traversal.
- **Timeline-Virtualisierung** (Record/Item-Trennung, Hysterese, 40 ms-Budget), Waveform-Tiles mit LOD/Culling,
  Marker als Single-Items mit `exposedRect`-Culling, Thumbnail-Pfad.
- **DB**: Alembic-Kette 18 Revisionen linear, genau ein Head `e1f2a3b4c5d6`, kein Branch; FK=ON auf beiden
  Engine-Pfaden; WAL + `busy_timeout` 120 s konsistent; Backup über `sqlite3.backup()` WAL-sicher.
- **Stem-Player** driftfrei über einen einzigen Stream mit gemeinsamer Master-Clock.
- **Agent-Governance-Tooling**: `agent_session.py` (worktree-übergreifende Registry, atomares Locking),
  `agent_start.ps1` (Session-Guard vor Dirty-Check), `agent_handoff.ps1`, `session_learning.py`, FFmpeg-SHA-Gate.
- **Studio-Brain-UI**: alle 6 Tabs verdrahtet, Cross-Tab-Wiring Memory→Audit→Explorer→Graph funktioniert;
  Graph-Cockpit bezieht echte Daten aus `struct_clip_tags`/`struct_compat_edge`.

---

## J. Vorschlag für die Reihenfolge (nicht ausgeführt — User entscheidet)

1. **B-727** Testisolation — vor jeder weiteren Vollsuite, sonst wird wieder in reale Projektdaten geschrieben.
2. **B-709** Ruff F811 — Einzeiler, entsperrt die gesamte CI.
3. **A1** (Pacing-Kurve neutralisiert Section-Pacing) — braucht eine **User-Entscheidung**: soll bei flacher
   Kurve die Section-Logik gewinnen, oder soll die Kurve immer gewinnen?
4. **A2/A3/A4** (Brain-Wirkungskette) — hängen zusammen; sinnvoll nur als Paket, und erst nach einer
   Grundsatzentscheidung, ob Studio-Brain der Default-Pfad sein soll.
5. **C-Block** Datenverlustrisiken (C1–C8) — davon sind C1/C3/C4/C5/C6 die, die stillen Schaden anrichten.
6. **B-Block** (Erfolg gemeldet, nichts getan) — billig zu beheben, hoher Vertrauensgewinn.
7. **E-Block** (falsche Auskunft) — reine Textkorrekturen, kein Logikrisiko.
8. Backlog entrümpeln, bevor die nächste Fix-Welle startet.
9. Danach erst: echter Medien-E2E-Lauf und Release-Gates.

---

## K. Grenzen dieser Aufnahme

- Keine Laufzeitverifikation. Jede Aussage über tatsächliches Verhalten unter Last, echte Freeze-Dauern,
  reale VRAM-Peaks oder tatsächliche Auto-Edit-Ergebnisse ist **nicht** belegt.
- A1–A4 folgen zwingend aus dem gelesenen Code, sind aber nicht durch einen Auto-Edit-Lauf bewiesen.
- Der Zustand `funktioniert-belegt` bedeutet „durch Log/Test/Live-Daten gestützt", nicht „live vom User gesehen".
- Kein `fixed`-Marker wurde gesetzt und keiner ist ableitbar — das setzt ausschließlich der User.
