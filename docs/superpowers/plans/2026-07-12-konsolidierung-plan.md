# Plan: PB-STUDIO-KONSOLIDIERUNG-2026-07-12

status: approved-for-implementation — OBERSTE PRIORITAET (User 2026-07-12:
"als erstes erledigt werden, auch wenn es ein anderer Agent machen muss")
decision: D-068 (Vault)
vault_mirror: wiki/synthesis/plan-konsolidierung-2026-07-12.md
quelle: /simplify 4-Agenten-Review 2026-07-12 (Reuse- + Altitude-Angle),
Finding 6/7 der User-Durchsprache

## Ziel

Duplikat-Implementierungen und Falsche-Ebene-Fixes konsolidieren: eine
Quelle pro Mechanismus, damit kuenftige Aenderungen nicht an 6-25
Stellen synchron gepflegt werden muessen. Verhaltensneutral ausser wo
explizit als User-Entscheid markiert (K6-FK).

## Prioritaets-Verhaeltnis

Dieser Plan laeuft VOR PB-STUDIO-PERF-DB-CLEANUP-2026-07-12. Die
virt-M4-User-Sichtung (`fixed`-Marker) bleibt parallel offen — sie ist
eine User-Aktion, keine Agent-Arbeit, und wird durch diesen Plan nicht
blockiert. Bei Konflikt mit einer laufenden User-Sichtung: Task pausieren.

## Tasks (Abarbeitungs-Reihenfolge = risikoarm zuerst)

### K9 — session.py: Monkey-Patch auf tote Konstanten entfernen
- `database/session.py:343-354` `_patch_service_paths` patcht
  `services.vector_db_service.DB_DIR`/`DB_FILE` — beide haben null
  Konsumenten (Service nutzt seit Lazy-Getter `_default_db_file()`
  Z.36-39 nur noch diesen). Load-bearing ist nur `"_instance": None`
  (F-030 Singleton-Reset).
- Fix: tote Konstanten (vector_db_service.py:23-24) + Patch-Eintraege
  entfernen, `_instance`-Reset behalten.
- Verify: vorher Tests auf DB_FILE/DB_DIR-Import greppen; pytest
  test_database + vector-db-Tests; App-Start + Projekt-Swap live.

### K4 — subprocess_kwargs: einen Helper, ~25 Inline-Stellen umstellen
- Helper existiert: `services/startup_checks.py:149` (privat).
- Duplikat-Stellen (3 Varianten, auf win32 funktional identisch):
  video_service.py:143-145, ingest_service.py:292-293,
  export_service.py:107-109 (+3 weitere), convert_service.py (6x,
  ternaer), lufs_service.py:36 (getattr-Variante),
  video_pipeline/primitives/proxy_generator.py (5x),
  workers/import_export.py:40-41,119-120, workers/video.py:647,
  ai_audio_service.py:216,957, ui/widgets/brain_v3_learning_dialog.py:65
- Fix: Helper oeffentlich machen (`subprocess_kwargs()` in
  startup_checks oder services/ffmpeg_utils), alle Stellen umstellen.
  Pro Datei ein Edit, ein Diff-Review.
- Verify: ruff+compile; ein ffmpeg-Aufruf pro betroffenem Service real
  ausfuehren (kein Konsolen-Fenster, Rueckgabe identisch).

### K7 — ffprobe-Duration + frame_rate-Parsing: je ein Helper mit Param
- Duration 5x: convert_service.py:431 (Fallback 0.0),
  video_analysis_service.py:387 (Fallback 60.0!), lufs_service.py:20
  (0.0), export_service.py:~536 (0.0), workers/import_export.py:114
  (0.0, csv=p=0-Variante).
- frame_rate 4x: export_service.py:73 `_parse_frame_rate` (kanonisch),
  video_service.py:166-173 (rundet 2 Stellen), ingest_service.py:304-306
  (Default 30/1!), video_pipeline/primitives/decoder.py:112-114.
- Fix: `probe_duration(path, fallback=0.0)` + `parse_frame_rate(raw,
  default=...)` in services/ffmpeg_utils.py; Callsites mit EXAKT ihren
  bisherigen Fallbacks/Rundungen umstellen. Divergenzen (60.0-Fallback,
  30-Default) bleiben dokumentiert erhalten — Vereinheitlichung waere
  Verhaltensaenderung -> nicht Teil dieses Plans.
- Verify: Unit-Tests pro Fallback-Pfad (kaputtes File, fehlendes Feld);
  bestehende probe-Tests gruen.

### K5 — Action-Factory: 10x ~40-Zeilen-Copy-Paste eindampfen
- services/actions/audio_actions.py:125-330 (5 Actions) +
  services/actions/video_actions.py:252-482 (5 Actions): identisches
  Muster (file_path-Lookup -> TaskManager-Check ->
  agent_command_signal.emit -> Result-Dict), Unterschied nur
  Name/Beschreibung/Schema.
- Fix: Factory `_make_enqueue_action(name, desc, schema)` + Schleife;
  Registry-Eintraege (Namen, Schemas, Docstrings fuer Agent-Discovery)
  byte-identisch halten.
- Verify: Registry-Dump vorher/nachher identisch (Namen+Schemas);
  eine Audio- + eine Video-Action real ueber Agent-Command ausfuehren.

### K2 — STEM_NAMES: eine Quelle
- Kanonisch: services/audio_constants.py:164. Parallel-Konstanten:
  stem_player.py:57, ui/widgets/stem_workspace.py:39 (STEM_ORDER),
  pacing/stem_section_aggregator.py:16. Inline-Tupel u.a.:
  ui/workspaces/stems_workspace.py:202/332, pacing_beat_grid.py:477/927,
  pacing_service.py:685, audio_pipeline/stages.py:186,
  storage_provenance/cross_project_reuse.py:361/389.
- ACHTUNG: Reihenfolge teils load-bearing (UI-Spalten vs.
  Demucs-Source-Order ai_audio_service.py:542). Pro Stelle pruefen ob
  Reihenfolge-Semantik existiert; wo ja: Kommentar + bewusster Import
  der geordneten Konstante, wo nein: Set-Nutzung.
- Verify: Stem-Player + Stem-Workspace UI-Smoke (Spaltenreihenfolge),
  pacing-Tests gruen.

### K3 — SigLIP-Modell-ID + Embedding-Dim: eine Quelle
- Kanonisch: services/model_warmup.py:29 SIGLIP_DEFAULT_MODEL.
  Hartkodiert: model_manager.py:894, siglip_embed_service.py:20,
  video_pipeline/app_integration.py:98, model_lifecycle_service.py:80,
  vector_db_service.py:32 (+ EMBEDDING_DIM 1152 vs. Literal in
  pacing_service.py:835).
- Fix: alle Defaults importieren SIGLIP_DEFAULT_MODEL; Dim-Literal
  1152 -> EMBEDDING_DIM-Import.
- Verify: SigLIP-Warmup + ein Embedding-Lauf auf GTX 1060 (Modell laedt,
  Dim 1152, VectorDB-Insert ok). GPU-Hartregel: nur cuda:0.

### K6 — pacing_service: Engine-Fabrik aus database/session.py nutzen
- services/pacing_service.py:349-364 `_make_auto_edit_engine` dupliziert
  nullpool_session-Engine-Bau OHNE Pragma-Listener (kein foreign_keys=ON,
  kein busy_timeout=120s, hartes timeout=30).
- Fix Teil A (verhaltensneutral): Engine-Bau + busy_timeout/
  connect-timeout ueber gemeinsame Fabrik aus database/session.py.
- Fix Teil B (VERHALTENSAENDERUNG, eigener User-Entscheid VOR
  Umsetzung): foreign_keys=ON auch im Auto-Edit-Pfad aktivieren.
  STOP + ASK beim Erreichen dieses Tasks.
- Verify: Auto-Edit-Lauf auf test33-Kopie, Ergebnis-Paritaet
  (Timeline-Rows identisch), Lock-Verhalten unter parallelem Zugriff.

### K1 — Undo-Writes: alle Commands durch _run_timeline_write routen
- ui/undo_commands.py: `_run_timeline_write` (NullPool + 3x Lock-Retry,
  B-512) nur von AddClipCommand genutzt; MoveClipCommand._apply (Z.100),
  Trim/Delete/Restore etc. schreiben direkt via gepooltem
  DBSession(engine).
- Fix: alle Command-_apply-Bodies durch _run_timeline_write routen
  (gleiche Writes, gleicher Retry-Schutz). Zusatz-Befund dokumentieren:
  `_timeline_write_session`-Branch auf `engine is _app_engine` existiert
  nur fuer Test-Monkeypatch — bei Gelegenheit explizit machen.
- Verify: komplette Undo/Redo-Testsuite (B-512-Suite) + Live-Smoke:
  Add/Move/Trim/Delete/Undo/Redo auf test33-Kopie.

### K8 — QThread-Verdrahtungen auf run_worker migrieren (15 Stellen)
- workers/base.py:171 `run_worker` (B-513: destroyed-Guard, weakref,
  shiboken-Check, deleteLater-Kette) nur 3x genutzt. Handgerollt ohne
  Guards: settings_dialog.py:573-579, model_manager_dialog.py (5x),
  chat_dock.py:401, ui/timeline.py:1393/1937/2019 (nach aktuellem
  Stand ggf. verschoben), controllers/export.py:72,
  controllers/edit_workspace.py:205, controllers/workspace_setup.py:892,
  dialogs/setup_wizard.py:571.
- Fix: pro Stelle einzeln migrieren (eigener Mini-Commit pro Datei),
  Signal-Verhalten identisch halten (error->quit, deleteLater-Kette).
- Verify: pro Stelle den betroffenen Flow live ausfuehren (Dialog
  oeffnen/schliessen waehrend Worker laeuft = B-513-Crash-Repro).
- Groesster Task — bewusst zuletzt.

## Leitplanken

- Ein Task = ein Commit = ein Vault-Log = eigene Verifikation.
- Byte-Paritaet wo moeglich (K5-Registry, K7-Fallbacks), sonst
  dokumentierter Paritaetsbeweis.
- K6 Teil B (FK-ON) NIEMALS ohne expliziten User-Entscheid.
- Reihenfolge: K9 -> K4 -> K7 -> K5 -> K2 -> K3 -> K6 -> K1 -> K8.
- `status: fixed` setzt nur der User nach Live-Test.
