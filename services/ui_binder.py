"""Bidirektionales Binding zwischen PacingProfile und UI-Widgets.

T4.3 (2026-05-09) Hardening D3..D10:
- D3 Initial-Sync: Konstruktor ruft am Ende apply_profile(profile).
- D4 dispose(): trennt alle Connections sauber.
- D5 findText case-insensitive via Qt.MatchFixedString.
- D6 Style-Drift-Schutz: bei findText == -1 KEIN Profil-Schreiben.
- D7 apply_profile mit QSignalBlocker (kein Re-Entry).
- D8 BREAKDOWN_CHOICES wird aus services.pacing_profile importiert.
- D9 @Slot-Decorators an allen Slots.
- D10 Slider/Spin-Range-Mismatch -> ValueError.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSignalBlocker, Slot
from PySide6.QtWidgets import QComboBox, QSlider, QSpinBox, QLineEdit

from services.pacing_profile import BREAKDOWN_CHOICES, PacingProfile

# D8: lokal abgeleitete Helfer aus dem zentralen Tuple.
_BREAKDOWN_LIST = list(BREAKDOWN_CHOICES)
_BREAKDOWN_INDEX = {name: i for i, name in enumerate(_BREAKDOWN_LIST)}


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
        # D10: Range-Mismatch zwischen Slider und Spin sofort ablehnen.
        if (
            reactivity_slider.minimum() != reactivity_spin.minimum()
            or reactivity_slider.maximum() != reactivity_spin.maximum()
        ):
            raise ValueError(
                "PacingProfileBinder: reactivity_slider und reactivity_spin "
                "muessen identische min/max haben "
                f"(slider=[{reactivity_slider.minimum()},{reactivity_slider.maximum()}], "
                f"spin=[{reactivity_spin.minimum()},{reactivity_spin.maximum()}])"
            )

        self.profile = profile
        self._cut = cut_rate_combo
        self._style = style_combo
        self._react_slider = reactivity_slider
        self._react_spin = reactivity_spin
        self._breakdown = breakdown_combo
        self._vibe = vibe_input

        # Connections fuer dispose() merken (D4).
        self._connections = [
            (self._cut.currentIndexChanged, self._on_cut),
            (self._style.currentIndexChanged, self._on_style),
            (self._react_slider.valueChanged, self._react_spin.setValue),
            (self._react_spin.valueChanged, self._react_slider.setValue),
            (self._react_spin.valueChanged, self._on_react),
            (self._breakdown.currentIndexChanged, self._on_breakdown),
            (self._vibe.textChanged, self._on_vibe),
        ]
        for sig, slot in self._connections:
            sig.connect(slot)

        # D3: Initial-Sync — Widgets reflektieren Profile direkt.
        self.apply_profile(profile)

    # --- Slots (D9) ---------------------------------------------------
    @Slot(int)
    def _on_cut(self, idx: int):
        self.profile.cut_rate_index = idx

    @Slot(int)
    def _on_style(self, idx: int):
        self.profile.style_preset = self._style.itemText(idx)

    @Slot(int)
    def _on_react(self, val: int):
        self.profile.energy_reactivity = val

    @Slot(int)
    def _on_breakdown(self, idx: int):
        if 0 <= idx < len(_BREAKDOWN_LIST):
            self.profile.breakdown = _BREAKDOWN_LIST[idx]

    @Slot(str)
    def _on_vibe(self, txt: str):
        self.profile.vibe = txt

    # --- API ----------------------------------------------------------
    def apply_profile(self, new_profile: PacingProfile) -> None:
        """Schreibt new_profile in self.profile UND in alle Widgets.

        D7: QSignalBlocker um die Widget-Setter — verhindert dass die
        bidirektionalen Slots waehrend des Sync zurueckschreiben.
        D6: findText == -1 -> style_preset wird NICHT veraendert (Drift-Schutz).
        """
        # D6: Style-Drift-Check zuerst, bevor self.profile veraendert wird.
        style_idx = self._style.findText(new_profile.style_preset, Qt.MatchFixedString)
        apply_style = style_idx != -1

        # Profile-Felder uebernehmen.
        self.profile.audio_id = new_profile.audio_id
        self.profile.video_id = new_profile.video_id
        self.profile.vibe = new_profile.vibe
        self.profile.cut_rate_index = new_profile.cut_rate_index
        if apply_style:
            self.profile.style_preset = new_profile.style_preset
        self.profile.energy_reactivity = new_profile.energy_reactivity
        self.profile.breakdown = new_profile.breakdown
        self.profile.manual_density_curve = new_profile.manual_density_curve
        self.profile.anchors = list(new_profile.anchors)

        # D7: QSignalBlocker fuer alle setter-Targets.
        blockers = [
            QSignalBlocker(self._cut),
            QSignalBlocker(self._style),
            QSignalBlocker(self._react_slider),
            QSignalBlocker(self._react_spin),
            QSignalBlocker(self._breakdown),
            QSignalBlocker(self._vibe),
        ]
        try:
            self._cut.setCurrentIndex(new_profile.cut_rate_index)
            if apply_style:
                self._style.setCurrentIndex(style_idx)
            self._react_slider.setValue(new_profile.energy_reactivity)
            self._react_spin.setValue(new_profile.energy_reactivity)
            self._breakdown.setCurrentIndex(
                _BREAKDOWN_INDEX.get(new_profile.breakdown, 0)
            )
            self._vibe.setText(new_profile.vibe)
        finally:
            del blockers  # explizit, damit Linter sieht: gehalten bis hier.

    def dispose(self) -> None:
        """D4: Trennt alle Signal-Connections. Idempotent."""
        for sig, slot in self._connections:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                # Bereits getrennt oder Widget weg — ignorieren.
                pass
        self._connections = []
