# Full Codebase Audit Report — PB Studio Rebuild v0.5.0

**Date:** 2026-04-10 | **Auditor:** SeniorAuditSpecialist | **Branch:** feature/phase6-sprint1

---

## Executive Summary

PB Studio is a DaVinci Resolve-style video/audio production application built with PySide6, SQLAlchemy (SQLite), and a local Ollama-based AI pipeline. The codebase spans ~60+ Python modules across 6 subsystems. This audit examined every module for correctness bugs, security vulnerabilities, resource leaks, thread safety issues, and architectural concerns.

**Overall Assessment:** The codebase is well-structured with clear separation of concerns (controllers, services, workers, database). Error handling is generally solid with a custom exception hierarchy and Result pattern. However, there are several **CRITICAL** and **HIGH** severity findings that should be addressed before production deployment.

### Finding Summary

| Severity | Count | Categories |
|----------|-------|------------|
| CRITICAL | 7 | Thread safety, resource leaks, data corruption, CUDA crash, deadlock, cross-thread UI |
| HIGH | 41 | Logic bugs, race conditions, incorrect API usage, audio drops, stale data, deps, UI freezes |
| MEDIUM | 64 | Code quality, minor bugs, missing validation, thread safety, DB design, UI jank, HTML injection |
| LOW | 40 | Style, documentation, minor improvements |

---

## CRITICAL Findings

### C-1: RLock.release() Loop is Incorrect (task_manager.py:417-429)

**File:** `services/task_manager.py:417-429`

```python
try:
    while GPU_LOAD_LOCK.release(): pass
except RuntimeError: pass
try:
    while GPU_EXECUTION_LOCK.release(): pass
except RuntimeError: pass
```

**Issue:** `threading.RLock.release()` returns `None`, not a boolean. This means `while None: pass` exits immediately — the loop never actually releases the lock more than once. The intent was to release all nested acquisitions, but this is a no-op. After `thread.terminate()`, if the terminated thread held these RLocks, they remain locked forever, causing **deadlocks** for all subsequent GPU operations.

**Impact:** GPU operations can permanently deadlock after a task is force-terminated. Users must restart the app.

**Fix:** Use a counter-based release or switch to a custom lock wrapper that tracks acquisition depth.

---

### C-2: closeEvent Executes Code After event.accept() (main.py:412-419)

**File:** `main.py:412-419`

```python
event.accept()  # Line 412

# 7. Close DB connection pool  — runs AFTER accept!
try:
    from database import engine
    engine.dispose()
except (ImportError, RuntimeError, OSError) as exc:
    ...

super().closeEvent(event)  # Line 420
```

**Issue:** After `event.accept()`, Qt considers the close event handled and may begin window destruction. The DB pool dispose on lines 416-419 runs in an undefined state. Additionally, `super().closeEvent(event)` is called after `event.accept()`, which is redundant and may cause double-processing.

**Impact:** Potential crash during app shutdown; DB connections may not be properly cleaned up.

**Fix:** Move `engine.dispose()` before `event.accept()`. Remove the redundant `super().closeEvent(event)` call.

---

### C-3: JSON Double-Parse on SQLAlchemy JSON Columns (ingest_service.py:175)

**File:** `services/ingest_service.py:175`

```python
beat_count = len(_json.loads(track.beatgrid.beat_positions))
```

**Issue:** `beat_positions` is declared as `Column(JSON)` in `database/models.py:150`, which means SQLAlchemy automatically deserializes JSON. Calling `json.loads()` on an already-deserialized list raises `TypeError: the JSON object must be str, bytes or bytearray, not list`. The `except` clause catches this, but it means **beat_count is always None** for valid data, hiding a permanent logic bug.

**Impact:** Beat count is never displayed correctly in the MEDIA workspace detail cards.

**Fix:** Remove the `json.loads()` wrapper — access `track.beatgrid.beat_positions` directly as a list.

---

### C-4: Thread-Local Variables May Be GC'd (main.py:656-683)

**File:** `main.py:665-676`

```python
def final_init():
    check_worker = StartupCheckWorker()
    check_thread = QThread(window)
    check_worker.moveToThread(check_thread)
    ...
    check_thread.start()
```

**Issue:** `check_worker` is a local variable with no strong reference kept after `final_init()` returns. Although `check_thread` has `window` as parent (preventing its GC), the worker has no parent and can be garbage collected while the thread is still running. This causes a crash or silent failure of the startup check.

**Impact:** Intermittent crash or silent startup check failure.

**Fix:** Store `check_worker` as `self._startup_worker` on the window object to prevent GC.

---

## HIGH Findings

### H-1: Update Banner Lambda Accumulates Connections (main.py:307-309)

**File:** `main.py:307-309`

```python
self._update_banner_link.clicked.connect(
    lambda: __import__("webbrowser").open(download_url)
)
```

**Issue:** If `_on_update_available` is called multiple times (e.g., periodic version checks), each call adds another `clicked.connect()`. This creates accumulating lambda connections — clicking the button opens the URL N times.

**Fix:** Disconnect before connecting, or use a flag to only connect once.

---

### H-2: EngineProxy Missing __setattr__ Override (database/session.py:34-80)

**File:** `database/session.py:34-80`

**Issue:** The `EngineProxy` class delegates `__getattr__` to the real engine, but does not override `__setattr__`. If any SQLAlchemy internal tries to set an attribute on the engine proxy, it sets it on the proxy, not the real engine. This can cause silent behavioral divergence.

**Impact:** Potential silent configuration bugs when using the engine proxy.

---

### H-3: _probe_cache Never Cleared (export_service.py:91)

**File:** `services/export_service.py:91`

```python
_probe_cache: dict[str, dict] = {}
```

**Issue:** Module-level dict that caches ffprobe results forever. If a video file is re-encoded or replaced at the same path, the cache serves stale metadata. There is no invalidation or TTL mechanism.

**Impact:** Stale video metadata may cause incorrect export rendering.

---

### H-4: get_all_audio Does Not Filter Soft-Deleted (ingest_service.py:215-245)

**File:** `services/ingest_service.py:220`

```python
tracks = session.query(AudioTrack).filter_by(project_id=project_id).limit(limit).all()
```

**Issue:** `AudioTrack` has a `deleted_at` column for soft-delete support, but `get_all_audio()` does not filter out soft-deleted records. Compare with `get_all_video()` which correctly filters `VideoClip.deleted_at.is_(None)`. This is an inconsistency.

**Impact:** Deleted audio tracks still appear in the media table.

---

### H-5: OllamaClient Chat Fallback Can Infinite Recurse (ollama_client.py:314-317)

**File:** `services/ollama_client.py:314-317`

```python
fallback = self._find_fallback_model(model)
if fallback:
    return self.chat(fallback, user_message, ...)
```

**Issue:** If the fallback model also triggers a memory layout error, `chat()` calls itself recursively with the next fallback. `_find_fallback_model` excludes failed models, but if ALL models fail, the recursion continues until the available set is empty. While it eventually terminates, deep recursion with large payloads can cause stack overflow.

**Impact:** Potential stack overflow in degraded environments.

**Fix:** Use iterative fallback loop instead of recursive calls.

---

### H-6: oom_recovery Decorator Swallows Return Value (model_manager.py:52-93)

**File:** `services/model_manager.py:52-93`

```python
def oom_recovery(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ...
                if not is_oom or attempt == max_retries - 1:
                    raise e
    return wrapper
```

**Issue:** If `is_oom` is True on the last attempt (`attempt == max_retries - 1`), the condition `not is_oom or attempt == max_retries - 1` is True, so `raise e` executes. This is actually correct upon closer inspection — the real bug is that if `is_oom` is True and `attempt < max_retries - 1`, the loop continues but if on the LAST attempt `is_oom` is True, it raises. However, the function implicitly returns `None` if the for-loop completes without the try block succeeding and without raising — which cannot happen in this code path. Downgrading: the decorator logic is correct but confusing; the `raise` after the loop should be explicit for clarity.

**Revised Impact:** Code clarity issue. Add explicit `raise` after the for-loop as a safety net.

---

### H-7: set_project Race Window (database/session.py:234-256)

**File:** `database/session.py:243-256`

```python
def set_project(project_path: Path):
    new_engine = _make_engine(db_file)  # Outside lock!
    with _APP_ROOT_LOCK:
        engine.swap(new_engine)
        APP_ROOT = project_path
        _patch_service_paths(project_path)
```

**Issue:** `_make_engine()` is called BEFORE acquiring `_APP_ROOT_LOCK`. If two threads call `set_project()` concurrently, both create new engines, but only the last one swap takes effect. The first engine is created but never disposed (resource leak).

**Impact:** Engine resource leak on concurrent project switches.

---

### H-8: delete_all_media Ignores Audio Soft-Deletes (ingest_service.py:284-374)

**File:** `services/ingest_service.py:299-303`

```python
audio_ids = [
    r[0] for r in session.query(AudioTrack.id).filter_by(project_id=project_id).all()
]
```

**Issue:** This query fetches ALL audio track IDs including soft-deleted ones. The video query does filter `deleted_at` in `get_all_video()` but not in `delete_all_media()`. Inconsistent soft-delete handling across the codebase.

---

## MEDIUM Findings

### M-1: Duplicate Exception Handlers (ingest_service.py:518-524)

The `import_video_folder` function has overlapping except clauses: `OSError` appears in both exception handler blocks.

### M-2: Multiple inspect() Calls in Migrations (migrations.py)

`_run_legacy_migrations()` calls `inspect(get_raw_engine())` ~8 times. Each call opens a new connection. Should cache the inspector.

### M-3: Settings Store Not Thread-Safe

If `SettingsStore` is accessed from worker threads for reading settings during analysis, there is no lock protection on the QSettings access.

### M-4: conversation_memory Grows Unbounded

The chat memory system likely accumulates messages without limit, potentially causing memory issues in long sessions.

### M-5: _NullPoolSessionContext Missing Auto-Commit

The `__exit__` method only calls `rollback()` on error and `close()` always. If the caller forgets to call `session.commit()`, all changes are silently lost.

### M-6: FK CASCADE Migration Drops and Recreates All Data Tables (migrations.py:52-113)

The FK cascade migration drops ALL data tables and recreates them. While it creates a backup, if the migration succeeds but the backup is corrupt, data loss is unrecoverable.

### M-7: export_service _probe_cache Not Thread-Safe

The module-level `_probe_cache` dict is accessed from worker threads without locking.

### M-8: task_manager create_task Uses Non-UUID Counter (task_manager.py:340-351)

`create_task()` uses a simple incrementing counter (`task_1`, `task_2`) while `start_task()` uses UUID-based IDs. Inconsistent task ID formats.

### M-9: Version Check Worker Has No Timeout Guard

The version check thread has no mechanism to clean up if the network request hangs indefinitely.

### M-10: shell=True in GPU Health Check Script (scripts/check_gpu_health.py:10)

`subprocess.run(cmd, shell=True)` — while this is a diagnostic script, `shell=True` is a security anti-pattern.

### M-11: Missing Project Foreign Key Validation

Several services default `project_id=1` without verifying the project exists.

### M-12: Timeline Service Potential Data Race

Timeline operations that read-modify-write timeline entries across separate DB sessions can create race conditions with concurrent auto-edit operations.

---

## LOW Findings

### L-1: Duplicate Step Numbering in closeEvent (main.py)

Step 7 appears twice in the closeEvent comments (lines 396 and 414).

### L-2: Unused import re in session.py

`re` is imported at the top of `database/session.py` but never used.

### L-3: model_manager_temp.py Exists as Likely Dead Code

A temporary model manager file exists alongside the real one — likely a leftover from refactoring.

### L-4: Redundant Video Extension Check in import_video_folder

`import_video_folder` checks extension at line 509, but the glob already filtered by extension.

### L-5: pyproject.toml Authors Placeholder

`authors = ["Your Name <you@example.com>"]` — should be updated.

### L-6: Multiple Session Log Files in Project Root

30+ session log files (`session_*.log`) accumulate in the project root. Should be in `logs/`.

---

## Additional Findings — Audio/Video Services Deep Dive

### C-5: GPU_LOAD_LOCK Released Before Whisper Inference (transcription_service.py:63-112)

**File:** `services/transcription_service.py:63-112`

**Issue:** The Whisper model is loaded inside `GPU_LOAD_LOCK` but transcription (lines 119-141) runs **outside** the lock. `model.transcribe()` performs GPU inference without holding `GPU_LOAD_LOCK`. A concurrent call to any other service that acquires `GPU_LOAD_LOCK` and calls `ModelManager().unload()` (e.g., RAFT or SigLIP loading) can evict CUDA memory while Whisper is actively using the GPU, leading to a **CUDA illegal memory access crash**.

**Impact:** Hard crash under concurrent GPU workloads (e.g., transcription + video analysis).

**Fix:** Hold `GPU_EXECUTION_LOCK` during the `model.transcribe()` call to prevent concurrent model eviction.

---

### H-9: Moondream NameError/VRAM Leak on Exception Paths (vision_analysis_service_moondream.py:157)

**File:** `services/vision_analysis_service_moondream.py:157`

**Issue:** `mm.unload()` is called unconditionally at end of `analyze()`, but `mm` is assigned inside a `with` block. If an exception occurs between function entry and `mm = ModelManager()` assignment (e.g., `GPU_LOAD_LOCK` acquisition error), `mm` is undefined and line 157 raises `NameError`. Additionally, if `cv2.VideoCapture()` fails after model load succeeds, the model is never unloaded — VRAM leak.

**Impact:** VRAM leak or NameError crash on certain exception paths.

---

### H-10: Audio Callback Read-Count Mismatch (stem_player.py:403)

**File:** `services/stem_player.py:403`

**Issue:** `handle.frames - min(pos, handle.frames)` uses the master-clock position, not the individual handle's read cursor. If a seek was applied or a previous chunk returned fewer frames, `read_count` is incorrect. This causes under-reading or negative values caught by `if read_count <= 0: continue`, silently dropping audio segments.

**Impact:** Silent audio dropout during stem playback.

---

### H-11: AutoDucker Uses Bare "ffmpeg" Instead of Managed Binary (ai_audio_service.py:405)

**File:** `services/ai_audio_service.py:405`

**Issue:** `AutoDucker.create_ducked_audio()` calls `"ffmpeg"` as a bare string, not the managed `_FFMPEG` binary resolved by `get_ffmpeg_bin()`. If FFmpeg is only in `FFMPEG_PATH` (not in `PATH`), this raises `FileNotFoundError`. All other services use the configured binary.

**Impact:** AutoDucker fails in environments where FFmpeg is not on PATH.

---

### H-12: Multi-GB Numpy Array Persists on Singleton (beat_analysis_service.py:55-58)

**File:** `services/beat_analysis_service.py:55-58`

**Issue:** `_last_y` and `_last_sr` store the full audio waveform as instance attributes on a singleton. For a 60-minute mix at 22kHz mono, this is ~160 MB of float32 data. The array persists indefinitely until the next analysis call or explicit clear. If `analyze()` is called standalone (not via `analyze_and_store()`), the array is never cleared.

**Impact:** Memory leak of 50-200 MB per analyzed track.

---

### Additional MEDIUM Findings (Audio/Video Services)

**M-13:** `video_analysis_service.py:270` — `ModelManager().unload()` evicts any concurrently loaded model (not just RAFT) during batch analysis.

**M-14:** `ai_audio_service.py:363` — Session uses default pool instead of `nullpool_session()`, risking "database is locked" under concurrent writes.

**M-15:** `ai_audio_service.py:256-264` — OOM retry path allocates second GPU chunk before first result is freed.

**M-16:** `audio_classify_service.py:301` — Double-logging of errors (stack trace + warning) for every classification failure.

**M-17:** `onset_rhythm_service.py:507` — No `MAX_DURATION` limit on audio loading. 2-hour DJ mix loads ~1.8 GB into RAM.

**M-18:** `stem_player.py:430-434` — `np.tanh()` in RT audio callback risks buffer underruns. Should use `np.clip()`.

**M-19:** `stem_player.py:457` — `_state` written from QTimer lambda without lock protection, race with `play()`/`pause()`.

**M-20:** `transcription_service.py:191` — Method `transcribe_and_store()` never stores; result logged but not persisted.

**M-21:** `beat_analysis_service.py:323-332` — `NamedTemporaryFile(delete=False)` with cleanup in `finally` — process crash leaves ~300 MB orphaned temp files.

**M-22:** `beat_analysis_service.py:466` — Retry sleep blocks calling thread up to 6 seconds.

### Additional LOW Findings (Audio/Video Services)

**L-7:** `audio_constants.py:108-113` — `clamp_bpm(None)` returns `None` despite `-> float` type annotation.

**L-8:** `audio_classify_service.py:219` — Dead code: `librosa.load()` never returns `None`.

**L-9:** `ai_audio_service.py:35` — `STEMS_DIR` evaluated at module import time; stale after project switch.

**L-10:** `onset_rhythm_service.py:600-604` — `load_from_db()` omits fields, callers get silently wrong defaults.

**L-11:** `spectral_analysis_service.py:192` — Float values stored in int-typed dataclass fields after Nyquist clamp.

**L-12:** `lufs_service.py:177` — `creationflags=0` on non-Windows. Should be inside `sys.platform == "win32"` guard.

**L-13:** `key_detection_service.py:234` — `.replace("m", "")` is fragile. Should use `.removesuffix("m")`.

**L-14:** `transcription_service.py:144` — Progress calculation jumps to ~90% on first segment.

**L-15:** `audio_service.py:12-13` — `_track_locks` dict grows unboundedly (one Lock per track, never removed).

**L-16:** `video_analysis_service.py:384` — Byte/string confusion in FFmpeg stderr logging.

---

## Additional Findings — Core Services (Ollama, ModelManager, Startup, Settings)

### C-6: oom_recovery Deadlock with _swap_lock and GPU_LOAD_LOCK (model_manager.py:91)

**File:** `services/model_manager.py:91`

**Issue:** Inside the `oom_recovery` decorator, `ModelManager().unload()` is called without holding `_swap_lock`, but `unload()` itself acquires `_swap_lock`. The decorated function is typically called inside `ensure_loaded()` which holds `GPU_LOAD_LOCK`. If another thread holds `_swap_lock` while waiting for `GPU_LOAD_LOCK`, this creates a **lock inversion deadlock**: Thread A holds `GPU_LOAD_LOCK` and waits for `_swap_lock`; Thread B holds `_swap_lock` and waits for `GPU_LOAD_LOCK`.

**Impact:** Potential permanent deadlock during OOM recovery under concurrent model loading.

---

### H-17: Startup Check Falsely Reports Ollama Ready (startup_checks.py:116)

**File:** `services/startup_checks.py:116`

**Issue:** `_check_ollama` returns `True` immediately after calling `subprocess.Popen` to auto-start Ollama, before confirming the server is actually listening. Callers treat `True` as "Ollama is ready", but the process may still be initializing. The UI reports `ollama_ok=True` while Ollama is still starting, causing failed LLM calls.

**Impact:** Race condition at startup — first chat/analysis requests fail silently.

---

### H-18: main.py final_init References Undefined Attributes (main.py:661,672,674)

**File:** `main.py:661,672,674`

**Issue:** `final_init()` references `window.console_text` and `window.timeline_view` without those attributes being defined in `PBWindow.__init__`. They are set up by controller/setup methods, but if any setup step fails, these will raise `AttributeError` silently inside the `QTimer.singleShot` callback with no error reporting.

**Impact:** Silent startup failure if any controller setup fails.

---

### H-19: --pre-cache Mode May Hang 30 Minutes Per Model (main.py:564-578)

**File:** `main.py:564-578`

**Issue:** `service.download_hf_model()` is called synchronously, then `done_event.wait(1800)` blocks for up to 30 minutes. If `download_hf_model` is itself synchronous/blocking, the progress callback with `finished=True` may never fire (no separate thread sets it), causing a 30-minute hang per model.

**Impact:** Pre-cache mode may hang indefinitely during installer builds.

---

### H-20: _unloadable_models Set Modified Without Lock (ollama_client.py:223-232)

**File:** `services/ollama_client.py:223-232`

**Issue:** `_find_fallback_model` adds `failed_model` to `self._unloadable_models` without holding `self._lock`. This set is read/written from multiple threads calling `chat`/`chat_with_history`, creating a race condition on the set. Python's GIL provides some protection but the pattern is incorrect and can lead to lost updates.

**Impact:** Race condition — fallback model selection may retry already-failed models.

---

### Additional MEDIUM Findings (Core Services)

**M-31:** `llm_service.py:249-253` — atexit handler acquires `self._lock`. If lock was abandoned by daemon thread during interpreter shutdown, this deadlocks the exit sequence.

**M-32:** `settings_store.py:227-232` — `get_settings_store()` singleton not thread-safe. Two threads can create two instances, causing double migration writes.

**M-33:** `project_manager.py:159-165` — Raw `sqlite3.connect()` leaks connection on exception (no context manager or try/finally).

**M-34:** `project_manager.py:120` — Bare `except Exception:` swallows all errors including `KeyboardInterrupt`/`SystemExit`.

**M-35:** `knowledge_loader.py:106-122` — `load_file()` not thread-safe. Concurrent calls read same file twice, waste I/O.

**M-36:** `startup_checks.py:267` — Dead code: `elif key == "cuda":` branch unreachable since "cuda" is never in `futures` dict.

### Additional LOW Findings (Core Services)

**L-23:** `settings_store.py:112-119` — Settings file written directly without atomic write pattern. Crash mid-write corrupts all settings.

**L-24:** `recent_projects.py:43-50` — `get_all()` triggers disk write on every call to filter stale paths.

**L-25:** `ollama_client.py:647-648` — `__repr__` calls `is_available()` which opens a network socket. Debugger/logging triggers 2-second latency.

**L-26:** `knowledge_loader.py:226-227` — Regex with `.*?` and `re.DOTALL` risks catastrophic backtracking on malformed knowledge files.

**L-27:** `conversation_memory.py:90` — `logger.warning()` called while holding `_lock`. Risk if custom log handler tries to acquire same lock.

---

## Additional Findings — Pipeline, Export, Vector & Pacing Services

### H-13: VectorDB delete_by_video Missing Cache Invalidation (vector_db_service.py:291-298)

**File:** `services/vector_db_service.py:291-298`

**Issue:** `delete_by_video()` does not call `_invalidate_cache()` after DELETE, unlike `add_embedding` and `add_embeddings_batch`. After deletion, the in-memory cache (`_cache_matrix` / `_cache_metadata`) still holds deleted rows. Subsequent `search()` calls return **stale ghost results** until process restart or another write operation triggers invalidation.

**Impact:** Deleted video embeddings continue appearing in semantic search results.

---

### H-14: VectorDBService Singleton Race Condition (vector_db_service.py:52-75)

**File:** `services/vector_db_service.py:52-75`

**Issue:** The `__new__` double-checked locking pattern is broken. The outer `if _instance is None` check is **not inside the lock**, so two threads can both pass it before either acquires `_instance_lock`, creating two instances briefly. One instance gets orphaned with a stale DB connection.

**Impact:** Potential duplicate singleton, stale DB connections, inconsistent search results.

---

### H-15: timeline_service Disposes Shared Engine in Retry Loop (timeline_service.py:48-58)

**File:** `services/timeline_service.py:48-58`

**Issue:** `apply_auto_edit_segments()` calls `engine.dispose()` on the **global shared engine** inside a retry loop. Disposing a shared engine while other threads hold connections from it causes those connections to fail immediately. This is a cross-thread resource destruction that can crash unrelated concurrent DB operations.

**Impact:** Concurrent DB operations crash when auto-edit retries trigger engine dispose.

---

### H-16: PacingStrategist Uses Ollama Model ID in HuggingFace Path (pacing_strategist.py:16)

**File:** `services/pacing_strategist.py:16`

**Issue:** `STRATEGIST_MODEL_ID = "gemma4:e4b"` is an Ollama model ID, but `_generate()` calls `mm.load_transformers(self.model_id)` through the HuggingFace path (fallback). `"gemma4:e4b"` is not a valid HuggingFace identifier — the load fails silently and falls back to `PacingPlan.default()`. Users never see the error; pacing always uses defaults.

**Impact:** AI-driven pacing strategist is silently non-functional. Always returns default plan.

---

### Additional MEDIUM Findings (Pipeline/Export/Vector)

**M-23:** `convert_service.py:219-233` — NVENC fallback drops bitrate caps, producing uncapped CRF-only CPU encode with no UI warning.

**M-24:** `convert_service.py:261-264` — `-hwaccel cuda` silently added to DNxHD encode path, may cause FFmpeg errors.

**M-25:** `analysis_status_service.py:47-143` — No retry on SQLite "database is locked", unlike timeline_service. Analysis steps silently lost under contention.

**M-26:** `vector_db_service.py:183-219` — Full DB read held under `_cache_lock` blocks concurrent writes.

**M-27:** `pacing_memory.py:137-163` — `session.get(AudioTrack, id)` not null-checked before accessing `.bpm`.

**M-28:** `export_service.py:185-189` — Resolution parsing `"1920x..."` not validated as numeric, cryptic FFmpeg error.

**M-29:** `pacing_beat_grid.py:40-80` — TOCTOU race in stem audio cache, doubles memory temporarily.

**M-30:** `ingest_service.py:519,522` — Duplicate/overlapping except handlers, `OSError` caught twice.

### Additional LOW Findings (Pipeline/Export/Vector)

**L-17:** `action_registry.py:180-196` — `inspect.signature` called on every execute, should be cached.

**L-18:** `ingest_service.py:162-212` — `get_audio_detail_data()` uses pool session not nullpool.

**L-19:** `pacing_strategist.py:213-240` — Uncaught `ValueError` in markdown fence parsing.

**L-20:** `services/actions/video_actions.py:266` — Missing null guard on `tm` in except block.

**L-21:** `pacing_beat_grid.py:83-90` — Cache invalidation during concurrent cached function execution.

**L-22:** `version_check_service.py:98` — `TimeoutError` vs `socket.timeout` cross-version issue.

---

## Additional Findings — Database, Workers & Dependencies

### H-21: Double init_db() Race on Startup (migrations.py:383 + main.py:659)

**File:** `database/migrations.py:383`, `main.py:659`, `workers/startup.py:19`

**Issue:** `init_db()` is called from `final_init()` in main.py AND from `StartupCheckWorker.run()` which runs in a separate QThread. Two concurrent calls race through `_run_alembic_migrations()` — Alembic `command.upgrade("head")` is NOT idempotent against concurrent callers, risking `MigrationError` or corrupt `alembic_version` table.

**Impact:** Intermittent migration failures or corrupt DB schema on startup.

---

### H-22: PBWindow Created Before init_db() (main.py:644-649)

**File:** `main.py:644-649`

**Issue:** `PBWindow.__init__` is called at line 645, which instantiates all controllers (some may query DB). `init_db()` is only called 500ms later via `QTimer.singleShot(500, final_init)`. Any DB access in those 500ms hits an un-migrated schema.

**Impact:** Controllers may crash or return wrong data before migrations run.

---

### H-23: KeyDetectionWorker Double-Serializes JSON Columns (audio_analysis.py:147-150)

**File:** `workers/audio_analysis.py:147-150`

**Issue:** `_save_to_db()` calls `json.dumps()` on `key_modulation_data` and `harmonic_tension_curve` before storing them, even though the ORM column is typed `Column(JSON)`. SQLAlchemy auto-serializes JSON columns. Result: stored value is a JSON string inside a JSON column (e.g., `"[{...}]"` instead of `[{...}]`). Reads via ORM return a `str` instead of a `list`, breaking downstream consumers that index into the data.

**Impact:** Key modulation and harmonic tension data unreadable after DB round-trip. Same class of bug as C-3.

---

### H-24: PyTorch Version/CUDA Conflict (pyproject.toml:33 vs requirements.txt:111)

**File:** `pyproject.toml:33`, `requirements.txt:111`

**Issue:** `pyproject.toml` declares `torch>=2.4.0,<2.5.0` (cu118 source), but `requirements.txt` pins `torch==2.5.1+cu124`. Different CUDA build variants AND different minor versions. `pip install -r requirements.txt` gets 2.5.1+cu124 while `poetry install` gets 2.4.x+cu118. This causes silent CUDA ABI mismatches between torch, torchaudio, and torchvision.

**Impact:** Silent CUDA crashes or incorrect GPU computations depending on installation method.

---

### H-25: SigLIP Model Invalidated Mid-Batch by Concurrent Unload (workers/video.py:191-373)

**File:** `workers/video.py:191-373`

**Issue:** `siglip_model_processor` is loaded inside `GPU_LOAD_LOCK`, but the pipeline loop runs WITHOUT holding the lock. A concurrent `BeatAnalysisService` or `TranscriptionWorker` can call `ModelManager.unload()`, invalidating SigLIP tensor references mid-batch, causing `RuntimeError: CUDA error` or silent wrong embeddings.

**Impact:** CUDA crash or wrong video embeddings during concurrent analysis.

---

### H-26: FK CASCADE Migration Has No Automatic Restore (migrations.py:80-112)

**File:** `database/migrations.py:80-112`

**Issue:** `_migrate_fk_cascade()` drops tables inside `engine.begin()` then calls `Base.metadata.create_all(engine)` outside that transaction. If `create_all()` fails after the DROP commit, the database has no tables and no automatic backup restore logic runs. The backup exists on disk but requires manual intervention.

**Impact:** Data loss on crash between DROP and CREATE phases.

---

### Additional MEDIUM Findings (Database, Workers, Dependencies)

**M-37:** `database/models.py:30-34` — `lazy='selectin'` on all Project relationships fires 4 extra SELECTs on every Project load, including trivial reads.

**M-38:** `database/models.py:273,371` — `created_at` stored as `String` via lambda, not `DateTime`. Prevents date-range queries.

**M-39:** `database/models.py:419` — `TimelineEntry.media_id` has no FK constraint. Deleting AudioTrack leaves orphaned timeline entries.

**M-40:** `database/migrations.py:290-305` — Index creation runs unconditionally without checking if referenced tables exist. Fails on fresh DB.

**M-41:** `database/alembic/...initial_schema...py:21-28` — Alembic baseline migration is a no-op (`pass`). Downgrades and autogenerate are permanently broken.

**M-42:** `database/session.py:250-254` — `set_project()` swap doesn't quiesce in-flight workers. Existing sessions write to old DB while new readers use new DB.

**M-43:** `workers/audio_analysis.py:147-150` — Double JSON serialization (same pattern as C-3 but in different worker).

**M-44:** `workers/import_export.py:222-231` — `BatchConvertWorker` passes unvalidated `self.fps`/`self.vcodec` strings to FFmpeg command.

**M-45:** `workers/startup.py:14-29` — `check_worker` not parented or held in persistent reference. GC can break signal connections (duplicate of C-4).

**M-46:** `requirements.txt:115` — `transformers==5.3.0` pinned (major version change from 4.x). API breakage possible.

**M-47:** `requirements.txt:11` — `beat-this` pinned to unpinned git commit hash. No integrity check.

### Additional LOW Findings (Database, Workers, Dependencies)

**L-28:** `database/session.py:199-207` — `get_active_project_id()` returns `1` silently on any exception.

**L-29:** `workers/video.py:311` — `gc.collect()` every 25 videos unnecessarily delays VRAM reclamation.

**L-30:** `workers/video.py:339-344` — `idx` variable stale after loop break, off-by-one in batch progress.

**L-31:** `requirements.txt` — `alembic` not listed as explicit dependency despite direct import.

**L-32:** `workers/base.py:49-50` — `_cancelled` bool read/written across threads without lock (GIL-dependent).

---

## Architecture Assessment

### Strengths

1. **Clean controller pattern** — UI logic separated into 12 controller classes, avoiding monolithic QMainWindow.
2. **Robust error hierarchy** — Custom exception classes with structured `details` dict and functional `Result[T]` pattern.
3. **Thread-safe task engine** — Cross-thread routing via `QueuedConnection` signals is correctly implemented.
4. **VRAM management** — Singleton ModelManager with GPU_LOAD_LOCK prevents concurrent model loading.
5. **Worker command pattern** — Registry-based worker instantiation keeps Qt object creation in the main thread.
6. **Database migration strategy** — Dual migration path (legacy + Alembic) with backup verification.
7. **Ollama integration** — Clean HTTP client with pause/resume for GPU coordination, model fallback chain.

### Weaknesses

1. **Soft-delete inconsistency** — Some queries filter `deleted_at`, others do not. Need a consistent approach.
2. **Inspector overuse in migrations** — `inspect()` called repeatedly, opening many connections.
3. **Module-level singletons** — Multiple singleton patterns with different initialization strategies.
4. **No connection pooling strategy for workers** — Some use `nullpool_session()`, others use the shared engine.

---

## Security Assessment

### Positive
- No `eval()` or `exec()` on user input
- No pickle deserialization of untrusted data
- No hardcoded secrets or API keys
- FFmpeg commands use list-based subprocess calls (no shell injection)
- SQL migration inputs validated with regex before string interpolation
- File path validation prevents Windows reserved name issues

### Concerns
- One `shell=True` in diagnostic script (low risk, not user-facing)
- User chat input passed to Ollama LLM without sanitization (acceptable for local-only LLM)
- `_probe_cache` could leak file path information in error messages

---

## Recommended Priority Actions

1. **P0** Fix RLock release loop (C-1): Prevents permanent GPU deadlocks
2. **P0** Fix closeEvent ordering (C-2): Prevents shutdown crashes
3. **P0** Fix JSON double-parse (C-3): Restores beat count display
4. **P0** Hold GPU_EXECUTION_LOCK during Whisper inference (C-5): Prevents CUDA crash
5. **P0** Fix oom_recovery lock ordering deadlock (C-6): Prevents deadlock during OOM recovery
6. **P1** Fix worker GC in final_init (C-4): Prevents startup crash
7. **P1** Fix Ollama startup race — wait for server ready (H-17): Prevents failed LLM calls
6. **P1** Fix VectorDB cache invalidation on delete (H-13): Prevents stale search results
7. **P1** Fix VectorDB singleton race condition (H-14): Prevents duplicate instances
8. **P1** Remove engine.dispose() from timeline retry loop (H-15): Prevents concurrent DB crashes
9. **P1** Fix PacingStrategist model ID (H-16): Makes AI pacing functional
10. **P1** Fix Moondream NameError/VRAM leak (H-9): Prevents crash and VRAM leak
11. **P1** Fix stem player read-count mismatch (H-10): Prevents audio dropout
12. **P1** Use managed FFmpeg binary in AutoDucker (H-11): Fixes reliability
13. **P1** Clear beat analysis numpy cache (H-12): Prevents 200MB memory leak
14. **P1** Make OllamaClient fallback iterative (H-5): Prevents stack overflow
15. **P1** Add soft-delete filter to get_all_audio (H-4): Consistency fix
16. **P2** Clear _probe_cache on project switch (H-3): Prevents stale metadata
17. **P2** Fix update banner connection accumulation (H-1): UX fix
18. **P2** Move engine creation inside lock (H-7): Prevents resource leak
19. **P2** Add MAX_DURATION to onset_rhythm_service (M-17): Prevents RAM exhaustion
20. **P2** Add DB retry logic to analysis_status_service (M-25): Prevents lost analysis steps

---

## Additional Findings — UI Layer (Controllers, Dialogs, Widgets, Workspaces, Timeline)

### HIGH Findings (H-27 through H-37)

#### H-27: Blocking HTTP Call on GUI Thread (model_manager_dialog.py:571)
`_check_ollama_status()` runs `urllib.request.urlopen` synchronously on the GUI thread. UI freezes for the full HTTP timeout if Ollama is unreachable.
**Fix:** Move into a QThread worker, emit result via signal.

#### H-28: Blocking Download on GUI Thread (model_manager_dialog.py:624-648)
`_start_download()` calls `svc.pull_ollama_model()` / `svc.download_hf_model()` synchronously on the main thread, freezing the UI for the entire download.
**Fix:** Move download into a QThread worker.

#### H-29: Thumbnail Thread Cleanup Blocks GUI (media_grid.py:484-488)
`_rebuild_cards()` calls `t.quit()` + `t.wait(200)` in a loop on all thumbnail threads. N threads × 200 ms blocks the GUI. Also, `_load_timer` is re-created each call without stopping the previous one, causing timer races.
**Fix:** Store `_load_timer` as instance attribute, stop before restart; use non-blocking thread cleanup.

#### H-30: Chat Worker Registry Lock Not Shared (chat_dock.py:104-113)
`_registry_lock` is per-worker-instance. The main thread never acquires it before reading `agent.registry`, so the race it claims to prevent still exists.
**Fix:** Use a shared lock on the agent object, or avoid mutating `agent.registry`.

#### H-31: ClipInspector _updating Flag Not Reset on Exception (clip_inspector.py:149-174)
If any `setValue()` call throws inside the `_updating = True` block, no `try/finally` resets it. The inspector becomes permanently read-only.
**Fix:** Wrap in `try/finally` to always reset `_updating = False`.

#### H-32: Timeline Uses Pool Session Instead of NullPool (timeline.py:158-162)
`_load_anchors` uses `DBSession(engine)` (pool connection) instead of `nullpool_session()`. Holds a pool connection during clip construction, risking pool exhaustion (mirrors VAD-45).
**Fix:** Replace with `nullpool_session()`.

#### H-33: ApplyAutoEditCommand Undo Corrupts on Failed Redo (undo_commands.py:282-308)
`_old_entries` snapshot is captured before `apply_auto_edit_segments` runs. If it raises, undo would delete current clips and re-insert the snapshot (which is identical to current state), duplicating all video clips.
**Fix:** Capture snapshot and apply atomically, or clear `_old_entries` on failure.

#### H-34: Flush Pending Moves Race with Undo (timeline.py:930-979)
200 ms debounce timer fires after the user already pressed Ctrl+Z. The stale `MoveClipCommand` is pushed with reverted positions, corrupting the undo stack.
**Fix:** Cancel move timer in undo/redo handlers.

#### H-35: Worker Dispatcher Accesses Private _tasks Without Lock (worker_dispatcher.py:29)
Direct access to `tm._tasks` from UI thread while worker threads mutate it — data race.
**Fix:** Use a public accessor or acquire `tm._lock`.

#### H-36: ImportMedia DeleteWorker Missing on_finish Callback (import_media.py:126-130)
`_on_done` is never passed as `on_finish` to `start_task()`. After clearing all media, UI tables display stale data.
**Fix:** Pass `on_finish=_on_done` to `start_task()`.

#### H-37: Audio Analysis Sequential State Overwrite Race (audio_analysis.py:292-299)
If user clicks analyze-all twice before first run completes, `_seq_steps`, `_seq_index` etc. are overwritten while QTimer callbacks from the first run still reference them.
**Fix:** Guard with `_seq_running` flag, disable button during run, reset on completion.

### MEDIUM Findings (M-48 through M-54)

#### M-48: Video Analysis Signals Not Queued (video_analysis.py:83-99)
`item_done`/`item_error` signals from worker thread not connected with `QueuedConnection`. Slots modify instance state from wrong thread.
**Fix:** Connect with `Qt.ConnectionType.QueuedConnection`.

#### M-49: Hardcoded Relative OTIO Export Path (edit_workspace.py:286)
`tls.save_otio("exports/auto_edit_phase3.otio")` uses relative path — resolves against CWD, not project folder. Directory may not exist.
**Fix:** Use `Path(database.APP_ROOT) / "exports" / ...` with `mkdir(parents=True)`.

#### M-50: FPS Combo ValueError Not Handled in Export (export.py:31)
`float(self.window.fps_combo.currentText())` can raise `ValueError` if combo has non-numeric text.
**Fix:** Wrap in `try/except ValueError` with fallback default.

#### M-51: ResourceMonitor Thread Leak on Widget Destroy (resource_monitor.py)
No `closeEvent` override — if parent closes without calling `stop()`, worker thread runs against destroyed widget (C++ object deleted crash).
**Fix:** Override `closeEvent` to call `self.stop()`.

#### M-52: Settings Dialog Double Test Thread (settings_dialog.py:465-471)
Clicking "Verbindung testen" twice quickly creates two concurrent `QThread`s. Both emit `_on_test_finished`, corrupting the combo-box.
**Fix:** Guard with `isRunning()` check or disable button during test.

#### M-53: Setup Wizard Blocking Hardware Check (setup_wizard.py:311-317)
`_run_check()` runs `run_startup_checks()` synchronously on GUI thread via `QTimer.singleShot`. Freezes wizard on startup.
**Fix:** Move into QThread worker.

#### M-54: Analysis Status Panel Synchronous DB Queries (analysis_status_panel.py:291-304)
`refresh()` runs DB queries synchronously on GUI thread on every filter change. Causes jank when DB is slow/locked.
**Fix:** Run queries in background thread, update via signal.

#### M-55: RemoveClipCommand Undo ID Overwrite (undo_commands.py:178-212)
After undo re-inserts a row, the new auto-increment `entry.id` overwrites `self._entry_id`. On repeated redo/undo cycles with different auto-IDs, visual clip removal looks for stale ID, leaving ghost clip items.
**Fix:** Store original ID separately; use `_restored_entry_id` for undo path.

#### M-56: Timeline Panning Ends on Wrong Button (timeline.py:1140-1148)
Panning ends on `LeftButton` release but starts only on `MiddleButton`. Simultaneous button presses swallow the left-button release, breaking rubber-band selection.
**Fix:** Only end panning on `MiddleButton` release.

#### M-57: Waveform Tile Off-By-One (waveform_item.py:114-115)
Floating-point `clip_rect.right()` can push `tile_end` one past valid range. Guard catches it but an unnecessary empty cache entry is created.
**Fix:** Clamp `tile_end` to `(w - 1) // TILE_WIDTH`.

#### M-58: Audio Analysis KeyError Crash (audio_analysis.py:245)
`result["bpm"]` and `result["num_samples"]` accessed with hard key indexing. Missing keys cause unhandled `KeyError` in UI thread.
**Fix:** Use `.get("bpm", 0)` with safe defaults.

---

## Additional Findings — UI Layer Deep Audit (Agent 4)

### CRITICAL (C-7)

#### C-7: Cross-Thread UI Mutation in MoveClipCommand (undo_commands.py:56)
`MoveClipCommand._apply()` calls `self._timeline._sync_clip_position()` directly after DB commit. When `QUndoStack.push()` is triggered from a worker-thread callback chain (via `edit_workspace.py` `_on_done` lambdas), this mutates QGraphicsItem from a non-main thread — prohibited by Qt and causes undefined behavior / crashes.
**Fix:** Ensure all undo command pushes happen on the main thread (use `QMetaObject.invokeMethod` with `QueuedConnection` or signal routing).

### HIGH (H-38 through H-41)

#### H-38: get_first_anchor_time Uses Pooled Session (timeline.py:200-207)
`get_first_anchor_time()` opens `DBSession(engine)` on the UI thread — same pool-exhaustion risk as H-32. Called on right-click and selection events.
**Fix:** Replace with `nullpool_session()`.

#### H-39: RemoveClipCommand.undo() Two-Session Orphan Risk (undo_commands.py:178-212)
Opens two sequential `nullpool_session()` contexts. First session commits new `TimelineEntry`, second looks up `AudioTrack`/`VideoClip` for title. If second fails, the entry is committed but not added to the timeline — orphaned row with inconsistent undo stack.
**Fix:** Combine both operations in a single session.

#### H-40: load_from_db UI Freeze on Waveform Finish (audio_analysis.py:245-246)
`_on_waveform_finished()` calls `self.window.timeline_view.load_from_db()` which opens a pooled `DBSession` and does O(N) item creation, freezing the UI for large projects.
**Fix:** Debounce or defer `load_from_db()` with `QTimer.singleShot`.

#### H-41: Project CreateWorker Closure Over Destroyed Window (project_management.py:27-57)
Inner `CreateWorker` captures `self.window` via closure in `_on_done`. If the dialog is GC'd before worker finishes, the closure references a destroyed Qt object.
**Fix:** Use weak references or connect via signal with `QueuedConnection`.

### MEDIUM (M-59 through M-64)

#### M-59: Crash Dialog HTML Injection (crash_dialog.py:61-62)
`exc_msg[:200]` rendered inside `<b>...</b>` rich-text QLabel without HTML escaping. Exception messages with `<`, `>`, `&` misrender or inject HTML.
**Fix:** Use `html.escape(exc_msg[:200])`.

#### M-60: Video Preview Scrubbing Stall (video_preview.py:98-113)
Previous extraction thread is `.quit()` + `.wait(500)` synchronously. Rapid scrubbing (JKL shuttle) creates repeated 500ms UI stalls.
**Fix:** Use `requestInterruption()` + non-blocking cleanup, or debounce extraction requests.

#### M-61: load_from_db Inconsistent Session (timeline.py load_from_db)
Uses `DBSession(engine)` (pooled) while all other DB access uses `nullpool_session()`. Pool-exhaustion risk when called concurrently with background workers.
**Fix:** Switch to `nullpool_session()`.

#### M-62: ShortcutManager Frequent QKeySequence Construction (shortcut_manager.py:92)
`QKeySequence` constructed from int on every key event. Comparison with multi-key sequences is unreliable.
**Fix:** Pre-compute and cache int representations.

#### M-63: Settings Dialog Thread/Worker Cleanup (settings_dialog.py:465-471)
`_test_thread` and `_test_worker` not cleaned up via `deleteLater()`. If dialog closes during test, thread leaks.
**Fix:** Connect `_test_thread.finished` to `deleteLater()`.

#### M-64: Waveform __del__ Cleanup Unreliable (waveform_item.py:82-88)
`__del__` with bare `except Exception: pass` for tile cache cleanup. `__del__` is unreliable in Python/Qt — not guaranteed to run.
**Fix:** Add explicit `cleanup()` method called from parent's cleanup path.

### LOW (L-33 through L-40)

#### L-33: QFont Created Before QApplication (timeline.py class variable)
`_RULER_FONT = QFont(...)` defined at class level. Crashes if module imported before `QApplication` exists.

#### L-34: app_icon Cache Used Before QApplication (app_icon.py:17)
`_ICON_CACHE` is module-level `QIcon`. No guard against pre-QApplication calls.

#### L-35: Splash processEvents Re-Entrancy (splash.py:125-126)
`QApplication.processEvents()` in `show_message()` can trigger re-entrant Qt calls during startup.

#### L-36: Sequential Helper Dangling Signals (audio_analysis.py:299)
`_SeqStepSignalHelper` overwritten on re-call; old helper's signal connections from previous worker may still fire.

#### L-37: Waveform Cache Full Clear (media_grid.py:62-101)
`_WAVEFORM_CACHE` grows to 200 then does full `clear()` — all subsequent renders are cache misses. LRU eviction would be better.

#### L-38: TaskManagerProxy Module-Level Init (video_analysis.py:29)
`TaskManagerProxy()` instantiated at module import time — silently points to nothing if singleton not yet created.

#### L-39: Theme Unsupported CSS Property (theme.py:361)
`letter-spacing: 1.5px` silently ignored by Qt QSS. Inconsistent with comments elsewhere noting this limitation.

#### L-40: MediaTableModel Type Annotation Bug (models/media_table_model.py:74)
`value: any` uses `builtins.any` (a function) instead of `typing.Any`. Confuses type checkers.
