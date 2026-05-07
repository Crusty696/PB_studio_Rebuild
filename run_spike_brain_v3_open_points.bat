@echo off
title Brain V3 - Open Points Validation Spike (vor Plan-Beginn)
echo ============================================
echo   Brain V3 — Open-Points Validation
echo   Verifiziert die 6 als "offen" markierten Punkte:
echo     1) F-Measure SubtrackDetector
echo     2) 500-Clip-Hochrechnung (50 Clips x 10)
echo     3) HNSW in sqlite-vec (0.1.9 installiert)
echo     4) Demucs + Brain Coexistenz
echo     5) NVENC + Brain
echo     6) PySide6-App-Boot VRAM
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

echo Python: %PB_PYTHON%
echo.
echo Dauer-Schaetzung: 10-30 min total (50-Clip-Lauf ist groesster Teil)
echo Output: outputs\spike_brain_v3_open_points\^<timestamp^>\
echo.

"%PB_PYTHON%" scripts\spike_brain_v3_open_points.py
set RC=%ERRORLEVEL%

echo.
echo ============================================
echo   Open-Points-Spike beendet (Exit-Code: %RC%)
echo   report.md im Output-Verzeichnis durchsehen
echo ============================================
echo.
pause
exit /b %RC%
