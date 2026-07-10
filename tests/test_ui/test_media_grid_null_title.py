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
    # 2026-07-10 Konsolidierung: set_items baut Cards nur, wenn das Grid sichtbar
    # ist (jovial Freeze-Fix: unsichtbares Grid schiebt den Rebuild auf showEvent).
    # Der Test braucht den eager-Pfad -> Grid sichtbar machen, damit _rebuild_cards
    # (und damit _load_index/_load_next_chunk) initialisiert wird.
    grid.show()

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
    
    # Cards aufbauen (set_items -> _rebuild_cards -> _apply_filter). Der
    # Filter lief damit bereits ueber den Null-Titel.
    grid.set_items(items)

    # M3 Grid-Virtualisierung (D-066): Cards baut das debounced Relayout
    # fuer das Scroll-Fenster — hier synchron anstossen statt auf den
    # 100ms-Timer zu warten (_load_next_chunk existiert nicht mehr).
    grid._do_relayout_debounced()

    # Wenn wir hier ankommen, liefen _apply_filter + Card-Bau fehlerfrei durch!
    assert len(grid._cards) == 1
    assert grid._cards[0]._title is None
