from pathlib import Path


def test_video_analysis_real_standalone_runner_is_ignored_by_pytest():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert "--ignore=tests/test_video_analysis_real.py" in pyproject


def test_export_convert_real_standalone_runner_is_ignored_by_pytest():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert "--ignore=tests/test_export_convert_real.py" in pyproject


def test_qa_artifacts_are_ignored_by_pytest_collection():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert "--ignore=tests/qa_artifacts" in pyproject
