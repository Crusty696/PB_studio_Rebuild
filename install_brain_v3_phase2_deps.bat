@echo off
title Brain V3 - Phase 2 Dependencies installieren
echo ============================================
echo   Brain V3 — Phase 2 Dependencies
echo   Installiert sqlite-vec ins conda-env pb-studio
echo ============================================
echo.

cd /d "%~dp0"

set "PB_PYTHON="
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
set "PB_CONDA_PY_ALT=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" (
    set "PB_PYTHON=%PB_CONDA_PY%"
) else if exist "%PB_CONDA_PY_ALT%" (
    set "PB_PYTHON=%PB_CONDA_PY_ALT%"
) else if exist ".venv310\Scripts\python.exe" (
    set "PB_PYTHON=.venv310\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PB_PYTHON=.venv\Scripts\python.exe"
) else (
    echo FEHLER: Keine Python-Umgebung gefunden.
    pause
    exit /b 1
)

echo Python: %PB_PYTHON%
echo.
echo Installation: sqlite-vec
echo.
"%PB_PYTHON%" -m pip install "sqlite-vec>=0.1.6"
set INSTALL_RC=%ERRORLEVEL%

echo.
echo ============================================
if %INSTALL_RC% EQU 0 (
    echo   Installation erfolgreich.
    echo   Du kannst jetzt run_pytest_brain_v3.bat ausfuehren —
    echo   die Phase-2-Tests werden dann nicht mehr geskippt.
) else (
    echo   Installation FEHLGESCHLAGEN ^(Exit-Code: %INSTALL_RC%^)
    echo   Pruefe Output oben.
)
echo ============================================
echo.
pause
exit /b %INSTALL_RC%
