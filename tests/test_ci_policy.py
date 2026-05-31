from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_defines_default_pytest_gate():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Run unit tests" in ci
    assert 'pytest -m "not live_gpu and not e2e and not slow"' in ci


def test_manual_heavy_test_commands_are_documented():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "Manual heavy-suite commands" in pyproject
    assert "pytest tests/test_db_deep.py -v" in pyproject
    assert "pytest tests/live_ollama_integration_test.py -v" in pyproject
    assert "pytest tests/test_services/test_video_pipeline_e2e_live.py -m live_gpu -v" in pyproject
