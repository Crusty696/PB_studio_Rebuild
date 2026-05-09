import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox, QLineEdit
from services.pacing_profile import PacingProfile
from services.ui_binder import PacingProfileBinder


def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_widget_to_profile_then_profile_to_widget():
    _qapp()
    profile = PacingProfile()
    cut = QComboBox(); cut.addItems(["1B", "2B", "4B", "8B", "16B"])
    style = QComboBox(); style.addItems(["Standard", "Techno", "House"])
    react_slider = QSlider(); react_slider.setRange(0, 100)
    react_spin = QSpinBox(); react_spin.setRange(0, 100)
    breakdown = QComboBox(); breakdown.addItems(["halve", "force16", "none"])
    vibe = QLineEdit()

    binder = PacingProfileBinder(
        profile, cut_rate_combo=cut, style_combo=style,
        reactivity_slider=react_slider, reactivity_spin=react_spin,
        breakdown_combo=breakdown, vibe_input=vibe,
    )

    cut.setCurrentIndex(3)
    react_spin.setValue(75)
    style.setCurrentIndex(1)
    breakdown.setCurrentIndex(2)
    vibe.setText("dunkel")

    assert profile.cut_rate_index == 3
    assert profile.energy_reactivity == 75
    assert profile.style_preset == "Techno"
    assert profile.breakdown == "none"
    assert profile.vibe == "dunkel"

    new_p = PacingProfile.from_preset("Cinematic")
    binder.apply_profile(new_p)
    assert cut.currentIndex() == 4
    assert react_spin.value() == 30
    assert breakdown.currentText() == "none"
