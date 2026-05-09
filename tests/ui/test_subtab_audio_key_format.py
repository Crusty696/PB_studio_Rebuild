"""Tonart-Em-Dash-Format (Phase 07 / Task T2.5).

Spec: 'Cm — 7A' mit Em-Dash, keine Klammern.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_set_key_em_dash_format():
    _qapp()
    t = SchnittTabAudio()
    t.set_key("Cm", "7A")
    text = t.key_label.text()
    assert "—" in text
    assert "(" not in text
    assert ")" not in text
    assert "Cm" in text
    assert "7A" in text


def test_set_key_without_camelot_no_dash():
    _qapp()
    t = SchnittTabAudio()
    t.set_key("F#m")
    text = t.key_label.text()
    assert "F#m" in text
    assert "—" not in text


def test_set_key_none_dash_placeholder():
    _qapp()
    t = SchnittTabAudio()
    t.set_key(None)
    assert t.key_label.text() == "Tonart: —"
