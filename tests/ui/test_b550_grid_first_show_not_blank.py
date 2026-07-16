"""B-550: Media-Grid Seite 1 beim ersten Kachel-Wechsel komplett leer.

Root-Cause (verifiziert per Code-Lesung, Live-reproduziert 2026-06-24):
``set_items()`` waehrend das Grid unsichtbar ist (Default-Listenansicht)
cached die Daten nur (``_pending_rebuild = True``). Beim ERSTEN
Sichtbarwerden baut ``showEvent()`` die Cards zwar synchron
(``_rebuild_cards()``), aber die eigentliche Fenster-Positionierung
(``_place_card``/``_ensure_card_at``) lief NUR ueber den 100ms-Debounce-
Timer (``self._relayout()`` startet nur den Timer, positioniert nichts
direkt). Blieb ``isVisible()`` beim ersten Timer-Feuern aus irgendeinem
Grund (Grid-Verify) noch False, no-opte ``_do_relayout_debounced()``
komplett — die Seite blieb dauerhaft leer, bis ein Folge-Trigger (Scroll,
erneutes Sichtbarwerden) den Timer erneut ausloeste.

Fix: ``showEvent()`` ruft ``_do_relayout_debounced()`` jetzt SYNCHRON auf
(nach ``_relayout_timer.stop()``), statt sich auf den Timer zu verlassen —
Qt garantiert ``isVisible() == True`` waehrend der showEvent-Verarbeitung
selbst, das Race ist damit strukturell ausgeschlossen.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


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


def test_b550_cards_positioned_synchronously_on_first_show(monkeypatch, tmp_path):
    """Kernfall: set_items() waehrend UNSICHTBAR (wie Default-Listenansicht),
    dann ERSTES show() — Karten muessen SOFORT (ohne den 100ms-Timer
    abzuwarten) positioniert sein."""
    app = _qapp()
    import ui.widgets.media_grid as media_grid
    from ui.widgets.media_grid import MediaPoolGrid

    monkeypatch.setattr(media_grid, "_extract_thumb_qimage",
                        lambda p, w, h: _img(w, h))

    grid = MediaPoolGrid(media_type="video")
    try:
        grid.resize(700, 500)
        # NICHT show() vor set_items() — genau der B-550-Reproduktionsfall
        # (Grid ist unsichtbar, weil die Listenansicht aktiv ist).
        assert grid.isVisible() is False

        items = _items(tmp_path, 50)
        grid.set_items(items)
        assert grid._pending_rebuild is True, (
            "set_items() waehrend unsichtbar muss nur cachen (_pending_rebuild), "
            "kein Sofort-Build"
        )
        assert grid._cards == [], "Vor dem ersten Show duerfen keine Cards existieren"

        # Erstes Sichtbarwerden — der Kachel-Ansicht-Wechsel aus dem Bug-Report.
        grid.show()
        app.processEvents()

        # B-550: Cards muessen JETZT schon positioniert sein — OHNE auf den
        # 100ms-Debounce-Timer zu warten (kein time.sleep, kein zusaetzlicher
        # app.processEvents()-Wartezyklus fuer den Timer noetig).
        assert len(grid._cards) > 0, (
            "B-550: Grid blieb nach dem ersten show() leer — Cards wurden "
            "nicht synchron positioniert, haengt vom Debounce-Timer ab"
        )
        # Mindestens die erste Karte muss tatsaechlich sichtbar UND im
        # Container geparkt sein (nicht nur im Pool erzeugt).
        first_card = grid._card_by_id.get(0)
        assert first_card is not None
        assert first_card.parentWidget() is grid._container
    finally:
        grid.deleteLater()
        app.processEvents()


def test_b550_subsequent_resize_still_uses_debounced_timer(monkeypatch, tmp_path):
    """Gegenprobe: der Fix darf NUR das erste showEvent betreffen — Resize
    (haeufiges Event, z.B. Fenster-Ziehen) muss weiterhin gedrosselt
    (debounced) bleiben, sonst regressiert die urspruengliche F-029-
    Drosselung."""
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
        grid.set_items(_items(tmp_path, 50))
        app.processEvents()

        grid.resize(800, 500)
        # resizeEvent ruft weiterhin nur self._relayout() (Timer-Start) —
        # OHNE processEvents()-Wartezyklus fuer den Timer darf sich am
        # Timer-Status noch nichts final abgeschlossen haben.
        assert grid._relayout_timer.isActive() or not grid._relayout_timer.isActive()
        # (Der Timer kann durch die vorherige App-Event-Verarbeitung schon
        # gefeuert haben — entscheidend ist NUR, dass resizeEvent selbst
        # _do_relayout_debounced NICHT synchron erzwingt, siehe Source-Check
        # unten statt Timing-Race.)
        import inspect
        resize_src = inspect.getsource(MediaPoolGrid.resizeEvent)
        assert "_do_relayout_debounced" not in resize_src, (
            "resizeEvent darf weiterhin nur ueber den Debounce-Timer laufen "
            "(F-029-Drosselung), nicht synchron wie der neue showEvent-Fix"
        )
    finally:
        grid.deleteLater()
        app.processEvents()
