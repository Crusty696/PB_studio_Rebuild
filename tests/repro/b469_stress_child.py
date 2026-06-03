"""B-469 Phase 0 — stress repro CHILD process.

Runs OUT-OF-PROCESS on purpose: the bug is a native Qt6Core crash
(0xc0000409). A native crash kills this process, so the PARENT
(`test_b469_media_reload_crash_stress.py`) asserts on this child's exit code.

What it stresses (the exact concurrency shape from the live crash session
2026-06-03, see wiki/bugs/B-469): under a real QApplication event loop it
repeatedly
  - starts several blocking "Medien-DB laden"-style DBFetchWorker tasks via the
    real GlobalTaskManager (QThread + moveToThread + finished/cleanup),
  - cancels a subset mid-flight (`cancel_task` -> thread.quit() while run() is
    still blocking),
  - clears finished tasks (`clear_finished` -> deleteLater of worker/thread),
  - swaps the SQLAlchemy engine via `set_project` while workers are non-idle.

If the process prints "B469_SURVIVED" and exits 0, no crash was observed in this
run. Any abnormal exit code is the native crash.

Usage:  python -m tests.repro.b469_stress_child [iterations] [workers_per_iter]
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Allow both `python tests/repro/b469_stress_child.py` and `-m` invocation:
# ensure the repo root is importable for database/services modules.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QCoreApplication


class _DBFetchWorker(QObject):
    """Faithful mirror of ui/controllers/media_table.py DBFetchWorker.

    Deliberately has NO cooperative ``cancel()`` — the real inline DBFetchWorker
    has none either. So ``cancel_task``'s ``thread.quit()`` is a no-op while
    run() is still executing (run() is a plain slot, the worker thread has no
    exec() event loop), and ``clear_finished`` can ``deleteLater`` the QThread
    while it is still running -> 'QThread: Destroyed while thread is still
    running' -> native fast-fail. run() blocks unconditionally long enough that
    the queued deleteLater is processed while the thread is still in run()."""

    finished = Signal(list, list)
    error = Signal(str)

    def run(self) -> None:
        try:
            from services.ingest_service import get_all_audio, get_all_video
            v: list = []
            a: list = []
            deadline = time.monotonic() + 0.25  # ~250ms unconditional DB work
            while time.monotonic() < deadline:
                v = get_all_video()
                a = get_all_audio()
            self.finished.emit(v, a)
        except Exception as e:  # noqa: BLE001 — mirror controller's broad catch
            self.error.emit(str(e))


def _make_project(tmp_root: Path, name: str) -> Path:
    p = tmp_root / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    workers_per_iter = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    app = QApplication(sys.argv)

    from database.session import set_project
    from services.task_manager import GlobalTaskManager

    tmp_root = Path(tempfile.mkdtemp(prefix="b469_stress_"))
    proj_a = _make_project(tmp_root, "proj_a")
    proj_b = _make_project(tmp_root, "proj_b")

    # Initial project (creates tables on a real engine).
    set_project(proj_a)

    tm = GlobalTaskManager.instance()

    pump = QCoreApplication.processEvents

    for i in range(iterations):
        started_ids: list[str] = []
        for _ in range(workers_per_iter):
            w = _DBFetchWorker()
            # finished -> trivial slot (queued), mirrors _apply_refreshed_data hop
            w.finished.connect(lambda v, a: None)
            res = tm.start_task(name="Medien-DB laden", worker=w,
                                description="stress")
            tid = getattr(res, "task_id", None) or (res if isinstance(res, str) else None)
            if tid:
                started_ids.append(tid)

        pump()  # let threads spin up and enter blocking run()

        # Cancel roughly half of them mid-flight (thread.quit while run() blocks).
        for tid in started_ids[::2]:
            tm.cancel_task(tid)

        # Engine swap while workers are non-idle (alternate projects).
        set_project(proj_b if (i % 2 == 0) else proj_a)

        # Tear down finished/cancelled tasks (deleteLater of worker/thread).
        tm.clear_finished()

        pump()
        if i % 25 == 0:
            print(f"B469_ITER {i}/{iterations}", flush=True)

    # Drain remaining events / cleanups.
    for _ in range(20):
        pump()
        time.sleep(0.01)

    print("B469_SURVIVED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
