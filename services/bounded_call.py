"""B-670: Wall-Clock-begrenzter Aufruf, der den Prozess-Exit nicht aufhaelt.

Warum nicht ``concurrent.futures.ThreadPoolExecutor``:

``concurrent.futures.thread`` registriert ``_python_exit`` als atexit-Hook.
Der macht ``t.join()`` OHNE Timeout auf jeden je erzeugten Worker-Thread —
auch nach ``executor.shutdown(wait=False)``. Ein bewusst abgekoppelter Call
(Timeout abgelaufen, Aufrufer laeuft weiter) haelt damit beim Beenden den
gesamten Prozess auf, im Ollama-Fall bis zum urllib-Inaktivitaets-Timeout
oder — bei streamendem Server — unbegrenzt. Der Hang wandert von der Laufzeit
in den Shutdown, statt zu verschwinden (gemessen: Aufrufer nach 0.5 s frei,
Prozess erst nach 7.9 s).

Ein ``threading.Thread(daemon=True)`` wird beim Interpreter-Exit nicht
gejoint. Genau deshalb setzen die rohen Thread-Nutzungen im Projekt
durchgaengig ``daemon=True``; nur die Executor-Pfade taten es nicht.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

__all__ = ["call_with_deadline"]


def call_with_deadline(
    fn: Callable[..., Any],
    *args: Any,
    timeout: float,
    thread_name: str = "bounded-call",
    on_start: Callable[[], None] | None = None,
    on_finish: Callable[[], None] | None = None,
    **kwargs: Any,
) -> Any:
    """Ruft ``fn`` auf und gibt nach ``timeout`` Sekunden auf.

    Der Aufruf laeuft in einem Daemon-Thread. Wird die Frist gerissen, kehrt
    diese Funktion mit ``TimeoutError`` zurueck; der Thread laeuft im
    Hintergrund aus und blockiert weder den Aufrufer noch spaeter den
    Prozess-Exit.

    Args:
        fn: aufzurufende Funktion (typischerweise blockierendes I/O).
        timeout: Wall-Clock-Grenze in Sekunden.
        thread_name: Name des Worker-Threads (Diagnose in Stack-Dumps).
        on_start: optional, wird IM Worker-Thread vor ``fn`` ausgefuehrt —
            z. B. um einen thread-lokalen Reentranz-Marker zu setzen.
        on_finish: optional, wird IM Worker-Thread nach ``fn`` ausgefuehrt,
            auch im Fehlerfall.

    Returns:
        Rueckgabewert von ``fn``.

    Raises:
        TimeoutError: wenn ``fn`` nicht rechtzeitig fertig wird. Der Aufrufer
            uebersetzt das in seinen eigenen Fehlertyp.
        BaseException: jede Exception aus ``fn`` wird unveraendert (inkl.
            Original-Traceback) im aufrufenden Thread erneut geworfen.
    """
    slot: dict[str, Any] = {}
    done = threading.Event()

    def _runner() -> None:
        if on_start is not None:
            on_start()
        try:
            slot["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — 1:1 an den Aufrufer weiterreichen
            slot["error"] = exc
        finally:
            if on_finish is not None:
                on_finish()
            done.set()

    worker = threading.Thread(target=_runner, name=thread_name, daemon=True)
    worker.start()

    if not done.wait(timeout):
        raise TimeoutError(
            f"{getattr(fn, '__name__', 'call')} ueberschritt {timeout:.1f}s"
        )

    if "error" in slot:
        raise slot["error"]
    return slot["value"]
