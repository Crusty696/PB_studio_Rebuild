from pathlib import Path


def test_start_pb_studio_batch_captures_stdout_and_stderr_logs() -> None:
    text = Path("start_pb_studio.bat").read_text(encoding="utf-8")

    assert "powershell -NoProfile -ExecutionPolicy Bypass" in text
    assert "Get-Date -Format yyyy-MM-dd_HHmmss" in text
    assert 'if not defined PB_TS set "PB_TS=no_timestamp"' in text
    assert "outputs\\app_run_%PB_TS%.log" in text
    assert "outputs\\app_run_%PB_TS%_err.log" in text
    assert "set PB_REQUIRE_NVENC=1" in text
    assert '"%PB_PYTHON%" main.py 1>"%PB_LOG%" 2>"%PB_LOG_ERR%"' in text
    assert "Logs: %PB_LOG% / %PB_LOG_ERR%" in text
