@echo off
REM =======================================================================
REM  build_installer.bat - Full Windows installer build for PB Studio
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
set TARGET_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe
set NSISBI_DEFAULT=%LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1\Bin\makensis.exe
set PYTHON_EXE=
set MAKENSIS_EXE=
set MAKENSIS_FLAGS=/V2

echo.
echo =====================================================
echo   %APP_NAME% v%APP_VERSION% - Windows Build Script
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
REM  2. Check Python environment
REM -----------------------------------------------------------------------
if not "%PB_STUDIO_PYTHON%" == "" (
    if exist "%PB_STUDIO_PYTHON%" (
        set PYTHON_EXE=%PB_STUDIO_PYTHON%
        echo [OK] Using PB_STUDIO_PYTHON: %PB_STUDIO_PYTHON%
        goto :env_ok
    )
)

if exist "%TARGET_PY%" (
    set PYTHON_EXE=%TARGET_PY%
    echo [OK] Using target Conda runtime: %TARGET_PY%
    goto :env_ok
)

if not "%CONDA_DEFAULT_ENV%" == "" (
    for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)"') do set PYTHON_EXE=%%P
    echo [OK] Active Conda environment detected: %CONDA_DEFAULT_ENV%
    goto :env_ok
)

echo [ERROR] Target Python runtime not found.
echo         Expected: %TARGET_PY%
echo         Or set PB_STUDIO_PYTHON to the pb-studio Python 3.10/cu113 runtime.
exit /b 1

:env_ok
"%PYTHON_EXE%" -c "import sys, torch; assert sys.version_info[:2] == (3, 10), sys.version; assert torch.__version__ == '1.12.1+cu113', torch.__version__; assert torch.cuda.is_available(); assert torch.cuda.get_device_name(0) == 'NVIDIA GeForce GTX 1060'; print('[OK] Runtime:', sys.executable, sys.version.split()[0], torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"
if errorlevel 1 (
    echo [ERROR] Target runtime check failed. Refusing release build.
    exit /b 1
)

REM -----------------------------------------------------------------------
REM  3. Ensure PyInstaller is installed
REM -----------------------------------------------------------------------
"%PYTHON_EXE%" -c "import PyInstaller; assert PyInstaller.__version__ == '6.20.0'; print('[OK] PyInstaller', PyInstaller.__version__)" 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller 6.20.0 is missing in the target runtime.
    echo         Install requirements-py310-cu113.txt before building.
    exit /b 1
)
echo [OK] PyInstaller available.

REM -----------------------------------------------------------------------
REM  4. Check for optional icon file - warn if missing but continue
REM -----------------------------------------------------------------------
if not exist "resources\pb_studio.ico" (
    echo [WARN] resources\pb_studio.ico not found.
    echo        The EXE will use the default PyInstaller icon.
    echo        To add a custom icon, place pb_studio.ico in resources\
)

REM -----------------------------------------------------------------------
REM  5. Clean previous dist/build artifacts
REM -----------------------------------------------------------------------
if "%PB_SKIP_PYINSTALLER%" == "1" (
    echo [INFO] PB_SKIP_PYINSTALLER=1 set. Reusing existing %DIST_DIR%\pb_studio\
    if not exist "%DIST_DIR%\pb_studio\pb_studio.exe" (
        echo [ERROR] Existing %DIST_DIR%\pb_studio\pb_studio.exe not found.
        exit /b 1
    )
    goto :pyinstaller_done
)

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

"%PYTHON_EXE%" -m PyInstaller %SPEC_FILE% --noconfirm --log-level WARN

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. Check output above.
    exit /b 1
)
echo [OK] PyInstaller build complete: %DIST_DIR%\pb_studio\

:pyinstaller_done

REM -----------------------------------------------------------------------
REM  7. Prune duplicated dependency DLLs
REM -----------------------------------------------------------------------
echo.
echo [STEP 1b/3] Pruning duplicated top-level DLLs...
"%PYTHON_EXE%" installer\prune_pyinstaller_dist.py --dist-dir "%DIST_DIR%\pb_studio"
if errorlevel 1 (
    echo [ERROR] PyInstaller prune failed.
    exit /b 1
)

REM -----------------------------------------------------------------------
REM  8. Copy LICENSE if present
REM -----------------------------------------------------------------------
if not exist "LICENSE.txt" (
    echo PB Studio v%APP_VERSION% - Copyright 2026 > LICENSE.txt
    echo For license terms see documentation.       >> LICENSE.txt
)

REM -----------------------------------------------------------------------
REM  9. Smoke test - verify the binary exists and responds
REM -----------------------------------------------------------------------
echo.
echo [STEP 2/3] Smoke-testing the PyInstaller build...
if not exist "%DIST_DIR%\pb_studio\pb_studio.exe" (
    echo [ERROR] pb_studio.exe not found in dist folder!
    exit /b 1
)
echo [OK] pb_studio.exe exists (%DIST_DIR%\pb_studio\pb_studio.exe)

"%PYTHON_EXE%" installer\smoke_test.py
if errorlevel 1 (
    echo [ERROR] Smoke test failed.
    exit /b 1
)

REM -----------------------------------------------------------------------
REM  10. NSIS packaging
REM -----------------------------------------------------------------------
echo.
echo [STEP 3/3] Building NSIS installer...

if not "%PB_NSISBI_MAKENSIS%" == "" (
    if exist "%PB_NSISBI_MAKENSIS%" (
        set MAKENSIS_EXE=%PB_NSISBI_MAKENSIS%
        set MAKENSIS_FLAGS=/V2 /DUSE_NSISBI
        echo [OK] Using NSISBI from PB_NSISBI_MAKENSIS.
        goto :makensis_ok
    )
)

if exist "%NSISBI_DEFAULT%" (
    set MAKENSIS_EXE=%NSISBI_DEFAULT%
    set MAKENSIS_FLAGS=/V2 /DUSE_NSISBI
    echo [OK] Using local NSISBI: %NSISBI_DEFAULT%
    goto :makensis_ok
)

for /f "delims=" %%M in ('where makensis 2^>nul') do if not defined MAKENSIS_EXE set MAKENSIS_EXE=%%M
if not defined MAKENSIS_EXE if exist "C:\Program Files (x86)\NSIS\makensis.exe" set MAKENSIS_EXE=C:\Program Files (x86)\NSIS\makensis.exe
if not defined MAKENSIS_EXE if exist "C:\Program Files\NSIS\makensis.exe" set MAKENSIS_EXE=C:\Program Files\NSIS\makensis.exe

if not defined MAKENSIS_EXE (
    echo [WARN] makensis not found on PATH.
    echo        Install NSIS 3.x from https://nsis.sourceforge.io/
    echo        Then re-run: makensis %OUTPUT_NSI%
    echo.
    echo [INFO] PyInstaller build is complete at: %DIST_DIR%\pb_studio\
    echo        You can manually run NSIS later to create the installer EXE.
    goto :done
)

:makensis_ok
"%MAKENSIS_EXE%" %MAKENSIS_FLAGS% "%OUTPUT_NSI%"

if errorlevel 1 (
    echo [ERROR] NSIS build failed. Check output above.
    exit /b 1
)

echo.
echo [OK] Installer created: %OUTPUT_EXE%

REM -----------------------------------------------------------------------
REM  11. Show final result
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
if exist "dist\pb_studio_setup_v%APP_VERSION%.nsisbin" (
    echo   Payload:     dist\pb_studio_setup_v%APP_VERSION%.nsisbin
)
echo.
echo   Next steps:
echo   1. Test on a clean Windows 11 VM (no Python installed)
echo   2. Copy %OUTPUT_EXE% and dist\pb_studio_setup_v%APP_VERSION%.nsisbin to the VM
echo   3. Verify: app launches, AI models download, audio/video loads
echo   4. Code-sign the installer EXE for distribution (optional)
echo.
endlocal
