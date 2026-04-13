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

:: .venv310 ist das einzige unterstuetzte Setup
if not exist ".venv310\Scripts\python.exe" (
    echo   FEHLER: .venv310 nicht gefunden!
    echo   Bitte zuerst Setup ausfuehren:
    echo     py -3.10 scripts\setup_py310_gpu.py
    echo.
    pause
    exit /b 1
)

echo   Python 3.10 + CUDA 11.3 (.venv310)
echo   Starte PB Studio...
echo.
".venv310\Scripts\python.exe" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %ERRORLEVEL%
    pause
)
