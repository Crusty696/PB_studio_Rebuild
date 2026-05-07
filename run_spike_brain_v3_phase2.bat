@echo off
title Brain V3 - Phase 2 Validation Spike (Embedder + KNN-Scaling)
echo ============================================
echo   Brain V3 — Phase 2 Validation
echo   1) Embedder End-to-End Smoke (CLAP+SigLIP-2)
echo   2) KNN Scaling auf 16k Vektoren
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
echo === 1/2: Embedder End-to-End Smoke ===
"%PB_PYTHON%" scripts\spike_brain_v3_embedder_smoke.py --n-audio 3 --n-video 3
set EMB_RC=%ERRORLEVEL%
echo (Embedder-Smoke Exit-Code: %EMB_RC%)
echo.

echo === 2/2: KNN-Scaling 16k Vektoren ===
"%PB_PYTHON%" scripts\spike_brain_v3_knn_scaling.py --n-vectors 16000 --n-queries 100
set KNN_RC=%ERRORLEVEL%
echo (KNN-Scaling Exit-Code: %KNN_RC%)

echo.
echo ============================================
echo   Phase 2 Validation beendet
echo   Embedder: %EMB_RC%, KNN: %KNN_RC%
echo   Output: outputs\spike_brain_v3_embedder\, outputs\spike_brain_v3_knn\
echo ============================================
echo.
pause
exit /b 0
