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
- Performs system checks (CUDA, FFmpeg, dependencies)
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
  - Checks/creates Python venv
  - Runs `main.py` in the venv
  - Handles errors and crash logs
  
- **`setup_pb_studio.py`** - Installation script
  - Creates Python 3.11 venv
  - Installs PyTorch with CUDA
  - Installs all dependencies
  - Verifies installation

- **`configure_ollama.py`** - Ollama configuration utility
  - Sets default Ollama model and URL in JSON settings

### Diagnostic Tools

Located in `scripts/` directory (NOT entry points):

- **`scripts/main_diag.py`** - Diagnostic startup script
  - Minimal diagnostic version of main.py
  - Prints step-by-step initialization messages
  - Useful for troubleshooting startup failures
  - Imports from main.py for shared setup functions

### Running PB Studio

**Windows:**
```bash
# Recommended: Use the launcher
start_pb_studio.bat

# Or directly with venv Python
.venv\Scripts\python.exe main.py
```

**Manual (after venv setup):**
```bash
poetry run python main.py
# or
python main.py  # if activated in venv
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

1. Run the diagnostic script:
   ```bash
   .venv\Scripts\python.exe scripts\main_diag.py
   ```

2. Check the logs:
   ```bash
   type logs\pb_studio.log
   type logs\crash.log
   ```

3. Verify dependencies:
   ```bash
   setup_pb_studio.py --repair
   ```

4. Test critical imports:
   ```bash
   scripts\debug_imports.py
   ```

## Architecture Notes

- **No `if __name__ == "__main__"` in multiple files** - Only main.py is the entry point
- **Diagnostic tools are in scripts/** - Clear separation from production code
- **Single initialization path** - No alternate entry points or initialization variants
- **Feature flags for variants** - Use environment variables, not separate entry files
