"""Main-Thread Performance Watchdog.

Misst die Dauer jedes Qt-Events im Main-Thread.
Wenn ein Event laenger als THRESHOLD_MS dauert, wird es geloggt
mit Typ, Empfaenger-Widget und Dauer.

Aktivierung in main.py:
    from services.perf_watchdog import install_watchdog
    install_watchdog(app, threshold_ms=50)

Deaktivierung: einfach den Aufruf entfernen.
"""

import logging
import sys
import threading
import time
import traceback

from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# Event-Typen die besonders interessant sind
_EVENT_NAMES = {
    QEvent.Type.Paint: "Paint",
    QEvent.Type.Resize: "Resize",
    QEvent.Type.Show: "Show",
    QEvent.Type.Hide: "Hide",
    QEvent.Type.Timer: "Timer",
    QEvent.Type.MouseMove: "MouseMove",
    QEvent.Type.MouseButtonPress: "MousePress",
    QEvent.Type.MouseButtonRelease: "MouseRelease",
    QEvent.Type.KeyPress: "KeyPress",
    QEvent.Type.DragMove: "DragMove",
    QEvent.Type.Drop: "Drop",
    QEvent.Type.LayoutRequest: "LayoutRequest",
    QEvent.Type.UpdateLater: "UpdateLater",
    QEvent.Type.Polish: "Polish",
    QEvent.Type.PolishRequest: "PolishRequest",
    QEvent.Type.MetaCall: "MetaCall",
}

THRESHOLD_MS = 50  # Default: alles ueber 50ms loggen


class EventProfiler(QObject):
    """Event-Filter der auf QApplication installiert wird."""

    def __init__(self, app: QApplication, threshold_ms: int = THRESHOLD_MS):
        super().__init__(app)
        self._threshold = threshold_ms / 1000.0
        self._slow_events: list[tuple[str, str, float]] = []
        self._report_timer = QTimer(self)
        self._report_timer.setInterval(5000)  # Alle 5s Report
        self._report_timer.timeout.connect(self._report)
        self._report_timer.start()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        result = super().eventFilter(obj, event)

        # Das eigentliche Event wird von Qt NACH diesem Filter verarbeitet.
        # Wir messen hier nur den Filter-Overhead, nicht das Event selbst.
        # Fuer echte Event-Messung brauchen wir einen anderen Ansatz.
        return result


class SlowEventHook:
    """Patch fuer QApplication.notify() — misst die tatsaechliche Event-Dauer."""

    def __init__(self, app: QApplication, threshold_ms: int = THRESHOLD_MS):
        self._app = app
        self._threshold = threshold_ms / 1000.0
        self._original_notify = app.notify
        self._slow_log: list[str] = []
        self._count = 0
        self._slow_count = 0
        self._main_thread_id = threading.current_thread().ident

        # Background-Thread der den Main-Thread-Stack sampelt bei langen Events
        self._sampling = False
        self._sample_stacks: list[str] = []

        # Monkey-patch notify
        app.notify = self._profiled_notify

        # Periodischer Report
        self._timer = QTimer()
        self._timer.setInterval(10000)  # Alle 10s
        self._timer.timeout.connect(self._report)
        self._timer.start()

        logger.info("[PerfWatchdog] Installiert. Threshold: %dms", threshold_ms)

    def _sample_main_thread(self):
        """Laeuft in einem Background-Thread und sampelt den Main-Thread-Stack alle 200ms."""
        while self._sampling:
            time.sleep(0.2)
            frame = sys._current_frames().get(self._main_thread_id)
            if frame:
                stack = "".join(traceback.format_stack(frame))
                self._sample_stacks.append(stack)
            if len(self._sample_stacks) > 50:
                break

    def _profiled_notify(self, receiver: QObject, event: QEvent) -> bool:
        if not isinstance(receiver, QObject):
            # PySide can route internal objects (e.g. QWidgetItem) through the
            # monkey-patched notify hook. QApplication.notify only accepts
            # QObject receivers; delegating those would raise TypeError and
            # turn a watchdog into an app-level exception.
            return False

        self._count += 1
        t0 = time.perf_counter()

        # Bei MousePress/Release: Sampler starten fuer tiefe Analyse
        event_type = event.type()
        is_interactive = event_type in (
            QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
            QEvent.Type.KeyPress,
        )
        if is_interactive:
            self._sample_stacks.clear()
            self._sampling = True
            sampler = threading.Thread(target=self._sample_main_thread, daemon=True)
            sampler.start()

        try:
            result = self._original_notify(receiver, event)
        except Exception:
            raise
        finally:
            self._sampling = False
            elapsed = time.perf_counter() - t0

            if elapsed > self._threshold:
                self._slow_count += 1
                event_name = _EVENT_NAMES.get(event_type, f"Type({int(event_type)})")

                try:
                    receiver_name = (
                        f"{type(receiver).__name__}"
                        f"({receiver.objectName() or '?'})"
                    )
                except (RuntimeError, AttributeError):
                    receiver_name = "<deleted>"

                ms = elapsed * 1000
                msg = f"[SLOW EVENT] {ms:.0f}ms | {event_name} -> {receiver_name}"
                self._slow_log.append(msg)
                logger.warning(msg)

                # Bei langen Events: Sampled Stacks zeigen (der echte Callstack!)
                if elapsed > 1.0 and self._sample_stacks:
                    # Dedupliziere und zeige die haeufigsten Stacks
                    unique = {}
                    for s in self._sample_stacks:
                        # Letzten relevanten Frame extrahieren
                        lines = [l for l in s.strip().split('\n') if 'perf_watchdog' not in l and 'threading' not in l]
                        key = '\n'.join(lines[-6:]) if lines else s
                        unique[key] = unique.get(key, 0) + 1
                    top = sorted(unique.items(), key=lambda x: -x[1])[:3]
                    for stack, count in top:
                        logger.warning(
                            "[SLOW EVENT] Sampled Stack (%dx bei %dms):\n%s",
                            count, int(ms), stack,
                        )
                    self._sample_stacks.clear()

        return result

    def _report(self):
        if self._slow_count > 0:
            logger.info(
                "[PerfWatchdog] Letzte 10s: %d/%d Events langsam (>%dms). "
                "Top Blocker:\n%s",
                self._slow_count, self._count, int(self._threshold * 1000),
                "\n".join(self._slow_log[-5:]) if self._slow_log else "(keine)",
            )
        self._slow_count = 0
        self._count = 0
        self._slow_log.clear()


def install_watchdog(app: QApplication, threshold_ms: int = 50):
    """Installiert den Performance-Watchdog auf der QApplication.

    Misst jedes Event im Main-Thread. Events die laenger als threshold_ms
    dauern werden geloggt mit Typ und Empfaenger-Widget.
    """
    hook = SlowEventHook(app, threshold_ms)
    # Referenz halten damit GC den Hook nicht loescht
    app._perf_watchdog = hook
    return hook
