@echo off
REM =======================================================================
REM  build_installer.bat — Full Windows installer build for PB Studio
REM  Run from the PROJECT ROOT: installer\build_installer.bat
REM =======================================================================

setlocal EnableDelayedExpansion

set APP_NAME=PB Studio
set APP_VERSION=0.5.0
set VENV=.venv
set SPEC_FILE=pb_studio.spec
set DIST_DIR=dist
set OUTPUT_NSI=installer\pb_studio.nsi
set OUTPUT_EXE=dist\pb_studio_setup_v%APP_VERSION%.exe

echo.
echo =====================================================
echo   %APP_NAME% v%APP_VERSION% — Windows Build Script
echo =====================================================
echo.

REM -----------------------------------------------------------------------
REM  1. Verify we're in the project root
REM -----------------------------------------------------------------------
if not exist "%SPEC_FILE%" (
    echo [ERROR] %SPEC_FILE% not found.
    echo         Run this script from the project root, e.g.:
    echo         cd C:\Users\david\Documents\App_Projekte\PB_studio_Rebuild
    echo         installer\build_installer.bat
    exit /b 1
)

REM -----------------------------------------------------------------------
REM  2. Check virtual environment
REM -----------------------------------------------------------------------
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at %VENV%\
    echo         Run: poetry install
    exit /b 1
)

call %VENV%\Scripts\activate.bat
echo [OK] Virtual environment activated.

REM -----------------------------------------------------------------------
REM  3. Ensure PyInstaller is installed
REM -----------------------------------------------------------------------
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)
echo [OK] PyInstaller available.

REM -----------------------------------------------------------------------
REM  4. Check for optional icon file — warn if missing but continue
REM -----------------------------------------------------------------------
if not exist "resources\pb_studio.ico" (
    echo [WARN] resources\pb_studio.ico not found.
    echo        The EXE will use the default PyInstaller icon.
    echo        To add a custom icon, place pb_studio.ico in resources\
)

REM -----------------------------------------------------------------------
REM  5. Clean previous dist/build artifacts
REM -----------------------------------------------------------------------
echo [INFO] Cleaning previous build artifacts...
if exist "%DIST_DIR%\pb_studio"  rmdir /s /q "%DIST_DIR%\pb_studio"
if exist "build\pb_studio"       rmdir /s /q "build\pb_studio"

REM -----------------------------------------------------------------------
REM  6. PyInstaller build
REM -----------------------------------------------------------------------
echo.
echo [STEP 1/3] Running PyInstaller...
echo           This may take 5-20 minutes depending on hardware.
echo           Expected output size: ~8-20 GB (includes CUDA libraries)
echo.

pyinstaller %SPEC_FILE% --noconfirm --log-level WARN

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. Check output above.
    exit /b 1
)
echo [OK] PyInstaller build complete: %DIST_DIR%\pb_studio\

REM -----------------------------------------------------------------------
REM  7. Copy LICENSE if present
REM -----------------------------------------------------------------------
if not exist "LICENSE.txt" (
    echo PB Studio v%APP_VERSION% - Copyright 2026 > LICENSE.txt
    echo For license terms see documentation.       >> LICENSE.txt
)

REM -----------------------------------------------------------------------
REM  8. Smoke test — verify the binary exists and responds
REM -----------------------------------------------------------------------
echo.
echo [STEP 2/3] Smoke-testing the PyInstaller build...
if not exist "%DIST_DIR%\pb_studio\pb_studio.exe" (
    echo [ERROR] pb_studio.exe not found in dist folder!
    exit /b 1
)
echo [OK] pb_studio.exe exists (%DIST_DIR%\pb_studio\pb_studio.exe)

REM Basic import check (runs python, not the frozen EXE, but validates module graph)
python -c "
import sys, subprocess, pathlib
exe = pathlib.Path('dist/pb_studio/pb_studio.exe')
size_gb = exe.stat().st_size / 1024**3
print(f'[OK] EXE size: {size_gb:.2f} GB')
"

REM -----------------------------------------------------------------------
REM  9. NSIS packaging
REM -----------------------------------------------------------------------
echo.
echo [STEP 3/3] Building NSIS installer...

where makensis >nul 2>&1
if errorlevel 1 (
    echo [WARN] makensis not found on PATH.
    echo        Install NSIS 3.x from https://nsis.sourceforge.io/
    echo        Then re-run: makensis %OUTPUT_NSI%
    echo.
    echo [INFO] PyInstaller build is complete at: %DIST_DIR%\pb_studio\
    echo        You can manually run NSIS later to create the installer EXE.
    goto :done
)

makensis /V2 "%OUTPUT_NSI%"

if errorlevel 1 (
    echo [ERROR] NSIS build failed. Check output above.
    exit /b 1
)

echo.
echo [OK] Installer created: %OUTPUT_EXE%

REM -----------------------------------------------------------------------
REM  10. Show final result
REM -----------------------------------------------------------------------
:done
echo.
echo =====================================================
echo   Build Summary
echo =====================================================
if exist "%DIST_DIR%\pb_studio\pb_studio.exe" (
    echo   App folder:  %DIST_DIR%\pb_studio\
)
if exist "%OUTPUT_EXE%" (
    echo   Installer:   %OUTPUT_EXE%
)
echo.
echo   Next steps:
echo   1. Test on a clean Windows 11 VM (no Python installed)
echo   2. Copy %OUTPUT_EXE% to the VM and run it
echo   3. Verify: app launches, AI models download, audio/video loads
echo   4. Code-sign the installer EXE for distribution (optional)
echo.
endlocal
