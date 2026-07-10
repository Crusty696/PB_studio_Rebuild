import sys
import os
import logging
import time
import inspect
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage

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


def test_grid_delete_later_invalidates_pending_thumbnails(monkeypatch, tmp_path):
    """B-508: deleteLater bump die Thumbnail-Generation, sodass noch
    laufende/gequeute Pool-Jobs ihr Ergebnis verwerfen (kein quit/wait
    auf per-Card-Threads mehr — der Pool ist geteilt und begrenzt)."""
    app = QApplication.instance() or QApplication(sys.argv)

    import threading
    import ui.widgets.media_grid as media_grid

    started = threading.Event()

    def slow_extract(path, w, h):
        started.set()
        time.sleep(0.2)
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        return img

    monkeypatch.setattr(media_grid, "_extract_thumb_qimage", slow_extract)

    grid = MediaPoolGrid(media_type="video")
    fake_items = []
    for i in range(20):
        media_path = tmp_path / f"slow_video_{i}.mp4"
        media_path.write_bytes(b"placeholder")
        fake_items.append({
            "id": i,
            "title": f"Slow Clip {i}",
            "file_path": str(media_path),
            "resolution": "1920x1080",
            "fps": 30.0,
        })

    try:
        # ddd2293 + M3 (D-066): Cards entstehen nur fuer das Scroll-Fenster
        # eines SICHTBAREN Grids -> sichtbar und gross genug machen.
        grid.resize(900, 800)
        grid.show()
        app.processEvents()
        grid.set_items(fake_items)
        deadline = time.time() + 3.0
        while time.time() < deadline and not started.is_set():
            app.processEvents()
            time.sleep(0.02)
        assert started.is_set()

        gen_before = grid._thumb_generation
        grid.deleteLater()
        # Generation muss bereits VOR dem tatsaechlichen Qt-Delete erhoeht
        # sein — laufende Runnables sehen den Bump und verwerfen still.
        assert grid._thumb_generation > gen_before

        app.processEvents()
    finally:
        # Pool-Jobs auslaufen lassen — darf nicht crashen.
        deadline = time.time() + 3.0
        while time.time() < deadline and media_grid._get_thumb_pool().activeThreadCount() > 0:
            app.processEvents()
            time.sleep(0.02)
        app.processEvents()


def test_grid_invalid_paths_do_not_start_thumbnail_jobs(monkeypatch):
    app = QApplication.instance() or QApplication(sys.argv)
    grid = MediaPoolGrid(media_type="video")
    started_paths = []

    original_start = grid._start_thumb_loader

    def record_start(card, file_path):
        started_paths.append(file_path)
        return original_start(card, file_path)

    monkeypatch.setattr(grid, "_start_thumb_loader", record_start)

    try:
        # ddd2293 + M3 (D-066): Cards entstehen nur fuer das Scroll-Fenster
        # eines SICHTBAREN Grids.
        grid.resize(700, 500)
        grid.show()
        app.processEvents()
        grid.set_items([
            {
                "id": 1,
                "title": "Missing Clip",
                "file_path": "C:/nonexistent/missing_clip.mp4",
                "resolution": "1920x1080",
                "fps": 30.0,
            }
        ])
        deadline = time.time() + 1.0
        while time.time() < deadline and not grid._cards:
            app.processEvents()
            time.sleep(0.02)

        assert grid._cards
        assert started_paths == []
    finally:
        grid.deleteLater()
        app.processEvents()


def test_thumb_loader_callbacks_do_not_capture_grid_self():
    src = inspect.getsource(MediaPoolGrid._start_thumb_loader)
    assert "self._apply_thumbnail" not in src
    assert "self._thumb_threads.remove" not in src
    assert "QThread(self)" not in src
    assert "lambda _path, img" not in src
    assert "card.apply_thumbnail_image" in src

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_grid_with_invalid_paths()
