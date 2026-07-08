"""NEUBAU-VOLLINTEGRATION T2.5.6 (FR-S4-5): ab_runner als UI-Funktion.

Vorher: run_ab nur von Demo/Tests erreicht — kein Produkt-Caller.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _fake_load(self, t_sec):
    """Ersetzt DB-Zugriff: 3 Kandidaten, einer motion-stark."""
    from services.pacing.scorer import AudioContext, ClipFeatures
    ctx = AudioContext(
        at_timestamp_sec=t_sec, at_beat_idx=1, at_section_type="drop",
        at_bpm=140.0, at_energy=0.9, at_key=None, at_key_confidence=None,
        at_harmonic_tension=0.5, at_mood_audio="energetic",
        at_mood_video="energetic", at_genre=None, at_sub_genre=None,
        at_spectral_hash=None, at_groove_template=None, at_lufs=None,
    )
    cands = [
        ClipFeatures(clip_id=i, scene_id=i, role="action",
                     mood_refined="energetic", style_bucket_id=0,
                     motion_score=m)
        for i, m in enumerate((0.9, 0.2, 0.5))
    ]
    return ctx, cands, [f"clip{i}" for i in range(3)]


class TestABCompareDialog:
    def test_run_produces_comparison(self, monkeypatch):
        _qapp()
        from ui.dialogs.ab_compare_dialog import ABCompareDialog
        monkeypatch.setattr(
            ABCompareDialog, "_load_context_and_candidates", _fake_load)
        dlg = ABCompareDialog()
        dlg._on_run()
        text = dlg.txt_result.toPlainText()
        assert "Profil A" in text and "Profil B" in text
        assert "Kandidaten: 3" in text
        assert "Fehler" not in text

    def test_weight_change_can_flip_choice(self, monkeypatch):
        """w_energy=0 in B: der motion-starke Clip verliert seinen Vorteil."""
        _qapp()
        from ui.dialogs.ab_compare_dialog import ABCompareDialog
        monkeypatch.setattr(
            ABCompareDialog, "_load_context_and_candidates", _fake_load)
        dlg = ABCompareDialog()
        dlg.spin_energy.setValue(0.0)
        dlg._on_run()
        text = dlg.txt_result.toPlainText()
        assert "Profil A (Standard) waehlt: clip0" in text  # motion 0.9 x energy 0.9

    def test_error_shown_not_raised(self, monkeypatch):
        _qapp()
        from ui.dialogs.ab_compare_dialog import ABCompareDialog

        def boom(self, t):
            raise RuntimeError("kein Projekt")

        monkeypatch.setattr(
            ABCompareDialog, "_load_context_and_candidates", boom)
        dlg = ABCompareDialog()
        dlg._on_run()  # darf nicht raisen
        assert "Fehler: kein Projekt" in dlg.txt_result.toPlainText()


def test_pacing_tab_has_button(monkeypatch):
    _qapp()

    class _Store:
        def get_nested(self, *p, default=None):
            return default

        def set_nested(self, *p, value=None):
            pass

    import services.settings_store as ss
    monkeypatch.setattr(ss, "get_settings_store", lambda: _Store())
    monkeypatch.setattr(ss, "get_ollama_settings", lambda: {"enabled": True})
    from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
    tab = SchnittTabPacingAnker()
    assert tab.btn_ab_compare.text() == "A/B-Gewichte testen"
