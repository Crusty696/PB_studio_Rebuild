"""B-638: StemPlayer._on_stream_finished aus dem PortAudio-Callback-Thread.

Root-Cause (adversarial CONFIRMED, siehe Vault-Bug-File): QTimer.singleShot
feuert nur, wenn der AUFRUFENDE Thread eine Qt-Event-Loop hat. Der
PortAudio-Callback-Thread ist kein QThread — die 4 singleShot()-Aufrufe in
``_on_stream_finished`` feuerten nie, ``playback_finished``/``state_changed``
wurden nie emittiert, ``_pos_timer`` lief ewig weiter (Leak).

Fix: ``QMetaObject.invokeMethod(self, "_finish_on_gui_thread",
Qt.QueuedConnection)`` marshallt den Aufruf korrekt in den Owner-Thread von
``self`` (GUI-Thread), analog dem etablierten Pattern in
``ui/widgets/ai_status_dot.py`` / ``ui/widgets/resource_monitor.py``.

Dieser Test ruft ``_on_stream_finished`` aus einem ECHTEN, nicht-Qt
``threading.Thread`` auf (wie der reale PortAudio-Callback) und verifiziert,
dass nach einem ``QApplication.processEvents()``-Pump im GUI-Thread die
Signals tatsaechlich ankommen — das ist der Kernfall, den QTimer.singleShot
NICHT konnte.
"""
from __future__ import annotations

import threading

from services.stem_player import StemPlayer


def test_on_stream_finished_called_from_foreign_thread_emits_signals(qapp):
    """Kernfall: Aufruf aus einem echten Nicht-Qt-Thread (wie PortAudio)."""
    player = StemPlayer()

    received_finished = []
    received_state = []
    player.playback_finished.connect(lambda: received_finished.append(True))
    player.state_changed.connect(lambda s: received_state.append(s))

    player._pos_timer.start()
    assert player._pos_timer.isActive() is True

    error_box: list[Exception] = []

    def _call_from_foreign_thread():
        try:
            player._on_stream_finished()
        except Exception as exc:  # pragma: no cover - Diagnose bei Fehlschlag
            error_box.append(exc)

    t = threading.Thread(target=_call_from_foreign_thread)
    t.start()
    t.join(timeout=5.0)
    assert not error_box, f"_on_stream_finished warf im Fremd-Thread: {error_box}"

    # QueuedConnection braucht einen Event-Loop-Pump im GUI-Thread, um
    # zuzustellen — das ist exakt der Unterschied zu QTimer.singleShot,
    # das ganz ohne Pump haette feuern muessen (und es nie tat).
    for _ in range(20):
        qapp.processEvents()

    assert received_finished == [True]
    assert received_state == ["stopped"]
    assert player._pos_timer.isActive() is False


def test_on_stream_finished_sets_state_stopped(qapp):
    player = StemPlayer()
    player._state = "playing"

    t = threading.Thread(target=player._on_stream_finished)
    t.start()
    t.join(timeout=5.0)

    for _ in range(20):
        qapp.processEvents()

    assert player._state == "stopped"


def test_on_stream_finished_from_gui_thread_still_works(qapp):
    """Rueckwaertskompat: direkter Aufruf aus dem GUI-Thread (z.B. Tests,
    synthetische Trigger) darf weiterhin funktionieren."""
    player = StemPlayer()
    received = []
    player.playback_finished.connect(lambda: received.append(True))

    player._on_stream_finished()
    for _ in range(20):
        qapp.processEvents()

    assert received == [True]
