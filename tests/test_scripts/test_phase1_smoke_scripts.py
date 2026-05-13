from pathlib import Path


def test_phase1_smoke_scripts_do_not_hardcode_local_repo_path() -> None:
    root = Path(__file__).resolve().parents[2]
    scripts = [
        root / "scripts" / "phase1_import_test.py",
        root / "scripts" / "phase1_cache_test.py",
    ]

    for script in scripts:
        src = script.read_text(encoding="utf-8")
        assert r"C:\Users\David Lochmann\Documents\PB_studio_Rebuild" not in src
        assert "Path(__file__).resolve()" in src
