# PB Studio Startup Documentation

## Single Entry Point Architecture

PB Studio has **one primary entry point**: `main.py`

### Entry Point

**`main.py`** - Main application entry point
- Initializes logging system
- Sets up Qt exception handlers
- Initializes SQLite database
- Creates QApplication instance
- Loads theme and UI
- Shows splash screen during startup
- Performs system checks (CUDA, FFmpeg, dependencies, Ollama when enabled)
- Creates and displays PBWindow (main application window)
- Starts event loop

### Startup Sequence

```
main.py
  ├─ setup_logging() - Configure rotating file logger
  ├─ init_db() - Initialize SQLite database
  ├─ QApplication() - Create Qt application
  ├─ get_stylesheet() - Load PB Studio Gold theme
  ├─ PBSplashScreen() - Show startup splash
  ├─ check_system() - Verify CUDA/FFmpeg/dependencies
  ├─ SetupWizard() - First-run setup (if needed)
  ├─ PBWindow() - Create main window
  └─ app.exec() - Enter Qt event loop
```

### Launcher Scripts

These are **infrastructure** scripts, not application entry points:

- **`start_pb_studio.bat`** / **`start_pb_studio.py`** - Windows launcher
  - Prefers conda env `pb-studio` (`%USERPROFILE%\miniconda3\envs\pb-studio\python.exe`)
  - Falls back to `.venv310`, then `.venv`
  - Runs `main.py`
  - Captures stdout/stderr logs in `outputs\app_run_<timestamp>.log`
  
- **`setup_pb_studio.bat`** / **`setup_pb_studio.py`** - Installation scripts
  - Create/update conda env `pb-studio` from `environment.yml`
  - Install PyTorch `1.12.1+cu113` and the CUDA 11.3 dependency set
  - Use `requirements-py310-cu113.txt` / `environment.yml` as active setup.
    The legacy/future Python 3.11+cu124 reference lives in
    `docs/archive/requirements.txt` (archived, D-073/E3).
  - Install `vendor/beat_this`
  - Verify installation

- **`run_pytest_schnitt.bat`** / **`run_pytest_brain_v3.bat`** - focused regression wrappers
  - Use the same Python selection order as the launcher
  - Write full pytest output to `outputs\`

### Diagnostic Tools

Located in `scripts/` directory (NOT entry points):

- **`scripts/diagnose_cuda.py`** - CUDA/PyTorch GPU diagnostic
- **`scripts/hardware_diag.py`** - hardware and dependency diagnostic
- **`scripts/phase_e_smoke_boot.py`** - PBWindow boot smoke helper
- **`scripts/phase_e_pipeline_smoke.py`** / **`scripts/phase_h_workflow_smoke.py`** - focused UI/pipeline smoke helpers

### Running PB Studio

**Windows:**
```bash
# Recommended: Use the launcher
start_pb_studio.bat

# Or directly with conda Python
%USERPROFILE%\miniconda3\envs\pb-studio\python.exe main.py
```

**Manual (after conda setup):**
```bash
conda activate pb-studio
python main.py
```

## Initialization Order

Critical services are initialized in this order:

1. **Environment** - Load .env file with dotenv
2. **Logging** - Setup rotating file handler (logs/pb_studio.log)
3. **Exception Hooks** - Install global exception handlers
4. **Database** - Initialize SQLite with all tables
5. **Qt Application** - Create QApplication instance
6. **Theme** - Apply custom stylesheet
7. **System Check** - Verify CUDA, FFmpeg, dependencies
8. **First-Run Setup** - Show setup wizard if needed
9. **Main Window** - Create PBWindow with all workspaces
10. **Event Loop** - Start Qt event processing

## Feature Flags

main.py supports environment-based feature flags:

```env
# .env file
PB_STUDIO_ENABLE_VERSION_CHECK=1  # Check for updates on startup
PB_STUDIO_ENABLE_SETUP_WIZARD=1   # Show first-run setup wizard
PB_STUDIO_JSON_LOGS=0             # Use JSON log format
```

## Troubleshooting

If main.py fails to start:

1. Run diagnostics:
   ```bash
   %USERPROFILE%\miniconda3\envs\pb-studio\python.exe scripts\diagnose_cuda.py
   %USERPROFILE%\miniconda3\envs\pb-studio\python.exe scripts\hardware_diag.py
   ```

2. Check the logs:
   ```bash
   type logs\pb_studio.log
   type logs\crash.log
   ```

3. Verify dependencies:
   ```bash
   setup_pb_studio.bat
   ```

4. Test critical imports:
   ```bash
   %USERPROFILE%\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_scripts -q
   ```

## Architecture Notes

- **No `if __name__ == "__main__"` in multiple files** - Only main.py is the entry point
- **Diagnostic tools are in scripts/** - Clear separation from production code
- **Single initialization path** - No alternate entry points or initialization variants
- **Feature flags for variants** - Use environment variables, not separate entry files
