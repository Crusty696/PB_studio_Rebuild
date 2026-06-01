from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest

from services import startup_checks


def test_startup_checks_run_without_qapplication(monkeypatch, tmp_path):
    monkeypatch.setattr(startup_checks, "_check_cuda", lambda: (False, "", 0))
    monkeypatch.setattr(startup_checks, "_check_ffmpeg", lambda: (True, "6.1", True))
    monkeypatch.setattr(startup_checks, "_check_disk", lambda _path: 64.0)
    monkeypatch.setattr(startup_checks, "_check_hf_cache", lambda: (True, str(tmp_path), "HF_HOME", "ok", []))
    monkeypatch.setattr(startup_checks, "_check_ollama", lambda: False)
    monkeypatch.setattr(startup_checks, "_check_ml_packages", lambda: (True, True))
    monkeypatch.setattr(startup_checks, "_get_nvidia_driver_version", lambda: ("", ""))
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(__version__="test", version=SimpleNamespace(cuda="test")),
    )

    sys.modules.pop("PySide6.QtWidgets", None)

    status = startup_checks.check_system(tmp_path)

    assert status.ffmpeg_ok is True
    assert status.disk_ok is True
    assert status.cuda_ok is False
    assert "PySide6.QtWidgets" not in sys.modules


def test_database_bootstrap_failure_logs_and_exits_cleanly(monkeypatch, caplog):
    class _Metadata:
        def create_all(self, _engine):
            raise RuntimeError("db locked for test")

    class _Splash:
        closed = False

        def show_message(self, _message):
            pass

        def close(self):
            self.closed = True

    fake_database = SimpleNamespace(
        Base=SimpleNamespace(metadata=_Metadata()),
        engine=object(),
        init_db=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "database", fake_database)

    splash = _Splash()
    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(SystemExit) as exc_info:
            startup_checks.run_database_bootstrap(
                splash=splash,
                process_events=lambda: None,
            )

    assert exc_info.value.code == 1
    assert splash.closed is True
    assert "Datenbank-Initialisierung beim Start fehlgeschlagen" in caplog.text
    assert "db locked for test" in caplog.text


def test_cuda_unavailable_is_degraded_status_not_crash(monkeypatch, caplog):
    fake_torch = SimpleNamespace(
        __version__="1.12.1+cu113",
        version=SimpleNamespace(cuda="11.3"),
        cuda=SimpleNamespace(is_available=lambda: False),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        startup_checks,
        "_get_nvidia_driver_version",
        lambda: ("551.00", "NVIDIA GeForce GTX 1060"),
    )

    with caplog.at_level(logging.WARNING):
        cuda_ok, gpu_name, vram_mb = startup_checks._check_cuda()

    assert cuda_ok is False
    assert gpu_name == "NVIDIA GeForce GTX 1060"
    assert vram_mb == 0
    assert "torch.cuda.is_available() ist False" in caplog.text
