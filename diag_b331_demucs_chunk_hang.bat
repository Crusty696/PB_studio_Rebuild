@echo off
title B-331 Diagnose: Demucs Chunk-Hang Repro (GTX 1060)
echo ============================================
echo   B-331 Repro: Demucs haengt nach Chunk ~51
echo   Echter separate()-Lauf + Watchdog + Stackdump
echo ============================================
echo.
echo   TIPP: Audio-Datei einfach auf diese .bat ZIEHEN (Drag and Drop),
echo         oder Pfad eingeben wenn gefragt.
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

:: Audio-Pfad aus Drag-and-Drop (%~1) oder Eingabe
set "PB_AUDIO=%~1"
if "%PB_AUDIO%"=="" set /p "PB_AUDIO=Pfad zum langen Audio-Mix eingeben: "
if "%PB_AUDIO%"=="" (
    echo   FEHLER: Kein Audio-Pfad angegeben.
    pause
    exit /b 1
)
if not exist "%PB_AUDIO%" (
    echo   FEHLER: Datei nicht gefunden: %PB_AUDIO%
    pause
    exit /b 1
)

echo   Python: %PB_PYTHON%
echo   Audio:  %PB_AUDIO%
echo   Chunk-Limit: 55 (knapp ueber den problematischen Chunk 51)
echo.
echo   WICHTIG: NICHT parallel zu anderen GPU-Jobs. Bei Hang in zweiter
echo            Shell "nvidia-smi" pruefen.
echo.

"%PB_PYTHON%" tools\diag_b331_demucs_chunk_hang.py --audio "%PB_AUDIO%" --max-chunks 55

echo.
echo   ---- fertig. Bei Hang: Stackdump oben + nvidia-smi-Verhalten ins Vault (B-331). ----
pause
