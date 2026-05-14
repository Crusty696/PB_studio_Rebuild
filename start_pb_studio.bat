@echo off
title PB Studio Rebuild v0.5.0 (SCHNITT-Redesign)
echo ============================================
echo   PB Studio Rebuild v0.5.0 - App starten
echo   UI: 4-Tab-Layout (PROJEKT / MATERIAL ^& ANALYSE / SCHNITT / EXPORT)
echo   SCHNITT-Tab: Empty/Loading/Editor + 4 Sub-Tabs
echo   Branch-State: code-fix-pending-live-verification
echo ============================================
echo.

:: Ins Skript-Verzeichnis wechseln (wichtig bei Shortcuts)
cd /d "%~dp0"

:: NVIDIA GTX 1060 Fix: Lazy Loading fuer CUDA Module
set CUDA_MODULE_LOADING=LAZY

:: B-215 Fix: OpenMP/MKL Doppel-Init verhindern.
:: Conda's intel-openmp (libiomp5md.dll) + Windows' vcomp140.dll = /GS-Stack-
:: Guard schlaegt zu (STATUS_STACK_BUFFER_OVERRUN, exit -1073740791) beim
:: zweiten Modell-Load (typisch: SigLIP geladen, dann RAFT crasht).
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4

:: Python-Auswahl: conda-env "pb-studio" bevorzugt (Migrations-Ziel
:: ab 2026-04-27, siehe wiki/synthesis/cycle-21-conda-migration-*.md).
:: Fallbacks: .venv310 (alt, Python 3.10 + CUDA 11.3) und .venv
:: (Legacy-Fallback). Reihenfolge spiegelt Praeferenz wieder.
set "PB_PYTHON="
set "PB_LABEL="
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
set "PB_CONDA_PY_ALT=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" goto use_conda
if exist "%PB_CONDA_PY_ALT%" goto use_conda_alt
if exist ".venv310\Scripts\python.exe" goto use_venv310
if exist ".venv\Scripts\python.exe" goto use_venv
goto no_python

:use_conda
set "PB_PYTHON=%PB_CONDA_PY%"
set "PB_LABEL=conda-env pb-studio (Python 3.10 + CUDA 11.3)"
goto run_app

:use_conda_alt
set "PB_PYTHON=%PB_CONDA_PY_ALT%"
set "PB_LABEL=conda-env pb-studio (Python 3.10 + CUDA 11.3, Anaconda)"
goto run_app

:use_venv310
set "PB_PYTHON=.venv310\Scripts\python.exe"
set "PB_LABEL=.venv310 (Python 3.10 + CUDA 11.3, Legacy)"
goto run_app

:use_venv
set "PB_PYTHON=.venv\Scripts\python.exe"
set "PB_LABEL=.venv (Legacy-Fallback)"
goto run_app

:no_python
echo   FEHLER: Keine kompatible Python-Umgebung gefunden.
echo   Erwartet (Praeferenz):
echo     1. conda-env pb-studio (siehe environment.yml)
echo     2. .venv310 oder .venv
echo.
echo   Setup ausfuehren:
echo     conda env create -f environment.yml
echo   oder
echo     setup_pb_studio.bat
echo.
pause
exit /b 1

:run_app
echo   Python: %PB_LABEL%
echo   Starte PB Studio...
echo.
echo   Live-Verify-Guide: docs\superpowers\plans\2026-05-09-schnitt-workspace-redesign\12_LIVE_VERIFY_USER_GUIDE.md
echo.

:: --- Log-Capture: outputs\app_run_<timestamp>.log + outputs\app_run_<timestamp>_err.log ---
if not exist "outputs" mkdir outputs
set "PB_TS="
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyy-MM-dd_HHmmss" 2^>nul') do set "PB_TS=%%I"
if not defined PB_TS set "PB_TS=no_timestamp"
set "PB_LOG=outputs\app_run_%PB_TS%.log"
set "PB_LOG_ERR=outputs\app_run_%PB_TS%_err.log"
echo   Log:    %PB_LOG%
echo   Err:    %PB_LOG_ERR%
echo.

"%PB_PYTHON%" main.py 1>"%PB_LOG%" 2>"%PB_LOG_ERR%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %ERRORLEVEL%
    echo   Logs: %PB_LOG% / %PB_LOG_ERR%
    pause
)
