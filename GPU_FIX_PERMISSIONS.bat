@echo off
setlocal
echo ============================================================
echo   PB Studio - GPU Recovery (Surface Book 2 / GTX 1060)
echo ============================================================
echo.

:: Pruefung auf Administrator-Rechte
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [FEHLER] Dieses Skript MUSS als ADMINISTRATOR ausgefuehrt werden!
    echo Bitte Rechtsklick auf die Datei -^> "Als Administrator ausfuehren".
    pause
    exit /b 1
)

echo [1/4] Pruefe GPU-Status...
powershell -NoProfile -Command ^
    "$gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' }; ^
     if ($gpu) { Write-Host \"GPU: $($gpu.Name) | Status: $($gpu.Status) | Code: $($gpu.ConfigManagerErrorCode)\" } ^
     else { Write-Host 'Keine NVIDIA GPU gefunden' }"
echo.

echo [2/4] Starte NVIDIA Display Container neu...
net stop NVDisplay.ContainerLocalSystem >nul 2>&1
timeout /t 2 >nul
net start NVDisplay.ContainerLocalSystem >nul 2>&1

echo.
echo [3/4] Reaktiviere GPU (Error 47 Fix)...
powershell -NoProfile -Command ^
    "$gpu = Get-PnpDevice | Where-Object { $_.FriendlyName -match 'NVIDIA' -and $_.Class -eq 'Display' }; ^
     if ($gpu -and $gpu.Status -ne 'OK') { ^
         Write-Host 'GPU deaktivieren...'; ^
         Disable-PnpDevice -InstanceId $gpu.InstanceId -Confirm:$false; ^
         Start-Sleep -Seconds 3; ^
         Write-Host 'GPU aktivieren...'; ^
         Enable-PnpDevice -InstanceId $gpu.InstanceId -Confirm:$false; ^
         Start-Sleep -Seconds 2; ^
         $g2 = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' }; ^
         Write-Host \"Neuer Status: $($g2.Status) (Code: $($g2.ConfigManagerErrorCode))\" ^
     } else { ^
         Write-Host 'GPU ist bereits OK — kein Fix noetig.' ^
     }"

echo.
echo [4/4] Verifiziere CUDA...
set "PB_CONDA_PY=%USERPROFILE%\miniconda3\envs\pb-studio\python.exe"
if exist "%PB_CONDA_PY%" (
    "%PB_CONDA_PY%" -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}' if torch.cuda.is_available() else 'CPU-Modus')"
) else if exist "%~dp0.venv310\Scripts\python.exe" (
    "%~dp0.venv310\Scripts\python.exe" -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}' if torch.cuda.is_available() else 'CPU-Modus')"
) else (
    echo Weder conda-env pb-studio noch .venv310 gefunden — CUDA-Test uebersprungen.
)

echo.
echo ============================================================
echo   Fertig. Falls GPU immer noch nicht geht: PC neustarten.
echo ============================================================
pause
endlocal
