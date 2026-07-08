import pytest
from PySide6.QtWidgets import QApplication
from ui.widgets.media_grid import MediaPoolGrid

# PySide6 benötigt eine laufende QApplication Instanz für Widget-Tests.
@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app

def test_media_grid_null_title(qapp):
    """Verifiziert, dass MediaPoolGrid nicht abstuerzt, wenn ein Item einen Null-Titel (None) hat."""
    grid = MediaPoolGrid(media_type="audio")
    
    # Item mit "title": None
    items = [
        {
            "id": 999,
            "title": None, # Null-Titel aus der DB
            "file_path": "dummy.mp3",
            "bpm": 120.0,
            "key": "Am",
            "genre": "Techno",
            "energy_curve": [0.1, 0.2]
        }
    ]
    
    # Cards aufbauen
    grid.set_items(items)
    
    # Da set_items asynchron Chunks via QTimer lädt, rufen wir _load_next_chunk direkt auf,
    # um die Karten synchron zu erstellen und den Filter auszuführen.
    grid._load_next_chunk()
    
    # Wenn wir hier ankommen, lief _apply_filter fehlerfrei durch!
    assert len(grid._cards) == 1
    assert grid._cards[0]._title is None
