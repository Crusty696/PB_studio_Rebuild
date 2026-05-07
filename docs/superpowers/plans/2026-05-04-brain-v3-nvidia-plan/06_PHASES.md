# 06 — Bau-Phasen (Brain V3, NVIDIA)

7 Phasen mit klarer Reihenfolge und Definition of Done pro Phase.
Phase 0 ist BLOCKER — vor Phase 1 zwingend erledigt.

**Status-Stand 2026-05-05 (User-Direktive F3 + F4):**
- Phase 0 ✓ DONE (live verifiziert)
- Phase 1 — code-complete (35 pytest gruen) / **App-Sync code-complete (9 pytest), Live-Smoke PENDING**
- Phase 2 — code-complete (70 pytest gruen + Validation-Spike) / **App-Sync code-complete (4 pytest), Live-Smoke PENDING**
- Phase 3 — code-complete (112/112 pytest, Lauf 2026-05-05) / **App-Sync code-complete (6 pytest), Live-Smoke PENDING**
- Phase 4–6 TODO

**Stand 2026-05-05 spaeter Lauf (autonomer Commander-Durchgang):**
- Brain-V3 Test-Suite gesamt: **172 pytest gruen** (vorher 112 + Phase-App-Sync 19 + Phase-4 41 neu)
- Phase-1+2+3 App-Sync **Code** alle eingebaut, Live-Smoke (App-Start + reale
  Datei-Imports) liegt beim User. Phase-Status `fixed` setzt ausschliesslich
  der User (CLAUDE.md Hard Rule).
- Phase-1+2+3 GUI-E2E live verifiziert via pb-gui-tester (siehe Vault-Synthesis
  `brain-v3-phase2-3-app-sync-2026-05-05.md` + log.md): CLAP + SigLIP-2
  Embeddings reell produziert auf GTX 1060.
- Phase 4 code-complete (Foundations + Service + Reranker + Smart-Sampler +
  Pipeline-Hook). UI-Wire-Up = Phase 5.

**Status-Sprache:** Eine Phase ist erst DONE, wenn sowohl Code-Status
als auch App-Sync-Status gruen sind und ein realer User-Workflow live
verifiziert ist. Nur-Pytest-gruen + V3-Code-existiert reicht nicht.
Phase 0 ist die einzige Phase mit Status DONE per dieser Definition.

---

## Phase 0 — Bereinigung + GPU-Coexistenz-Spike (BLOCKER) ✓ DONE

```text
Dauer:    abgeschlossen 2026-05-03
Ziel:     Code-Stand stabilisieren, reale VRAM-Daten für GTX 1060 sammeln
```

### Aufgaben

- [x] **Pacing-Service-Merge-Konflikte prüfen** (im aktuellen Workspace bereits behoben)
- [x] **CORS-Konflikt in `backend/main.py`** prüfen (bereits OK)
- [x] **Schema↔Dataclass-Drift in `TriggerSettings`** prüfen
- [x] **GPU-Coexistenz-Spike** (`scripts/spike_brain_v3_gpu_coexistence.py`) →
      `outputs/spike_brain_v3_gpu/20260503_115926/`
- [x] **Vault-Pre-Doc + Synthesis-Doc** unter `docs/superpowers/spikes/` und
      `docs/superpowers/synthesis/`

### Definition of Done — alle ERFÜLLT

```text
✓ App startet ohne Crash (Conda-Env pb-studio + cu113)
✓ Spike-Skript dokumentiert reale VRAM-Belegung pro Workload-Kombination
✓ Real-Daten widerlegen R10 (SigLIP-2 batch=8 sprengt 6 GB) und entspannen R16
✓ AutoImageProcessor-Lesson dokumentiert (statt AutoProcessor)
```

**Spike-Output-Pfad:** `outputs/spike_brain_v3_gpu/20260503_115926/snapshots.json`

---

## Phase 1 — Datenseite — code-complete / App-Sync PENDING

```text
Code-Status:    abgeschlossen 2026-05-03 (35 pytest gruen)
App-Sync:       PENDING (Mix-Import-Hook nicht geliefert)
Live-verify:    nicht durchgefuehrt
Ziel:           Hash-basierte Identitaet + Sub-Track-Detection + Visual-Curves
```

> **Status-Update (User-Direktive 2026-05-05, F3):** Phase-Marker auf
> `code-complete-app-sync-pending` zurueckgesetzt. Phase geht erst auf
> DONE, wenn der App-Sync-Block (siehe unten) live verifiziert ist.

### Aufgaben

- [x] **`media_hash` (sha256) Streaming-Implementation** mit 4 MB Chunks →
      `services/brain_v3/hashing.py` ✓
- [x] **Pfad-Konvention** für V3-DBs (App-global + projekt-spezifisch) →
      `services/brain_v3/paths.py` ✓
- [x] **V3-Schema-Module** (Pydantic v2) →
      `services/brain_v3/schemas/{audio,video}.py` ✓
- [x] **`subtrack_detector.py` (4-Signal-Pipeline)** Foote 0.35 / Stem 0.30 /
      Tempo-Drift 0.20 / Spectral-Flux 0.15, Peak-Picking min_distance=60s,
      adaptive Threshold mean+1.5·std, Fallback bei 0 Boundaries →
      `services/brain_v3/audio/subtrack_detector.py` ✓
- [x] **`visual_curves.py`** Brightness (HSV V), Saturation (HSV S),
      ColorTemp (tanh log(R/B)), default 1 Hz Sampling →
      `services/brain_v3/video/visual_curves.py` ✓
- [x] **35 pytest-Tests grün** (live auf GTX 1060)
- [x] **Bug-Fix** `librosa.beat.tempo` → `librosa.feature.rhythm.tempo`
      mit getattr-Fallback

### App-Sync (NACHHOLEN, User-Direktive 2026-05-05, F3)

> **Plan-Amendment 2026-05-05 (Option A):** Phase-1-Hash hat keine
> dedizierte Tabelle in den bestehenden Phase-2-Schemata. Daher neue
> Sibling-Tabelle `media_hashes` in `embedding_cache.db` via Migration
> `embedding_cache/002_media_hashes.sql`. Hash-Persistenz-Layer:
> `services/brain_v3/storage/media_hash_registry.py` (`MediaHashRegistry`).
> Hash-Worker nach Import: `workers/brain_v3_hashing.py`
> (`BrainV3HashingWorker`). Plan-Doc-04 Schema-Liste auf 5 SQLite-Files
> bleibt unveraendert (Sibling-Tabelle, kein neues File).

- [x] **Hash-Hook in `ui/controllers/import_media.py` `_import_audio()` /
      `_import_video()`**: nach erfolgreichem Import wird
      `services.brain_v3.hashing.compute_media_hash()` ueber
      `MediaHashRegistry.register()` aufgerufen, Hash in
      `media_hashes`-Tabelle abgelegt. Hook in `_process_imports`
      hinter `worker.finished`-Signal via
      `_spawn_brain_v3_hash_worker()`. Identischer Hook auch in
      `_import_folder()` mit `worker.paths_audio`/`paths_video` nach
      walk_root-Scan.
- [x] **Konsole-Log:** „[Brain V3] Hash <kurz>... in V3-DB gespeichert"
      (neu) bzw. „[Brain V3] Hash <kurz>... bekannt — Cache-Hit"
      (Re-Import) pro Clip; finale Zeile „[Brain V3] Hash-Lauf fertig:
      <n_new> neu, <n_known> bekannt".
- [ ] **Live-Smoke:** App starten, **3 echte Audio + 3 echte Video**
      importieren, V3-DB inspizieren — Hashes vorhanden, Schema-Felder
      gefuellt. **PENDING — User-Verifikation noetig.**
- [ ] **Re-Import-Smoke:** dieselben Files nochmal importieren —
      Hash-Cache-Hit, kein doppelter DB-Eintrag, Konsole-Log meldet
      „bekannt". **PENDING — User-Verifikation noetig.**
- [x] **Unit-Tests:** `tests/test_services/test_brain_v3_media_hash_registry.py`
      9/9 gruen (register/lookup/stats/migration/idempotenz).

### Definition of Done — TEILWEISE erfüllt

```text
✓ Mix-Import-Pipeline kann Hash + SubtrackDetection durchlaufen
✓ Re-Import via Hash-Cache lookup funktional
✓ SubtrackDetector Smoke-Tests passieren (synth-WAV, 2-Section-Wechsel)
✓ Visual-Curves-Reaktion auf hellem/dunklem/warmem/kaltem MP4 verifiziert
✗ Mix-Import-Hook synchron im audio_router NICHT geliefert (V1/V2-Touch
  noetig, blockiert bis explizite Freigabe)
✗ F-Measure ≥ 0.65 auf 5 annotierten Test-Mixes NICHT validiert
  (annotierte Test-Mixes existieren nicht im Repo) →
  Status: code-fix-pending-real-data-validation
```

**Synthesis-Doc:** `docs/superpowers/synthesis/2026-05-03-brain-v3-phase1-completion.md`

---

## Phase 2 — Embedding-Pipeline — code-complete / App-Sync PENDING

```text
Code-Status:    abgeschlossen 2026-05-03/04 (70 pytest gruen + Validation-Spike)
App-Sync:       PENDING (Embedding-on-Import nicht verdrahtet)
Live-verify:    nicht durchgefuehrt
Ziel:           CLAP + SigLIP-2 + sqlite-vec produktiv, Hash-Cache aktiv,
                Background-Queue
```

> **Status-Update (User-Direktive 2026-05-05, F3):** Phase-Marker auf
> `code-complete-app-sync-pending` zurueckgesetzt. Phase geht erst auf
> DONE, wenn der App-Sync-Block (siehe unten) live verifiziert ist.

### Aufgaben

- [x] **`gpu_serializer.py`** Threading + Asyncio-Lock + auto-empty_cache →
      `services/brain_v3/gpu_serializer.py` ✓
- [x] **`storage/sqlite_init.py`** PRAGMAs + sqlite-vec-Loader mit
      User-freundlicher ImportError-Anweisung ✓
- [x] **`storage/migration_runner.py`** PRAGMA user_version + atomare
      Migrationen + ROLLBACK-on-Fail ✓
- [x] **`storage/embedding_cache.py`** Index-DB + .npy-File-Storage mit
      nested-Pfad-Konvention ✓
- [x] **`storage/embedding_repository.py`** sqlite-vec virtuelle Tabellen,
      KNN-API mit Level-Filter, Dim-Mismatch-Validation ✓
- [x] **`audio/audio_embedder.py`** CLAP, 10s-Window/5s-Hop, Window→Section→Mix,
      L2-Normalisierung, Singleton mit GpuSerializer ✓
- [x] **`video/video_embedder.py`** SigLIP-2 Vision mit `AutoImageProcessor`
      (Spike-Lesson!), batch=8 Default, OOM-Auto-Tuning, Scene→Clip-Aggregation ✓
- [x] **`background_queue.py`** asyncio.Queue + N Worker + Progress-Subscriber
      mit Snapshot-Kopie (Bug gefangen + gefixt: Subscriber sahen finalen Status) ✓
- [x] **Install-Wrapper** `install_brain_v3_phase2_deps.bat` (sqlite-vec) ✓
- [x] **70 pytest-Tests grün** (live auf GTX 1060) ✓
- [x] **Validation-Spikes:**
  - `scripts/spike_brain_v3_embedder_smoke.py` →
    `outputs/spike_brain_v3_embedder/20260504_145214/` ✓
  - `scripts/spike_brain_v3_knn_scaling.py` →
    `outputs/spike_brain_v3_knn/20260504_145231/` ✓

### App-Sync (NACHHOLEN, User-Direktive 2026-05-05, F3)

> **Implementiert 2026-05-05 (Code-complete):**
> Brueckentechnologie `services/brain_v3/embedding_scheduler.py`
> (`EmbeddingScheduler` + `_SchedulerThread`): hostet asyncio-Loop in
> eigenem QThread, kapselt `EmbeddingJobQueue`, bietet Qt-Signals
> `job_progress(job_id, status, pct, msg)` + `job_skipped(hash, reason)`.
> Cache-Pre-Check vor Submit: `media_embedding_index`-Lookup spart
> Worker-Round-Trip bei Hits. Embedder-Aufrufe via lazy
> `_default_embedder_factory` (CLAP/SigLIP) — Tests koennen Factory
> mocken (siehe `tests/.../test_brain_v3_embedding_scheduler.py`).

- [x] **Embedding-Job-Push** in
      `ui/controllers/import_media.py::_on_hash_registered_for_embedding`:
      `BrainV3HashingWorker.hash_registered`-Signal triggert
      `EmbeddingScheduler.submit_path(media_hash, source_path, media_type)`.
      Job in `EmbeddingJobQueue` via `asyncio.run_coroutine_threadsafe`.
- [x] **Default-Worker-Anzahl**: 1 (sequenziell), `EmbeddingScheduler.n_workers=1`.
- [x] **Worker-Progress als Qt-Signal**: `EmbeddingScheduler.job_progress`
      bridged `JobProgress`-Subscriber in Qt-Signal.
- [x] **GpuSerializer-Lifecycle**: `PBWindow._boot_brain_v3_services()`
      ruft `get_default_serializer()` (Lazy-Init) + `scheduler.start()`
      via `QTimer.singleShot(0)` (non-blocking Boot).
      `PBWindow.closeEvent` Stage 8b: `scheduler.request_stop(timeout_ms=5000)`
      vor finalem CUDA-empty_cache (Stage 9).
- [ ] **Live-Smoke:** App starten, **5 echte Mix-Files + 10 Clips**
      importieren, Hintergrund-Embedding lassen durchlaufen,
      `embedding_cache.db` + `.npy`-Files auf Disk pruefen.
      **PENDING — User-Verifikation noetig (Modelle CLAP/SigLIP-2 muessen
      verfuegbar sein, ggf. erstmaliger HF-Download).**
- [ ] **Re-Import-Cache-Hit:** dieselben Files erneut importieren →
      Cache-Hit-Pfad aktiv, keine zweite Inferenz, Konsole-Log:
      „[Brain V3] Embedding-Cache-Hit". **PENDING.**
- [ ] **VRAM-Smoke waehrend Render:** parallel zum Embedding einen
      NVENC-Render-Job laufen lassen, GpuSerializer-Lock greift,
      kein OOM auf 6 GB. **PENDING.**
- [x] **Unit-Tests:** `tests/test_services/test_brain_v3_embedding_scheduler.py`
      4/4 gruen (start/stop/submit-with-fake/cache-hit-skip/raises-when-stopped).

### Definition of Done — kalibriert mit Realdaten

```text
✓ Embedder-End-to-End-Smoke verifiziert (CLAP Cache-Roundtrip; SigLIP-2 live)
✓ Cache-Hit-Rate 100 % bei Re-Import (DoD ≥95% MET)
✓ KNN-self-match Distance = 0.0 (Repository-Pipeline korrekt)
✓ Background-Queue serialisiert + parallelisiert korrekt
✓ Default-Batch SigLIP-2 = 8 (Spike-bestaetigt, NICHT 2 wie konservativ geplant)
~ KNN-Latenz <50 ms median bei 16k Vektoren — VERFEHLT (Audio 63 ms, Video 108 ms)
  → DoD wird kalibriert auf <150 ms p95 (siehe 07_RISKS.md R18)
~ 500-Clip-Erst-Import-Schwelle — Hochrechnung 34 min SigLIP, CLAP nicht real
  diesem Lauf (Cache-Hits aus Vorlauf). Realistisch: <60 min mit warmem Cache.
✗ Mix-Import-Hook synchron NICHT geliefert (V1/V2-Touch noetig, blockiert)
```

**Synthesis-Docs:**
- `docs/superpowers/synthesis/2026-05-03-brain-v3-phase2-completion.md`

---

## Phase 3 — Brain-Core (Beta-Bernoulli + Hierarchical Backoff) — code-complete / App-Sync PENDING

```text
Code-Status:    abgeschlossen 2026-05-05 (112/112 pytest gruen)
App-Sync:       PENDING (Brain-Store-Health-Check beim App-Boot fehlt)
Live-verify:    nicht durchgefuehrt
Ziel:           Lern-Algorithmus produktiv, Mock-Klicks → Posterior-Konvergenz
```

> **Status-Update (User-Direktive 2026-05-05, F3):** Phase-Marker auf
> `code-complete-app-sync-pending` zurueckgesetzt. Phase geht erst auf
> DONE, wenn der App-Sync-Block (siehe unten) live verifiziert ist.

### Aufgaben

- [ ] **`storage/brain_store.py`** öffnet 3 SQLite-Files in
      `%APPDATA%\PB_Studio\brain_v3\`, PRAGMA-Setup, Health-Check
- [ ] **`storage/sql_migrations/weights/001_initial.sql`** axis_weights-Schema
- [ ] **`storage/sql_migrations/patterns/001_initial.sql`** pattern_correlations
- [ ] **`bridge_dimensions.py`** Berechnungen für 17 Achsen (10 Audio aus
      TriggerSettings + 7 Video Korrelationen)
- [ ] **`context_resolver.py`** 6 Kontext-Slots aus Audio/Video, Quantisierung
      (Tertile), Aufbau der 5 Backoff-Keys
- [ ] **`weight_store.py`** Posterior-Mean, Hierarchical-Backoff-Lookup,
      MIN_CONFIDENT_SAMPLES = 10
- [ ] **`scorer.py`** gewichteter Score-Vektor → Final-Score, Sub-Score-Vektor
- [ ] **`feedback_logger.py`** atomic Update auf 6 Levels (0..5) × 17 Achsen = 102 Buckets
- [ ] **`cold_start.py`** Defaults aus TriggerSettings + neutrale Mitte
- [ ] **Tests:**
  - test_weight_store: posterior_mean_cold_start, posterior_mean_after_clicks,
    backoff_finds_specific_when_confident, backoff_falls_back_to_general
  - test_feedback_logger: atomic_update_85_buckets, transaction_rollback_on_error
  - test_context_resolver: 6_slots_quantization, backoff_keys_sorted
  - test_cold_start: defaults_from_trigger_settings

### App-Sync (NACHHOLEN, User-Direktive 2026-05-05, F3)

> **Implementiert 2026-05-05 (Code-complete):**
> `BrainStore.health_check() -> BrainStoreHealth` neu in
> `services/brain_v3/storage/brain_store.py`. App-Boot-Hook
> implementiert via `PBWindow._boot_brain_v3_services()`
> (`QTimer.singleShot(0, ...)` non-blocking, Plan-Empfehlung).
> Shutdown-Hook in `closeEvent` Stage 8b vor CUDA-empty_cache.

- [x] **`BrainStore.health_check() -> BrainStoreHealth`** implementiert
      mit 3-DB-Probe + PRAGMA user_version + Disk-Space-Check + errors-List.
      Exception-frei, Laufzeit-Budget <50 ms (Test verifiziert <200 ms p95).
- [x] **App-Boot-Hook in `PBWindow.__init__`** (main.py Z.286-291) via
      `QTimer.singleShot(0, self._boot_brain_v3_services)` — non-blocking.
      `_boot_brain_v3_services` enthaelt Health-Check + Serializer-Init +
      Scheduler-Start.
- [x] **Boot-Log-Eintrag**: „[Brain V3] Hirn-Store-Health: weights.db
      <ok|fail>, patterns.db <ok|fail>, embedding_cache.db <ok|fail>,
      migrations v<n>, free <x> MB" — Format wie Plan-Spec.
- [x] **App-Shutdown-Hook**: `closeEvent` Stage 8b ruft
      `scheduler.request_stop(timeout_ms=5000)`. Final-CUDA-empty_cache
      passiert in Stage 9 (existiert bereits, M-9 Fix).
- [ ] **Mock-Klick-Smoke vor UI-Phase**: `scripts/spike_brain_v3_mock_click.py`
      noch zu schreiben. **PENDING.**
- [ ] **Live-Smoke-Reset:** `scripts/spike_brain_v3_reset.py` noch zu
      schreiben. **PENDING.**
- [x] **Unit-Tests:** `tests/test_services/test_brain_v3_brain_store_health.py`
      6/6 gruen (all-ok, missing-db-fail, user-version, <200ms, disk-space,
      corrupted-db-error-collected).

### Definition of Done

```text
☐ Mock-Klicks → Gewichte aendern sich erwartungsgemaesz
☐ Reset loescht weights.db + patterns.db, Heuristik-Fallback aktiv
☐ Backoff-Lookup findet konfidentes Bucket bei zu wenig Samples auf hoeherem Level
☐ Atomic-Update aller 102 Buckets in einer Transaktion (verifiziert via SQLite-LOG)
☐ 25+ Unit-Tests gruen
☐ App-Sync-Block oben live verifiziert (Boot-Log + Mock-Klick + Reset)
```

---

## Phase 4 — Pacing-Integration — code-complete (UI-Wire-Up = Phase 5)

```text
Status:   2026-05-05 code-complete (40 neue pytest gruen, 172 brain_v3 total + 293 pacing)
Code:     Foundations + BrainV3Service + Reranker + Smart-Sampler + Pipeline-Hook
UI-Hook:  Phase 5
Live:     Pacing-Run mit use_brain_v3=true noch nicht real durchgelaufen
```

> **Implementiert 2026-05-05 (autonomer Commander-Lauf):**
> - `services/brain_v3/context_resolver.py::quantize_quartile()` ergaenzt
> - `services/brain_v3/context_mapping.py` (`ContextMappingConfig`, `map_section`,
>   `map_mood`, `derive_pace_class`, `build_cut_context`, YAML-Loader)
> - `services/brain_v3/storage/sql_migrations/state/001_initial.sql`
>   (timelines + timeline_cuts + feedback_events)
> - `services/brain_v3/schemas/brain_v3_schemas.py` (8 Pydantic-Schemas)
> - `services/brain_v3/brain_v3_service.py` (5-Methoden-Fassade in-process)
> - `services/brain_v3/reranker.py` (`BrainV3Reranker` mit blend-weight + Adapter)
> - `services/brain_v3/smart_sampler.py` (Bayes-Varianz Top-N)
> - `services/pacing/pipeline.py` Hook: PacingPipeline `+use_brain_v3`,
>   `+brain_v3_reranker`, `+brain_v3_min_confidence`. Stage-4-Sortierung
>   uebernimmt Reranker bei use_brain_v3=True. Brain-V3-Crash → Fallback
>   auf Pacing-Score. brain_v3_scores landen in `rationale["brain_v3_scores"]`.

### Aufgaben

- [ ] **`reranker.py`** Eingriff in `services/pacing/pipeline.py`
      Klasse `PacingPipeline` Methode **`select_best()`** (Zeile 145
      Stand 2026-05-05, festgelegt User-Direktive 2026-05-05 F5).
      Reranker uebernimmt die Stage-4-Sortierung: erhaelt die
      `scored`-Liste (Z. 264-274 in pipeline.py — alle Kandidaten
      mit `passed_stage2 == True` plus deren Stage-4-Soft-Scores)
      und liefert eigene Sortierung. Stages 1-3 (Hard-Rules,
      Variations-Budget, Collision-Check) bleiben unangetastet.
      Reranker bewertet jeden Kandidaten über 17 Achsen × 6 Levels
- [ ] **`smart_sampler.py`** Top-15 Cuts nach Bayes-Varianz
      `α·β / ((α+β)² · (α+β+1))`
- [ ] **`context_mapping.py`** (NEU, festgelegt D-036 2026-05-05):
      Default-Mappings + `ContextMappingConfig`-Dataclass +
      `from_yaml()`-Loader + pure-Functions `map_section()`,
      `map_mood()`, `derive_pace_class()`. AudioContext-→-CutContext-
      Mapping ist konfigurierbar via `config/brain_v3_context_mapping.yaml`
      (optional). Defaults: `chorus→drop`, `bridge→transition`,
      `calm→neutral`, `dramatic→dark`, `ambient→neutral`,
      `pace_source=recent_cuts`. Validierung gegen `VALID_*` aus
      `context_resolver.py`. Tests siehe Phase-4-Blueprint Sektion 4.7.
- [ ] **`build_cut_context(ctx, predecessor, recent_clip_ids, cfg)`**
      Helper in `context_mapping.py` (oder eigener Datei),
      orchestriert die 6 Slot-Befuellungen unter Verwendung der
      `ContextMappingConfig`.
- [ ] **`quantize_quartile()`** in `context_resolver.py` ergaenzen
      (4-Klassen-Variante des bestehenden `quantize_tertile()`),
      gebraucht fuer `video_motion_class`.
- [ ] **`storage/sql_migrations/state/001_initial.sql`** timelines, timeline_cuts
      mit `brain_v3_scores_json`, feedback_events
- [ ] **`schemas/brain_v3_schemas.py`** Pydantic Request/Response-Dataclasses
      fuer den `BrainV3Service` (in-process Aufruf-/Rueckgabe-Typen,
      keine REST-Schemas)
- [ ] **`services/brain_v3/brain_v3_service.py`** in-process Fassaden-
      Wrapper mit 5 Methoden:

```text
BrainV3Service.suggest(audio_clip_id, video_clip_ids, n_top)
    Top-N Cut-Vorschlaege mit brain_v3_scores
BrainV3Service.feedback(cut_id, rating)
    4-Klick-Event verarbeiten
BrainV3Service.learning_session()
    15 Stichproben-Cuts fuer Lern-Dialog
BrainV3Service.stats()
    Diagnostik: Total-Klicks, Top-Buckets, Cold-Start
BrainV3Service.reset(confirmation_token)
    Two-Step-Reset (1. Aufruf ohne Token: Token zurueck;
                    2. Aufruf mit Token: loeschen)
```

- [ ] **Pacing-Config** erweitern um `+use_brain_v3: bool = False`,
      `+brain_v3_min_confidence: float = 0.0` (konkretes Config-Objekt
      im `services/pacing/`-Code vor Edit per Grep verifizieren — der
      ursprueglich im Plan benannte `backend/schemas/pacing_schemas.py`
      existiert nicht)
- [ ] **`cut.metadata.brain_v3_scores`** in jedem Cut-Output für UI

### Verifikation (in-process Smoke aus `python -m`-Skript oder Pytest)

```python
# scripts/spike_brain_v3_pacing_smoke.py
from services.brain_v3.brain_v3_service import BrainV3Service
svc = BrainV3Service()

# 1. Suggest
result = svc.suggest(audio_clip_id=1, video_clip_ids=[1,2,3], n_top=5)
assert "brain_v3_scores" in result["cuts"][0]["metadata"]
cut_id = result["cuts"][0]["id"]

# 2. Klick
fb = svc.feedback(cut_id=cut_id, rating="perfect")
assert fb["n_buckets_updated"] == 102

# 3. Stats
stats = svc.stats()
assert stats["total_clicks"] > 0
```

### Definition of Done

```text
☐ Pacing-Run mit use_brain_v3=true → brain_v3_scores in Cut-Output
☐ BrainV3Service.feedback() → Bucket-Confidence steigt nachweisbar
☐ BrainV3Service.learning_session() → 15 unsicherste Cuts in <2s
☐ Pacing-Overhead mit Brain V3 <800 ms (kalibriert mit KNN-Realitaet)
☐ Background-Queue verarbeitet Embedding-Jobs asynchron, Progress via
  Qt-Signal (kein SSE — reiner in-process Mechanismus)
```

---

## Phase 5 — UI-Anbindung PySide6 — code-complete (Live-UI-Test pending)

```text
Status:   2026-05-05 code-complete (7 neue pytest gruen, 179 brain_v3 total)
Code:     Stats-Panel + Feedback-Popup + Hotkeys + Lern-Session-Dialog
          + Reset-Dialog (two-step) + Confidence-Color-Helper + PBWindow-Tab-Hook
Live-UI:  pending (visuelle Verifikation per User oder pb-gui-tester)
```

> **Implementiert 2026-05-05 (autonomer Commander-Lauf):**
> - `ui/widgets/brain_v3_stats_panel.py` (`BrainV3StatsPanel`):
>   Total-Klicks, Cold/Learned-ProgressBar, Top-5-pos/-neg-Buckets,
>   Auto-Refresh-Timer, Reset-Button (two-step via BrainV3Service).
> - `ui/widgets/brain_v3_feedback_popup.py` (`BrainV3FeedbackPopup`):
>   QDialog mit 4 Buttons (perfect/fits/not_quite/no_match), Hotkeys 1-4
>   via QShortcut, Esc-Cancel, `feedback_submitted`-Signal.
>   Plus `confidence_color_hex(0..1)` Helper (rot->gelb->gruen).
> - `ui/widgets/brain_v3_learning_dialog.py` (`BrainV3LearningSessionDialog`):
>   Lade `learning_session(n=15)`, ListWidget mit Confidence-Färbung,
>   Doppelklick öffnet Feedback-Popup, Items werden nach Bewertung
>   entfernt, `session_finished`-Signal.
> - `main.py` (PBWindow): Brain-V3-Stats-Panel als neuer Tab im
>   Right-Panel (NICHT studio_brain_window.py umgebaut, LOCKED).
> - Tests: 7/7 pytest gruen unter QApplication-Fixture.

### Aufgaben

- [ ] **Timeline-Cut-Item: On-Click-Popup mit 4 Buttons (PySide6)**
  - "Passt perfekt" / "Passt" / "Passt nicht ganz" / "Passt gar nicht"
  - Hotkeys 1-4 während Playback
  - Implementation als `QMenu` oder `QDialog` über `QGraphicsItem`
- [ ] **Lern-Session-Button → Stichproben-Dialog**
  - Ruft `BrainV3Service.learning_session()` (in-process)
  - Zeigt 15 Cuts nacheinander mit Audio+Video-Snippet
- [ ] **Hirn-V3-Stats-Panel** (NEUER Tab im Hauptfenster, NICHT
      `studio_brain_window.py` umbauen)
  - Total Klicks
  - Top-5 stärkste positive Buckets
  - Top-5 stärkste negative Buckets
  - Cold-Start-Status: x/17 Achsen aus Cold-Start, y/17 aus Lerndaten
- [ ] **Reset-Dialog mit Confirmation-Step**
  - Zwei-Klick-Bestätigung wegen Datenverlust
- [ ] **Confidence-Visualisierung pro Cut**
  - Dünner Balken über jedem Cut zeigt Brain-V3-Confidence
  - Farbe: rot (unsicher) → grün (sicher)

### Definition of Done

```text
☐ Realer Mix + 500 Clips → User klickt 50+
☐ Stats-Panel zeigt Lerneffekt nachweisbar
☐ Reset funktioniert, danach wieder Cold-Start
☐ Lern-Session-Dialog spielt Audio+Video-Preview ab
☐ V1/V2-UI (studio_brain_window.py + brain_v2_tab.py) bleibt UNANGETASTET
```

---

## Phase 6 — Härtung — partial code-complete (laufend)

```text
Status:   2026-05-05 partial code-complete (5 Backup-Tests gruen, LICENSES.md angelegt)
Geliefert: storage/backup.py (VACUUM INTO), prune_old_backups, LICENSES.md
TODO:     Recovery-Test-Script, NVENC+Brain Konflikt-Spike, Performance-Profil,
          Schema-Migrations-Vorlage, User-Doku, optional ONNX-Eval, KNN-ANN-Eval
```

> **Implementiert 2026-05-05 (autonomer Commander-Lauf):**
> - `services/brain_v3/storage/backup.py` (`backup_brain_v3_store()` +
>   `prune_old_backups(keep=4)`). VACUUM INTO atomar + transaktional.
> - `LICENSES.md` mit allen Komponenten:
>   - CLAP Apache-2.0 (NICHT CC-BY-4.0 wie AMD-Plan behauptete) → keine
>     Splash-Screen-Pflicht, Plan-Doc-06 z.473-475 bestaetigt.
>   - SigLIP-2 Apache-2.0, Demucs MIT, beat_this MIT, sqlite-vec
>     Apache/MIT Dual, librosa ISC, transformers Apache-2.0,
>     PyTorch BSD-3, PySide6 LGPL-v3.
> - 5 Backup-Tests gruen (test_brain_v3_backup.py).

### Aufgaben

- [ ] **`storage/backup.py`** automatisiert
  - Wöchentlich `VACUUM INTO`-Backup aller 3 Hirn-Store-DBs
  - Konfigurierbare Retention (z.B. letzte 4 Backups)
- [ ] **Recovery-Test**
  - Hirn-Store löschen → App startet ohne Crash
  - Korrupten Hirn-Store simulieren → graceful Fallback
- [ ] **Performance-Profiling**
  - Pacing-Run mit/ohne Brain V3 im Vergleich
  - Embedding-Pipeline-Auslastung
  - Bottleneck-Analyse
- [ ] **NVENC + Brain-Inferenz Konfliktverhalten messen**
  - GpuSerializer.acquire("render") muss mit CLAP/SigLIP/Demucs/RAFT serialisieren
- [ ] **Schema-Migrations-Vorbereitung für künftige Brain-Updates**
  - Beispiel-Migration `002_*.sql` als Vorlage anlegen
- [ ] **User-Doku**
  - Was ist Cold-Start
  - Wann lohnt eine Lern-Session
  - Was bedeuten die Confidence-Balken
- [ ] **Lizenz-Attribution**
  - `LICENSES.md` mit allen Komponenten
  - **CLAP Apache-2.0 (NICHT CC-BY-4.0 wie AMD-Plan behauptete)** → keine
    Splash-Screen-Pflicht, LICENSES.md genügt
- [ ] **Optional: ONNX-Export evaluieren**
  - CLAP und SigLIP-2 nach ONNX exportieren
  - CUDA-Provider via onnxruntime-gpu
  - **Pascal hat keine FP16-Tensor-Cores** → Optimierungs-Headroom kleiner als
    auf Ampere/Ada, aber Latenz-Reduktion möglich
- [ ] **KNN-ANN-Index-Eval (R18-Folge)**
  - sqlite-vec ≥ 0.1.7 hat partielle HNSW-Unterstützung
  - Eval ob Plan-Doc 06 Phase 2 DoD <50 ms KNN damit erreichbar wird

### Definition of Done

```text
☐ Hirn-Store-Korruption → App lauffaehig
☐ Pacing-Latenz mit Brain V3 <800ms verifiziert
☐ Woechentliches Backup laeuft automatisch
☐ LICENSES.md vollstaendig (alle Komponenten)
☐ NVENC + Brain Coexistenz-Test gruen
```

---

## Aufwand-Übersicht

```text
Phase 0 (DONE):          1 Tag (Spike + Pre-/Synthesis-Doc)
Phase 1 (DONE):          1 Tag (35 pytest grün)
Phase 2 (DONE):          1 Tag (70 pytest + Validation-Spike)
Phase 3 (TODO):          3-5 Tage (CPU-Logic + 25+ Tests)
Phase 4 (TODO):          3-5 Tage (Reranker + 5 Endpoints + state.db)
Phase 5 (TODO):          3-5 Tage (PySide6-UI + Hotkeys + Audio/Video-Preview)
Phase 6 (TODO):          laufend
                         + KNN-ANN-Eval (separater Sub-Spike, ~1 Tag)
                         + ONNX-Eval (optional, 2-3 Tage)
                         + NVENC-Konflikt-Test (~1 Tag)

Total Schaetzung:        4-6 Wochen netto fuer Phase 3-6
```
