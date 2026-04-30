# Full App Green Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring PB Studio Rebuild from the 2026-04-29 audit state (`6 failed, 1390 passed, 36 skipped`) to a clean green local verification baseline.

**Architecture:** Fix the known red tests and open regression paths in dependency/test collection, proxy generation, GPU dtype handling, prompt classification, Studio-Brain pacing bridge, and local QA tooling. Keep fixes narrow, preserve the existing single-process PySide6/SQLAlchemy/ModelManager architecture, and verify each change with targeted tests before running the full suite.

**Tech Stack:** Python 3.10 Conda env `pb-studio`, PySide6, SQLAlchemy/SQLite, PyTorch CUDA 11.3, torchvision RAFT, SigLIP/transformers, pytest, bandit, ruff.

---

## Current Evidence

Audit report: `test-report/full-app-audit-2026-04-29.md`

Full pytest result:

```text
6 failed, 1390 passed, 36 skipped, 47 warnings in 793.47s
```

Known red/pending items to clear:

- `B-219`: proxy/WinError-32 path reopened by `tests/test_video_analysis_real.py::test_analyze_and_store`.
- `B-257`: `tests/spikes/test_usearch_install.py` collected but `usearch` missing.
- `B-258`: `tests/spikes/test_shot_type_prompts_consistency.py::test_inter_class_separation` fails.
- `B-259`: RAFT full-suite dtype/state contamination.
- `B-260`: Studio-Brain pacing bridge stub/drift.
- `B-261`: Ruff missing in active py310 environment.
- Existing E2E degradation items: `B-253`, `B-254`, `B-255`.
- Pending-live-verification items: `B-240` to `B-246`, `B-249`, `B-252`.

## File Structure

- Modify `pyproject.toml`: test collection markers/addopts for spike tests; optional ruff config if needed.
- Modify `requirements-py310-cu113.txt`: add local dev dependencies that are expected in this env.
- Modify `tests/spikes/test_usearch_install.py`: mark USearch spike explicitly or make it dependency-gated.
- Modify `services/pacing/shot_type_classifier.py`: sharpen prompt sets for `vocal_dominant` and `bass_dominant`.
- Modify `tests/spikes/test_shot_type_prompts_consistency.py`: keep threshold and failure message; no lowering unless evidence proves threshold impossible.
- Modify `services/video_analysis_service.py`: align RAFT input dtype with model dtype.
- Modify `services/model_manager.py`: keep RAFT dtype deterministic or expose expected dtype.
- Modify `services/video_service.py`: make proxy timeout/file-lock cleanup deterministic and testable.
- Add or modify `tests/test_services/test_video_proxy_timeout_regression.py`: short-timeout regression for `B-219`.
- Modify `services/pacing/bridge.py`: remove contradictory stub behavior or convert it into a real feature-switch helper.
- Modify `services/pacing_service.py`: route Studio-Brain pipeline through one official bridge path.
- Modify `tests/test_services/test_pacing_bridge_flag.py` and `tests/integration/test_pacing_bridge_snapshot.py`: update expectations for the unified bridge.
- Modify `tests/test_services/test_ollama_start_readiness.py`, `tests/test_services/test_pacing_strategist.py`, or add focused tests for `B-254`.
- Modify `workers/structure_enrichment.py` or `services/enrichment/style_bucket_clusterer.py`: gracefully handle `<8` embeddings.
- Modify `services/beat_analysis_service.py` and packaging files if fixing `B-253` directly.
- Update Brain-Bug pages under `C:\Brain-Bug\projects\pb-studio\wiki\bugs\` as each bug is fixed and verified.

## Green Definition

The plan is complete only when these commands have fresh passing output:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest -q --tb=short
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m bandit -r . -c bandit.yaml -ll
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m ruff check .
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' tests\e2e_functional_test.py --audio tests\fixtures\golden_mix\segment.wav --video tests\fixtures\clips_20 --report test-report\e2e-functional-report-post-green-fix.md
```

Expected:

```text
pytest: 0 failed
bandit: No issues identified
ruff: All checks passed
E2E: 18/18 OK, 0 FAIL
```

---

### Task 1: Baseline Branch And Dirty-Tree Safety

**Files:**
- Read: `git status --short`
- No code changes in this task.

- [ ] **Step 1: Capture current dirty state**

Run:

```powershell
git status --short
```

Expected: existing dirty files are visible. Do not revert unrelated user changes.

- [ ] **Step 2: Create a work branch**

Run:

```powershell
git switch -c codex/full-app-green-fix-2026-04-29
```

Expected: branch switch succeeds.

- [ ] **Step 3: Record baseline failures**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\spikes\test_usearch_install.py tests\spikes\test_shot_type_prompts_consistency.py::test_inter_class_separation -q --tb=short
```

Expected: `test_usearch_install.py` fails with missing `usearch`; shot-type separation fails at `0.784 > 0.78`.

---

### Task 2: Fix B-261 Local Ruff Availability

**Files:**
- Modify: `requirements-py310-cu113.txt`
- Test: local ruff import and `ruff check`

- [ ] **Step 1: Add Ruff to the py310 requirements**

Add under the existing Dev section in `requirements-py310-cu113.txt`:

```text
ruff>=0.9.0,<1.0.0
```

- [ ] **Step 2: Install the missing local dev dependency**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pip install 'ruff>=0.9.0,<1.0.0'
```

Expected: pip installs Ruff into the active `pb-studio` env.

- [ ] **Step 3: Verify Ruff is available**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m ruff --version
```

Expected: prints a Ruff version.

- [ ] **Step 4: Run configured lint**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m ruff check .
```

Expected: either clean output or concrete lint findings to fix before moving on.

- [ ] **Step 5: Update Brain-Bug**

Set `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-261-local-py310-env-missing-ruff.md` to `status: fixed` only after Step 4 is green.

---

### Task 3: Fix B-257 USearch Spike Collection

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/spikes/test_usearch_install.py`
- Test: `tests/spikes/test_usearch_install.py`

**Decision:** Treat USearch as an optional spike, not a required runtime dependency, because the production Service-E2E currently uses SQLite VectorDB successfully.

- [ ] **Step 1: Add a pytest marker for optional spike tests**

In `pyproject.toml`, extend `markers`:

```toml
markers = [
    "gui: marks tests that require a display (deselect with -m 'not gui')",
    "e2e: marks end-to-end tests (deselect with -m 'not e2e')",
    "slow: marks slow tests (deselect with -m 'not slow')",
    "spike: marks exploratory dependency or model experiments outside the default green suite",
]
```

- [ ] **Step 2: Gate USearch import with pytest.importorskip**

Change `tests/spikes/test_usearch_install.py` to:

```python
"""PRE-5 Spike: USearch wheel availability + smoke test on Win/Py3.10/3.11."""

import pytest
import numpy as np

pytestmark = pytest.mark.spike


def _usearch_index():
    return pytest.importorskip("usearch.index", reason="USearch spike dependency is optional")


def test_usearch_imports():
    usearch = pytest.importorskip("usearch", reason="USearch spike dependency is optional")
    assert hasattr(usearch, "__version__")


def test_usearch_index_basic():
    Index = _usearch_index().Index

    idx = Index(ndim=128, metric="cos")
    vec = np.random.rand(128).astype("float32")
    idx.add(0, vec)
    assert len(idx) == 1

    matches = idx.search(vec, count=1)
    assert matches.keys[0] == 0


def test_usearch_siglip_dim():
    """Smoke-test with PB Studio's actual embedding dimension (1152)."""
    Index = _usearch_index().Index

    idx = Index(ndim=1152, metric="cos")
    n = 100
    rng = np.random.default_rng(seed=42)
    vecs = rng.standard_normal((n, 1152)).astype("float32")
    for i, v in enumerate(vecs):
        idx.add(i, v)

    assert len(idx) == n
    matches = idx.search(vecs[0], count=5)
    assert matches.keys[0] == 0
```

- [ ] **Step 3: Verify targeted behavior**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\spikes\test_usearch_install.py -q --tb=short
```

Expected without USearch installed:

```text
3 skipped
```

- [ ] **Step 4: Verify default full suite no longer fails on USearch**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\spikes\test_usearch_install.py tests\test_services\test_bridge_wiring_smoke.py -q
```

Expected: no failures.

- [ ] **Step 5: Update Brain-Bug**

Set `B-257` to `fixed` and record targeted evidence.

---

### Task 4: Fix B-258 Shot-Type Prompt Separation

**Files:**
- Modify: `services/pacing/shot_type_classifier.py`
- Test: `tests/spikes/test_shot_type_prompts_consistency.py`

- [ ] **Step 1: Verify current red test**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\spikes\test_shot_type_prompts_consistency.py::test_inter_class_separation -q --tb=short
```

Expected:

```text
vocal_dominant vs bass_dominant: inter-sim 0.784 too high (>0.78)
```

- [ ] **Step 2: Sharpen vocal and bass prompt semantics**

Replace only `vocal_dominant` and `bass_dominant` prompt lists in `services/pacing/shot_type_classifier.py`:

```python
    "vocal_dominant": [
        "human singer face close-up with microphone",
        "expressive vocalist mouth and eyes portrait",
        "front-lit performer singing into microphone",
        "intimate concert singer portrait shot",
    ],
```

```python
    "bass_dominant": [
        "dark heavy subwoofer speaker cone close-up",
        "massive low-frequency sound system wall",
        "deep bass vibration on speaker membrane",
        "black industrial sub bass cabinet texture",
    ],
```

- [ ] **Step 3: Run prompt consistency tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\spikes\test_shot_type_prompts_consistency.py -q --tb=short
```

Expected: all tests pass. If only the same pair remains above threshold, adjust one prompt at a time and rerun the exact command.

- [ ] **Step 4: Run shot classifier unit tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_shot_type_classifier.py -q
```

Expected: pass.

- [ ] **Step 5: Update Brain-Bug**

Set `B-258` to `fixed` only after Steps 3 and 4 pass.

---

### Task 5: Fix B-259 RAFT Dtype Stability

**Files:**
- Modify: `services/video_analysis_service.py`
- Optionally modify: `services/model_manager.py`
- Add test: `tests/test_services/test_raft_dtype_alignment.py`

- [ ] **Step 1: Add a regression test for dtype alignment**

Create `tests/test_services/test_raft_dtype_alignment.py`:

```python
import numpy as np
import torch


class _FakeRaft(torch.nn.Module):
    def __init__(self, dtype: torch.dtype):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1, dtype=dtype))
        self.seen_dtypes = []

    def forward(self, img1, img2):
        self.seen_dtypes.append((img1.dtype, img2.dtype))
        flow = torch.zeros((1, 2, 8, 8), dtype=img1.dtype, device=img1.device)
        return [flow]


def test_raft_motion_score_matches_model_parameter_dtype():
    from services.video_analysis_service import _raft_motion_score

    model = _FakeRaft(torch.float16).eval()
    frame1 = np.zeros((16, 16, 3), dtype=np.uint8)
    frame2 = np.ones((16, 16, 3), dtype=np.uint8)

    score = _raft_motion_score(model, torch.device("cpu"), frame1, frame2)

    assert score == 0.0
    assert model.seen_dtypes == [(torch.float16, torch.float16)]
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_raft_dtype_alignment.py -q --tb=short
```

Expected before implementation: fails because inputs remain `torch.float32`.

- [ ] **Step 3: Align input dtype in `_raft_motion_score`**

In `services/video_analysis_service.py`, inside `_raft_motion_score`, add a helper before `prep`:

```python
    try:
        model_dtype = next(raft_model.parameters()).dtype
    except (StopIteration, AttributeError):
        model_dtype = torch.float32
```

Then change the end of `prep` from:

```python
        return t.to(device)
```

to:

```python
        return t.to(device=device, dtype=model_dtype)
```

- [ ] **Step 4: Run dtype test**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_raft_dtype_alignment.py -q
```

Expected: pass.

- [ ] **Step 5: Run RAFT performance tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_performance_profiling.py::test_model_loading_performance tests\test_performance_profiling.py::test_raft_motion_performance -q --tb=short
```

Expected: pass.

- [ ] **Step 6: Update Brain-Bug**

Set `B-259` to `fixed` only after the full suite also passes once.

---

### Task 6: Fix B-219 Proxy Timeout Regression

**Files:**
- Modify: `services/video_service.py`
- Add test: `tests/test_services/test_video_proxy_timeout_regression.py`
- Update: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-219-winerror32-proxy-file-lock-after-pipeline.md`

- [ ] **Step 1: Add a short-timeout regression test**

Create `tests/test_services/test_video_proxy_timeout_regression.py`:

```python
import subprocess
from pathlib import Path

import pytest


class _NeverEndingProc:
    returncode = None

    def __init__(self, *args, **kwargs):
        self.killed = False

    def poll(self):
        return None

    def kill(self):
        self.killed = True

    def communicate(self):
        return "", ""


def test_create_proxy_timeout_raises_clear_timeout(monkeypatch, tmp_path):
    import services.video_service as video_service
    from services.video_service import VideoAnalyzer

    src = tmp_path / "input.mp4"
    src.write_bytes(b"not a real video")
    monkeypatch.setattr(video_service.subprocess, "Popen", _NeverEndingProc)
    monkeypatch.setattr(video_service, "FFMPEG_RENDER_TIMEOUT_SEC", 0.01)

    analyzer = VideoAnalyzer(proxy_dir=tmp_path / "proxies")

    with pytest.raises(subprocess.TimeoutExpired):
        analyzer.create_proxy(str(src))
```

- [ ] **Step 2: Run the regression test**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_video_proxy_timeout_regression.py -q --tb=short
```

Expected: pass or expose an untestable constructor/API mismatch to correct in the test.

- [ ] **Step 3: Make timeout cleanup deterministic**

In `services/video_service.py`, in the timeout branch of `create_proxy`, ensure the code waits after kill before unlink:

```python
                    proc.kill()
                    try:
                        proc.wait(timeout=2.0)
                    except (subprocess.TimeoutExpired, AttributeError):
                        pass
```

Place this before `_retry_on_file_lock("proxy unlink (timeout)", ...)`.

- [ ] **Step 4: Add a no-stale-proc assertion if supported**

Extend `_NeverEndingProc` with:

```python
    def wait(self, timeout=None):
        return 1
```

and assert the object was killed if the test captures it:

```python
created = []

def _factory(*args, **kwargs):
    proc = _NeverEndingProc()
    created.append(proc)
    return proc
```

Expected: `created[0].killed is True`.

- [ ] **Step 5: Run affected video tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_b219_winerror32_retry.py tests\test_services\test_video_proxy_timeout_regression.py tests\test_video_analysis_real.py::test_analyze_and_store -q --tb=short
```

Expected: pass. If `test_analyze_and_store` still takes the full 300s and fails, inspect generated proxy file and active file handles before changing timeout constants.

- [ ] **Step 6: Update Brain-Bug**

Keep `B-219` open until Step 5 and the final full suite pass. Then set `status: fixed`, add `reverified: 2026-04-29`, and record the commands.

---

### Task 7: Fix B-255 Structure Enrichment With Small Libraries

**Files:**
- Modify: `workers/structure_enrichment.py`
- Possibly modify: `services/enrichment/style_bucket_clusterer.py`
- Add test: `tests/enrichment/test_small_library_degraded.py`

- [ ] **Step 1: Add small-library test**

Create `tests/enrichment/test_small_library_degraded.py`:

```python
import numpy as np


def test_style_bucket_clusterer_small_library_returns_degraded_result():
    from services.enrichment.style_bucket_clusterer import StyleBucketClusterer

    clusterer = StyleBucketClusterer()
    embeddings = np.zeros((1, 1152), dtype=np.float32)

    result = clusterer.fit_predict(embeddings)

    assert len(result.labels) == 1
    assert result.labels[0] == 0
    assert getattr(result, "degraded", False) is True
```

- [ ] **Step 2: Run test and verify current behavior**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\enrichment\test_small_library_degraded.py -q --tb=short
```

Expected before fix: fail or raise because fewer than 8 embeddings are not handled.

- [ ] **Step 3: Implement degraded result**

In `services/enrichment/style_bucket_clusterer.py`, branch before UMAP/HDBSCAN when `len(embeddings) < 8`:

```python
        if len(embeddings) < 8:
            labels = np.zeros(len(embeddings), dtype=np.int32)
            return ClusterResult(
                labels=labels,
                probabilities=np.ones(len(embeddings), dtype=np.float32),
                degraded=True,
                reason=f"small_library:{len(embeddings)}",
            )
```

Use the actual local result dataclass/class names from the file. Keep the public return shape compatible with existing tests.

- [ ] **Step 4: Ensure worker reports degraded, not crashed**

In `workers/structure_enrichment.py`, when the cluster result is degraded, log and mark the enrichment step as successful-degraded instead of emitting `error`.

Use this message:

```python
logger.info("StructureEnrichment: kleine Library (%s Embeddings), nutze Single-Bucket-Degraded-Modus", count)
```

- [ ] **Step 5: Run enrichment tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\enrichment tests\workers\test_structure_enrichment_lock.py tests\integration\test_full_enrichment.py -q --tb=short
```

Expected: pass.

- [ ] **Step 6: Update Brain-Bug**

Set `B-255` to `fixed` only after the E2E no longer logs `Need at least 8 embeddings for clustering`.

---

### Task 8: Fix B-254 PacingStrategist Masked Ollama Outage

**Files:**
- Modify: `services/pacing_strategist.py`
- Modify: `tests/e2e_functional_test.py` if the E2E oracle currently treats fallback as PASS
- Add test: `tests/test_services/test_pacing_strategist_ollama_outage.py`

- [ ] **Step 1: Add failing test for outage visibility**

Create `tests/test_services/test_pacing_strategist_ollama_outage.py`:

```python
import pytest


def test_pacing_strategist_marks_default_plan_as_degraded(monkeypatch):
    from services.pacing_strategist import PacingStrategist

    class _BrokenOllama:
        def chat(self, *args, **kwargs):
            raise ConnectionError("ollama down")

    strategist = PacingStrategist(ollama_service=_BrokenOllama())
    plan = strategist.create_plan(audio_summary={"bpm": 140}, video_summary={"clips": 3})

    assert getattr(plan, "degraded", False) is True
    assert "ollama" in getattr(plan, "degraded_reason", "").lower()
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_pacing_strategist_ollama_outage.py -q --tb=short
```

Expected before fix: fails because fallback plan is indistinguishable from a real plan.

- [ ] **Step 3: Mark fallback plans explicitly**

In `services/pacing_strategist.py`, where the default plan is returned after an Ollama exception, attach:

```python
plan.degraded = True
plan.degraded_reason = f"ollama_unavailable:{exc}"
```

If the plan is a dict, attach:

```python
plan["degraded"] = True
plan["degraded_reason"] = f"ollama_unavailable:{exc}"
```

Use the actual return type in the file and keep existing call sites compatible.

- [ ] **Step 4: Update E2E oracle**

In `tests/e2e_functional_test.py`, for PacingStrategist, report fallback as `DEGRADED` or `FAIL` when `degraded` is true. For the green target, require real Ollama available and `degraded is not True`.

- [ ] **Step 5: Run pacing tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\pacing tests\test_services\test_pacing_strategist_ollama_outage.py -q --tb=short
```

Expected: pass.

- [ ] **Step 6: Update Brain-Bug**

Set `B-254` to `fixed` only after an outage test fails visibly and a live-Ollama E2E passes.

---

### Task 9: Fix B-253 beat_this Import In Active Conda Env

**Files:**
- Modify: `requirements-py310-cu113.txt`
- Modify: `services/beat_analysis_service.py` only if import path handling is wrong
- Add test: `tests/test_services/test_beat_this_import_env.py`

- [ ] **Step 1: Add import test**

Create `tests/test_services/test_beat_this_import_env.py`:

```python
def test_beat_this_importable_in_active_env():
    import beat_this

    assert beat_this is not None
```

- [ ] **Step 2: Run test and verify current failure**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_beat_this_import_env.py -q --tb=short
```

Expected before fix: `ModuleNotFoundError: No module named 'beat_this'`.

- [ ] **Step 3: Install vendored beat_this into active env**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pip install .\vendor\beat_this
```

Expected: package installs successfully.

- [ ] **Step 4: Record requirement**

In `requirements-py310-cu113.txt`, add a local install note near the beat_this-related dependencies:

```text
# Local package install required after requirements:
#   python -m pip install .\vendor\beat_this
```

If pip supports the path entry reliably in this environment, use:

```text
.\vendor\beat_this
```

- [ ] **Step 5: Run beat tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_beat_this_import_env.py tests\test_audio_analysis_real.py::test_3_beat_analysis -q --tb=short
```

Expected: pass, and logs should not say `beat_this Import fehlgeschlagen`.

- [ ] **Step 6: Update Brain-Bug**

Set `B-253` to `fixed` only after the full E2E uses beat_this or clearly reports the intended beat engine.

---

### Task 10: Fix B-260 Studio-Brain Pacing Bridge Drift

**Files:**
- Modify: `services/pacing/bridge.py`
- Modify: `services/pacing_service.py`
- Modify: `tests/test_services/test_pacing_bridge_flag.py`
- Modify: `tests/integration/test_pacing_bridge_snapshot.py`

- [ ] **Step 1: Add explicit bridge contract test**

In `tests/test_services/test_pacing_bridge_flag.py`, add:

```python
def test_bridge_flag_does_not_claim_unimplemented_when_pipeline_is_enabled(monkeypatch, caplog):
    from services.pacing import bridge

    monkeypatch.setenv(bridge.ENV_VAR, "1")

    assert bridge.use_studio_brain_pipeline() is True
    assert bridge.maybe_use_studio_brain_pipeline(audio_id=1, video_clip_ids=[1, 2]) is True
```

- [ ] **Step 2: Run bridge tests and verify failure**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_pacing_bridge_flag.py -q --tb=short
```

Expected before fix: new test fails because `maybe_use_studio_brain_pipeline()` returns `False`.

- [ ] **Step 3: Make bridge a real feature switch**

Change `services/pacing/bridge.py`:

```python
def maybe_use_studio_brain_pipeline(*, audio_id: int, video_clip_ids: list[int]) -> bool:
    """Return True when the Studio-Brain pacing path should run."""
    enabled = use_studio_brain_pipeline()
    if enabled:
        logger.info(
            "PB_USE_STUDIO_BRAIN_PIPELINE=1: Studio-Brain-Pacing aktiv. audio_id=%d, %d clips.",
            audio_id,
            len(video_clip_ids),
        )
    return enabled
```

Remove wording that says the bridge is not implemented.

- [ ] **Step 4: Remove unreachable pass block**

In `services/pacing_service.py`, replace the early block:

```python
    if maybe_use_studio_brain_pipeline(
        audio_id=audio_id, video_clip_ids=video_clip_ids,
    ):
        pass
```

with:

```python
    _studio_brain_requested = maybe_use_studio_brain_pipeline(
        audio_id=audio_id, video_clip_ids=video_clip_ids,
    )
```

Then pass `_studio_brain_requested` into `_auto_edit_phase3_inner` or let the inner function call `use_studio_brain_pipeline()` once. Keep one official decision point, not two contradictory ones.

- [ ] **Step 5: Run bridge and pacing snapshot tests**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_pacing_bridge_flag.py tests\integration\test_pacing_bridge_snapshot.py tests\pacing -q --tb=short
```

Expected: pass.

- [ ] **Step 6: Update Brain-Bug**

Set `B-260` to `fixed` after bridge tests pass and the report no longer contains "Bridge noch nicht implementiert" in current logs.

---

### Task 11: Verify Pending Ollama/Brain Bugs B-240 To B-246, B-249, B-252

**Files:**
- Read/update existing bug pages in `C:\Brain-Bug\projects\pb-studio\wiki\bugs`
- Use existing tests before adding new ones.

- [ ] **Step 1: Run targeted Ollama/Brain suites**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services\test_ollama_headless_background_start.py tests\test_services\test_ollama_start_readiness.py tests\test_services\test_local_agent_health_check.py tests\test_services\test_brain_wiring_b197.py tests\test_services\test_brain_wiring_b198_b199.py -q --tb=short
```

Expected: pass or produce a specific failure to fix before changing statuses.

- [ ] **Step 2: Run GUI harness**

Run:

```powershell
$env:PB_PYTHON='C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe'
python tests\gui_harness.py start --force
python tests\gui_harness.py wait-window --title PB_studio --timeout 45
python tests\gui_harness.py kill
```

Expected: window visible, process responsive, graceful kill.

- [ ] **Step 3: Run live Ollama caption smoke**

Run the service E2E in Task 13. Use its Vision-Captioning and PacingStrategist evidence to close only the pending bugs whose user-visible behavior is covered.

- [ ] **Step 4: Update bug statuses honestly**

For each pending page:

```text
status: fixed
verified: 2026-04-29
```

Only use `fixed` if a real command above exercised the user-visible path.

---

### Task 12: Full Local Test Pass

**Files:**
- No planned code changes.
- Test all changed areas.

- [ ] **Step 1: Run fast targeted suite**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest tests\test_services tests\pacing tests\enrichment tests\ui tests\test_ui tests\test_workers tests\workers -q --tb=short
```

Expected: `0 failed`.

- [ ] **Step 2: Run full suite**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m pytest -q --tb=short
```

Expected: `0 failed`. Skips are acceptable only when they are explicit dependency/hardware gates.

- [ ] **Step 3: Run lint/security**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m ruff check .
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -m bandit -r . -c bandit.yaml -ll
```

Expected:

```text
ruff: All checks passed
bandit: No issues identified
```

---

### Task 13: Full E2E Verification With Real Fixtures

**Files:**
- No planned code changes unless failures expose regressions.
- Test report: `test-report/e2e-functional-report-post-green-fix.md`

- [ ] **Step 1: Ensure Ollama is running headless**

Run:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' -c "from services.ollama_service import OllamaService; svc=OllamaService.get(); svc.start_background(); import time; time.sleep(5); print('ready', svc.ready_cached())"
```

Expected: prints `ready True` or the E2E later starts/observes Ollama ready.

- [ ] **Step 2: Run full service E2E**

Run:

```powershell
$env:PATH = (Join-Path (Get-Location) 'bin') + ';' + $env:PATH
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' tests\e2e_functional_test.py --audio tests\fixtures\golden_mix\segment.wav --video tests\fixtures\clips_20 --report test-report\e2e-functional-report-post-green-fix.md
```

Expected:

```text
18/18 OK, 0 FAIL
```

Additional expected log conditions:

- no `beat_this Import fehlgeschlagen`
- no `Need at least 8 embeddings for clustering`
- PacingStrategist reports real Ollama response, not degraded fallback

- [ ] **Step 3: Update Vault synthesis**

Create `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\test-report-post-green-fix-2026-04-29.md` with:

```markdown
---
title: "PB Studio Post-Green-Fix Verification 2026-04-29"
type: synthesis
project: pb-studio
created: 2026-04-29
tags: [test-report, verification, green]
---

# PB Studio Post-Green-Fix Verification 2026-04-29

## Ergebnis

- Full pytest: <paste exact result>
- Ruff: <paste exact result>
- Bandit: <paste exact result>
- Service-E2E: <paste exact result>

## Geschlossene Bugs

- <list fixed bug IDs with evidence>

## Rest-Risiko

- <list only remaining non-green or hardware-gated skips>
```

Replace each angle-bracket line with the actual command output summary before saving.

---

### Task 14: Final Cleanup And Commit

**Files:**
- All modified source/test/docs files from prior tasks.

- [ ] **Step 1: Review diff**

Run:

```powershell
git diff --stat
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 2: Review status**

Run:

```powershell
git status --short
```

Expected: only intentional files are modified/untracked.

- [ ] **Step 3: Commit in logical chunks**

Commit examples:

```powershell
git add requirements-py310-cu113.txt pyproject.toml tests\spikes\test_usearch_install.py
git commit -m "test: gate optional usearch spike"

git add services\pacing\shot_type_classifier.py tests\spikes\test_shot_type_prompts_consistency.py
git commit -m "fix: sharpen shot type prompt separation"

git add services\video_analysis_service.py tests\test_services\test_raft_dtype_alignment.py
git commit -m "fix: align raft inference dtype"

git add services\video_service.py tests\test_services\test_video_proxy_timeout_regression.py
git commit -m "fix: stabilize proxy timeout cleanup"
```

Expected: each commit succeeds only after its targeted tests pass.

## Self-Review

- Spec coverage: The plan covers all new audit findings `B-257` to `B-261`, reopens and addresses `B-219`, includes existing E2E degradations `B-253` to `B-255`, and includes pending-live-verification cleanup for `B-240` to `B-246`, `B-249`, `B-252`.
- Placeholder scan: The plan contains concrete files, commands, expected results, and implementation snippets. It avoids blank handoff steps.
- Type consistency: Test names and commands use the repository's current paths from the 2026-04-29 audit.
