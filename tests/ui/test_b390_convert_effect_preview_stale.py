"""B-390: veralteter Effekt-Preview-Worker darf neuere Vorschau nicht ueberschreiben.

`_on_effect_frame_ready()` setzte die Pixmap ohne Request-Abgleich. Ein aelterer
FrameExtractWorker, der spaeter fertig wird, konnte die neuere Preview ueberschreiben.
Fix: monotone Request-Sequenz; nur das Frame des juengsten Requests setzt die UI.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QLabel

from ui.controllers.convert import ConvertController


def _qapp():
    return QApplication.instance() or QApplication([])


def _rgb(w: int = 2, h: int = 2) -> bytes:
    return bytes([10, 20, 30]) * (w * h)


def _stub_with_seq(seq: int):
    stub = SimpleNamespace()
    stub._effect_request_seq = seq
    stub.window = SimpleNamespace(effects_preview=QLabel())
    return stub


def test_stale_effect_frame_is_discarded():
    _qapp()
    stub = _stub_with_seq(5)

    # aelterer Request 3 trifft spaet ein → darf UI nicht setzen
    ConvertController._on_effect_frame_ready(stub, _rgb(), 2, 2, 3)

    pm = stub.window.effects_preview.pixmap()
    assert pm is None or pm.isNull()


def test_latest_effect_frame_is_applied():
    _qapp()
    stub = _stub_with_seq(5)

    ConvertController._on_effect_frame_ready(stub, _rgb(), 2, 2, 5)

    pm = stub.window.effects_preview.pixmap()
    assert pm is not None and not pm.isNull()
