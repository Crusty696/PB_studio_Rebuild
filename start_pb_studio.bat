@echo off
title PB Studio Rebuild
echo ============================================
echo   PB Studio Rebuild - App starten
echo ============================================
echo.

:: Pruefen ob .venv existiert
if exist "%~dp0.venv\Scripts\python.exe" (
    echo   venv gefunden: .venv\
    echo   Starte PB Studio...
    echo.
    "%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
) else (
    echo   .venv nicht gefunden - starte Setup zuerst...
    echo.
    if exist "%~dp0setup_pb_studio.bat" (
        call "%~dp0setup_pb_studio.bat"
        if exist "%~dp0.venv\Scripts\python.exe" (
            echo.
            echo   Setup fertig - starte PB Studio...
            "%~dp0.venv\Scripts\python.exe" "%~dp0main.py"
        ) else (
            echo   Setup fehlgeschlagen. Bitte manuell pruefen.
            pause
            exit /b 1
        )
    ) else (
        echo   FEHLER: Weder .venv noch setup_pb_studio.bat gefunden!
        pause
        exit /b 1
    )
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %ERRORLEVEL%
    pause
)
