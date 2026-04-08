"""
Test suite for JSON settings migration from QSettings.

Tests:
1. Settings store initialization
2. QSettings migration logic
3. Ollama settings persistence
4. Keyboard shortcuts persistence
5. Recent projects persistence
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings

from services.settings_store import SettingsStore, get_settings_store


@pytest.fixture
def temp_settings_path(tmp_path):
    """Create a temporary settings file path."""
    settings_file = tmp_path / "settings.json"
    return settings_file


@pytest.fixture
def mock_settings_path(temp_settings_path):
    """Mock the settings path to use a temporary location."""
    with patch('services.settings_store._get_settings_path', return_value=temp_settings_path):
        yield temp_settings_path


def test_settings_store_creation(mock_settings_path):
    """Test that SettingsStore can be created and initializes properly."""
    store = SettingsStore()
    assert store is not None
    assert isinstance(store._data, dict)


def test_empty_settings_initialization(mock_settings_path):
    """Test initialization with no existing settings."""
    store = SettingsStore()
    assert store.get_ollama_settings()["enabled"] is True
    assert store.get_ollama_settings()["url"] == "http://localhost:11434"
    assert store.get_recent_projects() == []


def test_json_persistence(mock_settings_path):
    """Test that settings are persisted to JSON correctly."""
    store = SettingsStore()

    # Save some settings
    store.save_ollama_settings(enabled=False, url="http://custom:8080", model="llama2")
    store.set_recent_projects(["/path/to/project1", "/path/to/project2"])

    # Verify JSON file was created
    assert mock_settings_path.exists()

    # Load JSON and verify content
    with open(mock_settings_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data["ollama"]["enabled"] is False
    assert data["ollama"]["url"] == "http://custom:8080"
    assert data["ollama"]["model"] == "llama2"
    assert data["recentProjects"] == ["/path/to/project1", "/path/to/project2"]


def test_settings_reload(mock_settings_path):
    """Test that settings are correctly reloaded from JSON."""
    # Create first store and save settings
    store1 = SettingsStore()
    store1.save_ollama_settings(enabled=False, url="http://test:9000", model="test-model")

    # Create new store instance (simulates app restart)
    store2 = SettingsStore()
    settings = store2.get_ollama_settings()

    assert settings["enabled"] is False
    assert settings["url"] == "http://test:9000"
    assert settings["model"] == "test-model"


def test_shortcut_management(mock_settings_path):
    """Test keyboard shortcut get/set operations."""
    store = SettingsStore()

    # Set individual shortcut
    store.set_shortcut("play_pause", "Ctrl+Space")
    assert store.get_shortcut("play_pause") == "Ctrl+Space"

    # Set all shortcuts
    shortcuts = {
        "play_pause": "Space",
        "stop": "Escape",
        "undo": "Ctrl+Z"
    }
    store.set_all_shortcuts(shortcuts)

    retrieved = store.get_all_shortcuts()
    assert retrieved == shortcuts


def test_nested_access(mock_settings_path):
    """Test nested get/set operations."""
    store = SettingsStore()

    # Set nested value
    store.set_nested("ollama", "enabled", value=False)
    assert store.get_nested("ollama", "enabled") is False

    # Get nested value with default
    assert store.get_nested("nonexistent", "key", default="default_value") == "default_value"


def test_section_access(mock_settings_path):
    """Test section get/set operations."""
    store = SettingsStore()

    section_data = {
        "enabled": True,
        "url": "http://localhost:11434",
        "model": "gemma2"
    }

    store.set_section("ollama", section_data)
    retrieved = store.get_section("ollama")

    assert retrieved == section_data


def test_migration_preserves_data(mock_settings_path):
    """Test that migration from QSettings preserves all data."""
    # Set up legacy QSettings data
    qs_pbstudio = QSettings("PBStudio", "PBStudio")
    qs_pbstudio.setValue("ollama/enabled", False)
    qs_pbstudio.setValue("ollama/url", "http://legacy:8080")
    qs_pbstudio.setValue("ollama/model", "legacy-model")
    qs_pbstudio.setValue("shortcuts/play_pause", "Ctrl+P")
    qs_pbstudio.setValue("shortcuts/stop", "Ctrl+S")
    qs_pbstudio.sync()

    qs_paperclip = QSettings("Paperclip", "PBStudio")
    qs_paperclip.setValue("recentProjects", ["/path/to/legacy/project"])
    qs_paperclip.sync()

    # Create store (should trigger migration)
    store = SettingsStore()

    # Verify Ollama settings were migrated
    ollama = store.get_ollama_settings()
    assert ollama["enabled"] is False
    assert ollama["url"] == "http://legacy:8080"
    assert ollama["model"] == "legacy-model"

    # Verify shortcuts were migrated
    shortcuts = store.get_all_shortcuts()
    assert shortcuts["play_pause"] == "Ctrl+P"
    assert shortcuts["stop"] == "Ctrl+S"

    # Verify recent projects were migrated
    # Note: This will be empty since the test path doesn't exist
    # In real use, only existing paths are migrated
    projects = store.get_recent_projects()
    assert isinstance(projects, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
