from __future__ import annotations

from pathlib import Path


def test_storage_browser_dialog_contract_present() -> None:
    source = Path("ui/dialogs/storage_browser_dialog.py").read_text(encoding="utf-8")

    assert "class StorageBrowserDialog" in source
    assert "Analysen loeschen" in source
    assert "Ausgewaehlte loeschen" in source
    assert "nicht-genutzt" in source
    assert "alt >" in source


def test_settings_dialog_exposes_storage_browser_button() -> None:
    source = Path("ui/dialogs/settings_dialog.py").read_text(encoding="utf-8")

    assert "Storage-Browser" in source
    assert "StorageBrowserDialog" in source
