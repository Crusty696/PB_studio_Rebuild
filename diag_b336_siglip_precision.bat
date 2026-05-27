@echo off
title B-336 Diagnose: SigLIP fp16 vs fp32 (GTX 1060)
echo ============================================
echo   B-336 GPU-Benchmark: SigLIP fp16 vs fp32
echo   Prueft NaN/Inf + VRAM-Peak auf cuda:0
echo ============================================
echo.

cd /d "%~dp0"

:: GPU-Env wie in start_pb_studio.bat (gleiche Bedingungen wie App)
set CUDA_MODULE_LOADING=LAZY
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4

set "PB_PYTHON="
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
set "PB_CONDA_PY_ALT=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"
if exist "%PB_CONDA_PY%" set "PB_PYTHON=%PB_CONDA_PY%"
if not defined PB_PYTHON if exist "%PB_CONDA_PY_ALT%" set "PB_PYTHON=%PB_CONDA_PY_ALT%"
if not defined PB_PYTHON if exist ".venv310\Scripts\python.exe" set "PB_PYTHON=.venv310\Scripts\python.exe"
if not defined PB_PYTHON if exist ".venv\Scripts\python.exe" set "PB_PYTHON=.venv\Scripts\python.exe"

if not defined PB_PYTHON (
    echo   FEHLER: conda-env pb-studio nicht gefunden.
    echo   Erwartet: %PB_CONDA_PY%
    pause
    exit /b 1
)

echo   Python: %PB_PYTHON%
echo.
:: Alle uebergebenen Argumente durchreichen (z.B. --image, --batch)
"%PB_PYTHON%" tools\diag_b336_siglip_precision.py %*

echo.
echo   ---- fertig. Zahlen oben bitte ins Vault (B-336) zuruckmelden. ----
pause
