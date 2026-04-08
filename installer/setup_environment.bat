@echo off
REM =======================================================================
REM  setup_environment.bat — Post-installation environment setup
REM  Automatically configures PB Studio user environment
REM =======================================================================

setlocal EnableDelayedExpansion

set APP_NAME=PB Studio
set APP_VERSION=0.5.0
set CONFIG_DIR=%USERPROFILE%\.pb_studio
set CONFIG_FILE=%CONFIG_DIR%\config.env
set CACHE_DIR=%USERPROFILE%\.cache

echo.
echo =====================================================
echo   %APP_NAME% v%APP_VERSION% — Environment Setup
echo =====================================================
echo.

REM -----------------------------------------------------------------------
REM  1. Check if running as administrator (not required, but helpful)
REM -----------------------------------------------------------------------
net session >nul 2>&1
if %errorlevel% == 0 (
    echo [INFO] Running with administrator privileges
) else (
    echo [INFO] Running as standard user
)

REM -----------------------------------------------------------------------
REM  2. Create configuration directory
REM -----------------------------------------------------------------------
if not exist "%CONFIG_DIR%" (
    echo [INFO] Creating configuration directory: %CONFIG_DIR%
    mkdir "%CONFIG_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create configuration directory
        exit /b 1
    )
)
echo [OK] Configuration directory: %CONFIG_DIR%

REM -----------------------------------------------------------------------
REM  3. Create model cache directory
REM -----------------------------------------------------------------------
if not exist "%CACHE_DIR%" (
    echo [INFO] Creating model cache directory: %CACHE_DIR%
    mkdir "%CACHE_DIR%"
    if errorlevel 1 (
        echo [WARN] Failed to create cache directory (may already exist)
    )
)
echo [OK] Model cache directory: %CACHE_DIR%

REM -----------------------------------------------------------------------
REM  4. Create default configuration file
REM -----------------------------------------------------------------------
if exist "%CONFIG_FILE%" (
    echo [INFO] Configuration file already exists: %CONFIG_FILE%
    echo        Skipping creation. To reset, delete the file and re-run this script.
) else (
    echo [INFO] Creating default configuration file...
    (
        echo # PB Studio Configuration
        echo # Created: %DATE% %TIME%
        echo.
        echo # Hugging Face API Token (required for model downloads^)
        echo # Get token from: https://huggingface.co/settings/tokens
        echo HUGGINGFACE_API_TOKEN=
        echo.
        echo # GPU Configuration (optional^)
        echo # Specify which GPU to use (0 = first GPU, 1 = second GPU, etc.^)
        echo # CUDA_VISIBLE_DEVICES=0
        echo.
        echo # Model Cache Location (optional^)
        echo # Default: %%USERPROFILE%%\.cache
        echo # Uncomment to change location:
        echo # HF_HOME=C:\Models\huggingface
        echo.
        echo # Logging Level (optional^)
        echo # Options: DEBUG, INFO, WARNING, ERROR
        echo # LOG_LEVEL=INFO
        echo.
        echo # Offline Mode (optional^)
        echo # Set to 1 to prevent model downloads (models must be pre-cached^)
        echo # OFFLINE_MODE=0
    ) > "%CONFIG_FILE%"

    if errorlevel 1 (
        echo [ERROR] Failed to create configuration file
        exit /b 1
    )
    echo [OK] Configuration file created: %CONFIG_FILE%
)

REM -----------------------------------------------------------------------
REM  5. Check for NVIDIA GPU
REM -----------------------------------------------------------------------
echo.
echo [INFO] Checking for NVIDIA GPU...
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [WARN] nvidia-smi not found or no NVIDIA GPU detected
    echo        PB Studio requires an NVIDIA GPU with CUDA support
    echo        Install NVIDIA drivers from: https://www.nvidia.com/drivers
) else (
    echo [OK] NVIDIA GPU detected
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
)

REM -----------------------------------------------------------------------
REM  6. Check for CUDA libraries
REM -----------------------------------------------------------------------
echo.
echo [INFO] Checking for CUDA runtime...
if exist "%SystemRoot%\System32\cudart64_*.dll" (
    echo [OK] CUDA runtime libraries found
) else (
    echo [INFO] CUDA runtime not found in System32
    echo        This is normal - PB Studio bundles CUDA libraries
)

REM -----------------------------------------------------------------------
REM  7. Prompt for Hugging Face token
REM -----------------------------------------------------------------------
echo.
echo =====================================================
echo   Hugging Face Configuration
echo =====================================================
echo.
echo PB Studio requires a Hugging Face API token to download AI models.
echo.
echo 1. Visit: https://huggingface.co/settings/tokens
echo 2. Create a token with "Read" permissions
echo 3. Copy the token (starts with "hf_"^)
echo.

set /p HF_TOKEN="Enter your Hugging Face token (or press Enter to skip): "

if not "!HF_TOKEN!" == "" (
    echo.
    echo [INFO] Updating configuration file with token...

    REM Update the config file with the token
    powershell -Command "(Get-Content '%CONFIG_FILE%') -replace '^HUGGINGFACE_API_TOKEN=.*', 'HUGGINGFACE_API_TOKEN=!HF_TOKEN!' | Set-Content '%CONFIG_FILE%'"

    if errorlevel 1 (
        echo [WARN] Failed to update configuration file automatically
        echo        Please manually edit: %CONFIG_FILE%
        echo        And set: HUGGINGFACE_API_TOKEN=!HF_TOKEN!
    ) else (
        echo [OK] Token saved to configuration file
    )
) else (
    echo [INFO] Skipping token configuration
    echo        You can add it later by editing: %CONFIG_FILE%
)

REM -----------------------------------------------------------------------
REM  8. Create logs directory
REM -----------------------------------------------------------------------
set LOGS_DIR=%CONFIG_DIR%\logs
if not exist "%LOGS_DIR%" (
    echo.
    echo [INFO] Creating logs directory: %LOGS_DIR%
    mkdir "%LOGS_DIR%"
)

REM -----------------------------------------------------------------------
REM  9. Display summary
REM -----------------------------------------------------------------------
echo.
echo =====================================================
echo   Setup Complete
echo =====================================================
echo   Configuration: %CONFIG_FILE%
echo   Cache:         %CACHE_DIR%
echo   Logs:          %LOGS_DIR%
echo.
echo   Next steps:
echo   1. Launch PB Studio from Start Menu or Desktop
echo   2. On first launch, AI models will download (~4 GB^)
echo   3. This may take 10-30 minutes depending on connection
echo   4. Once complete, you can use PB Studio offline
echo.
echo   For help: docs\DEPLOYMENT.md
echo =====================================================
echo.

pause
endlocal
