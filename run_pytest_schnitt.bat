@echo off
title SCHNITT Workspace Redesign - pytest
echo ============================================
echo   SCHNITT Workspace Redesign - Tests (pytest)
echo   Branch: feat/schnitt-redesign-2026-05-09
echo   Plan: docs\superpowers\plans\2026-05-09-schnitt-workspace-redesign\
echo ============================================
echo.

cd /d "%~dp0"

set CUDA_MODULE_LOADING=LAZY
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4

set "PB_PYTHON="
set "PB_CONDA_PY=C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" (
    set "PB_PYTHON=%PB_CONDA_PY%"
) else if exist ".venv310\Scripts\python.exe" (
    set "PB_PYTHON=.venv310\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PB_PYTHON=.venv\Scripts\python.exe"
) else (
    echo FEHLER: Keine Python-Umgebung gefunden.
    pause
    exit /b 1
)

if not exist "outputs" mkdir outputs
set "RESULT_FILE=outputs\pytest_schnitt_results.txt"

echo Python: %PB_PYTHON%
echo Output: %RESULT_FILE%
echo.
echo Test-Lauf gestartet (26 SCHNITT-Test-Files, Output zugleich in %RESULT_FILE%):
echo.

"%PB_PYTHON%" -m pytest ^
    tests\test_services\test_pacing_profile.py ^
    tests\test_services\test_timeline_state.py ^
    tests\test_services\test_timeline_snapshot_service.py ^
    tests\test_services\test_project_notes_service.py ^
    tests\test_services\test_ui_binder_pacing.py ^
    tests\test_services\test_apply_auto_edit_locked.py ^
    tests\test_services\test_cockpit_open_schnitt.py ^
    tests\test_services\test_auto_edit_progress.py ^
    tests\ui\test_subtab_schnitt_layout.py ^
    tests\ui\test_subtab_pacing_anker_layout.py ^
    tests\ui\test_subtab_audio_layout.py ^
    tests\ui\test_subtab_audio_render.py ^
    tests\ui\test_subtab_rl_notes.py ^
    tests\ui\test_schnitt_workspace_states.py ^
    tests\ui\test_schnitt_views_skeleton.py ^
    tests\ui\test_schnitt_editor_view_skeleton.py ^
    tests\ui\test_schnitt_controller_loading_hook.py ^
    tests\ui\test_schnitt_controller_wiring.py ^
    tests\ui\test_wheel_guard.py ^
    tests\ui\test_lock_icon_item.py ^
    tests\ui\test_toggle_clip_lock_command.py ^
    tests\ui\test_timeline_clip_lock.py ^
    tests\ui\test_clip_lock_click.py ^
    tests\ui\test_regenerate_dialog.py ^
    tests\ui\test_qsettings_migration.py ^
    tests\ui\test_cuts_worker_progress.py ^
    -v --tb=short --color=no > "%RESULT_FILE%" 2>&1

set PYTEST_RC=%ERRORLEVEL%
type "%RESULT_FILE%"

echo.
echo ============================================
echo   pytest beendet (Exit-Code: %PYTEST_RC%)
echo   Vollstaendiges Log: %RESULT_FILE%
echo ============================================
echo.
pause
exit /b %PYTEST_RC%
