from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_pyinstaller_does_not_require_gitignored_ollama_bundle():
    spec = (ROOT / "pb_studio.spec").read_text(encoding="utf-8")

    assert "ROOT / 'redist' / 'ollama.exe'" not in spec
    assert "ROOT / 'redist' / 'lib'" not in spec
    assert "Ollama is NOT bundled" in spec


def test_frozen_app_keeps_optional_bundle_then_system_fallback():
    source = (ROOT / "services" / "ollama_service.py").read_text(encoding="utf-8")

    assert "if bundled.exists():" in source
    assert "Programs' / 'Ollama' / 'ollama.exe'" in source
    assert "return Path('ollama')" in source
