# JSON Settings Migration

## Overview

PB Studio now uses a **standard JSON format** for storing settings instead of platform-specific QSettings (Windows Registry / Ini files). This provides:

- **Cross-platform compatibility**: Settings stored in a standard, human-readable JSON format
- **Version control friendly**: Settings can be easily backed up, versioned, and shared
- **No platform dependencies**: No reliance on Windows Registry or platform-specific storage
- **Easy debugging**: Settings file can be inspected and edited directly
- **Automatic migration**: Existing QSettings data is automatically migrated on first run

## Settings File Location

Settings are stored in a platform-appropriate location:

- **Windows**: `%APPDATA%/PBStudio/settings.json`
  - Typically: `C:\Users\<Username>\AppData\Roaming\PBStudio\settings.json`

- **Linux/macOS**: `~/.config/PBStudio/settings.json`
  - Typically: `/home/<username>/.config/PBStudio/settings.json`

## Settings Structure

The JSON file contains the following sections:

```json
{
  "ollama": {
    "enabled": true,
    "url": "http://localhost:11434",
    "model": "gemma2"
  },
  "shortcuts": {
    "play_pause": "Space",
    "stop": "Escape",
    "shuttle_back": "J",
    "shuttle_pause": "K",
    "shuttle_fwd": "L",
    "set_in": "I",
    "set_out": "O",
    "set_anchor": "M",
    "delete_clip": "Del",
    "jump_start": "Home",
    "jump_end": "End",
    "frame_back": "Left",
    "frame_fwd": "Right",
    "zoom_in": "+",
    "zoom_out": "-",
    "undo": "Ctrl+Z",
    "redo": "Ctrl+Y",
    "copy": "Ctrl+C",
    "paste": "Ctrl+V"
  },
  "recentProjects": [
    "/path/to/project1",
    "/path/to/project2"
  ]
}
```

## Automatic Migration

### How It Works

When PB Studio starts for the first time after the migration:

1. **Check for existing JSON settings**: If `settings.json` exists, load it directly
2. **Check for legacy QSettings**: If JSON doesn't exist, check for legacy QSettings data
3. **Migrate data**: If legacy data is found, migrate it to JSON format
4. **Save migrated settings**: Write the migrated data to `settings.json`

### What Gets Migrated

All existing settings are preserved during migration:

- **Ollama Configuration**:
  - LLM backend enabled/disabled state
  - Ollama server URL
  - Selected model name

- **Keyboard Shortcuts**:
  - All custom keyboard shortcuts
  - If no customizations exist, defaults are used

- **Recent Projects**:
  - List of recently opened projects
  - Invalid/non-existent paths are filtered out during migration

### Migration Sources

The migration process reads from two legacy QSettings locations:

1. **PBStudio organization** (`"PBStudio" / "PBStudio"`):
   - Ollama settings (`ollama/*`)
   - Keyboard shortcuts (`shortcuts/*`)

2. **Paperclip organization** (`"Paperclip" / "PBStudio"`):
   - Recent projects (`recentProjects`)

## For Developers

### Using the Settings Store

Import and use the centralized settings store:

```python
from services.settings_store import get_settings_store

# Get the singleton instance
store = get_settings_store()

# Ollama settings
ollama_config = store.get_ollama_settings()
store.save_ollama_settings(enabled=True, url="http://localhost:11434", model="gemma2")

# Keyboard shortcuts
shortcut = store.get_shortcut("play_pause", default="Space")
store.set_shortcut("play_pause", "Ctrl+Space")
all_shortcuts = store.get_all_shortcuts()
store.set_all_shortcuts({"play_pause": "Space", "stop": "Escape"})

# Recent projects
projects = store.get_recent_projects()
store.set_recent_projects(["/path/to/project"])

# Generic access
value = store.get("custom_key", default="default_value")
store.set("custom_key", "custom_value")

# Nested access
value = store.get_nested("section", "subsection", "key", default="default")
store.set_nested("section", "subsection", "key", value="new_value")
```

### Backward Compatibility

The new system is fully backward compatible:

- **Existing code continues to work**: The public APIs in `settings_dialog.py`, `shortcut_manager.py`, and `recent_projects.py` remain unchanged
- **Drop-in replacement**: QSettings calls are replaced internally with JSON store calls
- **No breaking changes**: All existing function signatures and return types are preserved

### Migration Implementation

The migration logic is implemented in `services/settings_store.py`:

```python
def _migrate_from_qsettings(self) -> None:
    """Migrate existing data from QSettings to JSON format."""
    # Migration happens automatically on first initialization
    # when settings.json doesn't exist
```

### Testing Migration

Two testing approaches are provided:

1. **Unit tests**: `tests/test_settings_migration.py` - Comprehensive pytest suite
2. **Manual verification**: `scripts/verify_settings_migration.py` - Simple verification script

Run verification:
```bash
python scripts/verify_settings_migration.py
```

## Troubleshooting

### Settings Not Migrating

If your settings don't appear after the update:

1. Check if `settings.json` was created:
   - Windows: `%APPDATA%/PBStudio/settings.json`
   - Linux/macOS: `~/.config/PBStudio/settings.json`

2. Check the application logs for migration messages

3. Manually export legacy settings and import into JSON format if needed

### Resetting Settings

To reset all settings to defaults, simply delete the `settings.json` file:

```bash
# Windows
del "%APPDATA%\PBStudio\settings.json"

# Linux/macOS
rm ~/.config/PBStudio/settings.json
```

Settings will be recreated with defaults on next launch.

### Manual Settings Edit

You can manually edit `settings.json` with any text editor. Ensure valid JSON format:

```bash
# Validate JSON syntax (Linux/macOS with jq installed)
jq . ~/.config/PBStudio/settings.json

# Pretty-print for readability
python -m json.tool settings.json
```

## Migration Timeline

- **Legacy system**: QSettings (Registry/Ini) - **Deprecated**
- **New system**: JSON-based settings - **Active**
- **Automatic migration**: First run after update
- **Legacy support**: QSettings read-only during migration, not written afterward

## Benefits

### For Users

- ✅ Settings are preserved during migration
- ✅ Settings can be backed up by copying one file
- ✅ Settings work consistently across different operating systems
- ✅ No Windows Registry clutter

### For Developers

- ✅ Easy to debug (inspect JSON file)
- ✅ Easy to test (mock file paths)
- ✅ Version control friendly
- ✅ Platform-independent
- ✅ Centralized settings management

## See Also

- `services/settings_store.py` - Settings store implementation
- `ui/dialogs/settings_dialog.py` - Settings UI dialog
- `ui/shortcut_manager.py` - Keyboard shortcut manager
- `services/recent_projects.py` - Recent projects manager
