@echo off
title PB Studio Rebuild v0.5.0 - Setup (Conda)
echo ============================================
echo   PB Studio Rebuild v0.5.0 - Setup (Conda Workflow)
echo   UI: SCHNITT-Workspace-Redesign (4-Tab-Layout)
echo   Plan: docs\superpowers\plans\2026-05-09-schnitt-workspace-redesign\
echo ============================================
echo.

:: Migration ab 2026-04-27: Conda-zentriert. Standalone Python entfernt.
:: Legacy-Bootstrap (py -3.10) liegt als setup_pb_studio.legacy.bat.
::
:: SCHNITT-Workspace-Redesign 2026-05-09: UI auf 4 Top-Tabs reduziert
:: (PROJEKT / MATERIAL & ANALYSE / SCHNITT / EXPORT). Setup-Schritte
:: selbst sind UI-agnostisch (Conda-Env + ML-Stack), bleiben unveraendert.
:: Live-Verify-Guide: docs\superpowers\plans\2026-05-09-schnitt-workspace-redesign\12_LIVE_VERIFY_USER_GUIDE.md
::
:: Phasen:
::   A) conda env "pb-studio" sicherstellen (env create / update)
::   B) Post-Setup im aktivierten env (HF-Modelle, Ollama, FFmpeg)

cd /d "%~dp0"

:: --- Conda finden ---
set "CONDA_EXE="
if defined CONDA_PREFIX (
    if exist "%CONDA_PREFIX%\Scripts\conda.exe" set "CONDA_EXE=%CONDA_PREFIX%\Scripts\conda.exe"
)
if not defined CONDA_EXE (
    if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" set "CONDA_EXE=%USERPROFILE%\miniconda3\Scripts\conda.exe"
)
if not defined CONDA_EXE (
    if exist "%USERPROFILE%\anaconda3\Scripts\conda.exe" set "CONDA_EXE=%USERPROFILE%\anaconda3\Scripts\conda.exe"
)
if not defined CONDA_EXE (
    where conda >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "CONDA_EXE=conda"
)
if not defined CONDA_EXE (
    echo   FEHLER: Conda nicht gefunden.
    echo   Miniconda installieren: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)
echo   Conda: %CONDA_EXE%

:: --- Env "pb-studio" pruefen ---
"%CONDA_EXE%" env list | findstr /C:"pb-studio " >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   conda env "pb-studio" existiert. Update via environment.yml...
    "%CONDA_EXE%" env update -n pb-studio -f environment.yml --prune
) else (
    echo   conda env "pb-studio" fehlt. Erstelle aus environment.yml...
    "%CONDA_EXE%" env create -f environment.yml
)
if %ERRORLEVEL% NEQ 0 (
    echo   FEHLER: conda env create/update fehlgeschlagen.
    pause
    exit /b 1
)

:: --- Pfad zum env-Python (Standardpfad analog start_pb_studio.bat) ---
set "PB_PYTHON=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
if not exist "%PB_PYTHON%" (
    set "PB_PYTHON=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"
)
if not exist "%PB_PYTHON%" (
    echo   FEHLER: Python in pb-studio env nicht auffindbar.
    echo   Erwartet: %USERPROFILE%\miniconda3\envs\pb-studio\python.exe
    pause
    exit /b 1
)
echo   Python: %PB_PYTHON%

:: --- Post-Setup (HF-Modelle, Ollama, FFmpeg) ---
:: setup_py310_gpu.py legt parallel ein .venv310 an (Legacy-Verhalten).
:: Solange das Script nicht refactored ist, nur Post-Tasks ausfuehren.
:: TODO: scripts/setup_py310_gpu.py auf conda-env-Erkennung umbauen.
echo.
echo   Post-Setup: HF-Modelle, Ollama, FFmpeg ueberspringen Sie %PB_PYTHON%
"%PB_PYTHON%" "%~dp0scripts\setup_py310_gpu.py" --skip-venv %*
set "SETUP_EXIT=%ERRORLEVEL%"

echo.
if %SETUP_EXIT% EQU 0 (
    echo   Setup fertig.
    echo   App-Start:           start_pb_studio.bat
    echo   SCHNITT-Tests:       run_pytest_schnitt.bat   ^(26 Test-Files^)
    echo   Brain-V3-Tests:      run_pytest_brain_v3.bat
    echo   SCHNITT-Live-Verify: docs\superpowers\plans\2026-05-09-schnitt-workspace-redesign\12_LIVE_VERIFY_USER_GUIDE.md
) else (
    echo   Setup mit Fehlercode %SETUP_EXIT% beendet.
)
pause
exit /b %SETUP_EXIT%
