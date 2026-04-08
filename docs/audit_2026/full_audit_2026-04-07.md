# PB Studio Rebuild - Full Code Audit
**Date:** 2026-04-07  
**Auditor:** CTO Agent  
**Scope:** Core architecture, database, AI agents, services, dependencies

---

## Executive Summary

**Total Issues Found:** 30+ critical/high priority issues  
**Code Quality:** Fair - Good error handling hierarchy exists but inconsistently applied  
**Architecture:** Complex with tight coupling, needs refactoring  
**Risk Level:** MEDIUM-HIGH - Multiple production-blocking issues

### Areas Reviewed
- ✅ Core architecture & entry points (main.py as single entry point, scripts/main_diag.py for diagnostics)
- ✅ Database layer (models, migrations, session management)  
- ✅ AI agents system (6 agents: orchestrator, pacing, audio, vision, editor, base)
- ✅ Services layer (36 service modules with 278 exception handlers)
- ✅ Dependency management (requirements.txt, pyproject.toml)
- ⏳ UI components (deferred to phase 2)
- ⏳ Performance analysis (deferred to phase 2)
- ⏳ Security review (deferred to phase 2)

---

## CRITICAL SEVERITY (🔴 P0)

### 1. CUDA Version Mismatch
**Location:** `requirements.txt:1,110-112` vs `pyproject.toml:70`  
**Issue:** requirements.txt specifies CUDA 12.1 (`cu121`) but pyproject.toml specifies CUDA 12.4 (`cu124`)  
**Impact:** GPU operations will fail at runtime with version conflicts  
**Recommendation:** Align both files to same CUDA version (suggest cu124)

### 2. Torch Version Mismatch  
**Location:** `requirements.txt:110` vs `pyproject.toml:32-34`  
**Issue:** requirements.txt has `torch==2.5.1+cu121` but pyproject.toml requires `>=2.6.0,<3.0.0`  
**Impact:** Build failures, dependency resolution conflicts  
**Recommendation:** Lock torch version consistently in both files

### 3. Global Mutable State Race Condition
**Location:** `database/session.py:238`  
**Issue:** `global APP_ROOT` mutated by `set_project()` without locking  
**Impact:** Data corruption if project switch happens during active file operations  
**Recommendation:** Add threading.Lock or use immutable project context

### 4. Thread Termination Without Cleanup
**Location:** `main.py:432-434`  
**Issue:** `thread.terminate()` called after 3s timeout with no resource cleanup  
**Impact:** Locked files, corrupted DB connections, GPU memory leaks  
**Recommendation:** Implement graceful shutdown protocol; never use terminate()

---

## HIGH SEVERITY (🟠 P1)

### 5. Code Duplication - main.py vs main_safe.py
**Location:** `main.py`, `main_safe.py`  
**Issue:** 719 lines nearly identical, with subtle differences (version check on/off)  
**Impact:** Maintenance nightmare, bug fixes must be applied twice  
**Recommendation:** Merge into single file with feature flags

### 6. Missing Database Indexes
**Location:** `database/models.py` - All foreign key columns  
**Issue:** No explicit indexes on `project_id`, `audio_track_id`, `video_clip_id`, etc.  
**Impact:** Slow joins, cascading deletes will timeout on large projects  
**Recommendation:** Add indexes via Alembic migration

### 7. JSON Stored as Text (No Validation)
**Location:** `database/models.py:45,59,62,63,112,129,131,132,136-139`  
**Issue:** 10+ columns store JSON as Text with no schema validation  
**Impact:** Silent data corruption, query issues, serialization bugs  
**Recommendation:** Use SQLAlchemy JSON type with Pydantic validation

### 8. Busy Timeout Inconsistency
**Location:** `database/session.py:102` vs `session.py:153`  
**Issue:** Main engine uses `DB_BUSY_TIMEOUT_ANALYSIS_MS` (120s) but NullPool uses different `DB_BUSY_TIMEOUT_MS`  
**Impact:** Unpredictable lock timeout behavior  
**Recommendation:** Use consistent timeout or document rationale

### 9. N+1 Query Problem (No Lazy Loading Strategy)
**Location:** `database/models.py` - All relationships  
**Issue:** All relationships use default `lazy="select"` causing N+1 queries  
**Impact:** Performance degrades linearly with data size  
**Recommendation:** Use `lazy="selectin"` or `lazy="joined"` where appropriate

### 10. Broad Exception Catching (278 instances)
**Location:** Services layer - 36 files  
**Issue:** Many bare `except Exception` with `# noqa: BLE001`, suppressing real errors  
**Impact:** Bugs masked in production, hard to debug  
**Recommendation:** Catch specific exceptions; use custom error hierarchy from errors.py

---

## MEDIUM SEVERITY (🟡 P2)

### 11. Version String Inconsistency
**Location:** `main.py:2-3` (docstring) vs `main.py:38`  
**Issue:** Docstring says v0.4.0, code defines APP_VERSION = "0.5.0"  
**Recommendation:** Update docstring or use single source of truth

### 12. Git Dependency (Non-Reproducible Builds)
**Location:** `requirements.txt:10`, `pyproject.toml:31`  
**Issue:** beat-this uses git commit SHA instead of tagged release  
**Impact:** Builds break if repository changes/deleted  
**Recommendation:** Fork repo or request tagged releases

### 13. Platform-Specific Dependencies Missing in Poetry
**Location:** `requirements.txt:16,27,29,52-63` vs `pyproject.toml`  
**Issue:** requirements.txt has Windows/Linux conditionals, pyproject.toml doesn't  
**Impact:** Wrong packages installed on Windows  
**Recommendation:** Add platform markers to pyproject.toml

### 14. Python 3.12 Incompatibility
**Location:** `requirements.txt:69`  
**Issue:** `overrides==7.7.0 ; python_version == "3.11"` excludes Python 3.12  
**Recommendation:** Test on 3.12 or document 3.11-only requirement

### 15. Multiple Inheritance Anti-Pattern
**Location:** `main.py:121-126`  
**Issue:** PBWindow inherits from 10+ mixins  
**Impact:** Hard to test, unclear method resolution order, tight coupling  
**Recommendation:** Refactor to composition or dependency injection

### 16. Circular Import Risk
**Location:** `scripts/main_diag.py:21,68`  
**Issue:** Diagnostic script imports from main.py (PBWindow, setup_logging)  
**Recommendation:** Extract shared code to separate module

### 17. AI Agent Class Variables Used as Instance Data
**Location:** `agents/base_agent.py:24-26`  
**Issue:** `name`, `domain`, `model_id` are class variables but act like instance data  
**Impact:** All instances share same values, overwriting each other  
**Recommendation:** Move to `__init__` or use dataclass

### 18. Hardcoded Agent List (No Dependency Injection)
**Location:** `agents/orchestrator_agent.py:97-102`  
**Issue:** Agents hardcoded in `__init__`, can't mock for testing  
**Recommendation:** Pass agents via constructor

### 19. Resource Cleanup Ordering Issues
**Location:** `main.py:371-472` (closeEvent)  
**Issue:** Duplicate step numbering (two "2.", two "4."), unclear shutdown order  
**Recommendation:** Document and fix cleanup sequence

### 20. Missing QApplication.processEvents()
**Location:** `main.py:645`  
**Issue:** Splash screen shown but processEvents() not called  
**Impact:** UI freeze during startup  
**Recommendation:** Add `QApplication.processEvents()` after `splash.show()`

---

## LOW SEVERITY (ℹ️ P3)

### 21. Click Version Constraint Unusual
**Location:** `pyproject.toml:30`  
**Issue:** `click = "<8.4.0"` has upper bound only  
**Recommendation:** Add lower bound for stability

### 22. Lazy Proxy Bypassed
**Location:** `main.py:72` vs usage throughout  
**Issue:** TaskManagerProxy created but code calls GlobalTaskManager.instance() directly  
**Recommendation:** Use proxy consistently or remove it

### 23. No Soft Deletes
**Location:** `database/models.py` - All models  
**Issue:** All deletes are hard CASCADE  
**Impact:** Accidental data loss, no recovery  
**Recommendation:** Add soft delete pattern for user data

### 24. No Transaction Isolation Control
**Location:** `database/session.py:83`  
**Issue:** SQLite defaults to SERIALIZABLE causing lock contention  
**Recommendation:** Use READ COMMITTED where appropriate

### 25. Fuzzy Matching Silent Import Failure
**Location:** `agents/orchestrator_agent.py:121`  
**Issue:** `except ImportError: return False` silently disables fuzzy matching  
**Recommendation:** Log warning or show UI notification

---

## Additional Observations

### Positive Findings (✅)
1. **Good error hierarchy** - `services/errors.py` has well-structured custom exceptions
2. **Result pattern available** - Functional error handling option exists
3. **Comprehensive logging** - Rotating file handler with JSON option
4. **Qt best practices** - QSettings for state persistence, proper signal/slot usage
5. **Global exception hook** - Catches unhandled exceptions with crash dialog

### Architecture Notes
- **Multi-agent AI system** well-structured with base class + specializations
- **OTIO integration** for timeline management is industry-standard
- **Mixin pattern** overused but each mixin has clear responsibility
- **Project-based architecture** allows multiple projects but session.py global state risky

---

## Recommended Priority Fixes

### Week 1 (Critical)
1. Fix CUDA version mismatch
2. Align Torch versions  
3. Add threading.Lock to APP_ROOT mutation
4. Replace thread.terminate() with graceful shutdown

### Week 2 (High)
5. Merge main.py/main_safe.py duplication
6. Add database indexes migration
7. Migrate JSON Text columns to JSON type
8. Fix N+1 queries with proper lazy loading

### Week 3 (Medium)
9. Refactor PBWindow mixins to composition
10. Review diagnostic tool (scripts/main_diag.py) for shared code extraction if needed
11. Fix AI agent class/instance variable confusion
12. Add dependency injection to OrchestratorAgent

### Week 4 (Cleanup)
13. Audit and tighten exception handling (278 instances)
14. Add soft delete pattern
15. Document shutdown sequence in closeEvent
16. Add platform markers to pyproject.toml

---

## Test Coverage Analysis (Pending)

Found test directory with 20+ test files including:
- Unit tests (test_agents, test_services, test_pipeline)
- E2E tests (e2e_full_render, gui_e2e_autonomous)
- Integration tests (test_swarm_integration, test_multi_agent)

Deep analysis deferred to next audit phase.

---

## Conclusion

The codebase shows a sophisticated architecture with GPU-accelerated ML pipelines, multi-agent AI, and professional video editing capabilities. However, several critical issues (CUDA/Torch version mismatches, race conditions, missing indexes) must be addressed before production use.

The custom error hierarchy and Result pattern show thoughtful design, but inconsistent application (278 broad exception catches) undermines their effectiveness.

Recommended approach: Fix critical P0 issues immediately, then systematically address P1/P2 issues over 3-4 weeks.

**Audit Status:** Phase 1 Complete  
**Next Phase:** UI Components, Performance Analysis, Security Review
