"""M3 Grid-Virtualisierung (D-066): Guards fuer MediaPoolGrid.

Invarianten:
- Cards entstehen NUR fuer das Scroll-Fenster (viewport ± 1 Screen),
  nicht fuer alle Items (vorher: Vollbuild von ~375 Widgets).
- Container-Hoehe entspricht ALLEN gefilterten Records (Scrollbalken ehrlich).
- Scrollen materialisiert weitere Cards; einmal gebaute werden per
  media_id wiederverwendet.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

_CARD_H_GAP = None  # aus media_grid geladen


def _qapp():
    return QApplication.instance() or QApplication([])


def _img(w: int = 10, h: int = 10) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0xFF202020)
    return img


def _items(tmp_path, count: int) -> list[dict]:
    out = []
    for i in range(count):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"fake video")
        out.append({
            "id": i,
            "title": f"Clip {i:04d}",
            "file_path": str(p),
            "resolution": "1920x1080",
            "fps": 30.0,
        })
    return out


def _drain(app, grid, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and (
            grid._build_queue or grid._load_timer.isActive()
            or grid._relayout_timer.isActive()):
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()


def test_m3_only_window_cards_are_built(monkeypatch, tmp_path):
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid, _CH, _GAP

    monkeypatch.setattr(media_grid, "_extract_thumb_qimage",
                        lambda p, w, h: _img(w, h))

    grid = MediaPoolGrid(media_type="video")
    try:
        grid.resize(700, 500)
        grid.show()
        app.processEvents()
        items = _items(tmp_path, 200)
        grid.set_items(items)
        _drain(app, grid)

        assert len(grid._filtered_data) == 200  # alle Records da
        assert 0 < len(grid._cards) < 200, (
            f"M3: {len(grid._cards)} Cards gebaut — erwartet nur das "
            "Scroll-Fenster, nicht alle 200"
        )
        # Scrollbalken ehrlich: Container-Hoehe deckt ALLE Records ab.
        rows_total = (200 + grid._cols - 1) // grid._cols
        assert grid._container.minimumHeight() == rows_total * (_CH + _GAP) + 10
    finally:
        grid.deleteLater()
        app.processEvents()


def test_m3_scrolling_builds_more_and_reuses_pool(monkeypatch, tmp_path):
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid

    monkeypatch.setattr(media_grid, "_extract_thumb_qimage",
                        lambda p, w, h: _img(w, h))

    grid = MediaPoolGrid(media_type="video")
    try:
        grid.resize(700, 500)
        grid.show()
        app.processEvents()
        grid.set_items(_items(tmp_path, 200))
        _drain(app, grid)

        built_before = len(grid._cards)
        first_card = grid._card_by_id.get(0)
        assert first_card is not None

        # Ans Ende scrollen -> hintere Records werden materialisiert.
        sb = grid._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
        _drain(app, grid)

        assert len(grid._cards) > built_before, (
            "M3: Scrollen ans Ende hat keine weiteren Cards gebaut"
        )
        assert grid._card_by_id.get(199) is not None  # letztes Item gebaut
        # Pool-Wiederverwendung: Card #0 ist dasselbe Objekt geblieben
        # (versteckt, nicht zerstoert/neu gebaut).
        assert grid._card_by_id.get(0) is first_card
        assert first_card.isHidden()

        # Zurueck an den Anfang -> Card #0 wird ohne Neubau wieder gezeigt.
        sb.setValue(0)
        _drain(app, grid)
        assert grid._card_by_id.get(0) is first_card
        assert not first_card.isHidden()
    finally:
        grid.deleteLater()
        app.processEvents()
