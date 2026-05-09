import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QSlider, QSpinBox, QLineEdit

from services.pacing_profile import PacingProfile
from services.ui_binder import PacingProfileBinder


def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _make_widgets():
    cut = QComboBox(); cut.addItems(["1B", "2B", "4B", "8B", "16B"])
    style = QComboBox(); style.addItems(["Standard", "Techno", "House", "Cinematic"])
    react_slider = QSlider(); react_slider.setRange(0, 100)
    react_spin = QSpinBox(); react_spin.setRange(0, 100)
    breakdown = QComboBox(); breakdown.addItems(["halve", "force16", "none"])
    vibe = QLineEdit()
    return cut, style, react_slider, react_spin, breakdown, vibe


def _bind(profile=None):
    _qapp()
    profile = profile or PacingProfile()
    cut, style, slider, spin, brk, vibe = _make_widgets()
    binder = PacingProfileBinder(
        profile, cut_rate_combo=cut, style_combo=style,
        reactivity_slider=slider, reactivity_spin=spin,
        breakdown_combo=brk, vibe_input=vibe,
    )
    return binder, profile, cut, style, slider, spin, brk, vibe


def test_widget_to_profile_then_profile_to_widget():
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    cut.setCurrentIndex(3)
    spin.setValue(75)
    style.setCurrentIndex(1)
    brk.setCurrentIndex(2)
    vibe.setText("dunkel")

    assert profile.cut_rate_index == 3
    assert profile.energy_reactivity == 75
    assert profile.style_preset == "Techno"
    assert profile.breakdown == "none"
    assert profile.vibe == "dunkel"

    new_p = PacingProfile.from_preset("Cinematic")
    binder.apply_profile(new_p)
    assert cut.currentIndex() == 4
    assert spin.value() == 30
    assert brk.currentText() == "none"


def test_d3_initial_sync_widgets_reflect_profile_after_construction():
    """D3: Konstruktor ruft apply_profile am Ende → Widgets matchen Profile."""
    _qapp()
    profile = PacingProfile.from_preset("Festival")  # cut=1, react=90, brk=halve
    cut, style, slider, spin, brk, vibe = _make_widgets()
    PacingProfileBinder(
        profile, cut_rate_combo=cut, style_combo=style,
        reactivity_slider=slider, reactivity_spin=spin,
        breakdown_combo=brk, vibe_input=vibe,
    )
    assert cut.currentIndex() == 1
    assert spin.value() == 90
    assert slider.value() == 90
    assert brk.currentText() == "halve"


def test_d4_dispose_disconnects_all_signals():
    """D4: dispose() trennt alle 7 Connections; danach keine Profile-Updates."""
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    binder.dispose()
    cut.setCurrentIndex(3)
    spin.setValue(80)
    style.setCurrentIndex(2)
    brk.setCurrentIndex(2)
    vibe.setText("after-dispose")
    # Profile darf nicht mehr aktualisiert werden — Defaults bleiben.
    assert profile.cut_rate_index == 2  # default
    assert profile.energy_reactivity == 50  # default
    assert profile.style_preset == "Standard"
    assert profile.breakdown == "halve"
    assert profile.vibe == ""


def test_d4_dispose_idempotent():
    binder, *_ = _bind()
    binder.dispose()
    binder.dispose()  # darf nicht crashen


def test_d5_findtext_case_insensitive_via_matchfixedstring():
    """D5: apply_profile mit anderer Casing matcht Style trotzdem."""
    _qapp()
    profile = PacingProfile()
    cut, style, slider, spin, brk, vibe = _make_widgets()
    binder = PacingProfileBinder(
        profile, cut_rate_combo=cut, style_combo=style,
        reactivity_slider=slider, reactivity_spin=spin,
        breakdown_combo=brk, vibe_input=vibe,
    )
    new = PacingProfile(style_preset="techno")  # lowercase
    binder.apply_profile(new)
    # MatchFixedString ist case-insensitive in Qt → "Techno" matcht.
    assert style.currentText() == "Techno"
    assert profile.style_preset == "techno"


def test_d6_unknown_style_does_not_overwrite_profile():
    """D6: findText==-1 → style_preset im Profile bleibt unveraendert."""
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    profile.style_preset = "Standard"
    new = PacingProfile(style_preset="Voellig-Unbekannt")
    binder.apply_profile(new)
    assert profile.style_preset == "Standard"  # nicht ueberschrieben


def test_d7_apply_profile_no_signal_reentry():
    """D7: apply_profile darf Slots nicht erneut feuern (QSignalBlocker)."""
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    calls = {"cut": 0, "react": 0}
    cut.currentIndexChanged.connect(lambda _i: calls.__setitem__("cut", calls["cut"] + 1))
    spin.valueChanged.connect(lambda _v: calls.__setitem__("react", calls["react"] + 1))
    new = PacingProfile.from_preset("Cinematic")
    binder.apply_profile(new)
    # External listener darf 0 Mal feuern weil QSignalBlocker aktiv war.
    assert calls["cut"] == 0
    assert calls["react"] == 0


def test_d8_breakdown_choices_imported_from_pacing_profile():
    from services.pacing_profile import BREAKDOWN_CHOICES
    assert BREAKDOWN_CHOICES == ("halve", "force16", "none")


def test_d10_slider_spin_range_mismatch_raises():
    """D10: Range-Mismatch wirft ValueError."""
    _qapp()
    profile = PacingProfile()
    cut = QComboBox(); cut.addItems(["1B", "2B"])
    style = QComboBox(); style.addItems(["Standard"])
    slider = QSlider(); slider.setRange(0, 100)
    spin = QSpinBox(); spin.setRange(0, 50)  # mismatch!
    brk = QComboBox(); brk.addItems(["halve", "force16", "none"])
    vibe = QLineEdit()
    with pytest.raises(ValueError, match="reactivity_slider und reactivity_spin"):
        PacingProfileBinder(
            profile, cut_rate_combo=cut, style_combo=style,
            reactivity_slider=slider, reactivity_spin=spin,
            breakdown_combo=brk, vibe_input=vibe,
        )


# ---------------------------------------------------------------------------
# T5.2 Coverage-Sweep (E2)
# ---------------------------------------------------------------------------


def test_apply_profile_sets_style_combo_text():
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    new = PacingProfile.from_preset("Cinematic")
    binder.apply_profile(new)
    assert style.currentText() == "Cinematic"


def test_apply_profile_sets_vibe_text():
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    new = PacingProfile(vibe="aggressiv-laut")
    binder.apply_profile(new)
    assert vibe.text() == "aggressiv-laut"
    assert profile.vibe == "aggressiv-laut"


def test_apply_profile_sets_react_slider_via_spin():
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    new = PacingProfile(energy_reactivity=77)
    binder.apply_profile(new)
    assert slider.value() == 77
    assert spin.value() == 77
    assert profile.energy_reactivity == 77


def test_apply_profile_idempotent():
    """Zweimal hintereinander → identischer Endzustand, kein RecursionError."""
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    new = PacingProfile.from_preset("Cinematic")
    binder.apply_profile(new)
    state_after_1 = (
        cut.currentIndex(), style.currentText(), slider.value(),
        spin.value(), brk.currentText(), vibe.text(),
    )
    binder.apply_profile(new)
    state_after_2 = (
        cut.currentIndex(), style.currentText(), slider.value(),
        spin.value(), brk.currentText(), vibe.text(),
    )
    assert state_after_1 == state_after_2


def test_apply_profile_unknown_style_no_drift():
    """D6 Verifikation: bei findText=-1 keine Profil-Schreibung des Style-Felds."""
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    profile.style_preset = "House"
    new = PacingProfile(style_preset="Voellig-Unbekannt", energy_reactivity=42)
    binder.apply_profile(new)
    # Style bleibt unveraendert, andere Felder werden trotzdem geschrieben.
    assert profile.style_preset == "House"
    assert profile.energy_reactivity == 42


def test_initial_state_pushed_to_widgets():
    """D3 Verifikation: nach Konstruktor mit non-default Profil sind Widget-Werte=Profil."""
    _qapp()
    profile = PacingProfile(
        cut_rate_index=4, style_preset="House",
        energy_reactivity=33, breakdown="force16", vibe="custom",
    )
    cut, style, slider, spin, brk, vibe = _make_widgets()
    PacingProfileBinder(
        profile, cut_rate_combo=cut, style_combo=style,
        reactivity_slider=slider, reactivity_spin=spin,
        breakdown_combo=brk, vibe_input=vibe,
    )
    assert cut.currentIndex() == 4
    assert style.currentText() == "House"
    assert slider.value() == 33
    assert spin.value() == 33
    assert brk.currentText() == "force16"
    assert vibe.text() == "custom"


def test_dispose_disconnects():
    """Nach dispose() triggern Widget-Changes keine Profil-Schreibungen mehr."""
    binder, profile, cut, style, slider, spin, brk, vibe = _bind()
    binder.dispose()
    # Snapshot vor Aenderung
    snap = (
        profile.cut_rate_index, profile.style_preset,
        profile.energy_reactivity, profile.breakdown, profile.vibe,
    )
    cut.setCurrentIndex(4)
    style.setCurrentIndex(2)
    spin.setValue(11)
    brk.setCurrentIndex(1)
    vibe.setText("nope")
    snap_after = (
        profile.cut_rate_index, profile.style_preset,
        profile.energy_reactivity, profile.breakdown, profile.vibe,
    )
    assert snap == snap_after
