# Phase 09 — Worker Stage-Progress

**Ziel:** `AutoEditWorker` und `_CutsWorker` emittieren `progress(stage_key: str, fraction: float)`. `SchnittLoadingView` mappt das auf rotierenden Status-Text + Progress-Bar.

---

## Task 9.1: `AutoEditWorker.progress`-Signal

**Files:**
- Modify: `services/auto_edit_worker.py` (oder wo der Worker heute lebt)
- Test: `tests/test_services/test_auto_edit_progress.py`

- [ ] **Step 1: Quelle finden** — vor jeder Änderung lokalisieren:

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -c "import inspect, services; print(inspect.getsourcefile(__import__('services.auto_edit_worker', fromlist=['AutoEditWorker']).AutoEditWorker))"
```

Falls Modul-Pfad anders heißt: in `ui/controllers/edit_workspace.py` nach `AutoEditWorker` greppen und Quelle dort verfolgen.

- [ ] **Step 2: Failing Test**

```python
# tests/test_services/test_auto_edit_progress.py
from services.auto_edit_worker import AutoEditWorker


def test_class_has_progress_signal():
    assert hasattr(AutoEditWorker, "progress")


def test_emit_progress_collects_stage_keys(qtbot=None):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    w = AutoEditWorker(audio_id=1, video_ids=[1], settings=None)
    received: list[tuple[str, float]] = []
    w.progress.connect(lambda s, f: received.append((s, f)))
    w._emit_stage("audio_load", 0.1)
    w._emit_stage("cut_calc", 0.5)
    assert received == [("audio_load", 0.1), ("cut_calc", 0.5)]
```

- [ ] **Step 3: Fail bestätigen.**

- [ ] **Step 4: Worker erweitern**

```python
# services/auto_edit_worker.py — innerhalb class AutoEditWorker(QObject)
progress = Signal(str, float)
# Helper-Methode:
def _emit_stage(self, stage_key: str, fraction: float) -> None:
    try:
        self.progress.emit(stage_key, float(fraction))
    except Exception:
        pass
```

In der `run()`-Methode an den passenden Stellen `self._emit_stage("...", ...)` aufrufen — mindestens:

- direkt nach Audio-Load: `self._emit_stage("audio_load", 0.1)`
- nach Beatgrid: `self._emit_stage("beat_grid", 0.25)`
- nach Struktur: `self._emit_stage("structure", 0.4)`
- nach Cut-Calc: `self._emit_stage("cut_calc", 0.6)`
- nach Clip-Select: `self._emit_stage("clip_select", 0.8)`
- nach Anchor-Sync: `self._emit_stage("anchor_sync", 0.9)`
- vor DB-Write: `self._emit_stage("db_write", 0.95)`
- am Ende: `self._emit_stage("db_write", 1.0)`

- [ ] **Step 5: Pass bestätigen.**

- [ ] **Step 6: Commit**

```bash
git add services/auto_edit_worker.py tests/test_services/test_auto_edit_progress.py
git commit -m "feat(schnitt): AutoEditWorker emits progress(stage, fraction)"
```

- [ ] **Step 7: Vault-Update.**

---

## Task 9.2: `_CutsWorker` analog erweitern

**Files:**
- Modify: `ui/controllers/edit_workspace.py` (lokaler `_CutsWorker`)
- Test: `tests/ui/test_cuts_worker_progress.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_cuts_worker_progress.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.controllers.edit_workspace import _CutsWorker  # type: ignore


def _qapp():
    return QApplication.instance() or QApplication([])


def test_cuts_worker_has_progress_signal():
    _qapp()
    w = _CutsWorker(1, 1, None, 60.0, 1)
    assert hasattr(w, "progress")
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: `_CutsWorker` erweitern**

In der `class _CutsWorker(QObject):` Definition zusätzlich:

```python
progress = Signal(str, float)
```

In `run()` an passenden Stellen `self.progress.emit("cut_calc", 0.5)` etc.

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/controllers/edit_workspace.py tests/ui/test_cuts_worker_progress.py
git commit -m "feat(schnitt): _CutsWorker emits progress signal"
```

- [ ] **Step 6: Vault-Update.**

---

## Task 9.3: Loading-View an Workers koppeln (Controller-Hook)

**Files:**
- Create: `ui/controllers/schnitt_controller.py` (NEU)
- Test: `tests/ui/test_schnitt_controller_loading_hook.py`

- [ ] **Step 1: Failing Test**

```python
# tests/ui/test_schnitt_controller_loading_hook.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
from ui.controllers.schnitt_controller import SchnittController


class FakeWorker:
    def __init__(self):
        from PySide6.QtCore import QObject, Signal
        class _W(QObject):
            progress = Signal(str, float)
            done = Signal(list, float, int)
            failed = Signal(str, int)
        self.q = _W()


def _qapp():
    return QApplication.instance() or QApplication([])


def test_controller_routes_progress_to_loading_view():
    _qapp()
    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    fake = FakeWorker()
    ctrl.attach_worker(fake.q)
    ws.enter_loading()
    fake.q.progress.emit("cut_calc", 0.42)
    assert ws.current_state() == STATE_LOADING
    assert "Schnitte" in ws.loading_view.status_label.text()
    assert ws.loading_view.progress_bar.value() == 42
```

- [ ] **Step 2: Fail bestätigen.**

- [ ] **Step 3: Controller-Klasse**

```python
# ui/controllers/schnitt_controller.py
"""SchnittController — verbindet Workers mit SchnittWorkspace-States."""
from __future__ import annotations
from typing import Any
from PySide6.QtCore import QObject


class SchnittController(QObject):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._current_worker: Any | None = None
        workspace.cancel_requested.connect(self._on_cancel)

    def attach_worker(self, worker: Any) -> None:
        self._current_worker = worker
        if hasattr(worker, "progress"):
            worker.progress.connect(self.workspace.show_progress)
        if hasattr(worker, "done"):
            worker.done.connect(self._on_done)
        if hasattr(worker, "failed"):
            worker.failed.connect(self._on_failed)

    def _on_done(self, *args, **kwargs):
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    def _on_failed(self, *args, **kwargs):
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    def _on_cancel(self):
        if self._current_worker is not None and hasattr(self._current_worker, "cancel"):
            try:
                self._current_worker.cancel()
            except Exception:
                pass
        self.workspace.refresh_state_from_db()
        self._current_worker = None
```

- [ ] **Step 4: Pass bestätigen.**

- [ ] **Step 5: Commit**

```bash
git add ui/controllers/schnitt_controller.py tests/ui/test_schnitt_controller_loading_hook.py
git commit -m "feat(schnitt): SchnittController routes worker progress"
```

- [ ] **Step 6: Vault-Update.**

---

## Phasen-Abschluss

Phase 09 fertig. Worker liefern Stage-Progress; LoadingView reagiert über Controller.

Nächste Phase: [10_NAV_AND_INTEGRATION.md](10_NAV_AND_INTEGRATION.md).
