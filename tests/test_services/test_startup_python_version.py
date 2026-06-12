"""Unit tests for ``services.startup_checks.check_python_version``.

B-499 (Runtime-/Dependency-Drift): PB Studio darf nur unter dem
kanonischen Python 3.10 laufen (conda-env "pb-studio",
torch 1.12.1+cu113). ``check_python_version`` muss jeden fremden
Interpreter (z.B. conda-base 3.13, uv-Python 3.11) als Fehler melden —
ohne sys.exit, damit der Startup-Dialog die Meldung anzeigen kann.

``sys.version_info`` wird per monkeypatch ersetzt — die Tests duerfen
nicht vom Interpreter abhaengen, der die Testsuite ausfuehrt.
"""

from __future__ import annotations

import pytest

from services import startup_checks


def _patch_version(monkeypatch: pytest.MonkeyPatch, version: tuple) -> None:
    """Helper: replace ``sys.version_info`` as seen by startup_checks."""
    monkeypatch.setattr(startup_checks.sys, "version_info", version)


def test_check_passes_on_python_310(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_version(monkeypatch, (3, 10, 20, "final", 0))

    ok, version_str = startup_checks.check_python_version()

    assert ok is True
    assert version_str == "3.10.20"


def test_check_fails_on_python_313(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_version(monkeypatch, (3, 13, 13, "final", 0))

    ok, version_str = startup_checks.check_python_version()

    assert ok is False
    assert version_str == "3.13.13"


def test_check_fails_on_python_311(monkeypatch: pytest.MonkeyPatch) -> None:
    """uv-Python 3.11 (py-Launcher-Default auf diesem System) ist ebenso falsch."""
    _patch_version(monkeypatch, (3, 11, 15, "final", 0))

    ok, _version_str = startup_checks.check_python_version()

    assert ok is False


def test_check_fails_on_python_39(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auch ZU ALTE Interpreter muessen abgelehnt werden, nicht nur neuere."""
    _patch_version(monkeypatch, (3, 9, 18, "final", 0))

    ok, _version_str = startup_checks.check_python_version()

    assert ok is False
