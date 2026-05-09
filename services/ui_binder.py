"""Bidirektionales Binding zwischen PacingProfile und UI-Widgets."""
from __future__ import annotations
from PySide6.QtWidgets import QComboBox, QSlider, QSpinBox, QLineEdit
from services.pacing_profile import PacingProfile

_BREAKDOWN_INDEX = {"halve": 0, "force16": 1, "none": 2}
_BREAKDOWN_LIST = ["halve", "force16", "none"]


class PacingProfileBinder:
    def __init__(
        self,
        profile: PacingProfile,
        *,
        cut_rate_combo: QComboBox,
        style_combo: QComboBox,
        reactivity_slider: QSlider,
        reactivity_spin: QSpinBox,
        breakdown_combo: QComboBox,
        vibe_input: QLineEdit,
    ):
        self.profile = profile
        self._cut = cut_rate_combo
        self._style = style_combo
        self._react_slider = reactivity_slider
        self._react_spin = reactivity_spin
        self._breakdown = breakdown_combo
        self._vibe = vibe_input

        self._cut.currentIndexChanged.connect(self._on_cut)
        self._style.currentIndexChanged.connect(self._on_style)
        self._react_slider.valueChanged.connect(self._react_spin.setValue)
        self._react_spin.valueChanged.connect(self._react_slider.setValue)
        self._react_spin.valueChanged.connect(self._on_react)
        self._breakdown.currentIndexChanged.connect(self._on_breakdown)
        self._vibe.textChanged.connect(self._on_vibe)

    def _on_cut(self, idx: int):
        self.profile.cut_rate_index = idx

    def _on_style(self, idx: int):
        self.profile.style_preset = self._style.itemText(idx)

    def _on_react(self, val: int):
        self.profile.energy_reactivity = val

    def _on_breakdown(self, idx: int):
        self.profile.breakdown = _BREAKDOWN_LIST[idx]

    def _on_vibe(self, txt: str):
        self.profile.vibe = txt

    def apply_profile(self, new_profile: PacingProfile) -> None:
        self.profile.audio_id = new_profile.audio_id
        self.profile.video_id = new_profile.video_id
        self.profile.vibe = new_profile.vibe
        self.profile.cut_rate_index = new_profile.cut_rate_index
        self.profile.style_preset = new_profile.style_preset
        self.profile.energy_reactivity = new_profile.energy_reactivity
        self.profile.breakdown = new_profile.breakdown
        self.profile.manual_density_curve = new_profile.manual_density_curve
        self.profile.anchors = list(new_profile.anchors)

        self._cut.setCurrentIndex(new_profile.cut_rate_index)
        idx = max(0, self._style.findText(new_profile.style_preset))
        self._style.setCurrentIndex(idx)
        self._react_spin.setValue(new_profile.energy_reactivity)
        self._breakdown.setCurrentIndex(_BREAKDOWN_INDEX.get(new_profile.breakdown, 0))
        self._vibe.setText(new_profile.vibe)
