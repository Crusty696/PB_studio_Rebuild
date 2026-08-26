from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _fake_load(self, t_sec):
    from services.pacing.scorer import AudioContext, ClipFeatures

    ctx = AudioContext(
        at_timestamp_sec=t_sec,
        at_beat_idx=1,
        at_section_type="drop",
        at_bpm=140.0,
        at_energy=0.9,
        at_key=None,
        at_key_confidence=None,
        at_harmonic_tension=0.5,
        at_mood_audio="energetic",
        at_mood_video="energetic",
        at_genre=None,
        at_sub_genre=None,
        at_spectral_hash=None,
        at_groove_template=None,
        at_lufs=None,
    )
    candidates = [
        ClipFeatures(
            clip_id=i,
            scene_id=i,
            role="action",
            mood_refined="energetic",
            style_bucket_id=0,
            motion_score=motion,
        )
        for i, motion in enumerate((0.9, 0.2, 0.5))
    ]
    return ctx, candidates, [f"clip{i}" for i in range(3)]


def test_ab_compare_run_button_click_renders_success(monkeypatch) -> None:
    app = _qapp()
    from ui.dialogs.ab_compare_dialog import ABCompareDialog

    monkeypatch.setattr(ABCompareDialog, "_load_context_and_candidates", _fake_load)
    dialog = ABCompareDialog()
    try:
        dialog.show()
        app.processEvents()
        assert dialog.btn_run.text() == "Vergleich ausfuehren"
        assert dialog.btn_run.objectName() == "btn_accent"
        assert dialog.btn_run.isVisibleTo(dialog) is True
        assert dialog.btn_run.isEnabled() is True

        QTest.mouseClick(dialog.btn_run, Qt.MouseButton.LeftButton)
        app.processEvents()

        result = dialog.txt_result.toPlainText()
        assert "Kandidaten: 3" in result
        assert "Profil A" in result
        assert "Profil B" in result
        assert "Fehler:" not in result
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_ab_compare_run_button_click_renders_error(monkeypatch) -> None:
    app = _qapp()
    from ui.dialogs.ab_compare_dialog import ABCompareDialog

    def _boom(self, t_sec):
        raise RuntimeError("kein aktives Projekt")

    monkeypatch.setattr(ABCompareDialog, "_load_context_and_candidates", _boom)
    dialog = ABCompareDialog()
    try:
        dialog.show()
        app.processEvents()

        QTest.mouseClick(dialog.btn_run, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert dialog.txt_result.toPlainText() == "Fehler: kein aktives Projekt"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
