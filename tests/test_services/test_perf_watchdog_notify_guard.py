from PySide6.QtCore import QEvent, QObject

from services.perf_watchdog import SlowEventHook


def test_slow_event_hook_ignores_non_qobject_receiver(qapp) -> None:
    original_notify = qapp.notify
    hook = SlowEventHook(qapp, threshold_ms=10_000)
    try:
        event = QEvent(QEvent.Type.ChildAdded)

        result = hook._profiled_notify(object(), event)

        assert result is False
    finally:
        qapp.notify = original_notify
        hook._timer.stop()


def test_slow_event_hook_still_delegates_qobject_receiver(qapp) -> None:
    original_notify = qapp.notify
    calls = []

    def fake_notify(receiver, event):
        calls.append((receiver, event))
        return True

    qapp.notify = fake_notify
    hook = SlowEventHook(qapp, threshold_ms=10_000)
    receiver = QObject()
    event = QEvent(QEvent.Type.User)
    try:
        result = hook._profiled_notify(receiver, event)

        assert result is True
        assert calls == [(receiver, event)]
    finally:
        qapp.notify = original_notify
        hook._timer.stop()
