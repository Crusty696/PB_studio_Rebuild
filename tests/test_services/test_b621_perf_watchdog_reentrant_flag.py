"""B-621: Perf-Watchdog kennzeichnet SLOW-EVENT-Zeilen mit verschachteltem
Event-Loop (Modal-Dialog-Verdacht) statt sie unkommentiert als Freeze
auszuweisen.

Root-Cause (Vermutung im Bug-File war ungenau — echte Ursache ist das
bekannte, in ``docs/GUI_NAVIGATION_PLAYBOOK.md`` 2.2 dokumentierte
``QDialog.exec()``-reentrant-Muster): ``QApplication.notify()`` ist
reentrant — ein Klick-Handler, der synchron einen modalen Dialog oeffnet
(``QDialog.exec()``), pumpt WAEHREND des aeusseren ``notify()``-Aufrufs
eine eigene, verschachtelte Event-Loop. Die dabei verstrichene
Nutzerinteraktionszeit (Dialog offen bis Klick auf OK) faellt dem
AEUSSEREN Event ("MouseRelease") zur Last — absurde Werte wie 73716ms
ohne ``freeze_stacks.log``-Beleg.

Fix: ``SlowEventHook`` fuehrt einen Reentrancy-Stack, markiert den
AEUSSEREN Frame als "hatte verschachtelten Aufruf" und haengt bei
Ueberschreitung des Thresholds einen erklaerenden Suffix an die Log-Zeile.
"""
import logging

from PySide6.QtCore import QEvent, QObject

from services.perf_watchdog import SlowEventHook


def test_nested_notify_call_flags_outer_slow_event(qapp, caplog):
    """Simuliert QDialog.exec(): der aeussere notify()-Aufruf ruft
    WAEHREND seiner Verarbeitung selbst wieder notify() auf (verschachtelte
    Event-Loop) — die Log-Zeile des aeusseren Events muss den B-621-Hinweis
    tragen."""
    hook = SlowEventHook(qapp, threshold_ms=10)
    receiver = QObject()
    outer_event = QEvent(QEvent.Type.MouseButtonRelease)
    inner_event = QEvent(QEvent.Type.User)

    def fake_original_notify(recv, ev):
        if ev is outer_event:
            # Simuliert: Klick-Handler oeffnet synchron einen Dialog, der
            # intern nochmal notify() aufruft (verschachtelte Event-Loop) —
            # und der Nutzer laesst den Dialog eine Weile offen (>10ms
            # Test-Threshold), bevor er ihn schliesst.
            import time
            hook._profiled_notify(receiver, inner_event)
            time.sleep(0.02)
        return True

    hook._original_notify = fake_original_notify

    try:
        with caplog.at_level(logging.WARNING, logger="services.perf_watchdog"):
            hook._profiled_notify(receiver, outer_event)

        slow_lines = [r.message for r in caplog.records if "[SLOW EVENT]" in r.message]
        outer_lines = [l for l in slow_lines if "MouseRelease" in l]
        assert outer_lines, f"Erwartete SLOW-EVENT-Zeile fuer das aeussere Event, bekam: {slow_lines}"
        assert any("B-621" in line for line in outer_lines), (
            f"Erwartete B-621-Hinweis im aeusseren Event, bekam: {outer_lines}"
        )
    finally:
        hook._timer.stop()
        del qapp.notify
        assert "notify" not in qapp.__dict__


def test_non_nested_slow_event_has_no_reentrant_suffix(qapp, caplog):
    """Gegenprobe: ein SLOW EVENT ohne verschachtelten Aufruf (echter,
    einfacher langsamer Callback) darf NICHT faelschlich als B-621-Artefakt
    markiert werden."""
    hook = SlowEventHook(qapp, threshold_ms=10)
    receiver = QObject()
    event = QEvent(QEvent.Type.Paint)

    def fake_original_notify(recv, ev):
        import time
        time.sleep(0.02)  # ueberschreitet 10ms-Threshold, aber KEIN Nested-Call
        return True

    hook._original_notify = fake_original_notify

    try:
        with caplog.at_level(logging.WARNING, logger="services.perf_watchdog"):
            hook._profiled_notify(receiver, event)

        slow_lines = [r.message for r in caplog.records if "[SLOW EVENT]" in r.message]
        assert slow_lines, "Erwartete mind. eine SLOW-EVENT-Zeile"
        assert not any("B-621" in line for line in slow_lines), (
            f"Nicht-verschachteltes Event faelschlich als B-621-Artefakt markiert: {slow_lines}"
        )
    finally:
        hook._timer.stop()
        del qapp.notify
        assert "notify" not in qapp.__dict__


def test_call_stack_balanced_after_nested_calls(qapp):
    """Der interne Reentrancy-Stack darf nach verschachtelten Aufrufen nicht
    wachsen (Leak) — muss nach jedem Top-Level-Aufruf wieder leer sein."""
    hook = SlowEventHook(qapp, threshold_ms=10_000)
    receiver = QObject()
    outer_event = QEvent(QEvent.Type.MouseButtonRelease)
    inner_event = QEvent(QEvent.Type.User)

    def fake_original_notify(recv, ev):
        if ev is outer_event:
            hook._profiled_notify(receiver, inner_event)
        return True

    hook._original_notify = fake_original_notify

    try:
        hook._profiled_notify(receiver, outer_event)
        assert hook._call_stack == []
    finally:
        hook._timer.stop()
        del qapp.notify
        assert "notify" not in qapp.__dict__
