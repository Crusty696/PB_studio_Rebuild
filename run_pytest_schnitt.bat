@echo off
setlocal
title PB Studio - SCHNITT Tests

cd /d "%~dp0"

set "PB_PYTHON="
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
set "PB_CONDA_PY_ALT=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" set "PB_PYTHON=%PB_CONDA_PY%"
if not defined PB_PYTHON if exist "%PB_CONDA_PY_ALT%" set "PB_PYTHON=%PB_CONDA_PY_ALT%"
if not defined PB_PYTHON if exist ".venv310\Scripts\python.exe" set "PB_PYTHON=.venv310\Scripts\python.exe"
if not defined PB_PYTHON if exist ".venv\Scripts\python.exe" set "PB_PYTHON=.venv\Scripts\python.exe"

if not defined PB_PYTHON (
    echo FEHLER: Keine PB-Studio-Python-Umgebung gefunden.
    echo Erwartet: conda env pb-studio, .venv310 oder .venv.
    exit /b 1
)

if not defined QT_QPA_PLATFORM set "QT_QPA_PLATFORM=offscreen"

echo Python: %PB_PYTHON%
echo QT_QPA_PLATFORM=%QT_QPA_PLATFORM%
echo.

if "%~1"=="" (
    "%PB_PYTHON%" -m pytest ^
        tests\ui\test_b471_timeline_usability_recovery.py ^
        tests\test_ui\test_b471_thumbnail_request_path.py ^
        tests\test_ui\test_b471_thumbnail_load_manager.py ^
        tests\test_ui\test_b471_zoom_label_no_distort.py ^
        -q
) else (
    "%PB_PYTHON%" -m pytest %*
)

exit /b %ERRORLEVEL%
