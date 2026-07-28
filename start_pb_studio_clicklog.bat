@echo off
title PB Studio — CLICKLOG-Modus (Vollprotokoll)
echo ============================================
echo   PB Studio — CLICKLOG-Modus
echo   Alle Events werden aufgezeichnet:
echo   - UI-Klicks, Pipeline-Events, Fehler
echo   - Clip-Auswahl, Timeline-Generierung
echo   - GPU/CUDA, Worker-Lifecycle
echo   - Git-Commit/Branch, Ressourcen, Datenfluss
echo ============================================
echo.

:: Ins Skript-Verzeichnis wechseln (wichtig bei Shortcuts)
cd /d "%~dp0"

:: NVIDIA GTX 1060 Fix: Lazy Loading fuer CUDA Module
set CUDA_MODULE_LOADING=LAZY

:: DG-001 / Surface Book 2: Video-Encode muss NVENC nutzen.
set PB_REQUIRE_NVENC=1

:: B-215 Fix: OpenMP/MKL Doppel-Init verhindern.
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4

:: ===== CLICKLOG-SPEZIFISCH =====
:: DEBUG-Level aktivieren fuer maximale Aufzeichnung (main.py liest PB_LOG_LEVEL)
set PB_LOG_LEVEL=DEBUG
:: Click/Key-Logger aktivieren (main.py liest PB_CLICK_LOG; PB_CLICKLOG = Alias)
set PB_CLICK_LOG=1
set PB_CLICKLOG=1

:: Python-Auswahl (gleiche Logik wie start_pb_studio.bat)
set "PB_PYTHON="
set "PB_LABEL="
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
set "PB_CONDA_PY_ALT=%USERPROFILE%\anaconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" goto use_conda
if exist "%PB_CONDA_PY_ALT%" goto use_conda_alt
if exist ".venv310\Scripts\python.exe" goto use_venv310
if exist ".venv\Scripts\python.exe" goto use_venv
goto no_python

:use_conda
set "PB_PYTHON=%PB_CONDA_PY%"
set "PB_LABEL=conda-env pb-studio"
goto run_app

:use_conda_alt
set "PB_PYTHON=%PB_CONDA_PY_ALT%"
set "PB_LABEL=conda-env pb-studio (Anaconda)"
goto run_app

:use_venv310
set "PB_PYTHON=.venv310\Scripts\python.exe"
set "PB_LABEL=.venv310"
goto run_app

:use_venv
set "PB_PYTHON=.venv\Scripts\python.exe"
set "PB_LABEL=.venv"
goto run_app

:no_python
echo   FEHLER: Keine kompatible Python-Umgebung gefunden.
pause
exit /b 1

:run_app
echo   Python: %PB_LABEL%
echo.

:: Timestamp fuer Logdateien
if not exist "logs" mkdir logs
set "PB_TS="
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyy-MM-dd_HHmmss" 2^>nul') do set "PB_TS=%%I"
if not defined PB_TS set "PB_TS=no_timestamp"

:: D-085/B-743: Live-Session vollstaendig von echten AppData-/Recent-Project-
:: Zustaenden isolieren. Host-LOCALAPPDATA vor Override sichern.
set "PB_HOST_LOCALAPPDATA=%LOCALAPPDATA%"
set "PB_STABILITY_ROOT=%PB_HOST_LOCALAPPDATA%\PBStudioStability\%PB_TS%"
set "PB_STABILITY_PROJECT=%PB_STABILITY_ROOT%\project"
set "APPDATA=%PB_STABILITY_ROOT%\AppData\Roaming"
set "LOCALAPPDATA=%PB_STABILITY_ROOT%\AppData\Local"
if not exist "%APPDATA%" mkdir "%APPDATA%"
if not exist "%LOCALAPPDATA%" mkdir "%LOCALAPPDATA%"
if not exist "%PB_STABILITY_PROJECT%" mkdir "%PB_STABILITY_PROJECT%"

:: Clicklog-Datei: alles in eine Datei (stdout + stderr zusammen)
set "PB_CLICKLOG_FILE=logs\clicklog_%PB_TS%.log"
set "PB_RESOURCE_LOG=logs\resource_%PB_TS%.log"
set "PB_STOP_FILE=logs\.stop_%PB_TS%"
set "PB_SESSION_META=logs\session_%PB_TS%.txt"
if exist "%PB_STOP_FILE%" del /q "%PB_STOP_FILE%"

set "PB_GIT_COMMIT=unknown"
set "PB_GIT_BRANCH=unknown"
for /f %%I in ('git rev-parse HEAD 2^>nul') do set "PB_GIT_COMMIT=%%I"
for /f "delims=" %%I in ('git branch --show-current 2^>nul') do set "PB_GIT_BRANCH=%%I"

(
  echo run_id=%PB_TS%
  echo started_at=%DATE% %TIME%
  echo branch=%PB_GIT_BRANCH%
  echo commit=%PB_GIT_COMMIT%
  echo python=%PB_PYTHON%
  echo stability_root=%PB_STABILITY_ROOT%
  echo project_root=%PB_STABILITY_PROJECT%
  echo appdata=%APPDATA%
  echo localappdata=%LOCALAPPDATA%
  echo clicklog=%PB_CLICKLOG_FILE%
  echo resource_log=%PB_RESOURCE_LOG%
) > "%PB_SESSION_META%"

echo   === CLICKLOG-AUFZEICHNUNG AKTIV ===
echo   Branch:    %PB_GIT_BRANCH%
echo   Commit:    %PB_GIT_COMMIT%
echo   Session:   %PB_SESSION_META%
echo   Projekt:   %PB_STABILITY_PROJECT%
echo   AppData:   %APPDATA%
echo   Logdatei:  %PB_CLICKLOG_FILE%
echo   Standard:  logs\pb_studio.log (wie immer)
echo   Monitor:   logs\monitor_%PB_TS%.log (gefilterte Kern-Events)
echo   Ressourcen:%PB_RESOURCE_LOG%
echo   Level:     DEBUG (alle Events)
echo.

:: Fixplan 2026-07-07: Session-Monitor laeuft OHNE Claude Code parallel mit.
:: Filtert pb_studio.log auf Kern-Events (Fehler, Auto-Edit, Pacing, Render)
:: nach logs\monitor_<ts>.log und beendet sich selbst nach App-Ende.
:: Auswertung fuer Agenten: docs\SESSION_MONITORING_UND_ANALYSE.md
start "PB Session-Monitor" /min powershell -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0scripts\diag\session_log_monitor.ps1" -SessionTag "%PB_TS%"

:: Dataflow-Recorder: zeichnet alle ~30s auf WOHIN Daten fliessen (DB-Zustand
:: + Datei-Artefakte + Delta) nach logs\dataflow_<ts>.md. Laeuft OHNE Claude,
:: stoppt selbst bei App-Ende.
start "PB Dataflow-Recorder" /min powershell -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0scripts\diag\session_dataflow_recorder.ps1" -SessionTag "%PB_TS%" -PbPython "%PB_PYTHON%"

echo   Dataflow:  logs\dataflow_%PB_TS%.md (DB + Datei-Fluss alle 30s)

start "PB Resource-Monitor" /min powershell -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0scripts\start_pipeline_resource_monitor.ps1" ^
  -OutputLog "%~dp0%PB_RESOURCE_LOG%" -StopFile "%~dp0%PB_STOP_FILE%" ^
  -AppLog "%~dp0logs\pb_studio.log"

echo   Starte PB Studio...
echo.

:: stdout/stderr gleichzeitig auf Konsole + Clicklog. PowerShell reicht
:: $LASTEXITCODE der App an CMD durch; Pipeline darf Crash nicht verdecken.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "& '%PB_PYTHON%' main.py 2>&1 | Tee-Object -FilePath '%PB_CLICKLOG_FILE%'; exit $LASTEXITCODE"
set "PB_APP_EXIT=%ERRORLEVEL%"

type nul > "%PB_STOP_FILE%"
(
  echo ended_at=%DATE% %TIME%
  echo app_exit_code=%PB_APP_EXIT%
) >> "%PB_SESSION_META%"

if %PB_APP_EXIT% NEQ 0 (
    echo.
    echo   App beendet mit Fehlercode: %PB_APP_EXIT%
    echo   Clicklog: %PB_CLICKLOG_FILE%
    pause
)

exit /b %PB_APP_EXIT%
