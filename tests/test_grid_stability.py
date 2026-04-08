import sys
import os
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from ui.widgets.media_grid import MediaPoolGrid

def test_grid_with_invalid_paths():
    print("Starte Grid-Stabilitaetstest (Headless)...")
    app = QApplication(sys.argv)
    
    # Erstelle ein Grid fuer Videos
    grid = MediaPoolGrid(media_type="video")
    
    # Simuliere 100 Video-Eintraege mit ungueltigen Pfaden
    # Dies hat zuvor den Access Violation Crash verursacht
    fake_items = []
    for i in range(100):
        fake_items.append({
            "id": i,
            "title": f"Bad Clip {i}",
            "file_path": f"C:/nonexistent/video_{i}.mp4",
            "resolution": "1920x1080",
            "fps": 30.0
        })
    
    print(f"Lade {len(fake_items)} ungueltige Clips in das Grid...")
    grid.set_items(fake_items)
    
    # Gib dem Grid 2 Sekunden Zeit, um die Thumbnail-Threads zu starten
    print("Warte auf Hintergrund-Threads (sollte NICHT abstuerzen)...")
    
    def finish():
        print("Test erfolgreich: Kein Crash bei ungueltigen Pfaden!")
        app.quit()

    QTimer.singleShot(2000, finish)
    sys.exit(app.exec())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_grid_with_invalid_paths()
