@echo off
echo =====================================================
echo   PB Studio - Autonomer GUI E2E Test (Vordergrund)
echo =====================================================
echo.
set TARGET_PY=C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe
"%TARGET_PY%" scripts\run_e2e_gui_test.py
pause
