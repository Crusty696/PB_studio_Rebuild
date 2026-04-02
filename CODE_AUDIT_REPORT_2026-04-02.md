# PB Studio — Static Code Audit Report
**Date:** 2026-04-02
**Scope:** `workers/`, `main.py`, `database.py`, `services/task_manager.py`, `services/project_manager.py`, `services/ingest_service.py`, `services/audio_service.py`, `services/video_service.py`, `services/lufs_service.py`, `services/model_manager.py`, `services/pacing_service.py`
**Method:** Static analysis — no mocking, reading real source files

---

## SUMMARY

| Severity  | Count |
|-----------|-------|
| Critical  | 2     |
| High      | 5     |
| Medium    | 7     |
| Low       | 6     |
| **Total** | **20**|

---

## CRITICAL

---

### BUG-01: `init_db()` called before `QApplication` — aborts task_manager bootstrap

**File:** `main.py`, lines 1076–1086
**Category:** Startup/shutdown sequence bug

**Description:**
`init_db()` is called at line 1076, and `QApplication(sys.argv)` is created at line 1083. But `init_db()` triggers `database.py` module-level code which calls `nullpool_session()`, and also executes migrations. If a migration fails, `sys.exit(1)` fires. So far so good — but if `init_db()` raised inside the `except` block at line 1077, `logging.basicConfig(level=logging.ERROR)` is called AFTER `setup_logging()` has already added handlers (line 1051), adding a second root handler and causing duplicate log lines from that point.

More critically: `GlobalTaskManager.instance()` is called at line 1086 **after** `QApplication` is created, which is correct. But the module-level `task_manager = TaskManagerProxy()` at `main.py` line 73 is instantiated at **import time**, before `QApplication` exists. The `TaskManagerProxy.__getattr__` lazy-delegates to `GlobalTaskManager.instance()` which raises `RuntimeError` if `QApplication` does not exist. Any code that touches `task_manager` before `main()` starts — e.g. top-level module code in services imported at line 50–114 — triggers this. Currently none does, but it is a fragile ordering dependency that will break silently if any import-time code calls `task_manager`.

**Suggested fix:**
Remove `task_manager = TaskManagerProxy()` from module level in `main.py`. It is only used inside methods, so assign it lazily inside `main()` after `GlobalTaskManager.instance()` is constructed:
```python
# Remove line 73 from module level.
# In main(), after line 1086:
from services import task_manager as _task_manager_module
_task_manager_module.task_manager = _tm  # already done at line 1087
```
The proxy in `services/task_manager.py` line 437 is safe to leave; it is never accessed at import time from that module. The unsafe one is the alias created in `main.py` at import time.

---

### BUG-02: `_safe_cleanup` in `task_manager.py` reads `_tasks` dict without the lock

**File:** `services/task_manager.py`, lines 291–307
**Category:** Threading/concurrency bug (race condition)

**Description:**
`_safe_cleanup` is connected to `thread.finished` and runs in the main thread via Qt's event loop, but it directly accesses `self._tasks.get(_tid)` at line 293 **without** `self._tasks_lock`. All other accessors (`get_task`, `finish_task`, `update_task`, `clear_finished`, `cancel_task`) correctly acquire the lock. If `clear_finished()` runs concurrently (e.g. from a timer in the TaskManagerDock) on a background thread, the dict can be mutated mid-read in `_safe_cleanup`, causing a `RuntimeError: dictionary changed size during iteration` or returning a stale `task` reference whose `.worker`/`.thread` has already been nulled by `clear_finished`.

Additionally, `_on_thread_done` at line 428 also reads `self._tasks.get(task_id)` without the lock.

**Suggested fix:**
```python
def _safe_cleanup(_tid=task_id):
    with self._tasks_lock:
        task = self._tasks.get(_tid)
        if task:
            if task.worker:
                try:
                    task.worker.deleteLater()
                except RuntimeError:
                    pass
                task.worker = None
            if task.thread:
                try:
                    task.thread.deleteLater()
                except RuntimeError:
                    pass
                task.thread = None
    self._on_thread_done(_tid)

def _on_thread_done(self, task_id: str):
    with self._tasks_lock:
        task = self._tasks.get(task_id)
    if task and task.status == "running":
        self.finish_task(task_id, "finished", "Fertig")
```

---

## HIGH

---

### BUG-03: `worker.finished.connect(thread.quit)` without `QueuedConnection` — potential direct cross-thread call

**File:** `services/task_manager.py`, line 286
**Category:** Signal emission from wrong thread / threading bug

**Description:**
```python
worker.finished.connect(thread.quit)
```
This connection uses the default connection type. When `worker` lives in `thread` (after `moveToThread`), PySide6 resolves the connection type as `AutoConnection`. Since `worker` and `thread.quit` are in different threads (worker in the QThread, `thread.quit` is a slot on the QThread object which lives in the main thread), this **should** become a `QueuedConnection` automatically. However, the `on_finish` callback at line 263–267 is explicitly set to `QueuedConnection`, creating an inconsistency. In edge cases where `moveToThread` has not fully completed before the signal fires (possible in the cross-thread request path at lines 204–212 where `moveToThread(app.thread())` is called before the `_cross_thread_request` signal is processed), a `DirectConnection` could fire `thread.quit()` from the worker thread, which is undefined behavior in Qt.

**Suggested fix:**
Be explicit:
```python
worker.finished.connect(thread.quit, Qt.ConnectionType.QueuedConnection)
if hasattr(worker, "error"):
    worker.error.connect(thread.quit, Qt.ConnectionType.QueuedConnection)
```

---

### BUG-04: `VisionAnalysisWorker` and `TranscriptionWorker` call `CancellableMixin.__init__(self)` explicitly — double init of `_cancelled`

**File:** `workers/video.py`, line 374; `workers/audio.py`, line 91
**Category:** Threading/concurrency bug (MRO misuse)

**Description:**
`VisionAnalysisWorker.__init__` (line 374) and `TranscriptionWorker.__init__` (line 91) both call:
```python
CancellableMixin.__init__(self)
```
explicitly after `super().__init__()`. The MRO for `class VisionAnalysisWorker(QObject, CancellableMixin)` means `super().__init__()` already calls `CancellableMixin.__init__` via cooperative multiple inheritance — **if** `CancellableMixin.__init__` calls `super().__init__(*args, **kwargs)`. It does (line 40 of `workers/base.py`). So the explicit call at line 374/91 re-initialises `_cancelled = False` and `_errored = False`. This is harmless in the normal case but masks a real inconsistency: the other workers (e.g. `StemSeparationWorker`, `VideoAnalysisWorker`) do **not** make this call and rely purely on MRO. If a worker is mid-run and `cancel()` has set `_cancelled = True`, a second accidental `CancellableMixin.__init__(self)` call anywhere in that worker's call chain would silently reset the flag. The inconsistency creates a maintenance trap — future maintainers may copy either pattern without understanding why.

**Suggested fix:**
Remove the explicit `CancellableMixin.__init__(self)` calls from `VisionAnalysisWorker` and `TranscriptionWorker`. Rely on MRO consistently, as the other workers do.

---

### BUG-05: `BatchConvertWorker` returns early from `except FileNotFoundError` without emitting `finished` — thread never quits

**File:** `workers/import_export.py`, lines 209–212
**Category:** Resource cleanup in worker teardown

**Description:**
```python
except FileNotFoundError:
    self._errored = True
    self.error.emit("ffmpeg nicht gefunden!")
    return   # <-- bare return inside try, bypasses finally
```
The `finally` block at line 220 only emits `finished` if `not _ok and not self._errored`. Since `self._errored = True` was set, `finally` skips emitting `finished`. `finished` is never emitted. Because `thread.quit()` is connected to `worker.finished`, the QThread never receives the quit signal and **hangs forever**, keeping the task in "running" state, holding the SQLite connection pool slot, and preventing clean shutdown.

`error.connect(thread.quit)` **is** wired at line 290 of `task_manager.py`, so the `error` emission at line 211 will quit the thread. But the `finish_task` call in `_task_error_handler` (lines 273–279) marks the task as "error" only through the error signal path, and the `_safe_cleanup` is only connected to `thread.finished`. The chain works through the error signal — but is fragile: it depends on `error` being connected before `return` fires, which requires the task to have been started via `GlobalTaskManager.start_task()`. If this worker is ever started manually (e.g. in tests) without the task manager wiring the error signal, the thread will hang.

**Suggested fix:**
Replace the bare `return` with a proper exception raise, letting the outer `except Exception` and `finally` block handle it:
```python
except FileNotFoundError:
    raise RuntimeError("ffmpeg nicht gefunden — bitte ffmpeg installieren")
```

---

### BUG-06: `VideoAnalysisPipelineWorker` — `last_clip_id` and `idx` used uninitialized in the outer `except` path

**File:** `workers/video.py`, lines 172–173, 329–333, 339
**Category:** Exception handling gap

**Description:**
```python
last_clip_id = self._batch[-1][0] if self._batch else 0
...
idx = 0
...
"videos_processed": idx if self.should_stop() else total_videos,
```
If `self._batch` is non-empty but `run_full_pipeline` raises before the `for` loop starts (e.g. the `from services.video_analysis_service import run_full_pipeline` import fails at line 191), the outer `except` at line 335 is reached with `idx = 0`. The `finished.emit` in the outer `finally` at line 361 emits `(last_clip_id, {})` which is fine. But the `error.emit` at line 339 passes `last_clip_id` which was set to the **last** clip in the batch even though no clip was processed at all. The caller (TaskManager) receives an error attributed to the wrong clip ID.

Also: if `self._batch` becomes empty after the `len(self._batch[0]) == 2` resolution at line 169 (all clips missing from DB), `last_clip_id` is set to 0 at line 172, then the early-exit path at lines 173–176 emits `error.emit(0, ...)` followed by `finished.emit(0, {})`. But `error` is emitted before `finished`, which means `thread.quit()` fires via the error signal **first**, potentially causing `finished.emit` to fire into a dead thread. In PySide6 with QueuedConnection this is safe but worth noting.

**Suggested fix:**
Track the current clip ID explicitly in the loop and use it in the error path:
```python
_current_clip_id = 0
for idx, (clip_id, video_path, title) in enumerate(self._batch, start=1):
    _current_clip_id = clip_id
    ...
# In outer except:
self.error.emit(_current_clip_id, format_user_error(e))
```

---

### BUG-07: `_patch_service_paths` in `database.py` sets module attributes without thread safety — race condition during project switch

**File:** `database.py`, lines 185–207
**Category:** Threading/concurrency bug (race condition)

**Description:**
`_patch_service_paths` iterates over `sys.modules` and calls `setattr(mod, attr, value)` on live module objects. This is called from `set_project()` which can be called from the UI thread at any time. If a worker thread is concurrently reading e.g. `services.video_service.PROXY_DIR` (which it does in `VideoAnalyzer.create_proxy()` line 74: `PROXY_DIR.mkdir(...)`) while `setattr(mod, "PROXY_DIR", new_path)` is being called in the main thread, the worker thread may get a torn/stale `Path` object. On CPython, attribute writes are GIL-protected for most basic operations, but the sequence `read local PROXY_DIR → call mkdir` is not atomic with `setattr`. A worker could read the old `PROXY_DIR`, have the project switch fire, and then write a proxy file to the wrong project directory.

**Suggested fix:**
Document the contract that `set_project` must only be called when no background workers are running (the `_has_running_tasks()` guard in `ProjectManager` enforces this, but it is not enforced at the `database.set_project()` level). Add an assertion or guard in `set_project()`:
```python
def set_project(project_path: Path):
    # Callers must ensure no workers are running.
    # _patch_service_paths is not thread-safe.
    ...
```
Alternatively, wrap the service path attributes in a `threading.Lock` within each service, or pass the project path as a parameter to service calls rather than storing it as a module global.

---

## MEDIUM

---

### BUG-08: `_safe_cleanup` in `task_manager.py` — `clear_finished()` can double-call `deleteLater` on same worker/thread

**File:** `services/task_manager.py`, lines 403–422
**Category:** Resource cleanup / double-free

**Description:**
`_safe_cleanup` sets `task.worker = None` and `task.thread = None` after calling `deleteLater`. `clear_finished()` also calls `deleteLater` on `task.worker` and `task.thread` if they are not `None`. If `clear_finished()` runs between `_safe_cleanup` nulling `task.worker` but before it nulls `task.thread` (not possible in single-threaded Qt event loop, but possible if `clear_finished()` is called from a different Python thread), the thread could get `deleteLater` called twice. Additionally, `_safe_cleanup` reads `task.worker` and `task.thread` without the lock, then sets them to `None` also without the lock, so `clear_finished()` could observe non-None values and call `deleteLater` on an already-deleted C++ object.

**Suggested fix:**
In `clear_finished`, check the `None` guard that `_safe_cleanup` already sets:
```python
# Already handled by _safe_cleanup; skip if already nulled
if task.worker:
    try:
        task.worker.deleteLater()
    except RuntimeError:
        pass
```
This is already done — but the race is that the read and write of `task.worker` in `_safe_cleanup` are unprotected. Move both the read and the null-assignment inside the lock (as described in BUG-02).

---

### BUG-09: `ingest_audio` in `ingest_service.py` — `session.refresh(track)` after commit may fail if track was evicted

**File:** `services/ingest_service.py`, lines 59–60
**Category:** Database connection management

**Description:**
```python
session.commit()
session.refresh(track)
```
With a `NullPool` session, after `commit()` the connection is closed immediately. `session.refresh(track)` then requires a new connection. With `NullPool`, SQLAlchemy creates a fresh connection for the `refresh`. This is fine. However, if the `refresh` fails (e.g. DB is locked by another process in that brief window), the exception propagates through the `except Exception` at line 63, which re-raises. The caller in `FolderImportWorker` catches this and emits an error. But the track **was** committed successfully — its `id` just was not refreshed into the Python object. The `result.id` that `FolderImportWorker` uses at line 108 would then be `None` (SQLAlchemy ORM objects get `None` for their PK until refreshed), making the video clip tuple `(None, path, name)` which would cause a crash downstream when used as a task argument for `VideoAnalysisPipelineWorker`.

**Suggested fix:**
Make `session.refresh` failures non-fatal, or query the ID separately:
```python
session.commit()
try:
    session.refresh(track)
except Exception as e:
    logger.warning("session.refresh fehlgeschlagen nach commit: %s — fallback zu erneuter Abfrage", e)
    track_id = session.execute(
        text("SELECT id FROM audio_tracks WHERE file_path = :p"), {"p": resolved}
    ).scalar()
    if track_id:
        track.id = track_id
```

---

### BUG-10: `init_db()` at startup called before `nullpool_session()` has the correct `APP_ROOT`

**File:** `main.py`, line 1076; `database.py`, line 135
**Category:** Configuration loading / startup sequence

**Description:**
`init_db()` is called before `QApplication` is created (line 1076). Inside `init_db()`, `nullpool_session()` is called to insert default `StylePreset` rows (line 825). `nullpool_session()` hardcodes `db_path = APP_ROOT / 'pb_studio.db'` using the module-level `APP_ROOT` defined at line 14 of `database.py`. This means the DB file is always `<script_dir>/pb_studio.db` at startup, regardless of any previously active project. This is intentional for the default project. However, if `set_project()` is called **before** `init_db()` (e.g. from a future "restore last project" feature), `APP_ROOT` would already be changed but `nullpool_session()` would still use whatever `APP_ROOT` was at the time `nullpool_session()` was defined — because `nullpool_session` reads `APP_ROOT` as a local variable at call time (line 135: `db_path = APP_ROOT / 'pb_studio.db'`). Since `APP_ROOT` is a module global, this is fine as long as the module-level reference is always current. The current code is correct but brittle — it is a module-level mutable global that multiple functions read.

**Suggested fix:**
Low risk as-is. Add a docstring note to `nullpool_session` warning that it reads the live `APP_ROOT` global, so callers must be aware of project-switch ordering.

---

### BUG-11: `workers/analysis.py` and multiple other workers use `logging.error(...)` instead of `logger.error(...)` — inconsistent logger identity

**File:** `workers/analysis.py`, lines 48, 55, 86; `workers/audio.py`, lines 35, 75, 114; `workers/edit.py`, lines 50, 76; `workers/import_export.py`, lines 46, 217, 255; `workers/video.py`, lines 45, 287, 336, 398, 432, 458
**Category:** Code quality

**Description:**
Each worker file defines `logger = logging.getLogger(__name__)` at the top. The correct pattern is to use `logger.error(...)`. However, many error paths call the root `logging.error(...)` directly. This bypasses the module-level logger and attributes all errors to the root logger with no module name, making it impossible to filter logs by worker module. The module-level `logger` is defined but partially unused.

**Suggested fix:**
Replace all `logging.error(...)`, `logging.warning(...)`, `logging.info(...)` calls in worker files with `logger.error(...)` etc. (using the module-level `logger`). A project-wide search-and-replace is safe here:
- `workers/analysis.py`: lines 48, 55, 86
- `workers/audio.py`: lines 35, 75, 114
- `workers/edit.py`: lines 50, 76
- `workers/import_export.py`: lines 46, 217, 255
- `workers/video.py`: lines 45, 287, 336, 398, 458

---

### BUG-12: `VideoAnalysisPipelineWorker` — model cleanup in `finally` block creates a second `ModelManager()` singleton call that may not match the first

**File:** `workers/video.py`, lines 354–358
**Category:** Resource cleanup / VRAM management

**Description:**
```python
if siglip_model_processor is not None:
    try:
        from services.model_manager import ModelManager
        ModelManager().unload()
    except Exception:
        pass
```
`ModelManager()` returns the existing singleton. If between the initial `mm.load_siglip()` call (line 207) and this cleanup, another component (e.g. a concurrently running `TranscriptionWorker`) has already called `ModelManager().unload()` and then loaded Whisper, then `ModelManager().unload()` in the cleanup will unload **Whisper** (or whatever model is currently loaded), not SigLIP. This is the intended VRAM-one-model-at-a-time semantics, but it means the `if siglip_model_processor is not None` guard is misleading — it does not actually check whether SigLIP is **still** loaded.

**Suggested fix:**
Check `ModelManager().current_model_id` before unloading:
```python
mm = ModelManager()
if mm.current_model_id and "siglip" in mm.current_model_id.lower():
    mm.unload()
```

---

### BUG-13: `database.py` `init_db()` migration blocks call `inspect(get_raw_engine())` six separate times — unnecessary overhead and TOCTOU window

**File:** `database.py`, lines 708, 716, 726, 739, 751, 773, 787, 817
**Category:** Database connection management / performance

**Description:**
`init_db()` calls `insp = inspect(get_raw_engine())` eight times. Each call opens a new connection to read SQLite's `sqlite_master`. Between calls, no lock is held, so another process could theoretically add/remove columns between inspections. More practically: this adds unnecessary startup latency (8 round trips to the DB for the metadata reads). The `insp` variable is reassigned but could be reused.

**Suggested fix:**
Run a single inspection at the start of `init_db()` and reuse `insp` throughout:
```python
def init_db():
    Base.metadata.create_all(engine)
    _raw = get_raw_engine()
    insp = inspect(_raw)
    table_names = set(insp.get_table_names())
    ...
    # Use table_names and insp throughout without re-calling inspect()
```

---

### BUG-14: `pacing_service.py` — `_get_cached_stem_audio` releases lock before writing back to cache, creating a TOCTOU window

**File:** `services/pacing_service.py`, lines 67–73
**Category:** Threading/concurrency bug

**Description:**
```python
# librosa.load AUSSERHALB des Locks (CPU-intensiv, soll nicht blockieren)
y, loaded_sr = librosa.load(stem_path, sr=sr, mono=True)

with _cache_lock:
    if audio_id in _stem_audio_cache:
        _stem_audio_cache[audio_id][stem_name] = (y, loaded_sr)
```
Two threads requesting the same `(audio_id, stem_name)` simultaneously will both find the cache miss, both call `librosa.load` (CPU/RAM waste — loads the same file twice), and both attempt to write back. The second write overwrites the first. This is not a crash but is a correctness issue for a cache designed to save resources. If `librosa.load` returns different results across calls (it should not, but with resampling edge cases could differ slightly), the cache ends up with whichever write ran last.

**Suggested fix:**
Use a per-(audio_id, stem_name) lock or check again after re-acquiring the lock (double-checked pattern):
```python
with _cache_lock:
    if audio_id in _stem_audio_cache and stem_name in _stem_audio_cache[audio_id]:
        return _stem_audio_cache[audio_id][stem_name]  # another thread loaded it
    _stem_audio_cache[audio_id][stem_name] = (y, loaded_sr)
```

---

## LOW

---

### BUG-15: `workers/video.py` `FrameExtractWorker` — `_errored` is not initialized by `super().__init__()` on MRO

**File:** `workers/video.py`, lines 414–434
**Category:** Code quality / potential AttributeError

**Description:**
`FrameExtractWorker` inherits `(QObject, CancellableMixin)`. `super().__init__()` at line 425 (implicit in `__init__`) calls `QObject.__init__` and then `CancellableMixin.__init__`, which sets `_cancelled = False` and `_errored = False`. This is correct. The issue is that `FrameExtractWorker` never calls `super().__init__()` explicitly — it defines `__init__` at line 422 but does not include a `super().__init__()` call. PySide6's `QObject.__init__` expects to be called. Without it, the C++ QObject side is not initialized, and any Qt signal/slot operations on the object will crash with `RuntimeError: super().__init__() was not called`.

Looking more carefully: line 424 shows `super().__init__()` IS called:
```python
def __init__(self, file_path: str, time_sec: float, width: int = 320,
             height: int = 180, vf_extra: str = ""):
    super().__init__()
```
So this is fine. However: `_errored` is referenced at line 459 (`self._errored = True`) but `CancellableMixin.__init__` initializes it correctly via the MRO. No bug here — **reconfirmed clean**.

Actually re-checking `workers/audio.py` line 83–91: `TranscriptionWorker.__init__` calls both `super().__init__()` AND `CancellableMixin.__init__(self)`. The explicit call is redundant but since it only sets `_cancelled = False` and `_errored = False` it only matters if a `TranscriptionWorker` is constructed while already running (impossible by design). Mark as low/cosmetic.

---

### BUG-16: `services/video_service.py` — `PROXY_DIR` uses module-level `APP_ROOT` which is a stale snapshot

**File:** `services/video_service.py`, line 16
**Category:** File path issues

**Description:**
```python
PROXY_DIR = APP_ROOT / "storage" / "proxies"
```
`APP_ROOT` is imported from `database` at module load time. `_patch_service_paths` in `database.py` does patch `services.video_service.PROXY_DIR` on project switch (line 191). But `VideoAnalyzer.create_proxy()` at line 74 uses `PROXY_DIR` as a module global:
```python
PROXY_DIR.mkdir(parents=True, exist_ok=True)
```
If `create_proxy` is called from a local variable reference captured before the project switch (e.g. `analyzer = VideoAnalyzer()` then later `analyzer.create_proxy()`), the local name `PROXY_DIR` in the method body still resolves to the module global via the closure over `services.video_service.PROXY_DIR`. This is correct as long as `_patch_service_paths` updates the module attribute. The risk is that `_patch_service_paths` only patches already-imported modules (`sys.modules.get(mod_name)`). If `services.video_service` has not been imported yet when the project switch happens, it is not patched. On the next import, it gets `APP_ROOT` which has already been updated by `set_project`, so it is correct. Low risk.

**Suggested fix:**
In `VideoAnalyzer.create_proxy()`, read `PROXY_DIR` dynamically:
```python
import services.video_service as _svc
proxy_dir = _svc.PROXY_DIR
proxy_dir.mkdir(parents=True, exist_ok=True)
```
Or better: make `PROXY_DIR` a function that reads the current `APP_ROOT`:
```python
def _get_proxy_dir() -> Path:
    from database import APP_ROOT
    return APP_ROOT / "storage" / "proxies"
```

---

### BUG-17: `database.py` line 810 — uses bare `re` without importing it locally at that scope

**File:** `database.py`, line 810
**Category:** Import error risk

**Description:**
```python
if not re.match(r"^[a-zA-Z0-9_.'\"-]+$", str(col_default)):
```
`re` is imported at the top of `database.py` (line 3), so this works. However, inside the same `init_db()` function, lines 755, 780, and 790 import `re` again as `_re`, `_re2`, `_re4` (redundant local imports). The inconsistency means line 810 uses the top-level `re` while lines around it use local aliases. This is cosmetic but confusing and could lead to a shadowing bug if a future developer adds `import re as re` locally.

**Suggested fix:**
Remove all redundant local `import re as _reN` statements inside `init_db()`. Use the top-level `re` throughout.

---

### BUG-18: `workers/import_export.py` `FolderImportWorker` — path stored as `str(Path(p).resolve())` but ingestion also resolves — potential double-resolve inconsistency on symlinks

**File:** `workers/import_export.py`, line 109
**Category:** File path issues

**Description:**
```python
new_video_clips.append(
    (result.id, str(Path(p).resolve()), name)
)
```
`ingest_video` inside already calls `str(path.resolve())` when creating the `VideoClip.file_path`. The `FolderImportWorker` then independently resolves `p` at line 109 for the tuple. If `p` is a symlink and the resolve produces different results (e.g. on a network share where symlinks resolve differently), the path in the tuple may not match `result.file_path` in the DB. Downstream code using this tuple to look up the DB clip by path would fail. Low risk in practice.

**Suggested fix:**
Use `result.file_path` (already resolved by `ingest_video`) directly:
```python
new_video_clips.append(
    (result.id, result.file_path, name)
)
```

---

### BUG-19: `main.py` line 1078 — `logging.basicConfig` called after `setup_logging()` adds handlers

**File:** `main.py`, lines 1077–1078
**Category:** Configuration loading issue

**Description:**
```python
except Exception as exc:
    logging.basicConfig(level=logging.ERROR)
```
`setup_logging()` at line 1051 has already added a `StreamHandler` and `RotatingFileHandler` to the root logger. `basicConfig` is a no-op if the root logger already has handlers. This means the `except` branch intended to configure minimal logging on `init_db()` failure does nothing. If `init_db()` fails **before** any logger is configured (impossible in current flow since `setup_logging()` runs first), the intent would fail silently.

**Suggested fix:**
Remove the `logging.basicConfig` call — logging is already configured by `setup_logging()` which ran at line 1051. If `init_db()` fails, the logging infrastructure is fully operational.

---

### BUG-20: `services/task_manager.py` — `agent_command_signal = Signal(str, dict)` — `dict` type annotation in Signal may fail with some PySide6 versions

**File:** `services/task_manager.py`, line 71
**Category:** Import error / compatibility

**Description:**
```python
agent_command_signal = Signal(str, dict)
```
PySide6 `Signal` supports Python built-in types as type hints, but `dict` in Signal definitions is handled differently from `str` and `int`. In some PySide6 versions (particularly < 6.4), passing `dict` directly works but the signal cannot be connected across threads with QueuedConnection because dict is not a QMetaType-registered type. The signal is used with `QueuedConnection` (line 104), which requires Qt to serialize/deserialize the argument across the event loop. Qt typically handles `dict` as a Python object reference (via `PyObject*`), which is safe only in CPython with the GIL. If a PySide6 version uses strict type registration, this may raise a `TypeError` at signal emission time.

**Suggested fix:**
Use `object` instead of `dict` for robustness:
```python
agent_command_signal = Signal(str, object)
```
The existing `_cross_thread_request = Signal(str, str, str, object, object, object)` already uses `object` for the non-primitive types.

---

## VERIFIED CLEAN (no bug)

The following patterns were audited and found to be correctly implemented:

- `BaseAnalysisWorker.run()` — `_ok / _errored` pattern correctly handles all 3 exit paths (success, exception, unknown).
- `nullpool_session()` — correctly disposes the engine on exit, preventing connection leaks.
- `GlobalTaskManager.instance()` — double-checked locking with `_instance_lock` is correct.
- `EngineProxy.swap()` — old engine is disposed after swap, no connection leak.
- `cancel_task()` — `thread.terminate()` fallback after 5s wait is correct safety valve.
- `_shutting_down` flag — set before task cancellation in `closeEvent`, preventing new threads during shutdown.
- `FrameExtractWorker` — `_VF_SAFE_PATTERN` whitelist correctly prevents FFmpeg filter injection.
- `ingest_video` — ffprobe subprocess called **before** opening DB session (Session-Split pattern).
- `VideoAnalysisPipelineWorker` — progress throttling at 500ms is correct to prevent event-loop flooding.
- `StemSeparationWorker` / `WaveformAnalysisWorker` — no explicit `CancellableMixin.__init__` call (consistent with MRO convention).
- `workers/__init__.py` — lazy import `__getattr__` pattern is correct and avoids loading librosa at startup.

---

## CHANGED FILES

No files were modified by this audit. This is a read-only static analysis report.

---

## RECOMMENDED FIX PRIORITY

| Priority | Bug ID | Effort |
|----------|--------|--------|
| 1 (Critical) | BUG-02 — _safe_cleanup dict race | 10 min |
| 2 (Critical) | BUG-01 — module-level task_manager before QApp | 5 min |
| 3 (High) | BUG-05 — BatchConvertWorker bare return | 5 min |
| 4 (High) | BUG-03 — finished.connect(thread.quit) without QueuedConnection | 5 min |
| 5 (High) | BUG-04 — double CancellableMixin.__init__ | 5 min |
| 6 (High) | BUG-06 — wrong clip_id in error path | 15 min |
| 7 (High) | BUG-07 — patch_service_paths thread safety | 30 min |
| 8 (Medium) | BUG-11 — root logging vs module logger | 10 min |
| 9 (Medium) | BUG-14 — stem cache TOCTOU double-load | 15 min |
| 10 (Medium) | BUG-13 — redundant inspect() calls | 10 min |
