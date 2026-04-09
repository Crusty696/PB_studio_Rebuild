# Audit Report: PB Studio Rebuild

**Date:** 2026-04-09
**Auditor:** Gemini CLI via /audit-full
**Mode:** Full Audit (Security, Architecture, Dependencies)
**Scope:** Entire codebase

## Summary

| Metric | Value |
|--------|-------|
| Files loaded | ~120 |
| Lines of code | ~70,000 |
| Estimated tokens | ~500,000 |
| Context utilization | ~50% |

### Findings Overview

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 3 |
| MEDIUM | 3 |
| LOW | 1 |
| **Total** | **8** |

**Overall Health Score: 6/10**

## Findings

### CRITICAL

#### F-001: VRAM Collision with External Ollama Instance
- **Category:** Stability / Resource Management
- **File(s):** `services/model_manager.py`
- **Description:** `ModelManager._pause_ollama_if_active()` only sets a software flag in the client but does not force Ollama to unload models from VRAM. On 6GB GPUs, an active Ollama model (e.g., Llama 3) occupying 4-5GB VRAM will cause local model loads (SigLIP, Demucs) to fail or freeze the system.
- **Impact:** System freezes or crashes during AI analysis if the user has Ollama running in the background.
- **Evidence:**
  ```python
  def _pause_ollama_if_active(self):
      # Sets a flag but doesn't release GPU memory
      self._ollama_paused = True 
  ```
- **Remediation:** Send an explicit unload command to Ollama before loading local models.
  ```python
  def _pause_ollama_if_active(self):
      import requests
      requests.post(f"{self.url}/api/generate", json={"model": self.current_model, "keep_alive": 0})
  ```
- **Effort:** Low

### HIGH

#### F-002: Resource Leaks on Thread Termination
- **Category:** Reliability / Resource Management
- **File(s):** `services/task_manager.py`
- **Description:** `GlobalTaskManager` calls `thread.terminate()` after a 5s timeout. This is an "unsafe" termination that skips `finally` blocks in Python, preventing `ModelManager.unload()` from being called.
- **Impact:** VRAM remains occupied by the "zombie" task, causing subsequent tasks to fail with Out-of-Memory (OOM).
- **Remediation:** Implement a cooperative cancellation check (`should_stop`) in all loops and use `terminate()` only as a last resort, followed by a global `ModelManager().unload()` safety call.
- **Effort:** Medium

#### F-003: UI-Blocking Shutdown Process
- **Category:** Architecture / UX
- **File(s):** `main.py`
- **Description:** `PBWindow.closeEvent` waits synchronously for background threads (`thread.wait(10000)`). If multiple threads are active, the UI freezes for up to 10-30 seconds before closing.
- **Impact:** Application appears to have crashed on exit; user may force-kill, potentially corrupting the database.
- **Remediation:** Implement an asynchronous shutdown dialog or hide the window immediately while cleaning up threads in the background.
- **Effort:** Medium

#### F-004: Inference-Phase Race Condition
- **Category:** Concurrency
- **File(s):** `services/model_manager.py`, `workers/video.py`
- **Description:** `GPU_LOAD_LOCK` protects the loading of models, but not the actual inference. Multiple threads can trigger inference simultaneously on already loaded models, exceeding VRAM limits during computation.
- **Impact:** Random OOM crashes during heavy multi-track processing.
- **Remediation:** Introduce a `GPU_EXECUTION_LOCK` or extend `GPU_LOAD_LOCK` to cover the inference block.
- **Effort:** Medium

### MEDIUM

#### F-005: Scalability Bottleneck in Vector Search
- **Category:** Performance
- **File(s):** `services/vector_db_service.py`
- **Description:** `VectorDBService.search` re-reads all embeddings from SQLite on every query.
- **Impact:** Latency increases significantly as the library grows (>1000 clips).
- **Remediation:** Implement an in-memory cache for the embedding matrix.
- **Effort:** Low

#### F-006: UI Lag during Media Table Refresh
- **Category:** UI Performance
- **File(s):** `ui/controllers/media_table.py`
- **Description:** Rebuilds entire `QTableWidget` items on every update instead of using a Model/View architecture (`QAbstractTableModel`).
- **Impact:** Noticeable stutters when importing many files.
- **Remediation:** Refactor to `QSortFilterProxyModel` + `QAbstractTableModel`.
- **Effort:** High

#### F-007: Inconsistent ID Logic in Vector DB
- **Category:** Data Integrity
- **File(s):** `services/vector_db_service.py`
- **Description:** Single `add_embedding` uses `clip_id`, while `add_embeddings_batch` uses `clip_id * 1M + scene_index`.
- **Impact:** Manual deletions or updates might fail to find the correct records.
- **Remediation:** Standardize on the composite ID logic.
- **Effort:** Low

### LOW

#### F-008: Missing Audio Cancellation Checks
- **Category:** Reliability
- **File(s):** `workers/audio_analysis.py`
- **Description:** Analysis loops lack frequent `should_stop()` checks compared to video workers.
- **Impact:** Slow response to user cancellation requests.
- **Remediation:** Add `if self.should_stop(): break` to main audio processing loops.
- **Effort:** Low

## Architecture Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│      UI      │───▶ │ Controllers  │───▶ │   Workers    │ (QThreads)
└──────────────┘     └──────────────┘     └──────────────┘
                             │                    │
                             ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │   Services   │◀────│ ModelManager │ (GPU Lock)
                     └──────────────┘     └──────────────┘
                             │
                             ▼
                     ┌──────────────┐
                     │  Databases   │ (SQLite WAL)
                     └──────────────┘
```

**Violations:**
- `WorkerDispatcherController` duplicates some logic from `GlobalTaskManager`.
- UI Controllers sometimes call heavy `refresh` methods directly instead of emitting signals.

## Dependency Summary

| Package | Current | Latest | Status | Risk |
|---------|---------|--------|--------|------|
| torch | 2.4.1+cu118 | 2.5.1 | Stale | Low |
| PySide6 | 6.7.2 | 6.8.1 | Stale | Medium (Type strictness) |
| sentencepiece | 0.2.1 | 0.2.1 | Current | Low |

## Recommendations

### Immediate (Priority 1)
1. **Fix F-001:** Implement explicit Ollama unload to prevent 6GB VRAM collisions.
2. **Fix F-002:** Replace unsafe `thread.terminate()` with cooperative shutdown.

### Short-term (Priority 2)
1. **Fix F-003:** Refactor shutdown to be non-blocking.
2. **Fix F-005:** Add caching to `VectorDBService`.
3. **Fix F-007:** Standardize ID logic in Vector DB.

### Long-term (Backlog)
1. **Fix F-006:** Migrate Media Table to Model/View architecture for performance.
2. **Fix F-004:** Implement global GPU Execution Lock.

## Appendix

### Methodology
- Single-pass analysis focusing on VRAM constraints and thread safety.
- Cross-file audit of AI pipelines and resource cleanup patterns.
- Stress-testing hypotheses regarding 6GB GPU limitations.
