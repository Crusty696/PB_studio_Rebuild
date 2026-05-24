from __future__ import annotations

from pathlib import Path

from services import startup_checks


def test_hf_home_configured_reports_portable_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    ok, path, source, detail, warnings = startup_checks._check_hf_cache()

    assert ok is True
    assert path == str(tmp_path)
    assert source == "HF_HOME"
    assert "portabler" in detail
    assert warnings == []


def test_hf_hub_cache_takes_precedence(monkeypatch, tmp_path: Path) -> None:
    hub_cache = tmp_path / "hub"
    hub_cache.mkdir()
    monkeypatch.setenv("HF_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(hub_cache))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)

    ok, path, source, _detail, warnings = startup_checks._check_hf_cache()

    assert ok is True
    assert path == str(hub_cache)
    assert source == "HUGGINGFACE_HUB_CACHE"
    assert warnings == []


def test_missing_hf_cache_env_is_non_blocking_warning(monkeypatch) -> None:
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)

    ok, path, source, detail, warnings = startup_checks._check_hf_cache()

    assert ok is False
    assert path
    assert source == "default"
    assert detail == "kein portabler Cache gesetzt"
    assert warnings


def test_run_startup_checks_delegates_to_check_system(monkeypatch, tmp_path: Path) -> None:
    expected = startup_checks.SystemStatus(hf_cache_ok=True, hf_cache_path=str(tmp_path))

    def fake_check_system(app_root=None):
        assert app_root == tmp_path
        return expected

    monkeypatch.setattr(startup_checks, "check_system", fake_check_system)

    assert startup_checks.run_startup_checks(tmp_path) is expected
