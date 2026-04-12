@echo off
title PB Studio Rebuild
echo ============================================
echo   PB Studio Rebuild - App starten
echo ============================================
echo.

:: NVIDIA GTX 1060 Fix: Lazy Loading für CUDA Module (verhindert oft init errors)
set CUDA_MODULE_LOADING=LAZY

:: Pruefen ob .venv310 existiert (Python 3.10 + CUDA 11.3)
if exist "%~dp0.venv310\Scripts\python.exe" (
    echo   venv gefunden: .venv310\ (Python 3.10 + CUDA 11.3)
    echo   Starte PB Studio...
    echo.
    "%~dp0.venv310\Scripts\python.exe" "%~dp0main.py"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    echo   venv gefunden: .venv\ (Legacy)
    echo   Starte PB Studio...
    echo.
    "%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
) else (
    echo   Kein venv gefunden!
    echo   Bitte zuerst ausfuehren: py -3.10 scripts\setup_py310_gpu.py
    pause
    exit /b 1
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %ERRORLEVEL%
    pause
)
