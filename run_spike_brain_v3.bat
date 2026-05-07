@echo off
title Brain V3 - Phase 0 Spike (GPU-Coexistenz + VRAM-Budget)
echo ============================================
echo   Brain V3 — Phase 0 Spike
echo   GPU-Coexistenz + VRAM-Budget-Messung
echo ============================================
echo.

:: Ins Skript-Verzeichnis wechseln (wichtig bei Doppelklick aus Explorer)
cd /d "%~dp0"

:: Identische Env-Vars wie start_pb_studio.bat (B-215 + GTX 1060 LAZY-Loading)
set CUDA_MODULE_LOADING=LAZY
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4

:: Python-Auswahl in gleicher Praeferenz wie start_pb_studio.bat
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
goto run_spike

:use_venv310
set "PB_PYTHON=.venv310\Scripts\python.exe"
set "PB_LABEL=.venv310 (Python 3.10 + CUDA 11.3)"
goto run_spike

:use_venv
set "PB_PYTHON=.venv\Scripts\python.exe"
set "PB_LABEL=.venv (Python 3.11 CPU-Fallback)"
goto run_spike

:no_python
echo   FEHLER: Keine Python-Umgebung gefunden.
echo   Erwartet (Praeferenz):
echo     1. conda-env pb-studio
echo     2. .venv310 oder .venv
echo.
pause
exit /b 1

:run_spike
echo   Python: %PB_LABEL%
echo.
echo   1/2: CUDA-Diagnose (kostenlos, klaert ob torch/cuda OK)
echo ============================================
"%PB_PYTHON%" scripts\diagnose_cuda.py
set DIAG_RC=%ERRORLEVEL%
echo.
if %DIAG_RC% NEQ 0 (
    echo   WARNUNG: diagnose_cuda.py meldet %DIAG_RC% kritische Findings.
    echo   Spike trotzdem starten, kann aber bei CUDA-Init scheitern.
    echo.
    timeout /t 5
)

echo.
echo   2/2: Spike (CLAP + SigLIP-2 + Coexistenz)
echo ============================================
echo   ACHTUNG: Erstlauf laedt Modelle (~1.8 GB Download).
echo   Dauer: 10-30 min beim ersten Mal.
echo.
"%PB_PYTHON%" scripts\spike_brain_v3_gpu_coexistence.py
set SPIKE_RC=%ERRORLEVEL%

echo.
echo ============================================
echo   Spike beendet (Exit-Code: %SPIKE_RC%)
echo   Output: outputs\spike_brain_v3_gpu\<timestamp>\
echo     - snapshots.json
echo     - report.md
echo     - run.log
echo ============================================
echo.
pause
exit /b %SPIKE_RC%
