"""
Manual verification script for JSON settings migration.

Run this script to verify:
1. Settings store can be created
2. Settings can be saved and loaded
3. All APIs work correctly
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.settings_store import get_settings_store


def test_ollama_settings():
    """Test Ollama settings persistence."""
    print("Testing Ollama settings...")
    store = get_settings_store()

    # Save settings
    store.save_ollama_settings(
        enabled=False,
        url="http://test.local:8080",
        model="test-model"
    )

    # Retrieve settings
    settings = store.get_ollama_settings()

    assert settings["enabled"] is False, "Ollama enabled mismatch"
    assert settings["url"] == "http://test.local:8080", "Ollama URL mismatch"
    assert settings["model"] == "test-model", "Ollama model mismatch"

    print("✓ Ollama settings test passed")


def test_shortcuts():
    """Test keyboard shortcuts persistence."""
    print("Testing keyboard shortcuts...")
    store = get_settings_store()

    # Set shortcuts
    shortcuts = {
        "play_pause": "Ctrl+Space",
        "stop": "Escape",
        "undo": "Ctrl+Z"
    }
    store.set_all_shortcuts(shortcuts)

    # Retrieve shortcuts
    retrieved = store.get_all_shortcuts()

    assert retrieved == shortcuts, "Shortcuts mismatch"

    # Test individual shortcut
    assert store.get_shortcut("play_pause") == "Ctrl+Space", "Individual shortcut mismatch"

    print("✓ Keyboard shortcuts test passed")


def test_recent_projects():
    """Test recent projects persistence."""
    print("Testing recent projects...")
    store = get_settings_store()

    # Note: We use fake paths here, real implementation filters non-existent paths
    projects = ["/path/to/project1", "/path/to/project2"]
    store.set_recent_projects(projects)

    # Retrieve projects
    retrieved = store.get_recent_projects()

    assert retrieved == projects, "Recent projects mismatch"

    print("✓ Recent projects test passed")


def test_nested_access():
    """Test nested get/set operations."""
    print("Testing nested access...")
    store = get_settings_store()

    # Set nested value
    store.set_nested("custom", "section", "key", value="test_value")

    # Get nested value
    value = store.get_nested("custom", "section", "key")

    assert value == "test_value", "Nested value mismatch"

    # Test default value
    default = store.get_nested("nonexistent", "path", default="default_val")

    assert default == "default_val", "Default value mismatch"

    print("✓ Nested access test passed")


def show_settings_file():
    """Show the location and content of the settings file."""
    from services.settings_store import _get_settings_path
    import json

    path = _get_settings_path()
    print(f"\nSettings file location: {path}")

    if path.exists():
        print("\nCurrent settings content:")
        with open(path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        print(json.dumps(content, indent=2, ensure_ascii=False))
    else:
        print("Settings file does not exist yet")


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Settings Migration Verification")
    print("=" * 60)
    print()

    try:
        test_ollama_settings()
        test_shortcuts()
        test_recent_projects()
        test_nested_access()

        print()
        print("=" * 60)
        print("✓ All tests passed successfully!")
        print("=" * 60)

        show_settings_file()

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
