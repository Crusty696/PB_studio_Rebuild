@echo off
title PB Studio Rebuild - Setup
echo ============================================
echo   PB Studio Rebuild - Setup starten
echo ============================================
echo.

:: Python 3.11 suchen
set "PY311="

:: Versuch 1: py launcher
py -3.11 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PY311=py -3.11"
    goto :found
)

:: Versuch 2: Bekannter Installationspfad
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found
)

:: Versuch 3: Program Files
if exist "C:\Program Files\Python311\python.exe" (
    set "PY311=C:\Program Files\Python311\python.exe"
    goto :found
)

:: Versuch 4: C:\Python311
if exist "C:\Python311\python.exe" (
    set "PY311=C:\Python311\python.exe"
    goto :found
)

echo.
echo   FEHLER: Python 3.11 nicht gefunden!
echo   Bitte installiere Python 3.11 von:
echo   https://www.python.org/downloads/release/python-3110/
echo.
pause
exit /b 1

:found
echo   Python 3.11 gefunden: %PY311%
echo.

:: Setup-Skript mit Python 3.11 starten
%PY311% "%~dp0setup_pb_studio.py" %*

exit /b %ERRORLEVEL%
