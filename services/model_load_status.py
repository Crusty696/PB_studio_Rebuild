"""Zentraler Status-Emitter fuer das aktuell genutzte/ladende LLM.

Der OllamaService meldet hierueber, welches Modell fuer welche Aufgabe
gerade geladen wird bzw. bereit ist. Die UI (ModelStatusField) verbindet
sich mit dem Signal und zeigt Name + Typ + Ladebalken-Fuellung.

Threadsicher: OllamaService.chat()/vision() laufen in Worker-Threads;
Qt-Signals werden cross-thread automatisch als QueuedConnection zugestellt,
sodass der UI-Slot im Main-Thread laeuft.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class ModelLoadStatus(QObject):
    """Singleton-Emitter. ``phase`` ist einer von ``idle|loading|ready|error``.

    ``pct`` ist der Lade-Fortschritt 0..1 fuer Downloads; ``-1`` bedeutet
    unbestimmt (VRAM-Cold-Load ohne Prozentanzeige -> UI zeigt Lauf-Animation).
    ``task`` ist ``chat`` oder ``vision``.
    """

    changed = Signal(str, str, str, float)  # model, task, phase, pct

    _instance: "ModelLoadStatus | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "ModelLoadStatus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_loading(self, model: str, task: str, pct: float = -1.0) -> None:
        self.changed.emit(model or "", task or "", "loading", pct)

    def set_ready(self, model: str, task: str) -> None:
        self.changed.emit(model or "", task or "", "ready", 1.0)

    def set_error(self, model: str, task: str) -> None:
        self.changed.emit(model or "", task or "", "error", 0.0)

    def set_idle(self) -> None:
        self.changed.emit("", "", "idle", 0.0)
