"""B-427: check_ffmpeg soll sowohl lokales bin/ als auch System-PATH akzeptieren."""
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Setup: PROJECT_ROOT muss auf ein temp-dir zeigen, damit FFMPEG_BIN/FFPROBE_BIN nicht
# versehentlich echt existieren.

# Importiere nur die Funktion + Inventory, nicht das ganze Modul (vermeidet Side-Effects)
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_inventory():
    """Minimaler Inventory-Stub mit ffmpeg_ok Attribut."""
    from types import SimpleNamespace
    return SimpleNamespace(ffmpeg_ok=False)


def test_ffmpeg_local_bin_found(tmp_path, monkeypatch):
    """Wenn lokale bin/ffmpeg.exe + bin/ffprobe.exe existieren -> OK."""
    ffmpeg = tmp_path / "bin" / "ffmpeg.exe"
    ffprobe = tmp_path / "bin" / "ffprobe.exe"
    ffmpeg.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.touch()
    ffprobe.touch()

    import scripts.setup_py310_gpu as setup_mod
    monkeypatch.setattr(setup_mod, "FFMPEG_BIN", ffmpeg)
    monkeypatch.setattr(setup_mod, "FFPROBE_BIN", ffprobe)

    inv = _make_inventory()
    setup_mod.check_ffmpeg(inv)
    assert inv.ffmpeg_ok is True


def test_ffmpeg_system_path_found(tmp_path, monkeypatch):
    """Wenn kein lokales bin/, aber shutil.which findet FFmpeg -> OK."""
    ffmpeg = tmp_path / "bin" / "ffmpeg.exe"
    ffprobe = tmp_path / "bin" / "ffprobe.exe"
    # Nicht erstellen -> lokal fehlt

    import scripts.setup_py310_gpu as setup_mod
    monkeypatch.setattr(setup_mod, "FFMPEG_BIN", ffmpeg)
    monkeypatch.setattr(setup_mod, "FFPROBE_BIN", ffprobe)

    # System-PATH liefert FFmpeg
    def fake_which(name):
        if name in ("ffmpeg", "ffprobe"):
            return f"C:\\tools\\{name}.exe"
        return None

    monkeypatch.setattr(shutil, "which", fake_which)

    inv = _make_inventory()
    setup_mod.check_ffmpeg(inv)
    assert inv.ffmpeg_ok is True


def test_ffmpeg_neither_local_nor_system(tmp_path, monkeypatch):
    """Wenn weder lokal noch System-PATH -> FAIL."""
    ffmpeg = tmp_path / "bin" / "ffmpeg.exe"
    ffprobe = tmp_path / "bin" / "ffprobe.exe"

    import scripts.setup_py310_gpu as setup_mod
    monkeypatch.setattr(setup_mod, "FFMPEG_BIN", ffmpeg)
    monkeypatch.setattr(setup_mod, "FFPROBE_BIN", ffprobe)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    inv = _make_inventory()
    setup_mod.check_ffmpeg(inv)
    assert inv.ffmpeg_ok is False
