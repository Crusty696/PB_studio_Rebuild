@echo off
setlocal
echo ============================================================
echo   PB Studio v0.5.0 - Manual Test Mode
echo ============================================================
echo.

:: F?ge lokalen bin-Ordner zum PATH hinzu
set "PATH=%CD%\bin;%PATH%"

set PB_STUDIO_CI=0
set PB_STUDIO_JSON_LOGS=0

echo Pr?fe FFmpeg...
ffmpeg -version | findstr /C:"ffmpeg version"
if %ERRORLEVEL% NEQ 0 (
    echo [WARNUNG] FFmpeg wurde nicht im lokalen bin-Ordner gefunden!
)

echo Starte PB Studio...
.\.venv\Scripts\python.exe main.py
pause
endlocal
