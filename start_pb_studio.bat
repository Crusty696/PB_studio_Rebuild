@echo off
title PB Studio Rebuild
echo ============================================
echo   PB Studio Rebuild - App starten
echo ============================================
echo.

:: Ins Skript-Verzeichnis wechseln (wichtig bei Shortcuts)
cd /d "%~dp0"

:: NVIDIA GTX 1060 Fix: Lazy Loading fuer CUDA Module
set CUDA_MODULE_LOADING=LAZY

:: Python-Auswahl: conda-env "pb-studio" bevorzugt (Migrations-Ziel
:: ab 2026-04-27, siehe wiki/synthesis/cycle-21-conda-migration-*.md).
:: Fallbacks: .venv310 (alt, Python 3.10 + CUDA 11.3) und .venv
:: (Python 3.11, CPU). Reihenfolge spiegelt Praeferenz wieder.
set "PB_PYTHON="
set "PB_LABEL="
set "PB_CONDA_PY=C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" goto use_conda
if exist ".venv310\Scripts\python.exe" goto use_venv310
if exist ".venv\Scripts\python.exe" goto use_venv
goto no_python

:use_conda
set "PB_PYTHON=%PB_CONDA_PY%"
set "PB_LABEL=conda-env pb-studio (Python 3.10 + CUDA 11.3)"
goto run_app

:use_venv310
set "PB_PYTHON=.venv310\Scripts\python.exe"
set "PB_LABEL=.venv310 (Python 3.10 + CUDA 11.3, Legacy)"
goto run_app

:use_venv
set "PB_PYTHON=.venv\Scripts\python.exe"
set "PB_LABEL=.venv (Python 3.11 CPU-Fallback, Legacy)"
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
"%PB_PYTHON%" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %ERRORLEVEL%
    pause
)
