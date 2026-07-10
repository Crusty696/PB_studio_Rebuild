"""B-508: Grid-Thumbnails laufen ueber einen geteilten, begrenzten QThreadPool.

Vorher startete MediaPoolGrid pro VideoCard sofort einen eigenen QThread mit
ffmpeg-Subprocess — 300-Clip-Import = bis zu 300 parallele Threads + 300
ffmpeg-Prozesse. Jetzt: modulweiter QThreadPool mit setMaxThreadCount(4),
QRunnable + QObject-Signal-Holder, shiboken6.isValid-Check vor Emit und
Generation-Counter gegen veraltete Ergebnisse.

Alle Tests nutzen einen Fake-Extractor (kein echtes ffmpeg).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage


def _qapp():
    return QApplication.instance() or QApplication([])


def _img(w: int = 10, h: int = 10) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0xFF202020)
    return img


def _video_items(tmp_path, count: int) -> list[dict]:
    items = []
    for i in range(count):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"fake video")
        items.append({
            "id": i,
            "title": f"Clip {i}",
            "file_path": str(p),
            "resolution": "1920x1080",
            "fps": 30.0,
        })
    return items


def test_pool_limits_concurrency_to_four_and_serves_all(monkeypatch, tmp_path):
    """(a) 20 Cards -> nie mehr als 4 Extraktionen gleichzeitig aktiv,
    aber alle 20 werden bedient."""
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid

    lock = threading.Lock()
    state = {"active": 0, "max_active": 0, "done": 0}

    def fake_extract(path, w, h):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.05)  # haelt den Slot kurz besetzt -> Parallelitaet messbar
        with lock:
            state["active"] -= 1
            state["done"] += 1
        return _img(w, h)

    monkeypatch.setattr(media_grid, "_extract_thumb_qimage", fake_extract)

    grid = MediaPoolGrid(media_type="video")
    try:
        # ddd2293 (Freeze-Fix, B-613-Nachzug): unsichtbares Grid cached
        # set_items nur — fuer den Pool-Test muss das Grid sichtbar sein.
        grid.show()
        app.processEvents()
        grid.set_items(_video_items(tmp_path, 20))

        deadline = time.time() + 15.0
        while time.time() < deadline:
            app.processEvents()
            with lock:
                if state["done"] >= 20:
                    break
            time.sleep(0.02)

        assert state["done"] == 20, (
            f"B-508: nur {state['done']}/20 Thumbnail-Jobs bedient"
        )
        assert state["max_active"] <= 4, (
            f"B-508: {state['max_active']} gleichzeitige Extraktionen — "
            "Pool-Limit 4 verletzt"
        )
    finally:
        grid.deleteLater()
        app.processEvents()


def test_runnable_skips_emit_for_destroyed_card(monkeypatch):
    """(b) Card vor Ergebnis zerstoert -> kein Crash, kein Emit."""
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid, VideoCard, _ThumbRunnable

    monkeypatch.setattr(
        media_grid, "_extract_thumb_qimage", lambda p, w, h: _img(w, h)
    )

    grid = MediaPoolGrid(media_type="video")
    card = VideoCard(1, "t", "p.mp4")
    received: list[str] = []

    runnable = _ThumbRunnable(card, "p.mp4", 16, 9, grid, grid._thumb_generation)
    runnable.setAutoDelete(False)  # run() wird hier manuell gerufen, kein Pool
    runnable.signals.done.connect(lambda path, img: received.append(path))

    # Card zerstoeren BEVOR das Ergebnis kommt
    card.deleteLater()
    app.sendPostedEvents(card, QEvent.Type.DeferredDelete)

    runnable.run()  # darf nicht crashen
    app.processEvents()

    assert received == [], "B-508: Emit trotz zerstoerter Card"
    grid.deleteLater()
    app.processEvents()


def test_grid_lays_out_cards_when_shown_after_invisible_set_items(monkeypatch, tmp_path):
    """B-526 + ddd2293 (B-613-Nachzug): set_items bei UNSICHTBAREM Grid
    cached nur die Daten (lazy Freeze-Fix ddd2293 — vorher wurden Cards
    sofort gebaut). Beim Sichtbarwerden (showEvent) werden die Karten
    nachgebaut UND einsortiert — das Grid darf nicht leer bleiben (B-526)."""
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid

    monkeypatch.setattr(
        media_grid, "_extract_thumb_qimage", lambda p, w, h: _img(w, h)
    )

    grid = MediaPoolGrid(media_type="video")
    try:
        assert not grid.isVisible()
        items = _video_items(tmp_path, 6)
        grid.set_items(items)

        # ddd2293: unsichtbar -> KEIN Card-Aufbau, nur Daten-Cache.
        t2 = time.time() + 0.5
        while time.time() < t2:
            app.processEvents()
            time.sleep(0.02)
        assert grid._cards == []
        assert grid._pending_rebuild is True
        assert grid._grid.count() == 0

        # Umschalten auf Kachelansicht = Grid wird sichtbar -> showEvent
        # baut die Karten nach und sortiert sie ein.
        grid.show()
        deadline = time.time() + 10.0
        while time.time() < deadline and (
                len(grid._cards) < len(items) or grid._grid.count() < len(items)):
            app.processEvents()
            time.sleep(0.02)

        assert len(grid._cards) == len(items)
        assert grid._grid.count() == len(items), (
            f"B-526: Grid zeigt nach show() {grid._grid.count()}/{len(items)} Karten"
        )
    finally:
        grid.deleteLater()
        app.processEvents()


def test_clear_discards_stale_results(monkeypatch):
    """(c) clear() waehrend pending -> alte Generation, Ergebnis verworfen."""
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid, VideoCard, _ThumbRunnable

    monkeypatch.setattr(
        media_grid, "_extract_thumb_qimage", lambda p, w, h: _img(w, h)
    )

    grid = MediaPoolGrid(media_type="video")
    # ddd2293 (Freeze-Fix, B-613-Nachzug): clear() bei unsichtbarem Grid
    # deferred den Rebuild (kein Generation-Bump bis showEvent). Der
    # Stale-Invalidierungs-Test braucht den sofortigen Pfad -> sichtbar.
    grid.show()
    app.processEvents()
    card = VideoCard(1, "t", "p.mp4")
    received: list[str] = []

    runnable = _ThumbRunnable(card, "p.mp4", 16, 9, grid, grid._thumb_generation)
    runnable.setAutoDelete(False)
    runnable.signals.done.connect(lambda path, img: received.append(path))

    gen_before = grid._thumb_generation
    grid.clear()  # sichtbar -> _rebuild_cards -> _cancel_pending_thumbs -> Bump
    assert grid._thumb_generation > gen_before

    runnable.run()  # Job traegt noch die alte Generation
    app.processEvents()

    assert received == [], "B-508: veraltetes Ergebnis nach clear() zugestellt"

    # Frische Generation wird dagegen zugestellt (Gegenprobe).
    runnable2 = _ThumbRunnable(card, "p.mp4", 16, 9, grid, grid._thumb_generation)
    runnable2.setAutoDelete(False)
    runnable2.signals.done.connect(lambda path, img: received.append(path))
    runnable2.run()
    app.processEvents()
    assert received == ["p.mp4"]

    grid.deleteLater()
    app.processEvents()
