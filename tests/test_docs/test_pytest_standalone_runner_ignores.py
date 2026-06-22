from pathlib import Path


def test_video_analysis_real_standalone_runner_is_ignored_by_pytest():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert "--ignore=tests/test_video_analysis_real.py" in pyproject
