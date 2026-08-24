"""Legacy-Eventprofiler und sicherer Produktionsinstaller.

B-879: Globales Ersetzen von ``QApplication.notify`` durch Python-Code war
unter parallelen Qt-Thread-Events nicht stabil. ``install_watchdog`` belaesst
den nativen Dispatcher deshalb unangetastet. Main-Threads-Hangs schreibt die
separate Freeze-Probe in ``main.py`` weiterhin nach ``logs/freeze_stacks.log``.
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


class _ProfilerThreadState:
    """Pro-Thread-Zustand eines ``_profiled_notify``-Aufrufs.

    ``QCoreApplication::notify`` laeuft in JEDEM Thread mit Event-Loop, also
    auch in allen QThread-Workern. Vorher lagen ``_call_stack`` /
    ``_current_event_start`` / ``_current_event_name`` /
    ``_current_receiver_name`` ungeschuetzt als geteilte Instanzfelder: Frames
    vertauschten sich zwischen Threads, Freeze-Zeiten wurden verfaelscht und
    ``_call_stack.pop()`` konnte auf einem leeren Stack laufen (IndexError,
    Kandidat fuer die absurden SLOW-EVENT-Dauern, vgl. B-621).
    """

    __slots__ = ("call_stack", "event_start", "event_name", "receiver_name")

    def __init__(self) -> None:
        self.call_stack: list[bool] = []
        self.event_start: float = 0.0
        self.event_name: str = ""
        self.receiver_name: str = ""


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

        # Profiler-Zustand ist THREAD-LOKAL (siehe _ProfilerThreadState).
        # ``_main_state`` ist die Instanz des GUI-Threads — der Sampler-Thread
        # unten liest ausschliesslich sie und behaelt damit exakt seine
        # bisherige Semantik ("beobachte nur den GUI-Thread"), jetzt aber ohne
        # dass Worker-Threads ihm dazwischenschreiben koennen.
        # ``__init__`` laeuft im GUI-Thread (install_watchdog aus main.py).
        self._tls = threading.local()
        self._main_state = _ProfilerThreadState()
        self._tls.state = self._main_state

        # Background-Thread der den Main-Thread-Stack sampelt bei langen Events
        self._sampled_stacks: list[tuple[float, str]] = []
        self._stack_lock = threading.Lock()
        self._running = True

        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        # B-621-FIX: notify() ist reentrant — ein Klick, der synchron einen
        # modalen Dialog oeffnet (QDialog.exec()/QMenu.exec()), pumpt WAEHREND
        # des aeusseren notify()-Aufrufs eine eigene, verschachtelte Event-
        # Loop. Die dabei verstrichene Nutzerinteraktionszeit (Dialog offen
        # bis Klick auf OK) faellt dem AEUSSEREN Event ("MouseRelease") zur
        # Last, obwohl sie keine echte Verarbeitungsdauer ist — absurde Werte
        # wie 73716ms/239604ms ohne freeze_stacks-Beleg. Dieser Stack merkt
        # sich pro notify()-Frame, ob WAEHREND seiner Laufzeit ein
        # verschachtelter notify()-Aufruf stattfand, und kennzeichnet den
        # Log-Eintrag entsprechend statt ihn unkommentiert als Freeze
        # auszuweisen. Dieser Stack liegt pro Thread in
        # ``_ProfilerThreadState.call_stack``.

        # Monkey-patch notify
        app.notify = self._profiled_notify

        # Periodischer Report
        self._timer = QTimer()
        self._timer.setInterval(10000)  # Alle 10s
        self._timer.timeout.connect(self._report)
        self._timer.start()

        logger.info("[PerfWatchdog] Installiert. Threshold: %dms", threshold_ms)

    def _state(self) -> "_ProfilerThreadState":
        """Thread-lokalen Profiler-Zustand holen (bei Bedarf anlegen)."""
        state = getattr(self._tls, "state", None)
        if state is None:
            state = (
                self._main_state
                if threading.current_thread().ident == self._main_thread_id
                else _ProfilerThreadState()
            )
            self._tls.state = state
        return state

    def _watchdog_loop(self) -> None:
        """Laeuft in einem Background-Thread und sampelt den Main-Thread-Stack alle 200ms bei langen Events."""
        while self._running:
            time.sleep(0.2)
            # Nur der GUI-Thread-Zustand wird beobachtet (unveraenderte
            # Semantik, jetzt garantiert statt zufaellig).
            start_time = self._main_state.event_start
            if start_time > 0.0:
                elapsed = time.perf_counter() - start_time
                if elapsed > 1.0:  # Event dauert schon laenger als 1s
                    frame = sys._current_frames().get(self._main_thread_id)
                    if frame:
                        stack = "".join(traceback.format_stack(frame))
                        with self._stack_lock:
                            if len(self._sampled_stacks) < 50:
                                self._sampled_stacks.append((elapsed, stack))

    def _profiled_notify(self, receiver: QObject, event: QEvent) -> bool:
        if not isinstance(receiver, QObject):
            # PySide can route internal objects (e.g. QWidgetItem) through the
            # monkey-patched notify hook.
            return False

        state = self._state()
        self._count += 1
        t0 = time.perf_counter()

        event_type = event.type()
        event_name = _EVENT_NAMES.get(event_type, f"Type({int(event_type)})")
        try:
            receiver_name = (
                f"{type(receiver).__name__}"
                f"({receiver.objectName() or '?'})"
            )
        except (RuntimeError, AttributeError):
            receiver_name = "<deleted>"

        # Aktiviert das Sampling fuer dieses Event
        with self._stack_lock:
            self._sampled_stacks.clear()
        state.event_name = event_name
        state.receiver_name = receiver_name
        state.event_start = t0

        # B-621-FIX: dieser Aufruf ist verschachtelt in einem laufenden
        # aeusseren notify() -> markiere den aeusseren Frame als "hatte
        # verschachtelten Event-Loop" (Modal-Dialog-Verdacht).
        if state.call_stack:
            state.call_stack[-1] = True
        state.call_stack.append(False)

        try:
            result = self._original_notify(receiver, event)
        except Exception:
            raise
        finally:
            state.event_start = 0.0
            elapsed = time.perf_counter() - t0
            # Defensiv: pop() auf leerem Stack (theoretisch bei Reentranz
            # ueber Thread-Wechsel/Exception-Pfaden) darf nie IndexError werfen.
            had_nested_loop = state.call_stack.pop() if state.call_stack else False

            if elapsed > self._threshold:
                self._slow_count += 1
                ms = elapsed * 1000
                suffix = (
                    " [enthaelt verschachtelten Event-Loop — vermutlich "
                    "Modal-Dialog/Nutzerinteraktion, KEINE reine "
                    "Verarbeitungszeit, siehe B-621]"
                    if had_nested_loop else ""
                )
                msg = f"[SLOW EVENT] {ms:.0f}ms | {event_name} -> {receiver_name}{suffix}"
                self._slow_log.append(msg)
                logger.warning(msg)

                # Bei langen Events: Sampled Stacks zeigen (der echte Callstack!)
                with self._stack_lock:
                    stacks_to_process = list(self._sampled_stacks)
                    self._sampled_stacks.clear()

                if stacks_to_process:
                    unique = {}
                    for el_s, s in stacks_to_process:
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
    """Belasse Qts nativen Event-Dispatcher unveraendert.

    B-879: Python-Monkey-Patch von ``QApplication.notify`` wird auch aus
    Worker-QThreads betreten und ist unter parallelen Qt-Events nicht stabil.
    Main-Thread-Hangs erfasst bereits unabhaengige Freeze-Probe in ``main.py``.
    Parameter bleiben fuer API-Kompatibilitaet erhalten.
    """
    logger.info(
        "[PerfWatchdog] notify-Patch deaktiviert (B-879); "
        "Main-Thread-Freeze-Probe bleibt aktiv."
    )
    return None
