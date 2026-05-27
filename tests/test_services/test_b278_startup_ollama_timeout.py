"""B-278: Ollama-Startup-Timeout darf keinen kritischen Worker-Traceback ausloesen.

Root cause: In Python 3.10 ist ``concurrent.futures.TimeoutError`` KEINE
Subklasse des builtin ``TimeoutError``. Der ``except (TimeoutError, ...)``-Block
in ``check_system()`` fing den Future-Timeout daher nicht ab — die Exception
entkam aus ``check_system()`` und der StartupCheckWorker loggte einen
"Kritischer Fehler bei Systempruefung"-Traceback, obwohl Ollama nur langsam
startete.
"""

from __future__ import annotations

import time

from services import startup_checks


def test_concurrent_futures_timeout_is_not_builtin_subclass():
    """Regression-Anker: belegt die Ursache (distinkte Exception-Klassen)."""
    import concurrent.futures
    assert not issubclass(concurrent.futures.TimeoutError, TimeoutError)


def test_slow_ollama_check_does_not_escape_check_system(monkeypatch, tmp_path):
    """Ein Ollama-Check, der laenger als sein Future-Timeout braucht, darf
    NICHT aus check_system() entkommen; ollama_ok bleibt False."""

    # Future-Timeout fuer Ollama auf einen kurzen Wert druecken, damit der
    # Test schnell ist. _check_ollama schlaeft laenger als dieser Wert.
    monkeypatch.setattr(startup_checks, "STARTUP_OLLAMA_CHECK_TIMEOUT_SEC", 0.2)

    def slow_ollama():
        time.sleep(2.0)
        return True

    # Restliche Checks neutralisieren, damit der Test deterministisch/schnell ist.
    monkeypatch.setattr(startup_checks, "_check_cuda", lambda: (False, "", 0))
    monkeypatch.setattr(startup_checks, "_check_ffmpeg", lambda: (True, "6.0", True))
    monkeypatch.setattr(startup_checks, "_check_disk", lambda p: 100.0)
    monkeypatch.setattr(
        startup_checks, "_check_hf_cache", lambda: (True, "/x", "HF_HOME", "ok", [])
    )
    monkeypatch.setattr(startup_checks, "_check_ml_packages", lambda: (True, True))
    monkeypatch.setattr(startup_checks, "_check_ollama", slow_ollama)

    # Darf nicht werfen (vor dem Fix: concurrent.futures.TimeoutError entkam).
    status = startup_checks.check_system(tmp_path)

    assert isinstance(status, startup_checks.SystemStatus)
    # Der getimeoutete Ollama-Check bleibt auf seinem Default False (degradiert).
    assert status.ollama_ok is False
    # Andere Checks wurden normal befuellt.
    assert status.ffmpeg_ok is True
