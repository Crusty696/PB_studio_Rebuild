@echo off
title PB Studio Rebuild - Setup
echo ============================================
echo   PB Studio Rebuild - Setup
echo ============================================
echo.

:: Strategie: Python 3.10 + CUDA 11.3 (Treiber 461.40 kompatibel)
:: Fallback: Python 3.11 (ohne GPU oder mit neuerem Treiber)

:: Zuerst Python 3.10 suchen (bevorzugt fuer GPU)
set "PYEXE="

py -3.10 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYEXE=py -3.10"
    echo   Python 3.10 gefunden (GPU-kompatibel)
    goto :found
)

if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    echo   Python 3.10 gefunden: %PYEXE%
    goto :found
)

:: Fallback: Python 3.11
py -3.11 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYEXE=py -3.11"
    echo   Python 3.11 gefunden (kein GPU mit Treiber 461.40)
    goto :found
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    echo   Python 3.11 gefunden: %PYEXE%
    goto :found
)

echo.
echo   FEHLER: Weder Python 3.10 noch 3.11 gefunden!
echo   Bitte installieren: https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
echo.
pause
exit /b 1

:found
echo.
%PYEXE% "%~dp0scripts\setup_py310_gpu.py" %*
set "SETUP_EXIT=%ERRORLEVEL%"

echo.
if %SETUP_EXIT% EQU 0 (
    echo   Setup fertig. Du kannst das Fenster schliessen.
) else (
    echo   Setup mit Fehlercode %SETUP_EXIT% beendet.
)
pause
exit /b %SETUP_EXIT%
