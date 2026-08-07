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


def test_clicklog_batch_passes_valid_powershell_redirection() -> None:
    text = Path("start_pb_studio_clicklog.bat").read_text(encoding="utf-8")

    assert "2^>^&1 | Tee-Object" not in text
    assert "2>&1 | Tee-Object" in text
    assert "exit $LASTEXITCODE" in text
    assert 'set "PB_APP_EXIT=%ERRORLEVEL%"' in text


def test_clicklog_batch_seeds_empty_isolated_settings_before_app_start() -> None:
    text = Path("start_pb_studio_clicklog.bat").read_text(encoding="utf-8")

    settings_dir = (
        'if not exist "%APPDATA%\\PBStudio" mkdir "%APPDATA%\\PBStudio"'
    )
    settings_seed = (
        'if not exist "%APPDATA%\\PBStudio\\settings.json" '
        '> "%APPDATA%\\PBStudio\\settings.json" echo {}'
    )
    app_start = "& '%PB_PYTHON%' main.py"

    assert settings_dir in text
    assert settings_seed in text
    assert text.index(settings_dir) < text.index(app_start)
    assert text.index(settings_seed) < text.index(app_start)
