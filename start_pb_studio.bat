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

:: Venv-Auswahl: .venv310 bevorzugt (Python 3.10 + CUDA 11.3, GPU-Pfad),
:: Fallback .venv (Python 3.11, CPU-Pfad). Beide unterstuetzt.
:: Batch-Pitfall: Klammern in Strings innerhalb IF-Bloecken terminieren den
:: Block vorzeitig, deshalb hier goto-Labels statt verschachteltem if/else.
set "PB_VENV="

if exist ".venv310\Scripts\python.exe" goto use_venv310
if exist ".venv\Scripts\python.exe" goto use_venv
goto no_venv

:use_venv310
set "PB_VENV=.venv310"
echo   Python 3.10 + CUDA 11.3 .venv310
goto run_app

:use_venv
set "PB_VENV=.venv"
echo   Python 3.11 .venv - CPU-Fallback
goto run_app

:no_venv
echo   FEHLER: Keine kompatible venv gefunden.
echo   Erwartet: .venv310 oder .venv
echo.
echo   Setup ausfuehren:
echo     setup_pb_studio.bat
echo.
pause
exit /b 1

:run_app
echo   Starte PB Studio...
echo.
"%PB_VENV%\Scripts\python.exe" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %ERRORLEVEL%
    pause
)
