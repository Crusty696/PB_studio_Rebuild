@echo off
title PB Studio Rebuild - E2E GUI Test
echo =====================================================
echo   PB Studio Rebuild - Autonomer GUI E2E Test
echo =====================================================
echo.
cd /d "%~dp0"
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\run_e2e_gui_test.py
pause
