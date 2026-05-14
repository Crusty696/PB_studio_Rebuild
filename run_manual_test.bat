@echo off
setlocal
echo ============================================================
echo   PB Studio v0.5.0 - Manual Test Mode
echo ============================================================
echo.

:: Fuege lokalen bin-Ordner zum PATH hinzu
set "PATH=%CD%\bin;%PATH%"

set PB_STUDIO_CI=0
set PB_STUDIO_JSON_LOGS=0

echo Pruefe FFmpeg...
ffmpeg -version | findstr /C:"ffmpeg version"
if %ERRORLEVEL% NEQ 0 (
    echo [WARNUNG] FFmpeg wurde nicht im lokalen bin-Ordner gefunden!
)

echo Starte PB Studio...
:: Conda-env pb-studio bevorzugen (Migrations-Ziel ab 2026-04-27),
:: dann .venv310 (Python 3.10 + CUDA 11.3 Legacy), dann .venv (CPU).
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
set "PB_CONDA_PY_ALT=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"
if exist "%PB_CONDA_PY%" (
    "%PB_CONDA_PY%" main.py
) else if exist "%PB_CONDA_PY_ALT%" (
    "%PB_CONDA_PY_ALT%" main.py
) else if exist ".venv310\Scripts\python.exe" (
    .\.venv310\Scripts\python.exe main.py
) else if exist ".venv\Scripts\python.exe" (
    .\.venv\Scripts\python.exe main.py
) else (
    echo [FEHLER] Keine Python-Umgebung gefunden.
    exit /b 1
)
pause
endlocal
