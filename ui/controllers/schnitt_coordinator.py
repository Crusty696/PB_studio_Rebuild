"""Coordinator for feeding project data into visible SCHNITT binders."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from database.models import AudioTrack, Beatgrid, StructureSegment, WaveformData

logger = logging.getLogger(__name__)


class SchnittCoordinator:
    """Loads SCHNITT UI data from DB and delegates rendering to binders."""

    def __init__(self, audio_binder, db_engine):
        self.audio_binder = audio_binder
        self.db_engine = db_engine

    def refresh_audio(self, audio_id: int | None) -> None:
        self.audio_binder.set_audio_id(audio_id)
        if audio_id is None:
            self.audio_binder.update_waveform(None, [], [])
            self.audio_binder.update_audio_meta(None, None, None)
            return

        with Session(self.db_engine) as session:
            track = session.get(AudioTrack, audio_id)
            if track is None:
                self.audio_binder.update_waveform(None, [], [])
                self.audio_binder.update_audio_meta(None, None, None)
                return

            waveform = (
                session.query(WaveformData)
                .filter(WaveformData.audio_track_id == audio_id)
                .first()
            )
            beatgrid = (
                session.query(Beatgrid)
                .filter(Beatgrid.audio_track_id == audio_id)
                .first()
            )
            segments = (
                session.query(StructureSegment)
                .filter(StructureSegment.audio_track_id == audio_id)
                .order_by(StructureSegment.start_time)
                .all()
            )
            beat_positions = list(beatgrid.beat_positions or []) if beatgrid else []
            structure_markers = [
                {
                    "start": float(segment.start_time),
                    "end": float(segment.end_time),
                    "label": str(segment.label),
                }
                for segment in segments
            ]
            self.audio_binder.update_waveform(waveform, beat_positions, structure_markers)
            self.audio_binder.update_audio_meta(
                track.lufs,
                track.key,
                self._camelot_from_track(track),
            )

    @staticmethod
    def _camelot_from_track(track: AudioTrack) -> str | None:
        modulation_data: Any = track.key_modulation_data
        if isinstance(modulation_data, list):
            for entry in modulation_data:
                if not isinstance(entry, dict):
                    continue
                if entry.get("key") == track.key and entry.get("camelot"):
                    return str(entry["camelot"])
            for entry in modulation_data:
                if isinstance(entry, dict) and entry.get("camelot"):
                    return str(entry["camelot"])
        return None
