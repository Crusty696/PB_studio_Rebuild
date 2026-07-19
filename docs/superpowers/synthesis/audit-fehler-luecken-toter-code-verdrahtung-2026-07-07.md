# Audit-Bericht: Fehler, Lücken, toter Code, Verdrahtung, Pipelines, DB (2026-07-07)

- **Auftrag (User):** "suche nach fehler, lücken, totem code, falsch verdrahtet, nicht verdrahtet, kaputte pipelines, db bugs und wird auch alles richtig und wirklich eingesetzt und verwendet dort wo es gebraucht wird. erstelle erst mal nur einen bericht nicht mehr."
- **Modus:** Read-only. Keine Code-Änderung, kein Fix, kein Commit. Statische Analyse (Import-Graph, Grep-Kreuzverifikation ≥2 Muster pro Behauptung, Code-Lesung) durch 5 parallele Subagenten. Keine Laufzeit-Verifikation.
- **Branch:** `codex/OTK-021-source-consolidation-2026-06-22`, HEAD `13850b1`, Worktree clean.
- **Umfang:** 317 Produkt-Module (main.py → ui/ → services/ → workers/ → agents/ → database/), ~1042 .py Dateien gesamt.
- **Ergebnis:** 85 Findings (16 DEAD, 14 WIRE, 18 PIPE, 21 DB, 16 USE), davon ~10 Überschneidungen zwischen Kategorien (unten zusammengeführt). Dazu explizite Positiv-Befunde.

---

## TL;DR — Die 5 wichtigsten Erkenntnisse

1. **Jedes heute gerenderte Video hat nur harte Schnitte.** Der Auto-Edit berechnet Crossfades, aber der Worker serialisiert sie unter dem Key `crossfade`, während der Timeline-Service `crossfade_duration` liest → immer 0.0 (PIPE-001).
2. **Die Default-Audio-Pipeline (V2) lässt Mood/Genre/DJ-Mix-Klassifikation UND Waveform aus.** Matching läuft mood-blind, SCHNITT-Waveform bleibt leer, `analysis_status` wird nie geschrieben (PIPE-002/DB-002/DB-003/DB-006/PIPE-014).
3. **Alle 2026er-Neubauten sind vom Produkt abgeschnitten:** Studio-Brain-Pacing-Pipeline (Env-Flag nie gesetzt), Brain-V3-Reranker (`use_brain_v3` nie True), DAG-Video-Engine (Flag nie gesetzt), Slice-1-Pacing-Module, RL-v2, LLM-Pacing (kein UI-Schalter), SteerOverrideQueue (kein Consumer), Timeline-Snapshots (kein Caller). Das Produkt läuft überall auf Legacy-Pfaden (USE-001..009).
4. **~5.300+ Zeilen toter/unverdrahteter Produktcode** + 5 tote DB-Tabellen (HotCue, PacingBlueprint, AudioVideoAnchor, StepDep, TimelineSnapshot) + 3 Spalten die gelesen aber nie geschrieben werden (`sub_genre`, `spectral_hash`, `harmonic_tension`).
5. **Positiv:** Session-Handling, SQLite-Threading, Worker-Verdrahtung, Qt-Thread-Disziplin und die Kern-Modelle (Demucs, beat_this, SigLIP, RAFT, Qwen) sind sauber verdrahtet. Keine AttributeError-Kandidaten in Connects gefunden.

---

## A. Direkter Impact auf das gerenderte Video (höchste Schwere)

### A1. PIPE-001 — Crossfades berechnet, nie gerendert (Key-Mismatch)
- Writer: [workers/edit.py:64](workers/edit.py:64) serialisiert `"crossfade": s.crossfade_duration`.
- Reader: [services/timeline_service.py:308](services/timeline_service.py:308) liest `seg.get("crossfade_duration", 0.0)`.
- `ApplyAutoEditCommand` ([ui/undo_commands.py:402](ui/undo_commands.py:402)) reicht Dicts unverändert weiter, kein Adapter dazwischen. Export ([services/export_service.py:600](services/export_service.py:600), `:644`) erreicht den Crossfade-Filtergraph nie.
- **Folge:** Section-abhängige Crossfades (Breakdown-Dissolves, DJ-Mix bis 3.0s, [services/pacing_service.py:1199](services/pacing_service.py:1199)) existieren nur im RAM. Konfidenz: hoch.

### A2. PIPE-002 + DB-003 — V2-Default-Pipeline ohne Classify-Stage → Matching mood-blind
- `DEFAULT_STAGE_ORDER` ([services/audio_pipeline/stages.py:585](services/audio_pipeline/stages.py:585)): stem_gen, beat_grid, onset, key, structure, lufs, spectral, av_pacing — **keine** Classify-Stage. V2 ist Default (`audio.v2_default=True`, [ui/controllers/audio_analysis.py:305](ui/controllers/audio_analysis.py:305)).
- Reader: [services/pacing_service.py:779-782](services/pacing_service.py:779) (`mood`, `genre`, `is_dj_mix`), [services/pacing_edit_helpers.py:643](services/pacing_edit_helpers.py:643).
- **Folge:** Nach Komplett-Analyse bleiben `AudioTrack.mood/genre/is_dj_mix` NULL → "Dark Audio → dunkle Visuals" effektiv deaktiviert. Einziger Writer ist der separate Einzel-Button `AudioClassifyWorker` ([workers/audio_analysis.py:310](workers/audio_analysis.py:310)). Konfidenz: hoch.

### A3. PIPE-006 — Einheiten-Mismatch: Quellvideo-Szenenzeit als Timeline-Zeit injiziert
- [services/pacing_service.py:655-685](services/pacing_service.py:655): `scene.get("start")` (Zeit **im Quellvideo**) wird gegen Audio-`total_duration` geprüft und als Timeline-Cut auf Beats gesnappt — bevor überhaupt entschieden ist, welches Video wo spielt.
- **Folge:** Quasi-zufällige, musikalisch unmotivierte Zusatz-Cuts. Konfidenz: hoch (Code), mittel (ob als Feature gewollt).

### A4. PIPE-008 — SigLIP-Ausfall deaktiviert Embedding-Matching still
- [services/pacing_service.py:704-713](services/pacing_service.py:704): Fehler in `_precompute_mood_embeddings()` → nur Log-Warnung, `mood_embeddings={}` gated auch `vdb.get_all_embeddings()` + Fitness-Matrix. Fallback-Kette endet bei Motion/Round-Robin.
- **Folge:** Bei OOM/Modellfehler werden alle gespeicherten 1152-dim-Embeddings ignoriert, ohne UI-Fehler. Konfidenz: hoch.

### A5. PIPE-007 — Klassifikations-Limits machen DJ-Mix-Erkennung unmöglich
- [services/audio_classify_service.py:218](services/audio_classify_service.py:218): max 180s geladen → `duration_sec` ≤180 → `_quick_dj_mix_check` bricht bei `< 600s` immer mit False ab (`:478`). `AudioClassifyWorker` schreibt dieses immer-False in die DB. Mood/Genre eines 60-min-Mix basieren auf den ersten 3 Minuten (Intro → "calm"-Bias). Analog `MAX_DURATION_SPECTRAL=300s`, `MAX_DURATION_KEY=120s`.
- **Folge:** Irreführendes DB-Flag (Pacing rettet sich über `detect_dj_mix_from_stems`), verzerrte Visual-Präferenzen. Konfidenz: hoch.

### A6. PIPE-009 — Beat-Analyse-Fehler verschluckt → synthetisches Grid ohne Downbeats
- [workers/analysis.py:61-73](workers/analysis.py:61): Fehler → nur Warning, Worker meldet finished. [services/pacing_beat_grid.py:197-253](services/pacing_beat_grid.py:197): synthetische Beats aus `bpm`. beat_this-Unavailable → librosa-Fallback **ohne Downbeats** ([services/beat_analysis_service.py:256-348](services/beat_analysis_service.py:256)).
- **Folge:** Downbeat-bevorzugtes Cutting arbeitet mit leerer Liste; Schnitt verliert Takt-Hierarchie, ohne sichtbaren Fehler. Konfidenz: hoch.

### A7. PIPE-015 — Stille GPU→CPU-Weichen
- NVENC: [services/export_service.py:43-49](services/export_service.py:43) — ein transienter `detect_nvenc()`-Fehler cached prozessweit False → gesamte Session rendert libx264/CPU ohne Hinweis (außer `PB_REQUIRE_NVENC=1`).
- RAFT: [services/video_analysis_service.py:140-155](services/video_analysis_service.py:140) — Ladefehler → `_cpu_motion_score` mit **anderer Skalierung** als RAFT (`:353` vs `:158`) → gemischte, inkonsistente Motion-Scores in derselben Bibliothek.
- Konfidenz: hoch (Code), mittel (Häufigkeit).

---

## B. Teuer berechnet, nie konsumiert (Analyse-Ergebnisse ohne Wirkung)

| ID | Was | Writer | Fehlt |
|---|---|---|---|
| PIPE-003 | AVPacingStage: 4 Kurven (Centroid/Flux/Stereo/Percussive) über ganzen Mix inkl. HPSS | [services/audio_pipeline/stages.py:565-581](services/audio_pipeline/stages.py:565) reduziert auf `{"samples": n}`, `_persist_to_track` nie aufgerufen | Persistenz + Konsument. Minuten CPU pro Track für nichts |
| PIPE-004 | Onset-Daten (Kick/Snare/HiHat, Syncopation, Groove) persistiert | [services/onset_rhythm_service.py:616](services/onset_rhythm_service.py:616) | `refine_cut_points_with_onsets()` ([services/pacing_beat_grid.py:1146](services/pacing_beat_grid.py:1146)) hat **keinen Caller** — Cuts snappen nie sub-beat-genau |
| PIPE-005 | Structure-Enrichment (Role/Style-Buckets/Compat-Graph, UMAP/HDBSCAN+SigLIP) läuft nach jeder Video-Analyse | [services/video_analysis_service.py:1367](services/video_analysis_service.py:1367) | Kein Pacing-Reader; nur Studio-Brain-UI-Panels. `ClipFeatures`-Stubs bleiben `role="unknown"` ([services/pacing_service.py:1099](services/pacing_service.py:1099)) |
| PIPE-010 | `Beatgrid.stem_weighted_energy` write-only; im Legacy-Batch läuft BPM vor Stems → meist NULL | [services/beat_analysis_service.py:552](services/beat_analysis_service.py:552) | Kein Reader; Pacing berechnet pro Auto-Edit teuer neu (4× librosa.load) |
| PIPE-018 | Neue Video-Engine-Spalten (`embeddings_path`, `motion_path`, `scene_index`, …) | Nur neue Stages (Flag-gated) | Kein Produkt-Leser; Engine schreibt umgekehrt nicht in VectorDB/`Scene.energy` → mit Flag sähe Matching ihre Ergebnisse nicht |

---

## C. Implementiert, aber vom Produktfluss abgeschnitten (Flags/Setter/Consumer fehlen)

1. **USE-001 — Studio-Brain-Pacing-Pipeline:** Aktivierung nur via `PB_USE_STUDIO_BRAIN_PIPELINE` ([services/pacing/bridge.py:15](services/pacing/bridge.py:15)); Flag wird nirgends gesetzt (kein .env, kein Startskript, keine UI). DecisionRecorder, `mem_pacing_run`/`mem_decision`-Befüllung, Timeline-Feedback-Anbindung laufen im Default-Betrieb nie.
2. **USE-002 — Brain-V3-Reranker nie aktiv, auch mit Flag:** `PacingPipeline(use_brain_v3=False)`-Default; einzige Produkt-Instanzierung [services/pacing_service.py:980-991](services/pacing_service.py:980) übergibt kein `use_brain_v3=True` (nur Spike-Script tut das).
3. **USE-003 — DAG-Video-Engine:** `PB_ENABLE_VIDEO_PIPELINE_ENGINE` nie gesetzt; UI startet Monolith-Pfad. Bewusst "additiv" gebaut (DEAD-015), aber ohne Aktivierungsweg.
4. **USE-004 — SteerOverrideQueue:** UI schreibt (SteerTab/StructureTab), **kein** Backend-Consumer — Boost/Exclude/Pins wirkungslos. Eigenes Code-Eingeständnis: "the consumer (pacing agent) ships later" ([ui/studio_brain/steer_tab.py:41](ui/studio_brain/steer_tab.py:41)).
5. **USE-005 / DEAD-001 — Slice-1-Pacing-Cluster (16 Module, ~1.400 Zeilen):** cut_snapper (Onset-Snap), cut_density_modulator (Drop-Burst), vocal_hold_modifier, phrase_boundary_constraint, energy_match_reward, mood_match_score u.a. — nur von Tests/Demo-Script erreicht. `pacing/scorer.py` nutzt eigene, einfachere Funktionen.
6. **USE-006 — RL-Stack v2** (`rl_memory_v2`, `rl_policy`, `variety_memory`) tot; Produkt nutzt altes `pacing_memory`.
7. **USE-007 — LLM-Pacing:** `use_llm_strategist`/`use_llm_pacing` werden gelesen ([services/pacing_service.py:556](services/pacing_service.py:556), `:832`), aber repo-weit setzt sie niemand; kein UI-Schalter.
8. **USE-008 — Brain-V3-Lernschleife endet in der Anzeige:** Feedback-Writes verdrahtet, aber `mem_learned_pattern` liest nur der Memory-Tab; kein Scorer-Konsum. WeightStore wirkt nur über den inaktiven Reranker-Pfad (→ USE-002).
9. **USE-009 / DEAD-013 / DB-005 — Timeline-Snapshots:** Service + Tabelle + Model-Docstring ("bei jedem Auto-Edit-Run persistiert" — **falsch**), kein einziger Produkt-Caller. Undo läuft rein In-Memory. Nebenbefund DB-016 (version max+1 ohne UNIQUE) und DB-019 (detached ORM-Objekte) werden erst relevant, wenn verdrahtet.
10. **USE-012 — `audio.v2_default` ohne Setter:** wird gelesen, ist aber in keiner Settings-UI setzbar → Legacy-Pfad nur per Hand-Edit der settings.json erreichbar.
11. **USE-010 — Moondream:** nur Chat-Action (`analyze_video_content`) + Not-Fallback; kein UI-Pfad. USE-011 — `dispatch_cockpit_action` tot, UI ruft Controller direkt.

---

## D. DB-Bugs und Schema-Probleme

### Tote Tabellen / Write-only / Read-only
- **DB-001 HotCue:** kein Writer, kein Reader, nur Purge-DELETE ([database/models.py:447](database/models.py:447)). E2E-Befund `hotcues=0` ist strukturell.
- **DB-002 WaveformData:** V2-Pipeline hat keine Waveform-Stage; einziger Writer ist der manuelle Einzel-Button. E2E `waveform_data=0` = echte Pipeline-Lücke. SCHNITT-Audio-Tab/Waveform-Anzeigen bleiben leer.
- **DB-004 / PIPE-011:** `AudioTrack.sub_genre`, `spectral_hash`, `harmonic_tension` — definiert + von Pacing/Brain **gelesen**, aber **nie geschrieben** (Writer-Grep: 0 im Repo; `audio_classify_service` berechnet `sub_genre`, persistiert es nicht). Ursprünglicher "BUG-2" faktisch weiter offen.
- **DB-007 StepDep, DB-008 PacingBlueprint, DB-009 AudioVideoAnchor:** tote Tabellen (nur Deletes bzw. gar nichts). Manuelle Anker laufen real über `ClipAnchor` (aktiv).
- **DB-021 `AudioTrack.transcription`:** deklariert DEPRECATED, Legacy-Migration legt sie weiter an.

### Echte Fehlerquellen
- **DB-006 — V2-Worker schreibt keinerlei `analysis_status`** ([workers/audio_pipeline_v2_worker.py:40-88](workers/audio_pipeline_v2_worker.py:40)): Status-Dashboard falsch, Doppel-Analyse-Schutz greift nicht; teils entschärft durch Bulk-Reconcile beim Medien-Reload ([services/analysis_status_service.py:339](services/analysis_status_service.py:339)).
- **DB-010 — Migrations-Lücke `beatgrids.stem_weighted_energy`:** weder Legacy-Nachrüst-Block ([database/migrations.py:439](database/migrations.py:439)) noch irgendeine Alembic-Revision legt die Spalte auf Bestands-DBs an → auf alten DBs crasht jeder Beatgrid-Write mit `no such column`.
- **DB-011 — Check-then-Insert-Race** auf `beatgrids`/`waveform_data` (UNIQUE ohne Upsert; Retry fängt nur "database is locked") — B-581-Upsert-Pattern nur für `analysis_status` umgesetzt.
- **DB-012 — `spectral_bands` Doppel-Serialisierung:** `json.dumps`-String in `Column(JSON)` — abweichend vom Repo-Standard (H7/H-23); Reader `isinstance(list)`-Check schlägt fehl.
- **DB-017 — `init_db()` schluckt Alembic-Fehler** ([database/migrations.py:828](database/migrations.py:828)): fehlen dadurch `mem_*`-Tabellen (nur via Alembic erzeugt, nicht in `Base.metadata`), crasht der Auto-Edit erst zur Laufzeit (`no such table: mem_pacing_run`, [services/pacing_service.py:116](services/pacing_service.py:116)).
- **DB-015 — Soft-Delete ohne Kind-`deleted_at`** (bekannt B-186): Reader die direkt per `audio_track_id` querien ([ui/controllers/schnitt_coordinator.py:47](ui/controllers/schnitt_coordinator.py:47)) sehen Daten "gelöschter" Tracks.
- **DB-020 — `is_dj_mix`-Default-Drift:** Legacy-Migration `DEFAULT 0` vs. Model `NULL=unbekannt` → Semantik nicht unterscheidbar auf migrierten DBs.
- **DB-018 — `ai_pacing_memory`:** Range-Query auf nicht indizierten Spalten, Tabelle wächst per Policy unbegrenzt.
- **DB-014 — polymorphe `media_id` ohne FK:** dokumentiertes Design (D-028), Orphan-Restrisiko bestätigt.
- **DB-013 — Aufklärung E2E `timeline_entries=0`:** KEIN DB-Bug — [scripts/diag/e2e_functional_test.py:410](scripts/diag/e2e_functional_test.py:410) ruft nur `calculate_cut_points`, nie `apply_auto_edit_segments`. Produktions-Writer sind verdrahtet. Coverage-Loch im Diag-Skript.
- **DEAD-016 — Doppelte Migrationssysteme:** Alembic-Kette (14 Revisionen) parallel zu `database/migrations.py` (Raw-SQL, der real genutzte Pfad) — Drift-Quelle (siehe DB-010).

---

## E. UI-Verdrahtung

**Architektur-Korrektur:** `ui/mixins/` existiert nicht (mehr) — Repo nutzt Controller-Komposition (`ui/controllers/`, 13 Controller, alle in [main.py:272-284](main.py:272) instanziert). Doku/CLAUDE.md-Beschreibung "8 Mixin-Module" ist veraltet.

- **WIRE-001 / DEAD-002 — SetupWizard (~900 Zeilen) komplett unerreichbar:** intern korrekt verdrahtet, aber kein Import/Aufruf aus App-Code. Kein First-Run-/Modell-Download-Flow für User.
- **WIRE-002 — "Quellen pruefen"-Button:** erstellt + `setVisible(False)` ([ui/workspaces/workflow_pages.py:424](ui/workspaces/workflow_pages.py:424)), nie in Layout eingehängt, nie connected, nie sichtbar gemacht — Orphan-Widget, beworbene Sprungfunktion existiert nicht.
- **WIRE-003 — Video-Pool-Selection → pass-only Handler** ([ui/controllers/video_analysis.py:30](ui/controllers/video_analysis.py:30)).
- **WIRE-005 — `feedback_event_emitted` ohne Subscriber** ([ui/timeline.py:782](ui/timeline.py:782)): RL-Feedback (A/R/S, Rating) wird gespeichert, aber User bekommt keine sichtbare Bestätigung.
- **WIRE-004/008/009/010/011/012 — Dead-End-Signals im Studio-Brain-Bereich:** `nodeSelected`/`statsRefreshed` (GraphCockpit), `trackChanged`/`profileChanged` (SteerTab), `decisionSelected`/`verdictChanged` (DecisionExplorer), `patternsReset` (MemoryTab), `stats_refreshed`/`reset_done` (StatsPanel), `session_finished` (LearningDialog) — geplante Cross-Tab-Navigation/Refreshes fehlen durchgängig.
- **WIRE-006 — `_ProgressRelay` toter Code** im ModelManagerDialog; **WIRE-007 — `PrimaryActionBar` nie instanziert**; **WIRE-013 — OnboardingBanner.dismissed** ohne Empfänger (harmlos); **WIRE-014 — `job_skipped`** des EmbeddingSchedulers ohne UI-Slot.
- **PIPE-013 — Media-Panel-Re-Analyse ruft `VideoAnalysisPipelineWorker(video_id)` mit kaputtem Konstruktor** ([ui/workspaces/media_workspace.py:1575](ui/workspaces/media_workspace.py:1575)): funktioniert nur über FileNotFoundError→TOCTOU-Fallback-Umweg, umgeht Proxy-First, loggt irreführende Warnungen.

**Negativ geprüft (kein Befund):** keine AttributeError-Kandidaten in 34 geprüften Connect-Targets; Signal-Chaining korrekt; Thread-Disziplin sauber (Worker-Referenzen gehalten, Qt.QueuedConnection-Disziplin, kein GC-Capture-Bug); alle übrigen ~30 Buttons cross-file verdrahtet; Timeline-Transport komplett verbunden.

---

## F. Toter Code (Löschkandidaten — Entscheidung beim User)

| ID | Modul(e) | Zeilen | Kategorie |
|---|---|---|---|
| DEAD-001 | `services/pacing/` 16 Module (Pacing-V2-Cluster) | ~1.400 | nur-tests/scripts (→ USE-005/006) |
| DEAD-002 | `ui/dialogs/setup_wizard.py` | 868 | nur-tests (→ WIRE-001) |
| DEAD-003..007 | Brain-V3: subtrack_detector, embedding_repository, onnx_export, visual_curves, schemas audio/video | ~1.130 | nur-tests/scripts |
| DEAD-008 | `services/video_pipeline/`: trigger_queue, coverage_guard, status_reporter, observability, disk_budget, gpu_lock_aware | 543 | nur-tests |
| DEAD-009 | `services/storage_provenance/`: project_bundle, backup_portability, disk_budget, adapter_layer | 665 | nur-tests/scripts — **Achtung: OTK-021-Branch, evtl. laufende Arbeit** |
| DEAD-010 | `services/release_readiness.py` | 279 | nur-scripts (Tooling, liegt aber unter services/) |
| DEAD-011 | audio_pipeline: cleanup, migration, vram_guard | 231 | nur-tests |
| DEAD-012 | `services/audio_pipeline/auto_save_scheduler.py` | 80 | **komplett tot** (0 Referenzen repo-weit) |
| DEAD-013 | timeline_snapshot_service + timeline_state | 152 | nur-tests (→ USE-009) |
| DEAD-014 | `services/auto_edit_worker.py` (Re-Export-Shim) | 13 | doppelt |
| WIRE-006/007, USE-016 | _ProgressRelay, PrimaryActionBar, PrepareWorkspace, LegacyAnalysisWorkspace | ~150 | nie instanziert |

Negativ: keine auskommentierten Blöcke >10 Zeilen, keine `if False:`-Blöcke, keine gesetzt-aber-nie-gelesenen Config-Flags.

---

## G. Weitere Pipeline-Lücken (mittel)

- **PIPE-012 — `_get_video_info_cached` (lru_cache) wird nach Video-Re-Analyse nicht invalidiert** → zweiter Auto-Edit in derselben Session nutzt veraltete Szenen/Motion-Werte.
- **PIPE-016 — Onset-Analyse hart auf 1800s gekappt** ([services/onset_rhythm_service.py:28](services/onset_rhythm_service.py:28)) — bei Mixen >30min fehlt die zweite Hälfte (aktuell folgenlos wegen PIPE-004, wird relevant sobald Onset-Snap verdrahtet wird).
- **PIPE-017 — Legacy-Batch reicht veraltetes BPM an Structure-Worker** (Snapshot vor Schritt 1 gelesen); `beat_positions`/`energy_per_beat`-Parameter werden nie befüllt. Nur relevant bei `audio.v2_default=false`.

---

## H. Positiv-Befunde (explizit geprüft, sauber)

- **Session-Handling:** durchgängig context-managed, NullPool-Worker-Sessions, EngineProxy-Swap gegen laufende Tasks gesperrt.
- **SQLite-Threading:** WAL + busy_timeout 120s + check_same_thread=False konsistent.
- **`analysis_status`-Race:** per Upsert gelöst (B-581).
- **Import-Duplikatschutz:** Unique-Constraints vorhanden.
- **Worker:** alle 11 Registry-Kommandos + direkte UI-Worker haben Produkt-Aufrufer (einzige Ausnahme: flag-gated Engine-Worker, USE-003).
- **agents/-System lebt** (ChatDock → LocalAgentService → Orchestrator → ~60 Actions). Einschränkung: LLM-Tool-Use exponiert nur 11 Read-only-Tools; schreibende Actions hängen an Keyword-/Fuzzy-Routing.
- **Modelle:** Demucs, beat_this, SigLIP, RAFT, Qwen-Captioning im Produktpfad verdrahtet und konsumiert (Moondream nur Fallback/Chat).
- **Qt-Thread-Disziplin:** schwere Arbeit in Workern, QueuedConnection-Disziplin, Referenz-Haltung gegen GC.

---

## I. Aufklärung der bekannten E2E-Verdachtsfälle (B-538-Lauf)

| Verdacht | Ergebnis |
|---|---|
| `waveform_data=0` | Echte Lücke: V2-Pipeline hat keine Waveform-Stage (DB-002) |
| `hotcues=0` | Totes Feature: kein Writer existiert (DB-001) |
| `timeline_entries=0` | Kein DB-Bug: Diag-Skript ruft Apply-Pfad nie auf (DB-013) |
| "Audio truncated to 1800 sec" | Hardcodiertes Limit in Onset-Analyse (PIPE-016) |

---

## Einschränkungen dieses Audits

- Rein statisch (Code-Lesung + Import-Graph + Grep-Kreuzverifikation). **Keine Laufzeit-Verifikation** — Findings mit Konfidenz "hoch" sind code-belegt, aber nicht live reproduziert. Gemäß Top-Rule gilt: nichts hiervon ist "verified" im Live-Sinn.
- DEAD-009 (storage_provenance-Teile) könnte laufende OTK-021-Arbeit sein — vor jeder Konsequenz mit User klären.
  **GESCHLOSSEN 2026-07-19 (D-073/E5-5.3):** OTK-021 hat live-evidence-pass →
  storage_provenance ist aktiv, NICHT tot. Code bleibt, DEAD-009 erledigt.
- Auftragsgemäß **keine Fixes, keine Priorisierungs-Entscheidung** — Fixplan wäre der nächste, separate Schritt nach User-Freigabe.

## Vorgeschlagene Priorisierung für einen späteren Fixplan (nur Vorschlag)

1. **P0:** PIPE-001 (Crossfade-Key, Einzeiler-Kandidat mit großem Effekt), PIPE-002/DB-002 (Classify+Waveform-Stage in V2), DB-010 (Migrations-Lücke = Crash-Kandidat auf Bestands-DBs).
2. **P1:** PIPE-006 (falsche Zusatz-Cuts), PIPE-008/PIPE-009/PIPE-015 (stille Degradierung sichtbar machen), DB-006 (V2-Status), PIPE-013.
3. **P2:** Entscheidung pro abgeschnittenem Neubau (Kapitel C): verdrahten oder löschen — das ist eine Produkt-Entscheidung des Users, kein Bugfix.
4. **P3:** Toter Code aufräumen (Kapitel F), Dead-End-Signals (Kapitel E), Index/Wachstum (DB-018).
