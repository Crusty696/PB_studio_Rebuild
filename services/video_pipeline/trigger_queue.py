"""User-Trigger-Queue (Phase 38).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 38 (Tier 3 Workspace+Services)

Plain Python state machine fuer:
- Per-Step-Trigger (User klickt einzelne Stage)
- "Alle ausstehenden ausfuehren" sequentiell
- Pause / Resume / Cancel
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


__all__ = ["QueueState", "TriggerJob", "TriggerQueue"]


class QueueState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    DONE = "done"


@dataclass
class TriggerJob:
    stage_id: str
    runner: Callable[[], "object"]
    status: str = "pending"   # pending / running / done / failed / skipped
    result: object | None = None


import threading


class TriggerQueue:
    """Sequentielle Queue mit Pause/Cancel-Support.

    Usage:
        q = TriggerQueue()
        q.enqueue(TriggerJob("a", lambda: run_a()))
        q.enqueue(TriggerJob("b", lambda: run_b()))
        q.run_all()                      # sequentiell
        # oder
        q.run_single("a")                # nur diese Stage
    """

    def __init__(self):
        self._jobs: list[TriggerJob] = []
        self._state = QueueState.IDLE
        self._resume_event = threading.Event()
        self._resume_event.set()  # Standardmäßig offen (nicht pausiert)

    @property
    def state(self) -> QueueState:
        return self._state

    def enqueue(self, job: TriggerJob) -> None:
        if any(j.stage_id == job.stage_id for j in self._jobs):
            raise ValueError(f"duplicate stage_id: {job.stage_id}")
        self._jobs.append(job)

    def get_job(self, stage_id: str) -> TriggerJob:
        for j in self._jobs:
            if j.stage_id == stage_id:
                return j
        raise KeyError(stage_id)

    def jobs(self) -> list[TriggerJob]:
        return list(self._jobs)

    def pending_jobs(self) -> list[TriggerJob]:
        return [j for j in self._jobs if j.status == "pending"]

    def pause(self) -> None:
        if self._state == QueueState.RUNNING:
            self._state = QueueState.PAUSED
            self._resume_event.clear()

    def resume(self) -> None:
        if self._state == QueueState.PAUSED:
            self._state = QueueState.RUNNING
            self._resume_event.set()

    def cancel(self) -> None:
        self._state = QueueState.CANCELLED
        self._resume_event.set()  # Weckt wartende Threads auf

    def run_single(self, stage_id: str) -> TriggerJob:
        job = self.get_job(stage_id)
        if job.status == "done":
            return job
        self._state = QueueState.RUNNING
        job.status = "running"
        try:
            job.result = job.runner()
            job.status = "done"
        except Exception as ex:
            job.status = "failed"
            job.result = ex
        self._state = QueueState.IDLE
        return job

    def run_all(self) -> list[TriggerJob]:
        """Fuehrt alle pending-Jobs in Enqueue-Reihenfolge aus.

        Respektiert Pause/Cancel zwischen Jobs.
        """
        self._state = QueueState.RUNNING
        self._resume_event.set()  # Sicherstellen, dass die Schranke offen ist beim Start
        ran: list[TriggerJob] = []
        for job in self._jobs:
            if self._state == QueueState.CANCELLED:
                break
            
            # F-18 (B-350): Blockiert hier ohne CPU-Last (no polling), 
            # falls pausiert, anstatt die Methode vorzeitig zu verlassen
            # und verbleibende Jobs zu droppen.
            self._resume_event.wait()
            
            if self._state == QueueState.CANCELLED:
                break
            if job.status not in {"pending", "failed"}:
                continue
            job.status = "running"
            try:
                job.result = job.runner()
                job.status = "done"
            except Exception as ex:
                job.status = "failed"
                job.result = ex
            ran.append(job)

        if self._state != QueueState.CANCELLED:
            self._state = QueueState.DONE
        return ran
