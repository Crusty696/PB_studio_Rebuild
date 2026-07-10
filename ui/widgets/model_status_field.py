"""ModelStatusField — zeigt das aktuell genutzte/ladende LLM.

Ein dezentes Statusleisten-Feld: Modellname + Typ (Vision/Chat). Waehrend ein
Modell geladen wird, fuellt es sich wie ein Ladebalken von links nach rechts in
passender Farbe (echter Download-Prozent, sonst Lauf-Animation). Voll = bereit.

Speist sich aus services.model_load_status.ModelLoadStatus (vom OllamaService
gefuettert). Reiner Anzeige-Consumer — keine eigene Inference-Logik.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont
from PySide6.QtWidgets import QWidget

from ui.theme import ACCENT, BG2, OK, T3, WARN
from services.model_load_status import ModelLoadStatus

_TASK_LABEL = {"vision": "Vision", "chat": "Chat", "": "LLM"}


class ModelStatusField(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = ""
        self._task = ""
        self._phase = "idle"      # idle|loading|ready|error
        self._pct = 0.0           # 0..1, oder <0 = unbestimmt
        self._anim = 0.0          # Lauf-Animations-Phase 0..1
        self.setMinimumWidth(150)
        self.setFixedHeight(18)
        self.setToolTip(self.tr("Aktuelles KI-Modell (LLM)."))

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(40)
        self._anim_timer.timeout.connect(self._tick)

        # cross-thread QueuedConnection (OllamaService emittiert aus Worker-Threads)
        ModelLoadStatus.get().changed.connect(self._on_status)

        # Initial (nicht blockierend): aktuelles Default-Modell ermitteln + anzeigen.
        threading.Thread(target=self._probe_initial, name="ModelStatus-Init", daemon=True).start()

    # ── Initial-Probe ────────────────────────────────────────────
    def _probe_initial(self):
        try:
            from services.ollama_service import OllamaService
            model = OllamaService.get().get_default_model()
            if model:
                # ueber den Emitter -> landet threadsicher im _on_status-Slot
                ModelLoadStatus.get().set_ready(model, "chat")
        except Exception:
            pass

    # ── Status-Updates ───────────────────────────────────────────
    def _on_status(self, model: str, task: str, phase: str, pct: float):
        self._model = model
        self._task = task
        self._phase = phase
        self._pct = pct
        if phase == "loading" and pct < 0:
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._anim_timer.stop()
        self._update_tooltip()
        self.update()

    def _update_tooltip(self):
        if not self._model:
            self.setToolTip(self.tr("Kein KI-Modell aktiv."))
            return
        label = _TASK_LABEL.get(self._task, "LLM")
        state = {"loading": "wird geladen…", "ready": "bereit",
                 "error": "Fehler", "idle": ""}.get(self._phase, "")
        self.setToolTip(f"KI-Modell: {self._model} ({label}) — {state}")

    def _tick(self):
        self._anim = (self._anim + 0.025) % 1.0
        self.update()

    # ── Zeichnen ─────────────────────────────────────────────────
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = 4.0

        # Hintergrund
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        p.fillPath(path, QColor(BG2))
        p.setClipPath(path)

        # Füllfarbe je Phase
        if self._phase == "ready":
            fill = QColor(OK)
        elif self._phase == "error":
            fill = QColor(WARN)
        else:
            fill = QColor(ACCENT)
        fill.setAlpha(70)

        w = r.width()
        if self._phase == "ready":
            p.fillRect(r, fill)
        elif self._phase == "loading" and self._pct >= 0:
            p.fillRect(QRectF(r.left(), r.top(), w * max(0.0, min(1.0, self._pct)), r.height()), fill)
        elif self._phase == "loading":
            # unbestimmt: laufendes Segment
            seg = w * 0.35
            x = r.left() + (w + seg) * self._anim - seg
            p.fillRect(QRectF(max(r.left(), x), r.top(), min(seg, r.right() - max(r.left(), x)), r.height()), fill)

        # Text: "modell · Typ"
        p.setClipping(False)
        label = _TASK_LABEL.get(self._task, "LLM")
        if self._model:
            text = f"{self._model} · {label}"
        else:
            text = self.tr("LLM: —")
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QColor(T3))
        p.drawText(r.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.end()
