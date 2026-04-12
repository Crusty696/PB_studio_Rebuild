@echo off
REM Security scan script for PB Studio Rebuild (Windows)
REM Uses Bandit to scan Python code for security vulnerabilities

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

echo ======================================
echo PB Studio Security Scan with Bandit
echo ======================================
echo.

REM Activate virtual environment (.venv310 bevorzugt)
if exist "%PROJECT_ROOT%\.venv310\Scripts\activate.bat" (
    echo Activating virtual environment (.venv310)...
    call "%PROJECT_ROOT%\.venv310\Scripts\activate.bat"
) else if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    echo Activating virtual environment (.venv)...
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
)

REM Check if bandit is installed
where bandit >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Bandit is not installed. Install with: pip install bandit
    exit /b 1
)

REM Run bandit security scan
echo Running Bandit security scan...
echo Excluding: .venv, vendor, tests, installer, scripts
echo.

REM Run with medium+ severity for CI/CD
bandit -r "%PROJECT_ROOT%" ^
    -x "./.venv/*,./.venv310/*,./vendor/*,./tests/*,./installer/*,./scripts/*" ^
    -ll ^
    -f txt ^
    -o "%PROJECT_ROOT%\security_scan_report.txt"

echo.
echo Security scan complete!
echo Report saved to: security_scan_report.txt
echo.

REM Also generate JSON for machine parsing
bandit -r "%PROJECT_ROOT%" ^
    -x "./.venv/*,./.venv310/*,./vendor/*,./tests/*,./installer/*,./scripts/*" ^
    -f json ^
    -o "%PROJECT_ROOT%\security_scan_results.json"

echo JSON results saved to: security_scan_results.json
echo.

echo Done!
pause
