@echo off
title Brain V3 - pytest (Phase 0-5)
echo ============================================
echo   Brain V3 — Tests (Phase 0-5, 24 Test-Files)
echo   Plan: docs\superpowers\plans\2026-05-04-brain-v3-nvidia-plan\
echo ============================================
echo.

cd /d "%~dp0"

set CUDA_MODULE_LOADING=LAZY
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set MKL_NUM_THREADS=4

set "PB_PYTHON="
set "PB_CONDA_PY=C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe"

if exist "%PB_CONDA_PY%" (
    set "PB_PYTHON=%PB_CONDA_PY%"
) else if exist ".venv310\Scripts\python.exe" (
    set "PB_PYTHON=.venv310\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PB_PYTHON=.venv\Scripts\python.exe"
) else (
    echo FEHLER: Keine Python-Umgebung gefunden.
    pause
    exit /b 1
)

if not exist "outputs" mkdir outputs
set "RESULT_FILE=outputs\pytest_brain_v3_results.txt"

echo Python: %PB_PYTHON%
echo Output: %RESULT_FILE%
echo.
echo Test-Lauf gestartet (Output wird gleichzeitig in %RESULT_FILE% geschrieben):
echo.

"%PB_PYTHON%" -m pytest ^
    tests\test_services\test_brain_v3_background_queue.py ^
    tests\test_services\test_brain_v3_backup.py ^
    tests\test_services\test_brain_v3_brain_core.py ^
    tests\test_services\test_brain_v3_brain_store_health.py ^
    tests\test_services\test_brain_v3_embedding_scheduler.py ^
    tests\test_services\test_brain_v3_gpu_serializer.py ^
    tests\test_services\test_brain_v3_hashing.py ^
    tests\test_services\test_brain_v3_hashing_worker.py ^
    tests\test_services\test_brain_v3_knn_ann_eval.py ^
    tests\test_services\test_brain_v3_media_hash_registry.py ^
    tests\test_services\test_brain_v3_migration_templates.py ^
    tests\test_services\test_brain_v3_nvenc_conflict_script.py ^
    tests\test_services\test_brain_v3_nvenc_serialization.py ^
    tests\test_services\test_brain_v3_onnx_eval.py ^
    tests\test_services\test_brain_v3_paths_and_schemas.py ^
    tests\test_services\test_brain_v3_performance_profile_script.py ^
    tests\test_services\test_brain_v3_phase4_foundations.py ^
    tests\test_services\test_brain_v3_phase4_pacing_smoke_script.py ^
    tests\test_services\test_brain_v3_phase5_widgets.py ^
    tests\test_services\test_brain_v3_reranker_sampler.py ^
    tests\test_services\test_brain_v3_service.py ^
    tests\test_services\test_brain_v3_storage_cache.py ^
    tests\test_services\test_brain_v3_storage_repo.py ^
    tests\test_services\test_brain_v3_subtrack_detector.py ^
    tests\test_services\test_brain_v3_visual_curves.py ^
    -v --tb=short --color=no > "%RESULT_FILE%" 2>&1

set PYTEST_RC=%ERRORLEVEL%
type "%RESULT_FILE%"

echo.
echo ============================================
echo   pytest beendet (Exit-Code: %PYTEST_RC%)
echo   Vollstaendiges Log: %RESULT_FILE%
echo ============================================
echo.
pause
exit /b %PYTEST_RC%
