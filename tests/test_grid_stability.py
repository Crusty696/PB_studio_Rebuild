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
    # Qt erlaubt nur EINE QApplication pro Prozess. Wenn die Suite andere
    # UI-Tests vor diesem laesst, existiert bereits eine — wiederverwenden,
    # statt eine zweite zu erzeugen (sonst RuntimeError im Vollauf).
    app = QApplication.instance() or QApplication(sys.argv)

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

    # Statt app.exec() (das blockiert den ganzen Suite-Lauf) verwenden wir
    # processEvents in einem zeitbegrenzten Loop. Faengt Pending-Events,
    # ohne den globalen Eventloop zu starten — kompatibel mit Suite-Lauf.
    import time
    deadline = time.time() + 2.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    print("Test erfolgreich: Kein Crash bei ungueltigen Pfaden!")
    # Cleanup: Grid und seine Threads ordentlich abbauen.
    grid.deleteLater()
    app.processEvents()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_grid_with_invalid_paths()
