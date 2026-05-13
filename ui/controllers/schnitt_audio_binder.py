"""Binder for real audio data into the visible SCHNITT audio tab."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SchnittAudioBinder:
    """Small adapter between existing audio/stem services and SCHNITT UI."""

    def __init__(self, tab_audio, stem_player=None):
        self.tab_audio = tab_audio
        self.stem_player = None
        if stem_player is not None:
            self.connect_stem_player(stem_player)

    def connect_stem_player(self, stem_player) -> None:
        self.stem_player = stem_player
        stem_workspace = self._stem_workspace()
        self._connect(stem_workspace.stem_volume_changed, stem_player.set_volume)
        self._connect(stem_workspace.stem_mute_toggled, stem_player.set_mute)
        self._connect(stem_workspace.play_requested, stem_player.play)
        self._connect(stem_workspace.pause_requested, stem_player.pause)
        self._connect(stem_workspace.stop_requested, stem_player.stop)
        self._connect(stem_workspace.seek_requested, stem_player.seek)
        self._connect(stem_player.position_changed, stem_workspace.update_position)
        self._connect(stem_player.state_changed, stem_workspace.update_playback_state)
        if hasattr(stem_player, "playback_finished"):
            self._connect(stem_player.playback_finished, lambda: stem_workspace.update_position(0.0))

    def update_stems(self, track_id: int | None, stem_paths: dict[str, str | None] | None) -> None:
        self._stem_workspace().update_for_track(track_id, stem_paths)

    def set_duration(self, duration: float) -> None:
        self._stem_workspace().set_duration(duration)

    def update_position(self, seconds: float) -> None:
        self._stem_workspace().update_position(seconds)

    def update_waveform(
        self,
        waveform_row: Any,
        beat_positions: list[float] | None = None,
        structure_markers: list[dict] | None = None,
    ) -> None:
        self.tab_audio.set_waveform_data(waveform_row, beat_positions or [])
        self.tab_audio.set_structure_markers(structure_markers or [])

    def update_audio_meta(
        self,
        lufs: float | None,
        key: str | None,
        camelot: str | None = None,
    ) -> None:
        self.tab_audio.set_lufs(lufs)
        self.tab_audio.set_key(key, camelot)

    def set_audio_id(self, audio_id: int | None) -> None:
        self.tab_audio.set_audio_id(audio_id)

    def _stem_workspace(self):
        return self.tab_audio.stem_workspace

    @staticmethod
    def _connect(signal, slot) -> None:
        try:
            signal.connect(slot)
        except (RuntimeError, TypeError) as exc:
            logger.debug("[SchnittAudioBinder] signal connect skipped: %s", exc)
