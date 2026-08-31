"""B-953 — die Vorschau lief klein in der Mitte der Flaeche.

Die Frames kamen in 320x180 und wurden 1:1 angezeigt; die Flaeche im
DELIVER-Bereich ist 960x540. Userentscheidung 2026-08-31: "mach nur doppelt so
gross wie jetzt" — also 640x360, nicht formatfuellend.

Der SCHNITT-Player nutzt dieselbe Klasse und ist hoechstens 560x315 gross. Dort
wuerde ein 640x360-Pixmap ohne Anpassung abgeschnitten.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPixmap

from ui.widgets.video_preview import _PREVIEW_H, _PREVIEW_W, VideoPreviewWidget


def test_frames_sind_doppelt_so_gross():
    assert (_PREVIEW_W, _PREVIEW_H) == (640, 360)


def test_seitenverhaeltnis_bleibt_16_zu_9():
    assert _PREVIEW_W / _PREVIEW_H == pytest.approx(16 / 9)


def test_in_der_deliver_flaeche_bleibt_das_bild_gross(qapp):
    w = VideoPreviewWidget()
    w.setFixedSize(960, 540)
    try:
        w._zeige_bild(QPixmap(_PREVIEW_W, _PREVIEW_H))

        assert w.pixmap().width() == _PREVIEW_W
        assert w.pixmap().height() == _PREVIEW_H
    finally:
        w.deleteLater()


def test_im_schnitt_player_wird_heruntergerechnet(qapp):
    """560x315 ist kleiner als 640x360 — ohne Anpassung waere das Bild beschnitten."""
    w = VideoPreviewWidget()
    w.setFixedSize(560, 315)
    try:
        w._zeige_bild(QPixmap(_PREVIEW_W, _PREVIEW_H))

        assert w.pixmap().width() <= 560
        assert w.pixmap().height() <= 315
        # Seitenverhaeltnis darf dabei nicht kippen
        assert w.pixmap().width() / w.pixmap().height() == pytest.approx(16 / 9, abs=0.02)
    finally:
        w.deleteLater()


def test_kleines_bild_wird_nicht_kuenstlich_vergroessert(qapp):
    """Nur begrenzen, nicht hochrechnen — sonst wird es unscharf."""
    w = VideoPreviewWidget()
    w.setFixedSize(960, 540)
    try:
        w._zeige_bild(QPixmap(320, 180))

        assert w.pixmap().width() == 320
    finally:
        w.deleteLater()


def test_standbild_nutzt_dieselbe_groesse():
    """Sonst springt die Anzeige beim Wechsel zwischen Standbild und Wiedergabe."""
    import inspect

    src = inspect.getsource(VideoPreviewWidget._extract_and_show_frame)

    assert "_PREVIEW_W, _PREVIEW_H" in src
    assert "320, 180" not in src
